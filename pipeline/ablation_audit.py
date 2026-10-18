# -*- coding: utf-8 -*-
"""Ablation: does the 2026-10 feature upgrade (base -> + current-day raw levels) and the
inner-CV lambda choice actually pay off?  Uses the exact same walk-forward protocol as the
metrics table in dashboard_data.json, and changes only the feature set / lambda rule."""
import json, os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import feat_ext, model

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
P = lambda *a: os.path.join(BASE, *a)

feat = json.load(open(P("data", "processed", "semporna_features.json"), encoding="utf-8"))
days = feat["days"]; n = len(days)
# memory block from the STRICTLY CAUSAL index (see feat_ext.add_memory)
feat_ext.add_memory(days)
dates = [r["date"] for r in days]
ALL = feat_ext.feature_keys(days)
RAW = [k for k in ALL if k in feat_ext.RAW_LEVELS]
BASEK = [k for k in ALL if k not in RAW]
idx = np.array([r["n_haz"] / 3.0 for r in days])
folds = [(np.arange(0, int(n * s)), np.arange(int(n * s), min(n, int(n * s) + 180))) for s in (0.62, 0.75, 0.88)]

CONFIGS = [
    ("base_lam5", "基础特征 + 固定 λ=5", BASEK, 5.0),
    ("base_inner", "基础特征 + 内窗 CV 选 λ", BASEK, None),
    ("ext_lam5", "基础 + 当日原始水平 + 固定 λ=5", ALL, 5.0),
    ("ext_inner", "基础 + 当日原始水平 + 内窗 CV 选 λ（主表配置／报告口径）", ALL, None),
]
out = []
for cid, label, keys, fixed in CONFIGS:
    X = model.matrix(days, keys)
    by_h = {}
    for h in (1, 3, 7, 14):
        y = np.array([idx[min(n - 1, i + h)] for i in range(n)])
        Pm, Y, LAMS = [], [], []
        for tr, te in folds:
            lam = fixed if fixed is not None else model.inner_lambda(X[tr], y[tr])
            LAMS.append(int(lam))
            w, mu, sd = model.ridge_fit(X[tr], y[tr], lam)
            Pm.append(model.ridge_pred(w, mu, sd, X[te]))
            Y.append(y[te])
        Pm = np.concatenate(Pm); Y = np.concatenate(Y)
        lab = (Y > 0).astype(float)
        by_h[str(h)] = dict(rmse=round(float(np.sqrt(np.mean((Pm - Y) ** 2))), 4),
                            auc=round(model.auc(Pm, lab), 3), lam=LAMS)
    out.append(dict(id=cid, label=label, features=len(keys),
                    lam_mode=("fixed-5" if fixed else "inner-cv"), by_h=by_h))
    print(cid, len(keys), json.dumps({k: (v["rmse"], v["auc"]) for k, v in by_h.items()}))

payload = dict(
    protocol="3 folds (cuts 0.62 / 0.75 / 0.88, 180-day test windows) — identical to the metrics table in dashboard_data.json",
    features_base=len(BASEK), features_ext=len(ALL), raw_levels=list(RAW),
    configs=out, report_config="ext_inner")
open(P("data", "processed", "ablation_audit.json"), "w", encoding="utf-8", newline="\n").write(
    json.dumps(payload, ensure_ascii=False, indent=1))
print("WROTE ablation_audit.json  base=%d ext=%d" % (len(BASEK), len(ALL)))