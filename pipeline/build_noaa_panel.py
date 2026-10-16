# -*- coding: utf-8 -*-
# build_noaa_panel.py - 把 NOAA CRW 官方 5 km BAA 白化预警汇总 CSV 解析成单页用的官方对照数据。
import csv, json, os, sys
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV_PATH = os.path.join(ROOT, "data", "external", "noaa_crw", "stats_alert01_baa5.csv")
DASH_PATH = os.path.join(ROOT, "data", "processed", "dashboard_data.json")
OUT = os.path.join(ROOT, "data", "processed", "noaa_crw_panel.json")

def num(s):
    s = (s or "").strip().replace("%", "").replace(",", "")
    if s == "":
        return None
    try:
        return float(s)
    except ValueError:
        return None

with open(CSV_PATH, newline="", encoding="utf-8", errors="replace") as fh:
    rd = csv.reader(fh)
    header = next(rd)
    raw = [r for r in rd if len(r) >= 12]

print("HEADER " + json.dumps(header, ensure_ascii=False))
print("ROWS " + str(len(raw)))
print("FIRST " + json.dumps(raw[0], ensure_ascii=False))
print("LAST " + json.dumps(raw[-1], ensure_ascii=False))

years = {}
order = []
for r in raw:
    try:
        y = int(r[0].strip())
        m = int(r[1].strip())
        d = int(r[2].strip())
    except ValueError:
        continue
    g = num(r[8])
    p = num(r[9])
    a = num(r[10])
    i = num(r[11])
    if y not in years:
        years[y] = {"year": y, "days": 0, "global_max": 0.0, "pacific_max": 0.0, "atlantic_max": 0.0, "indian_max": 0.0, "global_sum": 0.0, "pacific_sum": 0.0}
        order.append(y)
    e = years[y]
    e["days"] += 1
    for k, v in (("global", g), ("pacific", p), ("atlantic", a), ("indian", i)):
        if v is None:
            continue
        if v > e[k + "_max"]:
            e[k + "_max"] = v
        if k in ("global", "pacific"):
            e[k + "_sum"] += v

annual = []
for y in order:
    e = years[y]
    e["global_mean"] = e["global_sum"] / e["days"]
    e["pacific_mean"] = e["pacific_sum"] / e["days"]
    del e["global_sum"]
    del e["pacific_sum"]
    for k in ("global_max", "pacific_max", "atlantic_max", "indian_max", "global_mean", "pacific_mean"):
        e[k] = round(e[k], 6)
    annual.append(e)

last = raw[-1]
latest = {"date": last[3].strip(), "global_n": int(num(last[4]) or 0), "pacific_n": int(num(last[5]) or 0),
          "atlantic_n": int(num(last[6]) or 0), "indian_n": int(num(last[7]) or 0),
          "global_pct": num(last[8]), "pacific_pct": num(last[9]), "atlantic_pct": num(last[10]), "indian_pct": num(last[11])}

best_g = max(annual, key=lambda e: e["global_max"])
best_p = max(annual, key=lambda e: e["pacific_max"])
early = [e for e in annual if 1985 <= e["year"] <= 2000]
early_max_g = max(e["global_max"] for e in early) if early else 0.0

dash = json.load(open(DASH_PATH, encoding="utf-8"))
station = [{"year": e["year"], "compound": e["compound"], "hot_days": e["hot_days"]} for e in dash["yearly"]]
table = []
for s in station:
    s["year"] = int(s["year"])
    m = [e for e in annual if e["year"] == s["year"]]
    a = m[0] if m else None
    table.append({"year": s["year"], "compound": s["compound"], "hot_days": s["hot_days"],
                  "global_max": a["global_max"] if a else None, "pacific_max": a["pacific_max"] if a else None,
                  "days": a["days"] if a else 0})

out = {"source": "NOAA Coral Reef Watch 5 km v3.1 官方公开汇总（BAA 白化预警级别分区计数与占比）",
       "url": "https://coralreefwatch.noaa.gov/data_current/5km/v3.1_op/daily/csv/5km-v3.1_stats-alert01_baa5_dailyupdate.csv",
       "header": header, "n_rows": len(raw), "span": [raw[0][3].strip(), last[3].strip()],
       "latest": latest, "annual": annual, "station_table": table,
       "record": {"global_year": best_g["year"], "global_max": best_g["global_max"], "pacific_year": best_p["year"], "pacific_max": best_p["pacific_max"], "early_max_global": early_max_g}}
json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("WROTE " + OUT + " " + str(os.path.getsize(OUT)) + " bytes")
print("SPAN " + out["span"][0] + " .. " + out["span"][1] + "  years " + str(len(annual)))
print("LATEST " + json.dumps(latest, ensure_ascii=False))
print("RECORD " + json.dumps(out["record"], ensure_ascii=False))
print("TABLE " + json.dumps(table, ensure_ascii=False))
print("ANNUAL_2016_2026 " + json.dumps([e for e in annual if e["year"] >= 2016], ensure_ascii=False))