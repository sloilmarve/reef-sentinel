# -*- coding: utf-8 -*-
"""Prove that no model input reads the future.

Every column the model reads is rebuilt from the RAW INPUTS of a truncated prefix of the
record (day 0 .. day T) and compared, column by column, with the value stored in
data/processed/semporna_features.json.  A strictly causal recipe reproduces the stored
value exactly at T for every T; a recipe that smooths over a centred window does not.

The audit also reports the same test for the three RETROSPECTIVE ANALYSIS columns
(sl_still / sl_anom / surge) that the page shows and the model is verified against.  They
are expected to FAIL the prefix test - that is exactly why the model is not allowed to
read them, and why the record keeps them only as analysis.

Writes data/processed/leakage_audit.json.
"""
import json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import feat_ext

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
P = lambda *a: os.path.join(BASE, *a)
EPS = 1e-9

feat = json.load(open(P("data", "processed", "semporna_features.json"), encoding="utf-8"))
days = feat["days"]; n = len(days)
TH = feat["thresholds"]
CTH = feat.get("causal_thresholds") or feat_ext.causal_thresholds(days)
FEATS = feat_ext.feature_keys(days)

# raw inputs a truncated prefix is allowed to keep: the observations themselves
RAW_IN = ("date",) + tuple(feat_ext.RAW_LEVELS)
ANALYSIS_COLS = ("sl_still", "sl_anom", "surge")

cuts = sorted({int(n * 0.40), int(n * 0.55), int(n * 0.70), int(n * 0.85), n - 8, n - 2})
rows = []
for T in cuts:
    sub = [{k: r.get(k) for k in RAW_IN} for r in days[:T + 1]]
    feat_ext.add_all(sub, TH=CTH)
    miss = [k for k in FEATS if k not in sub[T]]
    diffs = [abs(sub[T][k] - days[T][k]) for k in FEATS
             if k in sub[T] and isinstance(sub[T][k], (int, float)) and isinstance(days[T][k], (int, float))]
    rows.append(dict(cut=days[T]["date"], t=T, missing=miss,
                     n_compared=len(diffs), max_abs_diff=max(diffs) if diffs else None))
    print("[leak] 前缀 %s（%d 天）重建 %d 列，最大偏差 %.3e%s"
          % (days[T]["date"], T + 1, len(diffs), max(diffs) if diffs else float("nan"),
             ("，缺列 " + ",".join(miss)) if miss else ""))

dmax = max((r["max_abs_diff"] or 0.0) for r in rows)
missing_any = sorted({m for r in rows for m in r["missing"]})
leaked = [k for k in ANALYSIS_COLS if k in FEATS]

# the analysis columns, for contrast: how far a prefix-only rebuild sits from the stored value
an_rows = []
for col in ANALYSIS_COLS:
    per = []
    for T in cuts:
        sub = [{k: r.get(k) for k in RAW_IN} for r in days[:T + 1]]
        w = [sub[j].get("sl_mean") for j in range(max(0, T - 12), min(len(sub), T + 13))]
        w = [v for v in w if v is not None]
        pre = sum(w) / len(w)
        if col == "sl_still":
            per.append(abs(pre - days[T][col]))
        elif col == "sl_anom":
            per.append(abs((days[T]["sl_mean"] - pre) - days[T][col]))
        else:
            per.append(abs((days[T]["sl_mean"] - pre) - days[T][col]))
    an_rows.append(dict(col=col, max_abs_diff=max(per)))
    print("[leak] 回顾性分析列 %-8s 前缀重建最大偏差 %.4f（正因如此不进模型）" % (col, max(per)))

# how many of the last 8 days a prefix-only rebuild cannot reproduce for sl_still
bad = 0
for T in range(n - 8, n):
    sub = [{k: r.get(k) for k in RAW_IN} for r in days[:T + 1]]
    w = [sub[j].get("sl_mean") for j in range(max(0, T - 12), T + 1)]
    w = [v for v in w if v is not None]
    if abs(sum(w) / len(w) - days[T]["sl_still"]) > EPS:
        bad += 1

ok = (dmax < EPS) and not missing_any and not leaked
verdict = "PASS" if ok else "FAIL"
out = dict(task="model inputs are strictly causal (no feature reads day t+1 or later)",
           protocol="rebuild every model column from the raw inputs of the truncated prefix 0..T with the record's causal thresholds, then compare with the stored value",
           n_days=n, feature_count=len(FEATS), causal_thresholds={k: round(v, 6) for k, v in CTH.items()},
           cuts=rows, max_abs_diff=dmax, missing_columns=missing_any,
           analysis_cols_excluded=an_rows, analysis_cols_in_features=leaked,
           analysis_leak_days_last8=bad,
           verdict=verdict)
json.dump(out, open(P("data", "processed", "leakage_audit.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("")
print("LEAKAGE AUDIT %s：%d 个模型列在 %d 个截断点全部可由「只用过去数据」复现，最大偏差 %.3e；回顾性分析列最大偏差 %.4f（已排除在模型之外），最后 8 天有 %d 天无法用前缀复现"
      % (verdict, len(FEATS), len(cuts), dmax, max(r["max_abs_diff"] for r in an_rows), bad))
if not ok:
    print("  FAIL 细节：missing=%s leaked=%s" % (missing_any, leaked))
    sys.exit(1)
