
# -*- coding: utf-8 -*-
"""Semporna coral bleaching heat-stress pipeline.

Reads hourly SST (Open-Meteo Marine API) -> daily aggregates -> DHW (Degree Heating Weeks)
  MMM        : Maximum of the Monthly Mean climatology (NOAA CRW definition)
  HotSpot    : daily SST - MMM, only counted when > 1.0 C  (NOAA CRW)
  DHW        : rolling 12-week (84-day) sum of HotSpots > 1 C, in degC-weeks
  Bleaching Alert Level (heritage CRW): 0 none | 1 watch | 2 warning | 3 AL1 | 4 AL2 | 5 AL3/4/5
"""
import csv, json, os, statistics as st
from datetime import date, timedelta

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(BASE, "data", "raw", "semporna_sst_hourly_2023_2026.csv")
OUT = os.path.join(BASE, "data", "processed")
os.makedirs(OUT, exist_ok=True)

# ---------- 1. hourly -> daily ----------
byday = {}
with open(RAW, newline="", encoding="utf-8") as f:
    for row in csv.DictReader(f):
        d = row["time_utc"][:10]
        byday.setdefault(d, []).append(float(row["sst_c"]))

days = sorted(byday)
daily = []
for d in days:
    v = byday[d]
    daily.append({"date": d, "sst_mean": round(st.mean(v), 3),
                  "sst_max": round(max(v), 3), "sst_min": round(min(v), 3),
                  "n_hours": len(v)})
print("daily records:", len(daily), daily[0]["date"], "->", daily[-1]["date"])

# ---------- 2. MMM = max of monthly-mean climatology (baseline 2023-2025) ----------
BASELINE = ("2023-01-01", "2025-12-31")
bymonth = {}
for r in daily:
    if BASELINE[0] <= r["date"] <= BASELINE[1]:
        bymonth.setdefault(r["date"][:7], []).append(r["sst_mean"])
monthly_means = {m: round(st.mean(v), 3) for m, v in sorted(bymonth.items())}
mmm = max(monthly_means.values())
mmm_month = max(monthly_means, key=lambda m: monthly_means[m])
print("months in baseline:", len(monthly_means), "MMM =", mmm, "C (from", mmm_month + ")")

# ---------- 3. HotSpot + DHW (84-day rolling sum of HotSpot>1C, in degC-weeks) ----------
for r in daily:
    r["hotspot"] = round(r["sst_mean"] - mmm, 3)
    r["hotspot_counted"] = r["hotspot"] if r["hotspot"] > 1.0 else 0.0

by_date = {r["date"]: r for r in daily}
for r in daily:
    d0 = date.fromisoformat(r["date"])
    total = 0.0
    for k in range(84):
        rr = by_date.get((d0 - timedelta(days=k)).isoformat())
        if rr:
            total += rr["hotspot_counted"]
    r["dhw"] = round(total / 7.0, 3)

def alert_level(dhw, hs):
    if dhw < 1 and hs <= 1: return 0
    if dhw < 1: return 1          # watch
    if dhw < 4: return 2          # warning
    if dhw < 8: return 3          # AL1
    if dhw < 12: return 4         # AL2
    return 5                       # AL3/4/5

ALERT_NAMES = {0: "No Stress", 1: "Watch", 2: "Warning", 3: "Bleaching Alert Level 1",
               4: "Bleaching Alert Level 2", 5: "Bleaching Alert Level 3-5"}
for r in daily:
    r["alert_level"] = alert_level(r["dhw"], r["hotspot"])
    r["alert_name"] = ALERT_NAMES[r["alert_level"]]

# ---------- 4. write outputs ----------
cols = ["date", "sst_mean", "sst_max", "sst_min", "hotspot", "dhw", "alert_level", "alert_name"]
csv_path = os.path.join(OUT, "semporna_dhw_daily.csv")
with open(csv_path, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
    w.writeheader(); w.writerows(daily)

summary = {
    "site": {"name": "Semporna, Sabah, Malaysia", "lat": 4.6, "lon": 118.7,
             "note": "西里伯斯海 / 珊瑚大三角边缘，仙本那群岛"},
    "period": {"start": daily[0]["date"], "end": daily[-1]["date"], "days": len(daily)},
    "mmm_c": mmm, "mmm_source_month": mmm_month,
    "monthly_means_c": monthly_means,
    "peak": {
        "dhw_max": max(r["dhw"] for r in daily),
        "dhw_max_date": max(daily, key=lambda r: r["dhw"])["date"],
        "sst_max": max(r["sst_max"] for r in daily),
        "days_alert_ge_3": sum(1 for r in daily if r["alert_level"] >= 3),
        "days_alert_ge_1": sum(1 for r in daily if r["alert_level"] >= 1),
    },
    "alert_days_by_year": {},
    "last_30_days": daily[-30:],
}
for r in daily:
    y = r["date"][:4]
    summary["alert_days_by_year"].setdefault(y, {})["AL>=%d" % 1] = summary["alert_days_by_year"].get(y, {}).get("AL>=1", 0) + (1 if r["alert_level"] >= 1 else 0)
    summary["alert_days_by_year"][y]["AL>=3"] = summary["alert_days_by_year"][y].get("AL>=3", 0) + (1 if r["alert_level"] >= 3 else 0)

json_path = os.path.join(OUT, "semporna_summary.json")
with open(json_path, "w", encoding="utf-8") as f:
    json.dump(summary, f, ensure_ascii=False, indent=2)

print("\n=== RESULT ===")
print("MMM:", mmm, "C | peak DHW:", summary["peak"]["dhw_max"], "on", summary["peak"]["dhw_max_date"])
print("days with AL>=3:", summary["peak"]["days_alert_ge_3"], "| AL>=1:", summary["peak"]["days_alert_ge_1"])
print("alert days by year:", json.dumps(summary["alert_days_by_year"], ensure_ascii=False))
print("\nlast 7 days:")
for r in daily[-7:]:
    print(" ", r["date"], "sst", r["sst_mean"], "hs", r["hotspot"], "dhw", r["dhw"], r["alert_name"])
print("\nwrote:", csv_path)
print("wrote:", json_path)
