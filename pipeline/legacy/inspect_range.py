
import csv, statistics as st, os
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
p = os.path.join(BASE, "data", "processed", "semporna_dhw_daily.csv")
rows = list(csv.DictReader(open(p, encoding="utf-8")))
for r in rows:
    r["sst_mean"] = float(r["sst_mean"]); r["sst_max"] = float(r["sst_max"])
print("range of daily mean SST:", min(r["sst_mean"] for r in rows), "->", max(r["sst_mean"] for r in rows))
print("range of hourly max SST :", min(r["sst_max"] for r in rows), "->", max(r["sst_max"] for r in rows))
bym = {}
for r in rows: bym.setdefault(r["date"][:7], []).append(r["sst_mean"])
print("\nmonthly mean SST:")
for m in sorted(bym): print("  ", m, round(st.mean(bym[m]), 2), " max-daily:", round(max(bym[m]), 2))
