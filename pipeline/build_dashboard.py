# -*- coding: utf-8 -*-
"""Build a self-contained demo dashboard (single HTML file, data embedded)."""
import json, os, math, sys
from datetime import date
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import feat_ext, model

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
P = lambda *a: os.path.join(BASE, *a)

feat = json.load(open(P("data","processed","semporna_features.json"), encoding="utf-8"))
days = feat["days"]; TH = feat["thresholds"]; n = len(days)
# 预报区间标定表（由 interval_audit.py 生成）：缺失时退回 ±1 RMSE
try:
    IA = json.load(open(P("data","processed","interval_audit.json"), encoding="utf-8"))
except Exception:
    IA = None
# 方差收缩校准表（由 blend_audit.py 生成）：只作为"精度上限"对照，不改变上面部署的满幅预报
try:
    BA = json.load(open(P("data","processed","blend_audit.json"), encoding="utf-8"))
except Exception:
    BA = None
dates = [r["date"] for r in days]

feat_ext.add_memory(days)        # strictly causal memory (counts the causal index, not the analysis one)

FEATS = feat_ext.feature_keys(days)
X = model.matrix(days, FEATS)
idx = np.array([r["n_haz"]/3.0 for r in days])
comp = np.array([r["compound"] for r in days], dtype=float)

fit = model.ridge_fit
pred = model.ridge_pred
rmse = model.rmse

# ---- walk-forward validation (last 3 x 180-day test windows) ----
folds = [(np.arange(0,int(n*s)), np.arange(int(n*s), min(n,int(n*s)+180))) for s in (0.62,0.75,0.88)]
ALL_LAMS = []                     # 逐折内窗 CV 挑出的 λ（跨 4 个时效汇总，供成品页当日预报取众数）
metrics = {}
for h in (1,3,7,14):
    y = np.array([idx[min(n-1,i+h)] for i in range(n)])
    Pm,Pp,Pc,Pf,Y = [],[],[],[],[]
    LAMS = []
    for tr,te in folds:
        lam = model.inner_lambda(X[tr], y[tr]); LAMS.append(int(lam)); ALL_LAMS.append(int(lam))
        w,mu,sd = fit(X[tr], y[tr], lam)
        Pm.append(pred(w,mu,sd,X[te]))
        Pp.append(np.array([idx[max(0,i-6):i+1].mean() for i in te]))
        doy = np.array([int(d[5:7])*31+int(d[8:10]) for d in dates])
        Pc.append(np.array([y[tr][doy[tr]==doy[i]].mean() if (doy[tr]==doy[i]).any() else y[tr].mean() for i in te]))
        Pf.append(np.full(len(te), float(y[tr].mean())))     # constant-mean baseline
        Y.append(y[te])
    Pm,Pp,Pc,Pf,Y = map(np.concatenate,(Pm,Pp,Pc,Pf,Y))
    rm = lambda a: float(np.sqrt(np.mean((a-Y)**2)))
    cc = lambda a: float(np.corrcoef(a,Y)[0,1]) if a.std()>0 else 0.0
    auc = model.auc
    lab = (Y > 0).astype(float)
    m = dict(model_rmse=rm(Pm), pers_rmse=rm(Pp), clim_rmse=rm(Pc), flat_rmse=rm(Pf),
                      model_r=cc(Pm), pers_r=cc(Pp), pers_rmse_h=rm(Pp),
                      model_auc=round(auc(Pm,lab),3), pers_auc=round(auc(Pp,lab),3), clim_auc=round(auc(Pc,lab),3), inner_lambda=LAMS)
    if BA and str(h) in BA:                       # 收缩校准对照（beta* 由内层交叉验证挑出）
        b = BA[str(h)]
        m.update(blend_rmse=b["blend_rmse"], blend_auc=b["blend_auc"], blend_beta=b["beta_star"],
                 blend_gain_pct=b["gain_vs_flat_pct"], blend_beats_all=b["beats_all_baselines"])
    metrics[h] = m

# ---- operational forecast: driven by real NWP forecast drivers ----
# History ends at the last observation.  The forward-looking driver values come from
# data/raw/semporna_forecast_drivers.json (Open-Meteo forecast API, NWP).  The wave /
# SST / sea-level forecast product reaches 8 days ahead right now, so the driven
# forecast stops there instead of silently freezing the drivers.
FD = json.load(open(P("data","raw","semporna_forecast_drivers.json"), encoding="utf-8"))["days"]
hist = list(days)
fut = []
for r in FD:
    if r["date"] <= hist[-1]["date"]:
        continue                                     # already inside the observed record
    if r.get("wh_max") is None or r.get("sst_mean") is None or r.get("sl_mean") is None:
        break                                        # marine forecast horizon ends here
    fut.append(dict(r))   # keep the whole fetched row: the model reads current-day levels too
seq = hist + fut

# --- model features for the forecast rows: the SAME strictly causal recipe ---
# feat_ext.add_all() rebuilds levels -> causal index -> rolling block -> memory over the
# whole sequence with the RECORD's causal thresholds, so every forecast row carries
# exactly the columns the model was trained on and no feature reads a later day.
CTH = feat.get("causal_thresholds") or feat_ext.causal_thresholds(hist)
feat_ext.add_all(seq, TH=CTH)

# The ANALYSIS (centred non-tidal residual) is still derived for the forecast rows, so the
# page can display the retrospective quantity the model is verified against.  The model
# never reads it - that is exactly the split pipeline/leakage_audit.py checks.
for i, r in enumerate(fut):
    gi = len(hist) + i
    win = [seq[j].get("sl_mean") for j in range(max(0, gi-12), min(len(seq), gi+13))]
    win = [v for v in win if v is not None]
    r["sl_still"] = sum(win)/len(win)
    r["sl_anom"] = r["sl_mean"] - r["sl_still"]
    r["surge"] = r["sl_anom"]
    r["h_wave"]  = 1 if r["wh_max"] >= TH["wave"]["p90"] else 0
    r["h_rain"]  = 1 if (r.get("precipitation_sum") or -1) >= TH["rain"]["p90"] else 0
    r["h_surge"] = 1 if r["surge"] >= TH["surge"]["p90"] else 0
    r["n_haz"] = r["h_wave"] + r["h_rain"] + r["h_surge"]
    r["compound"] = 1 if r["n_haz"] >= 2 else 0

Xf = model.matrix(fut, FEATS)
LAM = max(sorted(set(ALL_LAMS)), key=ALL_LAMS.count) if ALL_LAMS else model.inner_lambda(X, idx)   # 众数
wf, mu, sd = fit(X, idx, LAM)
vf = pred(wf, mu, sd, Xf) if len(fut) else np.array([])
fut_out = []
for i, r in enumerate(fut):
    k = i + 1
    v = float(vf[i])
    vc = max(0.0, min(1.0, v))          # 显示用的点预报先夹到 [0,1]，区间以它为圆心
    mh = min(metrics, key=lambda h: abs(h-k))
    rmse_k = metrics[mh]["model_rmse"]
    if IA:
        kh = min(IA, key=lambda h: abs(int(h)-k))
        half = float(IA[kh]["q80_multiplier"]) * float(IA[kh]["sigma"])
    else:
        half = rmse_k
    fut_out.append(dict(lead=k, date=r["date"], risk=round(vc,3),
                        lo=round(max(0.0,vc-half),3), hi=round(min(1.0,vc+half),3),
                        half=round(half,4), rmse=round(rmse_k,4),
                        wh_max=r["wh_max"], rain=r["precipitation_sum"], sst=round(r["sst_mean"],2),
                        surge=round(r["surge"],4), n_haz=r["n_haz"]))

today = days[-1]
risk_now = float(idx[-1])
pers7 = float(idx[-7:].mean())
clim = float(np.mean([r["n_haz"]/3.0 for r in days if int(r["date"][5:7])==int(today["date"][5:7])]))

# ---- daily compact series for the charts ----
def g(r, k, d=0.0):
    v = r.get(k)
    return d if v is None else v
series = dict(date=[], risk=[], compound=[], sst=[], rain=[], wave=[], surge=[])
for r in days:
    series["date"].append(r["date"]); series["risk"].append(round(g(r,"n_haz")/3.0,3))
    series["compound"].append(int(g(r,"compound")))
    series["sst"].append(round(g(r,"sst_mean"),2)); series["rain"].append(round(g(r,"precipitation_sum"),1))
    series["wave"].append(round(g(r,"wh_max"),2)); series["surge"].append(round(g(r,"surge"),4))

# yearly aggregates
years = sorted({d[:4] for d in dates})
yearly = []
for y in years:
    rs = [r for r in days if r["date"][:4]==y]
    if not rs: continue
    yearly.append(dict(year=y, days=len(rs),
        compound=sum(int(g(r,"compound")) for r in rs),
        hot_days=sum(1 for r in rs if g(r,"sst_mean",-99) >= TH["sst"]["p90"]),
        avg_risk=round(sum(g(r,"n_haz")/3.0 for r in rs)/len(rs),3),
        max_sst=round(max(g(r,"sst_mean",-99) for r in rs),2),
        max_rain=round(max(g(r,"precipitation_sum") for r in rs),1),
        max_wave=round(max(g(r,"wh_max") for r in rs),2)))

FD_META = json.load(open(P("data","raw","semporna_forecast_drivers.json"), encoding="utf-8"))
payload = dict(site=dict(name="Semporna, Sabah, Malaysia", lat=4.6, lon=118.7),
    span=dict(start=dates[0], end=dates[-1], days=n),
    forecast_meta=dict(mode="driven", horizon=len(fut_out), driver_source=FD_META["source"],
                       band=("empirical-80" if IA else "one-rmse"), features=len(FEATS), lam=LAM),
    thresholds=TH, metrics=metrics, forecast=fut_out,
    now=dict(date=today["date"], risk=round(risk_now,3), pers7=round(pers7,3), clim=round(clim,3),
             sst=round(today["sst_mean"],2), rain=today["precipitation_sum"], wave=today["wh_max"],
             surge=round(today["surge"],4), n_haz=today["n_haz"]),
    series=series, yearly=yearly)

open(P("data","processed","dashboard_data.json"),"w",encoding="utf-8", newline="\n").write(
    json.dumps(payload, ensure_ascii=False, separators=(",",":")))
print("payload days:", n, "| features:", len(FEATS))
print("metrics:", json.dumps({k:{kk:(round(vv,4) if not isinstance(vv,list) else vv) for kk,vv in v.items() if kk!='pers_rmse_h'} for k,v in metrics.items()}))
print("forecast (%d driven days, band %s):" % (len(fut_out), payload["forecast_meta"]["band"]), json.dumps(fut_out[:3]))
print("now:", json.dumps(payload["now"]))
print("yearly:", json.dumps(yearly))
