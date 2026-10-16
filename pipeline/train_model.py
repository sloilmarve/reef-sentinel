# -*- coding: utf-8 -*-
"""7-day-ahead compound coastal-hazard warning model (numpy logistic regression, walk-forward validation).

Task: P(compound hazard day within the next 7 days) for Semporna, from accessible
Open-Meteo marine + weather drivers. Validated by expanding-window time-series CV.
"""
import json, os, math
import numpy as np

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
P = os.path.join(BASE, "data", "processed", "semporna_features.json")
d = json.load(open(P, encoding="utf-8"))
TH, days = d["thresholds"], d["days"]

FEATS = [k for k in days[len(days)//2] if k.startswith("f_")] + ["doy_sin", "doy_cos"]
# keep only features populated for essentially all rows
def fill_ok(k): return sum(1 for r in days if r.get(k) is not None) >= len(days) - 5
FEATS = [k for k in FEATS if fill_ok(k)]
print("features used:", len(FEATS))
print("  ", ", ".join(FEATS))

X = np.array([[float(r.get(k)) if r.get(k) is not None else np.nan for k in FEATS] for r in days])
y = np.array([r["y7"] for r in days], dtype=float)
dates = [r["date"] for r in days]
n, p = X.shape

def impute_fit(Xtr):
    med = np.nanmedian(Xtr, axis=0); med = np.where(np.isnan(med), 0.0, med)
    return med
def apply_impute(Xa, med):
    Z = Xa.copy()
    for j in range(p):
        m = np.isnan(Z[:, j]); Z[m, j] = med[j]
    return Z

def standardize_fit(Z):
    mu, sd = Z.mean(0), Z.std(0); sd[sd == 0] = 1.0
    return mu, sd

def train_logreg(Z, yy, l2=1.0, lr=0.5, iters=4000):
    n, p = Z.shape
    Zb = np.hstack([np.ones((n, 1)), Z])
    w = np.zeros(p + 1)
    for it in range(iters):
        z = Zb @ w
        pr = 1.0 / (1.0 + np.exp(-np.clip(z, -30, 30)))
        g = Zb.T @ (pr - yy) / n
        g[1:] += l2 * w[1:] / n
        w -= lr * g
    return w
def predict(w, Z):
    Zb = np.hstack([np.ones((Z.shape[0], 1)), Z])
    return 1.0 / (1.0 + np.exp(-np.clip(Zb @ w, -30, 30)))

def auc(yt, yp):
    order = np.argsort(yp); yt = yt[order]
    pos, neg = yt.sum(), (1 - yt).sum()
    if pos == 0 or neg == 0: return float("nan")
    ranks = np.arange(1, len(yt) + 1)
    return (ranks[yt == 1].sum() - pos * (pos + 1) / 2) / (pos * neg)

def brier(yt, yp): return float(np.mean((yp - yt) ** 2))

# climatology baseline: P(y7=1) by 10-day bin of the year
doy = np.array([int(dd[5:7]) * 31 + int(dd[8:10]) for dd in dates])
bins = (doy // 10).astype(int)
def clim_pred(train_idx, test_idx):
    rate = {}
    for b in np.unique(bins[train_idx]):
        m = (bins[train_idx] == b)
        rate[b] = y[train_idx][m].mean()
    glob = y[train_idx].mean()
    return np.array([rate.get(b, glob) for b in bins[test_idx]])

# walk-forward folds
folds = []
start_test = int(n * 0.55)
while start_test < n - 60:
    end_test = min(n, start_test + 180)
    train_idx = np.arange(0, start_test)
    test_idx = np.arange(start_test, end_test)
    folds.append((train_idx, test_idx))
    start_test = end_test
print("\nfolds:", [(dates[a[0]], dates[a[-1]], dates[b[0]], dates[b[-1]]) for a, b in folds])

rows = []
all_pred, all_true, all_clim = [], [], []
for k, (tr, te) in enumerate(folds):
    med = impute_fit(X[tr]); Ztr = apply_impute(X[tr], med); Zte = apply_impute(X[te], med)
    mu, sd = standardize_fit(Ztr); Ztr = (Ztr - mu) / sd; Zte = (Zte - mu) / sd
    best = None
    for l2 in (0.3, 1.0, 3.0, 10.0):
        w = train_logreg(Ztr, y[tr], l2=l2)
        ptr = predict(w, Ztr)
        a = auc(y[tr], ptr)
        if best is None or a > best[0]: best = (a, l2, w)
    _, l2, w = best
    pt = predict(w, Zte)
    pc = clim_pred(tr, te)
    all_pred.append(pt); all_true.append(y[te]); all_clim.append(pc)
    thr = 0.25
    pred_bin = (pt >= thr).astype(int)
    tp = int(((pred_bin == 1) & (y[te] == 1)).sum()); fp = int(((pred_bin == 1) & (y[te] == 0)).sum())
    fn = int(((pred_bin == 0) & (y[te] == 1)).sum()); tn = int(((pred_bin == 0) & (y[te] == 0)).sum())
    rows.append(dict(fold=k+1, train="%s..%s" % (dates[tr[0]], dates[tr[-1]]), test="%s..%s" % (dates[te[0]], dates[te[-1]]),
                     n_test=len(te), l2=l2, auc=round(auc(y[te], pt), 3), brier=round(brier(y[te], pt), 3),
                     base_rate=round(float(y[te].mean()), 3),
                     clim_auc=round(auc(y[te], pc), 3), clim_brier=round(brier(y[te], pc), 3),
                     tp=tp, fp=fp, fn=fn, tn=tn,
                     recall=round(tp/(tp+fn), 3) if tp+fn else None,
                     precision=round(tp/(tp+fp), 3) if tp+fp else None,
                     far=round(fp/(fp+tn), 3) if fp+tn else None))
    print("fold", k+1, rows[-1])

P_all = np.concatenate(all_pred); Y_all = np.concatenate(all_true); C_all = np.concatenate(all_clim)
overall = dict(n=int(len(Y_all)), positives=int(Y_all.sum()),
               model_auc=round(auc(Y_all, P_all), 3), model_brier=round(brier(Y_all, P_all), 3),
               clim_auc=round(auc(Y_all, C_all), 3), clim_brier=round(brier(Y_all, C_all), 3))
print("\nOVERALL:", overall)

# final model on all data, with the coefficients for the write-up
med = impute_fit(X); Z = apply_impute(X, med); mu, sd = standardize_fit(Z); Zs = (Z - mu) / sd
w = train_logreg(Zs, y, l2=1.0)
coef = sorted(zip(FEATS, w[1:]), key=lambda t: -abs(t[1]))[:12]
print("\ntop coefficients (standardized):")
for k, v in coef: print("   %-22s %+.3f" % (k, v))

latest = dict(zip(FEATS, (X[-1] - mu) / sd))
print("\nlatest forecast P(next 7 days have a compound hazard day) =", round(float(predict(w, ((apply_impute(X[-1:], med) - mu) / sd))[0]), 3))

json.dump(dict(features=FEATS, folds=rows, overall=overall,
               final_coef={k: round(float(v), 4) for k, v in zip(["intercept"] + FEATS, w)},
               latest_date=dates[-1],
               latest_prob=round(float(predict(w, ((apply_impute(X[-1:], med) - mu) / sd))[0]), 4),
               thresholds=TH),
          open(os.path.join(BASE, "data", "processed", "model_report.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print("\nwrote", os.path.join(BASE, "data", "processed", "model_report.json"))
