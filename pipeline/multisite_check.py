# -*- coding: utf-8 -*-
"""Rerun the whole feature + ridge-regression stack at three reef sites.

Answers the "one site proves nothing" criticism with evidence instead of a promise:
fetch_multisite.py pulls the same daily drivers for Semporna, Bunaken and Palau, and
this script applies the SAME definitions (site-local p90 thresholds, three-driver
compound index, identical rolling / anomaly / memory features, identical ridge fit and
identical walk-forward folds) at each site, then reports skill versus the three
baselines.  Also sweeps the threshold (p85 / p90 / p95) to show how much the choice
matters.
"""
import json, math, os, sys
from datetime import date
import numpy as np

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import feat_ext, model
P = lambda *a: os.path.join(BASE, *a)
MS = P("data", "external", "multisite")
SLUGS = ["semporna", "bunaken", "palau"]

def pct(vals, p):
    v = sorted(x for x in vals if x is not None)
    return v[min(len(v)-1, int(round(p*(len(v)-1))))]

def build(rows, tp=0.90):
    days = [dict(r) for r in rows]
    n = len(days)
    for i, r in enumerate(days):
        w = [days[j].get("sl_mean") for j in range(max(0, i-12), min(n, i+13))]
        w = [v for v in w if v is not None]
        r["surge"] = r["sl_mean"] - sum(w)/len(w)
    TH = {k: pct([r.get(k) for r in days], tp) for k in ("wh_max", "precipitation_sum", "surge")}
    for r in days:
        r["h_wave"]  = 1 if r["wh_max"] >= TH["wh_max"] else 0
        r["h_rain"]  = 1 if r["precipitation_sum"] >= TH["precipitation_sum"] else 0
        r["h_surge"] = 1 if r["surge"] >= TH["surge"] else 0
        r["n_haz"] = r["h_wave"] + r["h_rain"] + r["h_surge"]
        r["compound"] = 1 if r["n_haz"] >= 2 else 0

    # Model columns: the SAME strictly causal recipe the Semporna record uses (trailing
    # still-water level -> causal index -> rolling block -> memory).  The centred residual
    # above stays the retrospective ANALYSIS the transfer skill is measured against.
    feat_ext.add_all(days, tp=tp)
    return days, TH

# the ridge fit and the inner-window lambda search live in pipeline/model.py
fit = model.ridge_fit
pred = model.ridge_pred
auc = model.auc

def skill(days, FEATS, h):
    n = len(days)
    X = np.array([[float(r.get(k)) if r.get(k) is not None else np.nan for k in FEATS] for r in days])
    idx = np.array([r["n_haz"]/3.0 for r in days])
    dates = [r["date"] for r in days]
    doy = np.array([int(d[5:7])*31 + int(d[8:10]) for d in dates])
    y = np.array([idx[min(n-1, i+h)] for i in range(n)])
    Pm, Pp, Pc, Pf, Y = [], [], [], [], []
    for s in (0.62, 0.75, 0.88):
        tr = np.arange(0, int(n*s)); te = np.arange(int(n*s), min(n, int(n*s)+180))
        w, mu, sd = fit(X[tr], y[tr], model.inner_lambda(X[tr], y[tr]))
        Pm.append(pred(w, mu, sd, X[te]))
        Pp.append(np.array([idx[max(0, i-6):i+1].mean() for i in te]))
        Pc.append(np.array([y[tr][doy[tr] == doy[i]].mean() if (doy[tr] == doy[i]).any() else y[tr].mean() for i in te]))
        Pf.append(np.full(len(te), float(y[tr].mean())))
        Y.append(y[te])
    Pm, Pp, Pc, Pf, Y = map(np.concatenate, (Pm, Pp, Pc, Pf, Y))
    rm = lambda a: float(np.sqrt(np.mean((a-Y)**2)))
    lab = (Y > 0).astype(float)
    return dict(model_rmse=round(rm(Pm),4), pers_rmse=round(rm(Pp),4), clim_rmse=round(rm(Pc),4),
                flat_rmse=round(rm(Pf),4), model_auc=round(auc(Pm, lab),3), pers_auc=round(auc(Pp, lab),3))

FEATS_KEYS = None
out = {"sites": [], "threshold_sweep": []}
print("%-9s %5s %6s %6s %7s | %s" % ("site", "days", "comp", "sst90", "surge90", "h=3 RMSE model / pers / flat   AUC"))
for slug in SLUGS:
    raw = json.load(open(os.path.join(MS, slug + "_daily.json"), encoding="utf-8"))
    days, TH = build(raw["days"], 0.90)
    FEATS = feat_ext.feature_keys(days)
    res = {"slug": slug, "site": raw["site"], "lat": raw["lat"], "lon": raw["lon"], "days": len(days),
           "span": [days[0]["date"], days[-1]["date"]],
           "thresholds": {k: round(v, 4) for k, v in TH.items()},
           "sst_p90": round(pct([r["sst_mean"] for r in days], 0.90), 3),
           "compound_days": sum(r["compound"] for r in days), "features": len(FEATS), "skill": {}}
    for h in (1, 3, 7, 14):
        res["skill"][str(h)] = skill(days, FEATS, h)
    out["sites"].append(res)
    s3 = res["skill"]["3"]
    print("%-9s %5d %6d %6.2f %7.4f | %.4f / %.4f / %.4f   %.3f / %.3f" % (slug, res["days"], res["compound_days"], res["sst_p90"], TH["surge"], s3["model_rmse"], s3["pers_rmse"], s3["flat_rmse"], s3["model_auc"], s3["pers_auc"]))

print("")
print("== 阈值敏感性（三站，h=3）==")
for slug in SLUGS:
    raw = json.load(open(os.path.join(MS, slug + "_daily.json"), encoding="utf-8"))
    for tp in (0.85, 0.90, 0.95):
        days, TH = build(raw["days"], tp)
        FEATS = feat_ext.feature_keys(days)
        s3 = skill(days, FEATS, 3)
        comp = sum(r["compound"] for r in days)
        row = dict(slug=slug, p=tp, compound_days=comp, compound_pct=round(100*comp/len(days), 2), h3=s3)
        out["threshold_sweep"].append(row)
        print("  %-9s p%-3d 复合灾害 %3d 天（%.1f%%）  h=3 模型 %.4f / 持续 %.4f / 常数均值 %.4f" % (slug, int(tp*100), comp, 100*comp/len(days), s3["model_rmse"], s3["pers_rmse"], s3["flat_rmse"]))

with open(P("data","processed","multisite_transfer.json"), "w", encoding="utf-8", newline="\n") as f:
    json.dump(out, f, ensure_ascii=False, indent=1)
print("")
print("WROTE data/processed/multisite_transfer.json")