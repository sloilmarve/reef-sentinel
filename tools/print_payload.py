import json, os, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
P = lambda *a: os.path.join(ROOT, *a)
D = json.load(open(P("data", "processed", "dashboard_data.json"), encoding="utf-8"))
print("SPAN", D["span"])
print("YEARLY", json.dumps(D["yearly"], ensure_ascii=False))
print("METRICS", json.dumps(D["metrics"], ensure_ascii=False))
print("NOW", json.dumps(D["now"], ensure_ascii=False))
print("THRESH", json.dumps(D["thresholds"], ensure_ascii=False))
R = json.load(open(P("data", "processed", "regression_skill.json"), encoding="utf-8"))
print("REGKEYS", sorted(R.keys())[:14])
for k in sorted(R.keys()):
    v = R[k]
    if isinstance(v, list) and v and isinstance(v[0], dict):
        print(" REG", k, json.dumps(v, ensure_ascii=False)[:900])
    elif not isinstance(v, (dict, list)):
        print(" REG", k, v)