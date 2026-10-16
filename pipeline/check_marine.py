
import csv, os
p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "raw", "semporna_marine_hourly.csv")
cols = None; counts = {}
with open(p, newline="", encoding="utf-8") as f:
    rd = csv.DictReader(f, delimiter=";")
    cols = rd.fieldnames
    n = 0
    for row in rd:
        n += 1
        for c in cols[1:]:
            if row[c] not in ("", None): counts[c] = counts.get(c, 0) + 1
print("rows:", n)
print("columns:", cols)
for c in cols[1:]: print("  non-empty", c, counts.get(c, 0), "=", round(100*counts.get(c,0)/n, 1), "%")
