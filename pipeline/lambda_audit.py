# -*- coding: utf-8 -*-
"""How was the ridge penalty lambda chosen, and what does that choice cost?

Ridge shrinkage trades point accuracy (RMSE) against ranking ability (AUC).
This script runs the same walk-forward protocol as the dashboard page
(3 folds 0.62/0.75/0.88, 180-day test windows) over a lambda grid and records,
per horizon: out-of-sample RMSE, ranking AUC (any of the three drivers above
its threshold h days ahead), top-decile hit rate and prediction spread, plus
the lambda that an expanding-window search INSIDE the training data alone
would pick (no test peeking).
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

fit = model.ridge_fit
pred = model.ridge_pred
rmse = model.rmse
auc = model.auc

def top_hit(p, l, frac=0.10):
    k = max(1, int(len(p)*frac))
    return float(l[np.argsort(-p)[:k]].mean())

GRID = model.LAMBDA_GRID
folds = [(np.arange(0, int(n*s)), np.arange(int(n*s), min(n, int(n*s)+180))) for s in (0.62, 0.75, 0.88)]

inner_pick = model.inner_lambda

print("features: %d stages: %d" % (len(FEATS), len(folds)))
print("%-5s %-8s %-8s %-8s %-8s %-8s" % ("lam", "h=1", "h=3", "h=7", "h=14", "meanAUC"))
out = {"protocol": "3 folds 0.62/0.75/0.88 with 180-day test windows (the same protocol as the page)",
       "grid": [int(g) for g in GRID], "horizons": {}}
rows = {}
for h in (1, 3, 7, 14):
    y = np.array([idx[min(n-1, i+h)] for i in range(n)])
    per = {}
    for lam in GRID:
        Pm, Y = [], []
        for tr, te in folds:
            w, mu, sd = fit(X[tr], y[tr], lam)
            Pm.append(pred(w, mu, sd, X[te])); Y.append(y[te])
        Pm = np.concatenate(Pm); Y = np.concatenate(Y)
        lab = (Y > 0).astype(float)
        per["%d" % int(lam)] = dict(rmse=round(rmse(Pm, Y), 4), auc=round(auc(Pm, lab), 3),
                                    pred_std=round(float(Pm.std()), 4), top10=round(top_hit(Pm, lab), 3))
    Pf, Pp, Y = [], [], []
    for tr, te in folds:
        Pf.append(np.full(len(te), float(y[tr].mean())))
        Pp.append(np.array([idx[max(0, i-6):i+1].mean() for i in te]))
        Y.append(y[te])
    Pf = np.concatenate(Pf); Pp = np.concatenate(Pp); Y = np.concatenate(Y)
    lab = (Y > 0).astype(float)
    lams = [inner_pick(X[tr], y[tr]) for tr, te in folds]
    rows[h] = per
    out["horizons"]["%d" % h] = dict(
        per_lam=per,
        inner_cv_lam=[int(v) for v in lams],
        flat_rmse=round(rmse(Pf, Y), 4), pers_rmse=round(rmse(Pp, Y), 4),
        flat_auc=round(auc(Pf, lab), 3), pers_auc=round(auc(Pp, lab), 3))
    best_rm = min(GRID, key=lambda g: per["%d" % int(g)]["rmse"])
    best_au = max(GRID, key=lambda g: per["%d" % int(g)]["auc"])
    out["horizons"]["%d" % h]["best_rmse_lam"] = int(best_rm)
    out["horizons"]["%d" % h]["best_auc_lam"] = int(best_au)
    out["horizons"]["%d" % h]["flat_rmse_at_best"] = out["horizons"]["%d" % h]["flat_rmse"]
    print("h=%-3d flat %.4f AUC(flat) %.3f pers %.4f AUC(pers) %.3f innerCV lam %s -> RMSE %.4f" % (
        h, rmse(Pf, Y), auc(Pf, lab), rmse(Pp, Y), auc(Pp, lab),
        ",".join("%d" % v for v in lams),
        float(np.mean([per["%d" % int(v)]["rmse"] for v in lams]))))
for g in GRID:
    print("%-5d %-8s %-8s %-8s %-8s %-8.3f" % (int(g), rows[1]["%d" % int(g)]["rmse"], rows[3]["%d" % int(g)]["rmse"],
          rows[7]["%d" % int(g)]["rmse"], rows[14]["%d" % int(g)]["rmse"],
          float(np.mean([rows[h]["%d" % int(g)]["auc"] for h in (1, 3, 7, 14)]))))
for h in (1, 3, 7, 14):
    o = out["horizons"]["%d" % h]
    print("h=%-3d flat %.4f | lam5 RMSE %.4f AUC %.3f | lam%d RMSE %.4f AUC %.3f" % (
        h, o["flat_rmse"], o["per_lam"]["5"]["rmse"], o["per_lam"]["5"]["auc"],
        o["best_rmse_lam"], o["per_lam"]["%d" % o["best_rmse_lam"]]["rmse"], o["per_lam"]["%d" % o["best_rmse_lam"]]["auc"]))
json.dump(out, open(os.path.join(BASE, "data", "processed", "lambda_audit.json"), "w", encoding="utf-8", newline="\n"), indent=2, ensure_ascii=False)
print("wrote lambda_audit.json")