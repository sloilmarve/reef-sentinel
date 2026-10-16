# -*- coding: utf-8 -*-
"""Final model selection: does anything beat the naive baselines, and at what horizon?

Baselines (all computable operationally, no hindsight):
  persist7 : the average hazard index of the last 7 days, carried forward
  clim     : day-of-year climatology of the hazard index
Model: ridge regression (numpy) on driver + memory features, walk-forward validated.
"""
import json, os, sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import feat_ext, model

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
d = json.load(open(os.path.join(BASE, "data", "processed", "semporna_features.json"), encoding="utf-8"))
days = d["days"]; n = len(days); dates = [r["date"] for r in days]

# continuous hazard index = fraction of the 3 compound-hazard drivers exceeded
idx = np.array([r["n_haz"] / 3.0 for r in days], dtype=float)
comp = np.array([r["compound"] for r in days], dtype=float)

# memory block from the STRICTLY CAUSAL index (see feat_ext.add_memory)
feat_ext.add_memory(days)

FEATS = feat_ext.feature_keys(days)
X = model.matrix(days, FEATS)
print("features:", len(FEATS), "(rolling/memory/seasonal + current-day levels)")

# the ridge fit and the inner-window lambda search live in pipeline/model.py
ridge_fit = model.ridge_fit
ridge_pred = model.ridge_pred
rmse = model.rmse

def corr(a, b):
    a = a-a.mean(); b = b-b.mean()
    den = np.sqrt((a*a).sum()*(b*b).sum())
    return float((a*b).sum()/den) if den > 0 else float("nan")

folds = [(np.arange(0, int(n*s)), np.arange(int(n*s), min(n, int(n*s)+180))) for s in (0.55, 0.65, 0.75, 0.85)]
print("\n%-5s %-8s %-8s %-8s %-8s %-8s %-8s" % ("h","modelRMSE","persRMSE","climRMSE","flatRMSE","modelR","persR"))
out = {}
for h in (1, 2, 3, 5, 7):
    y = np.array([idx[min(n-1, i+h)] for i in range(n)])          # hazard index h days ahead
    Pm, Pp, Pc, Pf, Y = [], [], [], [], []
    LAMS = []
    for tr, te in folds:
        lam = model.inner_lambda(X[tr], y[tr]); LAMS.append(int(lam))
        w, mu, sd = ridge_fit(X[tr], y[tr], lam)
        Pm.append(ridge_pred(w, mu, sd, X[te]))
        Pp.append(np.array([idx[max(0, i-6):i+1].mean() for i in te]))        # persist7
        Pc.append(np.array([y[tr][(np.arange(len(tr)) % 365) == (i % 365)].mean() if ((np.arange(len(tr)) % 365) == (i % 365)).any() else y[tr].mean() for i in te]))
        Pf.append(np.full(len(te), float(y[tr].mean())))                       # constant-mean: always predict the training average
        Y.append(y[te])
    Pm = np.concatenate(Pm); Pp = np.concatenate(Pp); Pc = np.concatenate(Pc); Pf = np.concatenate(Pf); Y = np.concatenate(Y)
    auc = model.auc
    lab = (Y > 0).astype(float)      # ranking target: is any of the three drivers above threshold h days ahead
    print("%-5d %-8.4f %-8.4f %-8.4f %-8.4f %-8.3f %-8.3f" % (h, rmse(Pm,Y), rmse(Pp,Y), rmse(Pc,Y), rmse(Pf,Y), corr(Pm,Y), corr(Pp,Y)))
    print("      ranking AUC (index>0): model %.3f | persist7 %.3f | clim %.3f" % (auc(Pm,lab), auc(Pp,lab), auc(Pc,lab)))
    out[h] = dict(model_rmse=round(rmse(Pm,Y),4), pers_rmse=round(rmse(Pp,Y),4), clim_rmse=round(rmse(Pc,Y),4),
                  flat_rmse=round(rmse(Pf,Y),4), model_r=round(corr(Pm,Y),3), pers_r=round(corr(Pp,Y),3),
                  model_auc=round(auc(Pm,lab),3), pers_auc=round(auc(Pp,lab),3), clim_auc=round(auc(Pc,lab),3),
                  inner_lambda=LAMS)

json.dump(out, open(os.path.join(BASE,"data","processed","regression_skill.json"),"w",encoding="utf-8"), indent=2, ensure_ascii=False)
print("\nwrote regression_skill.json")
