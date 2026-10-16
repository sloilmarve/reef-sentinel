# -*- coding: utf-8 -*-
"""Build the daily feature + label table for the Semporna early-warning model."""
import csv, json, os, math, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import feat_ext
from collections import defaultdict
from datetime import date, timedelta
import statistics as st

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(BASE, "data", "raw"); OUT = os.path.join(BASE, "data", "processed")
os.makedirs(OUT, exist_ok=True)

# ---------- marine hourly -> daily ----------
mar = defaultdict(list)
with open(os.path.join(RAW, "semporna_marine_hourly.csv"), newline="", encoding="utf-8") as f:
    for r in csv.DictReader(f, delimiter=";"):
        mar[r["time_utc"][:10]].append(r)

def fnum(x):
    try: return float(x)
    except: return None

days = []
for d in sorted(mar):
    rec = mar[d]
    def col(name):
        return [fnum(x[name]) for x in rec if fnum(x[name]) is not None]
    sl = col("sea_level_height_msl"); wh = col("wave_height")
    wp = col("wave_period"); sst = col("sea_surface_temperature")
    ww = col("wind_wave_height"); oc = col("ocean_current_velocity")
    row = {"date": d, "n_hours": len(rec)}
    if sl: row.update(sl_mean=st.mean(sl), sl_max=max(sl), sl_min=min(sl), sl_range=max(sl)-min(sl))
    if wh: row.update(wh_mean=st.mean(wh), wh_max=max(wh))
    if wp: row["wp_mean"] = st.mean(wp)
    if sst: row.update(sst_mean=st.mean(sst), sst_max=max(sst))
    if ww: row["ww_mean"] = st.mean(ww)
    if oc: row["oc_mean"] = st.mean(oc)
    days.append(row)

# ---------- weather daily ----------
wpath = os.path.join(RAW, "semporna_weather_daily.csv")
wby = {}
with open(wpath, newline="", encoding="utf-8") as f:
    for r in csv.DictReader(f, delimiter=";"):
        wby[r["date"]] = r
for row in days:
    w = wby.get(row["date"])
    if not w: continue
    for k in ("temperature_2m_max","temperature_2m_min","temperature_2m_mean","precipitation_sum",
              "wind_speed_10m_max","wind_gusts_10m_max","wind_direction_10m_dominant","relative_humidity_2m_mean"):
        v = fnum(w.get(k))
        if v is not None: row[k] = v

print("daily rows:", len(days), days[0]["date"], "->", days[-1]["date"])

# ---------- tide removal (RETROSPECTIVE ANALYSIS): 25-DAY centred rolling mean of the daily mean sea level ----------
# The centred filter is the standard non-tidal-residual definition for describing the past;
# it is NOT fed to the model.  Every model input is rebuilt from past-only windows below.
idx = {r["date"]: i for i, r in enumerate(days)}
for i, r in enumerate(days):
    win = [days[j].get("sl_mean") for j in range(max(0, i-12), min(len(days), i+13))]
    win = [v for v in win if v is not None]
    if win and r.get("sl_mean") is not None:
        r["sl_still"] = st.mean(win)
        r["surge"] = r["sl_mean"] - r["sl_still"]          # non-tidal residual
        r["sl_anom"] = r["sl_mean"] - st.mean(win)          # same for now, kept for clarity

# ---------- percentile thresholds from the record ----------
def pct(vals, p):
    v = sorted(x for x in vals if x is not None); 
    return v[min(len(v)-1, int(round(p*(len(v)-1))))]

TH = {}
for name, key in (("wave", "wh_max"), ("rain", "precipitation_sum"), ("surge", "surge"), ("sst", "sst_mean")):
    vals = [r.get(key) for r in days]
    TH[name] = {"key": key, "p90": round(pct(vals, .90), 3), "p95": round(pct(vals, .95), 3), "p99": round(pct(vals, .99), 3)}
print("\nthresholds (90/95/99 pct):")
for k, v in TH.items(): print("  ", k, v["p90"], v["p95"], v["p99"])

for r in days:
    r["h_wave"]  = 1 if (r.get("wh_max") or -1) >= TH["wave"]["p90"] else 0
    r["h_rain"]  = 1 if (r.get("precipitation_sum") or -1) >= TH["rain"]["p90"] else 0
    r["h_surge"] = 1 if (r.get("surge") or -1) >= TH["surge"]["p90"] else 0
    r["n_haz"] = r["h_wave"] + r["h_rain"] + r["h_surge"]
    r["compound"] = 1 if r["n_haz"] >= 2 else 0          # >=2 simultaneous hazards = compound event

ncomp = sum(r["compound"] for r in days)
print("\ncompound-hazard days:", ncomp, "of", len(days), "=", round(100*ncomp/len(days), 1), "%")
byyear = defaultdict(int)
for r in days: byyear[r["date"][:4]] += r["compound"]
print("compound by year:", dict(sorted(byyear.items())))

# ---------- label: compound event within next 7 days ----------
for i, r in enumerate(days):
    r["y7"] = 1 if any(days[j]["compound"] for j in range(i+1, min(len(days), i+8))) else 0
print("positive rate y7:", round(100*sum(r["y7"] for r in days)/len(days), 1), "%")

# ---------- model features: STRICTLY CAUSAL (every window ends at the day itself) ----------
# feat_ext.add_all() builds the trailing still-water level, the causal hazard index the
# memory features count, the rolling / anomaly block and the seasonal terms.  Nothing
# here reads day t+1 or later; pipeline/leakage_audit.py proves it by truncation.
CTH = feat_ext.add_all(days)
print("causal thresholds (p90):", {k: round(v, 4) for k, v in CTH.items()})

with open(os.path.join(OUT, "semporna_features.json"), "w", encoding="utf-8") as f:
    json.dump({"thresholds": TH, "causal_thresholds": CTH, "days": days}, f, ensure_ascii=False)
print("\nwrote", os.path.join(OUT, "semporna_features.json"))
last = days[-1]
print("latest day record:", {k: last[k] for k in ("date","wh_max","precipitation_sum","surge","sst_mean","compound","y7") if k in last})
