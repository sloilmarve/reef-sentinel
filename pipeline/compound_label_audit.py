# -*- coding: utf-8 -*-
# compound_label_audit.py - 把排序目标换成产品真正主打的「复合灾害日」再评一次。
# 动机：成品页用排序 AUC 证明价值，但那个标签是「至少一项驱动越过本站 p90」（正类约 27.7%）；
# 而产品反复主打的复合灾害日（>=2 项同时越线）只有约 3% 的样本，此前从未单独评估。
# 这里用与主表完全相同的 3 折协议（只换标签，特征 / 折 / 模型 / λ 规则不动）如实补上，差也照报。
import json, os, sys
import numpy as np
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import feat_ext, model

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
P = lambda *a: os.path.join(BASE, *a)
d = json.load(open(P('data', 'processed', 'semporna_features.json'), encoding='utf-8'))
days = d['days']
n = len(days)
dates = [r['date'] for r in days]
feat_ext.add_memory(days)
FEATS = feat_ext.feature_keys(days)
X = model.matrix(days, FEATS)
idx = np.array([r['n_haz'] / 3.0 for r in days])
comp = np.array([r['compound'] for r in days], dtype=float)
fit, pred, rmse, auc = model.ridge_fit, model.ridge_pred, model.rmse, model.auc

def pr_auc(p, lab):
    # 平均精度（average precision）：把样本按预测值降序排，逐步累计精确率再加权
    p = np.asarray(p, dtype=float); lab = np.asarray(lab, dtype=float)
    order = np.argsort(-p, kind='mergesort')
    hit = lab[order]
    tp = np.cumsum(hit)
    prec = tp / np.arange(1, len(hit) + 1)
    total = hit.sum()
    return float((prec * hit).sum() / total) if total > 0 else float('nan')

folds = [(np.arange(0, int(n * s)), np.arange(int(n * s), min(n, int(n * s) + 180))) for s in (0.62, 0.75, 0.88)]
print('复合灾害日标签（未来 h 天是否 >=2 项驱动同时越线），同一 3 折协议 0.62/0.75/0.88，每折 180 天')
print('%-4s %-6s %-7s %-9s %-9s %-9s %-9s %-8s' % ('h', 'pos', 'base', 'modelAUC', 'persAUC', 'modelPR', 'persPR', 'lift'))
out = {'task': '把排序目标换成复合灾害日（>=2 项驱动同时越过本站 p90）后模型还有没有排序能力',
       'protocol': '3 折 0.62/0.75/0.88，每折 180 天；特征 / 模型 / λ 规则与主表完全相同，只换标签',
       'n_days': n, 'feature_count': len(FEATS),
       'label': '未来 h 天出现复合灾害日（n_haz >= 2）',
       'note': '模型预测的是连续危险指数（0 / 1/3 / 2/3 / 1），这里只把它当作排序分数；复合日样本很少，数值噪声大',
       'by_h': {}}
main = json.load(open(P('data', 'processed', 'dashboard_data.json'), encoding='utf-8'))
selfcheck = True
for h in (1, 3, 7, 14):
    y = np.array([idx[min(n - 1, i + h)] for i in range(n)])
    yc = np.array([comp[min(n - 1, i + h)] for i in range(n)])
    Pm, Pp, Y, Yc = [], [], [], []
    for tr, te in folds:
        lam = model.inner_lambda(X[tr], y[tr])
        w, mu, sd = fit(X[tr], y[tr], lam)
        Pm.append(pred(w, mu, sd, X[te]))
        Pp.append(np.array([idx[max(0, i - 6):i + 1].mean() for i in te]))
        Y.append(y[te]); Yc.append(yc[te])
    Pm, Pp, Y, Yc = map(np.concatenate, (Pm, Pp, Y, Yc))
    rm = float(np.sqrt(np.mean((Pm - Y) ** 2)))
    if abs(rm - main['metrics'][str(h)]['model_rmse']) > 5e-5:
        selfcheck = False
    pos = int(Yc.sum()); base = float(Yc.mean())
    ma, pa = auc(Pm, Yc), auc(Pp, Yc)
    mp, pp = pr_auc(Pm, Yc), pr_auc(Pp, Yc)
    print('%-4d %-6d %-7.3f %-9.3f %-9.3f %-9.3f %-9.3f %-8.2f' % (h, pos, base, ma, pa, mp, pp, (mp / base) if base > 0 else float('nan')))
    out['by_h'][str(h)] = {'pos': pos, 'base_rate': round(base, 4), 'model_auc': round(ma, 3), 'pers_auc': round(pa, 3),
                           'model_pr_auc': round(mp, 3), 'pers_pr_auc': round(pp, 3),
                           'lift_vs_base': round(mp / base, 2) if base > 0 else None, 'model_rmse_index': round(rm, 4)}
out['selfcheck'] = ('同一协议逐时效复现主表 RMSE（<=5e-5）' if selfcheck else 'FAILED: 与主表 RMSE 不一致')
print('self-check ' + ('OK' if selfcheck else 'FAILED') + '：模型 RMSE 与主表逐时效一致（只换了标签）')
if not selfcheck:
    sys.exit(1)
json.dump(out, open(P('data', 'processed', 'compound_label_audit.json'), 'w', encoding='utf-8', newline="\n"), indent=2, ensure_ascii=False)
print('wrote compound_label_audit.json')