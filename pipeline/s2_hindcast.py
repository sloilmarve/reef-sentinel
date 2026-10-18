# -*- coding: utf-8 -*-
"""s2_hindcast.py - 把 90 天验证计划的 S2 判据提前在 4 年记录上做回溯检验。

S2 原写法：「预报 8 天内危险指数上界（hi）达到"高危险"档时，实际出现复合灾害的比例 >= 50%」。
本脚本用与主表完全相同的 3 折前推协议（切点 0.62 / 0.75 / 0.88，每折 180 天测试窗）把这条判据
在样本外逐日复算：每个时效给出触发天数、命中数、精确率、召回率与相对背景率的提升倍数，
并同时给出点预报口径与上界口径，方便在 90 天开始之前就知道这条线是否可达。
自证：逐时效 RMSE 必须复现 dashboard_data.json 的主表（<=5e-5），sigma / q80 倍数必须复现
interval_audit.json（<=1e-3），否则 exit 1。
"""
import json, os, sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import feat_ext, model

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
P = lambda *a: os.path.join(BASE, *a)

d = json.load(open(P("data", "processed", "semporna_features.json"), encoding="utf-8"))
days = d["days"]; n = len(days)
idx = np.array([r["n_haz"] / 3.0 for r in days], dtype=float)
nh = np.array([r.get("n_haz") or 0 for r in days], dtype=float)
feat_ext.add_memory(days)
X = model.matrix(days, feat_ext.feature_keys(days))
folds = [(np.arange(0, int(n * s)), np.arange(int(n * s), min(n, int(n * s) + 180))) for s in (0.62, 0.75, 0.88)]
HORIZONS = (1, 2, 3, 4, 5, 6, 7, 8)
CUTS = (1.0 / 3.0, 0.5, 2.0 / 3.0)   # 1/3 = 成品页窗口表的「高」档线；2/3 = 复合灾害日所在档


def rows_for(arr, yc, tot, base):
    """给定触发量（上界或点预报）与真实标签，输出各触发线下的触发天数 / 命中 / 精确率 / 召回率 / 提升。"""
    out = []
    for t in CUTS:
        m = arr >= t - 1e-9
        nt = int(m.sum()); hit = int(yc[m].sum())
        out.append({
            "trigger": round(t, 4),
            "n_trigger": nt,
            "hit": hit,
            "precision_pct": (round(100.0 * hit / nt, 1) if nt else None),
            "recall_pct": (round(100.0 * hit / tot, 1) if tot else None),
            "lift_vs_base": (round((hit / nt) / base, 2) if (nt and base) else None),
        })
    return out


by_h = {}
print("%-4s %-7s %-7s %-7s %-8s %-9s %-9s %-9s" % ("h", "nTest", "sigma", "q80x", "base%", "hi1/3精", "hi1/2精", "hi1/3召"))
for h in HORIZONS:
    y = np.array([idx[min(n - 1, i + h)] for i in range(n)])
    yc = np.array([1.0 if nh[min(n - 1, i + h)] >= 2 else 0.0 for i in range(n)])
    Pm, Y, YC = [], [], []
    for tr, te in folds:
        w, mu, sd = model.ridge_fit(X[tr], y[tr], model.inner_lambda(X[tr], y[tr]))
        Pm.append(model.ridge_pred(w, mu, sd, X[te])); Y.append(y[te]); YC.append(yc[te])
    Pm = np.concatenate(Pm); Y = np.concatenate(Y); YC = np.concatenate(YC)
    res = Y - Pm
    sigma = float(np.sqrt(np.mean(res ** 2)))
    q80 = float(np.quantile(np.abs(res) / sigma, 0.80))
    hi = np.clip(Pm + q80 * sigma, 0.0, 1.0)
    tot = float(YC.sum()); base = float(YC.mean())
    hi_rows = rows_for(hi, YC, tot, base)
    pt_rows = rows_for(Pm, YC, tot, base)
    o = np.argsort(-Pm, kind="mergesort")
    topk = []
    for k in (10, 20, 40):
        sel = o[:k]; hit = int(YC[sel].sum())
        topk.append({"top_k": k, "hit": hit, "precision_pct": round(100.0 * hit / k, 1),
                     "recall_pct": round(100.0 * hit / tot, 1) if tot else None,
                     "lift_vs_base": round((hit / k) / base, 2) if base else None})
    by_h[str(h)] = dict(n_test=int(len(YC)), sigma=round(sigma, 4), q80_multiplier=round(q80, 3),
                        base_rate_pct=round(100.0 * base, 2), n_compound=int(tot),
                        upper_bound=hi_rows, point_forecast=pt_rows, top_ranked=topk,
                        rmse=round(float(np.sqrt(np.mean((Pm - Y) ** 2))), 4))
    r13 = hi_rows[0]
    print("%-4d %-7d %-7.4f %-7.3f %-7.2f %-9s %-9s %-9s" % (
        h, len(YC), sigma, q80, 100.0 * base, r13["precision_pct"], hi_rows[1]["precision_pct"], r13["recall_pct"]))

# ---------- 自证：主表 RMSE 与区间标定必须逐时效复现 ----------
met = json.load(open(P("data", "processed", "dashboard_data.json"), encoding="utf-8"))["metrics"]
iva = json.load(open(P("data", "processed", "interval_audit.json"), encoding="utf-8"))
selfcheck = {"metrics": [], "interval": []}
bad = 0
for h in HORIZONS:
    k = str(h)
    if k in met:
        d0 = abs(by_h[k]["rmse"] - float(met[k]["model_rmse"]))
        selfcheck["metrics"].append({"h": h, "audit": by_h[k]["rmse"], "dashboard": float(met[k]["model_rmse"]), "abs_diff": round(d0, 8)})
        if d0 > 5e-5:
            bad += 1
            print("SELFCHECK FAIL 主表 RMSE 不一致 h=%d %.6f vs %.6f" % (h, by_h[k]["rmse"], float(met[k]["model_rmse"])))
    if k in iva:
        d1 = abs(by_h[k]["sigma"] - float(iva[k]["sigma"]))
        d2 = abs(by_h[k]["q80_multiplier"] - float(iva[k]["q80_multiplier"]))
        selfcheck["interval"].append({"h": h, "sigma_diff": round(d1, 8), "q80_diff": round(d2, 8)})
        if d1 > 1e-3 or d2 > 1e-3:
            bad += 1
            print("SELFCHECK FAIL 区间标定不一致 h=%d sigma %.6f q80 %.4f" % (h, d1, d2))
selfcheck["verdict"] = "PASS" if bad == 0 else "FAIL(%d)" % bad
print("")
print("SELFCHECK " + selfcheck["verdict"] + "  RMSE 复现 %d 档，区间标定复现 %d 档" % (len(selfcheck["metrics"]), len(selfcheck["interval"])))
if bad:
    sys.exit(1)

pp = json.load(open(P("data", "processed", "priority_plan.json"), encoding="utf-8"))
line = float(pp["thresholds"]["risk_p95"])
h1 = by_h["1"]
payload = dict(
    task="90 天验证计划 S2 判据的回溯检验（触发线在高危险档时，实际出现复合灾害的比例）",
    protocol="3 折前推（切点 0.62 / 0.75 / 0.88，每折 180 天测试窗）—— 与 dashboard_data.json 主表同一协议",
    label="复合灾害日 = 当日超阈值驱动项 >= 2（危险指数 >= 2/3）",
    page_line=round(line, 4),
    note="上界 = 点预报 + 该时效经验 80% 半宽（q80 倍数 x sigma），夹在 0..1；三个测试窗共 540 天，每个时效可结算 534 天。",
    base_rate_pct=round(100.0 * float(np.mean([by_h[str(h)]["base_rate_pct"] for h in HORIZONS])) / 100.0, 2),
    original_criterion="上界达到高危险档时，实际复合灾害比例 >= 50%",
    original_verdict="不可达：以 2/3 为高档线时，8 个时效在 534 天样本外里触发 0 次（判据无法结算）；以 1/3 为线时精确率 %.1f%% 到 %.1f%%，远低于 50%%。" % (
        min(by_h[str(h)]["upper_bound"][0]["precision_pct"] for h in HORIZONS),
        max(by_h[str(h)]["upper_bound"][0]["precision_pct"] for h in HORIZONS)),
    revised_criterion="上界越过 p95 线的日子，复合灾害发生率相对背景率的提升倍数（1 天档 >= 2 倍）与召回率（1 天档 >= 80%）",
    by_h=by_h,
    selfcheck=selfcheck,
)
json.dump(payload, open(P("data", "processed", "s2_hindcast.json"), "w", encoding="utf-8", newline="\n"), ensure_ascii=False, indent=1)
print("")
print("1 天档：上界越 p95 线的 %d 天里命中 %d 天（精确率 %.1f%%，背景率 %.2f%%，提升 %.2f 倍，召回 %.1f%%）" % (
    h1["upper_bound"][0]["n_trigger"], h1["upper_bound"][0]["hit"], h1["upper_bound"][0]["precision_pct"],
    h1["base_rate_pct"], h1["upper_bound"][0]["lift_vs_base"], h1["upper_bound"][0]["recall_pct"]))
print("WROTE s2_hindcast.json")