# -*- coding: utf-8 -*-
"""interval_audit.py - 预报区间标定：用与成品页完全相同的折设置，检查区间覆盖率并给出经验倍数。

问题：页面上的不确定区间原来是 risk ± 1 * RMSE，隐含高斯假设（约 68% 覆盖）。
本脚本把样本外残差按分位数标定：给出经验 80% / 90% 区间的倍数，并如实报告覆盖率，
用于把成品页的区间改成"80% 经验区间"，而不是嘴上说高斯。
"""
import json, os, sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import feat_ext, model

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
d = json.load(open(os.path.join(BASE, "data", "processed", "semporna_features.json"), encoding="utf-8"))
days = d["days"]; n = len(days)
idx = np.array([r["n_haz"] / 3.0 for r in days], dtype=float)

# memory block from the STRICTLY CAUSAL index (see feat_ext.add_memory)
feat_ext.add_memory(days)

FEATS = feat_ext.feature_keys(days)
X = model.matrix(days, FEATS)

ridge_fit = model.ridge_fit
ridge_pred = model.ridge_pred

# 与成品页 build_dashboard.py 完全相同的折（3 折，每折 180 天测试窗）
folds = [(np.arange(0, int(n*s)), np.arange(int(n*s), min(n, int(n*s)+180))) for s in (0.62, 0.75, 0.88)]
G = {68: 1.0, 80: 1.2816, 90: 1.6449, 95: 1.9600}
out = {}
print("%-4s %-8s %-8s %-8s %-8s %-8s %-8s %-8s" % ("h", "nTest", "sigma", "cov68", "cov80", "cov90", "q80x", "kurt"))
for h in (1, 2, 3, 4, 5, 6, 7, 8, 10, 14):
    y = np.array([idx[min(n-1, i+h)] for i in range(n)])
    P, Y = [], []
    for tr, te in folds:
        w, mu, sd = ridge_fit(X[tr], y[tr], model.inner_lambda(X[tr], y[tr]))
        P.append(ridge_pred(w, mu, sd, X[te])); Y.append(y[te])
    P = np.concatenate(P); Y = np.concatenate(Y)
    res = Y - P
    sigma = float(np.sqrt(np.mean(res**2)))
    a = np.abs(res) / sigma
    cov = {k: float((a <= G[k]).mean() * 100.0) for k in G}
    q80 = float(np.quantile(a, 0.80)); q90 = float(np.quantile(a, 0.90))
    z = (res - res.mean()) / (res.std() + 1e-12)
    kurt = float(((z**4).mean()) - 3.0)
    out[str(h)] = dict(n_test=int(len(res)), sigma=round(sigma, 4),
                       coverage_1sigma=round(cov[68], 1), coverage_128sigma=round(cov[80], 1),
                       coverage_164sigma=round(cov[90], 1), coverage_196sigma=round(cov[95], 1),
                       q80_multiplier=round(q80, 3), q90_multiplier=round(q90, 3),
                       mean_resid=round(float(res.mean()), 4), kurtosis=round(kurt, 2))
    print("%-4d %-8d %-8.4f %-8.1f %-8.1f %-8.1f %-8.3f %-8.2f" % (h, len(res), sigma, cov[68], cov[80], cov[90], q80, kurt))

p = os.path.join(BASE, "data", "processed", "interval_audit.json")
json.dump(out, open(p, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
print("")
print("高斯假设下 ±1 sigma 应覆盖 68.3%，实际覆盖见上表；q80x = 经验 80% 区间所需倍数。")
print("wrote", p)