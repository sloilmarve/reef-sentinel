# -*- coding: utf-8 -*-
"""blend_audit.py - 方差收缩校准：把"点预报精度"与"排序能力"的取舍量化出来。

问题：岭回归在 1 天赢过所有基线，但 3/7/14 天的 RMSE 输给"常数均值"——线性模型把预测方差
放大到超出真实信号。补救办法是把预报向训练期均值收缩：
    pred(beta) = mean_train + beta * (ridge - mean_train)，beta=0 即常数均值，beta=1 为原始模型。

做法（全部只用训练段信息，不接触测试段）：在每折训练段内部再切一刀（前 80% 拟合、后 20% 验证），
把三折的内部验证平方误差按样本数汇总，取汇总 RMSE 最小的 beta 作为该时效的收缩系数。
然后用同一 beta 跑标准的三折样本外测试，报告 RMSE 与排序 AUC。

结论形状：3/7/14 天收缩后 RMSE 分别约 0.1636/0.1631/0.1629，低于常数均值 0.1637/0.1635/0.1639；
AUC 基本不变（正的线性缩放不改变折内排序），代价是点预报被拉向均值、日与日之间的差异变小。
成品页因此保留满幅预报做排序，同时把两个口径都公开。
"""
import json, os, sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import feat_ext, model

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
d = json.load(open(os.path.join(BASE, "data", "processed", "semporna_features.json"), encoding="utf-8"))
days = d["days"]; n = len(days); dates = [r["date"] for r in days]
idx = np.array([r["n_haz"] / 3.0 for r in days], dtype=float)

# memory block from the STRICTLY CAUSAL index (see feat_ext.add_memory)
feat_ext.add_memory(days)

FEATS = feat_ext.feature_keys(days)
X = model.matrix(days, FEATS)
doy = np.array([int(x[5:7])*31 + int(x[8:10]) for x in dates])

fit = model.ridge_fit
pred = model.ridge_pred
rmse = model.rmse
auc = model.auc

folds = [(np.arange(0, int(n*s)), np.arange(int(n*s), min(n, int(n*s)+180))) for s in (0.62, 0.75, 0.88)]
CANDS = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
HORIZONS = (1, 2, 3, 4, 5, 6, 7, 8, 10, 14)
HEAD = (1, 3, 7, 14)
print("features: %d   folds: %d x 180d   beta grid: %s" % (len(FEATS), len(folds), CANDS))
print("%-4s %-7s %-8s %-8s %-9s %-9s %-9s %-9s %s" % ("h", "beta*", "blendRMSE", "flatRMSE", "persRMSE", "climRMSE", "blendAUC", "ridgeAUC", "beats-all"))
out = {}
for h in HORIZONS:
    y = np.array([idx[min(n-1, i+h)] for i in range(n)])
    sse = {b: 0.0 for b in CANDS}; cnt = 0
    PIN, M, Y, P, PP, PC = [], [], [], [], [], []
    for tr, te in folds:
        cut = int(len(tr)*0.8)
        lam = model.inner_lambda(X[tr], y[tr])
        w1, m1, s1 = fit(X[tr[:cut]], y[tr[:cut]], lam)
        pin = pred(w1, m1, s1, X[tr[cut:]]); yin = y[tr[cut:]]; mun = float(y[tr[:cut]].mean())
        for b in CANDS:
            sse[b] += float(np.sum((mun + b*(pin-mun) - yin)**2))
        cnt += len(yin)
        w, mu, sd = fit(X[tr], y[tr], lam)
        P.append(pred(w, mu, sd, X[te])); M.append(float(y[tr].mean())); Y.append(y[te])
        PP.append(np.array([idx[max(0, i-6):i+1].mean() for i in te]))
        PC.append(np.array([y[tr][doy[tr] == doy[i]].mean() if (doy[tr] == doy[i]).any() else y[tr].mean() for i in te]))
    bstar = min(CANDS, key=lambda b: sse[b])
    Yc = np.concatenate(Y); lab = (Yc > 0).astype(float)
    Pb = np.concatenate([m + bstar*(p-m) for p, m in zip(P, M)])
    Pr = np.concatenate(P)
    Pp = np.concatenate(PP); Pc = np.concatenate(PC)
    Pf = np.concatenate([np.full(len(yy), m) for yy, m in zip(Y, M)])
    base = dict(pers=rmse(Pp, Yc), clim=rmse(Pc, Yc), flat=rmse(Pf, Yc))
    br = rmse(Pb, Yc); rr = rmse(Pr, Yc)
    beats = br < min(base.values())
    inner = {str(b): round(float(np.sqrt(sse[b]/cnt)), 4) for b in CANDS}
    frontier = [dict(beta=b, rmse=round(rmse(np.concatenate([m + b*(p-m) for p, m in zip(P, M)]), Yc), 4),
                     auc=round(auc(np.concatenate([m + b*(p-m) for p, m in zip(P, M)]), lab), 3)) for b in CANDS]
    out[str(h)] = dict(beta_star=bstar, inner_cv_rmse=inner,
                       blend_rmse=round(br, 4), blend_auc=round(auc(Pb, lab), 3),
                       ridge_rmse=round(rr, 4), ridge_auc=round(auc(Pr, lab), 3),
                       flat_rmse=round(base["flat"], 4), pers_rmse=round(base["pers"], 4), clim_rmse=round(base["clim"], 4),
                       gain_vs_flat_pct=round((base["flat"]-br)/base["flat"]*100.0, 2),
                       gain_vs_ridge_pct=round((rr-br)/rr*100.0, 2), beats_all_baselines=bool(beats), frontier=frontier)
    if h in HEAD:
        print("%-4d %-7.1f %-8.4f %-8.4f %-9.4f %-9.4f %-9.3f %-9.3f %s" % (
            h, bstar, br, base["flat"], base["pers"], base["clim"], auc(Pb, lab), auc(Pr, lab), beats))

p = os.path.join(BASE, "data", "processed", "blend_audit.json")
json.dump(out, open(p, "w", encoding="utf-8", newline="\n"), indent=2, ensure_ascii=False)
head = [out[str(h)] for h in HEAD]
print("")
print("1/3/7/14 天：收缩后 RMSE %s，全部低于常数均值：%s" % ([x["blend_rmse"] for x in head], all(x["beats_all_baselines"] for x in head)))
print("beta* 由训练段内部交叉验证联合挑选（按样本汇总），不含测试段信息。")
print("wrote", p)