# -*- coding: utf-8 -*-
"""Semporna coral bleaching heat-stress pipeline v2.

Data   : Open-Meteo Marine API, hourly sea_surface_temperature, 4.600N / 118.700E
Baseline: 2023-01-01 .. 2023-12-31  (short record -> documented limitation)
  MMM  = max of monthly-mean SST over the baseline  (NOAA CRW definition)
  HotSpot = daily SST - MMM, counted only when > 1.0 C
  DHW  = 84-day (12-week) rolling sum of counted HotSpots / 7  [degC-weeks]
  BAA  = heritage CRW alert: 0 none | 1 watch | 2 warning | 3 AL1 | 4 AL2 | 5 AL3-5
"""
import csv, json, os, statistics as st
from datetime import date, timedelta

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(BASE, "data", "raw", "semporna_sst_hourly_2022_2026.csv")
OUT = os.path.join(BASE, "data", "processed")
os.makedirs(OUT, exist_ok=True)

byday = {}
with open(RAW, newline="", encoding="utf-8") as f:
    for row in csv.DictReader(f):
        byday.setdefault(row["time_utc"][:10], []).append(float(row["sst_c"]))

daily = []
for d in sorted(byday):
    v = byday[d]
    daily.append({"date": d, "sst_mean": round(st.mean(v), 3), "sst_max": round(max(v), 3), "sst_min": round(min(v), 3)})
print("daily:", len(daily), daily[0]["date"], "->", daily[-1]["date"])

BASELINE = ("2023-01-01", "2023-12-31")
bymonth = {}
for r in daily:
    if BASELINE[0] <= r["date"] <= BASELINE[1]:
        bymonth.setdefault(r["date"][:7], []).append(r["sst_mean"])
monthly_means = {m: round(st.mean(v), 3) for m, v in sorted(bymonth.items())}
mmm = max(monthly_means.values()); mmm_month = max(monthly_means, key=lambda m: monthly_means[m])
print("baseline months:", len(monthly_means), "| MMM =", mmm, "C (", mmm_month, ")")

for r in daily:
    r["hotspot"] = round(r["sst_mean"] - mmm, 3)
    r["hs_counted"] = r["hotspot"] if r["hotspot"] > 1.0 else 0.0

by_date = {r["date"]: r for r in daily}
for r in daily:
    d0 = date.fromisoformat(r["date"])
    s = 0.0
    for k in range(84):
        rr = by_date.get((d0 - timedelta(days=k)).isoformat())
        if rr: s += rr["hs_counted"]
    r["dhw"] = round(s / 7.0, 3)

def baa(dhw, hs):
    if dhw < 1: return 1 if hs > 1 else 0
    if dhw < 4: return 2
    if dhw < 8: return 3
    if dhw < 12: return 4
    return 5
NAMES = {0: "No Stress", 1: "Bleaching Watch", 2: "Bleaching Warning", 3: "Alert Level 1", 4: "Alert Level 2", 5: "Alert Level 3-5"}
for r in daily:
    r["baa"] = baa(r["dhw"], r["hotspot"]); r["baa_name"] = NAMES[r["baa"]]

cols = ["date", "sst_mean", "sst_max", "sst_min", "hotspot", "dhw", "baa", "baa_name"]
with open(os.path.join(OUT, "semporna_stress_daily.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore"); w.writeheader(); w.writerows(daily)

post = [r for r in daily if r["date"] >= "2024-01-01"]
peak = max(daily, key=lambda r: r["dhw"])
byyear = {}
for r in daily:
    y = r["date"][:4]
    e = byyear.setdefault(y, {"days_baa_ge1": 0, "days_baa_ge2": 0, "days_baa_ge3": 0, "dhw_max": 0.0, "dhw_max_date": None})
    for lvl in (1, 2, 3):
        if r["baa"] >= lvl: e["days_baa_ge%d" % lvl] += 1
    if r["dhw"] > e["dhw_max"]: e["dhw_max"] = r["dhw"]; e["dhw_max_date"] = r["date"]

summary = {
 "site": {"name": "Semporna, Sabah, Malaysia", "lat": 4.6, "lon": 118.7},
 "sst_source": "Open-Meteo Marine API (hourly sea_surface_temperature)",
 "period": {"start": daily[0]["date"], "end": daily[-1]["date"], "days": len(daily)},
 "baseline": {"start": BASELINE[0], "end": BASELINE[1], "mmm_c": mmm, "mmm_month": mmm_month,
              "monthly_means_c": monthly_means,
              "caveat": "基线仅 1 年（2023），远短于 NOAA CRW 的 1985-1993 标准基线；作为保守下限使用"},
 "peak": {"dhw_max": peak["dhw"], "date": peak["date"], "baa": peak["baa"], "baa_name": peak["baa_name"]},
 "by_year": byyear,
 "current": daily[-1],
 "recent_30d": daily[-30:],
}
with open(os.path.join(OUT, "semporna_summary.json"), "w", encoding="utf-8") as f:
    json.dump(summary, f, ensure_ascii=False, indent=2)

print("\nMMM =", mmm, "C")
print("peak DHW =", peak["dhw"], "on", peak["date"], "|", peak["baa_name"])
for y in sorted(byyear): print(" ", y, byyear[y])
print("\nlatest:", daily[-1])
