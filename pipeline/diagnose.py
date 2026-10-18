# -*- coding: utf-8 -*-
"""Diagnose model skill by horizon; add hazard-memory features; compare against baselines."""
import json, os, math
import numpy as np

from ssum import ssum   # naive accumulation, see pipeline/ssum.py

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
d = json.load(open(os.path.join(BASE, "data", "processed", "semporna_features.json"), encoding="utf-8"))
days = d["days"]; n = len(days); dates = [r["date"] for r in days]

# ---- hazard memory features (no leakage: only information up to and including day i) ----
for i, r in enumerate(days):
    for tag in ("h_wave", "h_rain", "h_surge"):
        for w in (3, 7, 14):
            r["m_%s_%dd" % (tag, w)] = ssum(days[j][tag] for j in range(max(0, i-w+1), i+1))
    r["m_nhaz_7d"] = sum(days[j]["n_haz"] for j in range(max(0, i-6), i+1))
    r["m_compound_14d"] = sum(days[j]["compound"] for j in range(max(0, i-13), i+1))
    r["m_compound_30d"] = sum(days[j]["compound"] for j in range(max(0, i-29), i+1))
    r["m_gap_since_compound"] = next((k for k in range(0, 200) if i-k >= 0 and days[i-k]["compound"]), 200)

base_feats = [k for k in days[n//2] if k.startswith("f_") and not k.startswith("f_surge")] + ["doy_sin", "doy_cos"]
mem_feats = ["m_h_wave_3d","m_h_wave_7d","m_h_wave_14d","m_h_rain_3d","m_h_rain_7d","m_h_rain_14d",
             "m_h_surge_3d","m_h_surge_7d","m_h_surge_14d","m_nhaz_7d","m_compound_14d","m_compound_30d","m_gap_since_compound"]
FEATS = [k for k in base_feats + mem_feats if sum(1 for r in days if r.get(k) is not None) >= n - 5]
print("features:", len(FEATS))

def build_y(horizon):
    y = np.zeros(n)
    for i in range(n):
        y[i] = 1.0 if any(days[j]["compound"] for j in range(i+1, min(n, i+1+horizon))) else 0.0
    return y

X = np.array([[float(r.get(k)) if r.get(k) is not None else np.nan for k in FEATS] for r in days])
p = X.shape[1]
doy = np.array([int(x[5:7])*31+int(x[8:10]) for x in dates]); bins = (doy//10).astype(int)

def auc(yt, yp):
    o = np.argsort(yp); yt = yt[o]
    pos, neg = yt.sum(), (1-yt).sum()
    if pos == 0 or neg == 0: return float("nan")
    r = np.arange(1, len(yt)+1)
    return (r[yt==1].sum() - pos*(pos+1)/2)/(pos*neg)

def fit(Xtr, ytr, l2=1.0, lr=0.5, iters=3000):
    mu = np.nanmean(Xtr, 0); mu = np.where(np.isnan(mu), 0, mu)
    Z = np.where(np.isnan(Xtr), mu, Xtr)
    sd = Z.std(0); sd[sd == 0] = 1
    Z = (Z-mu)/sd
    Zb = np.hstack([np.ones((len(Z),1)), Z]); w = np.zeros(Zb.shape[1])
    for _ in range(iters):
        pr = 1/(1+np.exp(-np.clip(Zb@w,-30,30)))
        g = Zb.T@(pr-ytr)/len(Z); g[1:] += l2*w[1:]/len(Z); w -= lr*g
    return w, mu, sd

def pred(w, mu, sd, Xa):
    Z = np.where(np.isnan(Xa), mu, Xa); Z = (Z-mu)/sd
    return 1/(1+np.exp(-np.clip(np.hstack([np.ones((len(Z),1)), Z])@w, -30, 30)))

def clim(train_idx, test_idx, ytr):
    rate = {}
    for b in np.unique(bins[train_idx]):
        m = bins[train_idx] == b; rate[b] = ytr[m].mean()
    g = ytr.mean()
    return np.array([rate.get(b, g) for b in bins[test_idx]])

print("\n%-8s %-7s %-7s %-7s %-7s %-7s %-6s" % ("horizon","base%","modelAUC","climAUC","persAUC","Brier","n_pos"))
out = {}
folds = [(np.arange(0, int(n*s)), np.arange(int(n*s), min(n, int(n*s)+180))) for s in (0.55, 0.65, 0.75, 0.85)]
for h in (1, 3, 7, 14):
    y = build_y(h)
    P, C, PER, Y = [], [], [], []
    for tr, te in folds:
        w, mu, sd = fit(X[tr], y[tr], l2=1.0)
        pt = pred(w, mu, sd, X[te]); pc = clim(tr, te, y[tr])
        pers = np.array([y[max(0, i-1)] for i in te])  # persistence: yesterday's label
        P.append(pt); C.append(pc); PER.append(pers); Y.append(y[te])
    P = np.concatenate(P); C = np.concatenate(C); PER = np.concatenate(PER); Y = np.concatenate(Y)
    br = float(np.mean((P-Y)**2))
    print("%-8d %-7.3f %-7.3f %-7.3f %-7.3f %-7.3f %-6d" % (h, Y.mean(), auc(Y,P), auc(Y,C), auc(Y,PER), br, int(Y.sum())))
    out[h] = dict(prev=round(float(Y.mean()),3), model_auc=round(float(auc(Y,P)),3),
                  clim_auc=round(float(auc(Y,C)),3), persistence_auc=round(float(auc(Y,PER)),3), brier=round(br,3))

json.dump(out, open(os.path.join(BASE,"data","processed","diagnostics.json"),"w",encoding="utf-8", newline="\n"), indent=2)
