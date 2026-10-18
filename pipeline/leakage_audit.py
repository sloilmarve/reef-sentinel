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
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import feat_ext, model as M

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

# ---------- part B: the THRESHOLDS and the TARGET have to be causal too ----------
# Part A proves every model column is a function of the past *given* the thresholds.  It says
# nothing about the thresholds themselves: the three p90 values are read off the WHOLE
# record, and the shipped target (n_haz, built on the CENTRED residual) needs days up to
# t+12.  Instead of arguing about the size of those two channels, this part re-runs the same
# walk-forward protocol in three arms on identical folds:
#   as_shipped       thresholds and target exactly as pipeline/skill_regression.py uses them
#   prefix_thresholds thresholds recomputed from the training prefix of each fold only
#   causal_target    target from the strictly causal index (surge_trail), record thresholds
HEAD = (1, 3, 7, 14)
FOLDS = (0.55, 0.65, 0.75, 0.85)
RAW_KEYS = ("date",) + tuple(feat_ext.RAW_LEVELS)

_base = [{k: r.get(k) for k in RAW_KEYS} for r in days]
feat_ext.add_levels(_base)          # trailing columns: prefix-safe by construction

def _build(th):
    sub = [dict(r) for r in _base]
    feat_ext.add_causal_index(sub, th)
    feat_ext.add_rolls(sub)
    feat_ext.add_memory(sub)
    return sub

def _idx(sub, causal=True):
    key = "n_haz_t" if causal else "n_haz"
    return np.array([r[key] / 3.0 for r in sub], dtype=float)

def _run(make, h):
    """Walk-forward pass for one arm; `make(s)` returns (X, idx) for the fold at s."""
    nm = len(days)
    Pm, Pp, Y = [], [], []
    for s in FOLDS:
        X, idx = make(s)
        y = np.array([idx[min(nm - 1, i + h)] for i in range(nm)])
        tr = np.arange(0, int(nm * s)); te = np.arange(int(nm * s), min(nm, int(nm * s) + 180))
        lam = M.inner_lambda(X[tr], y[tr])
        w, mu, sd = M.ridge_fit(X[tr], y[tr], lam)
        Pm.append(M.ridge_pred(w, mu, sd, X[te]))
        Pp.append(np.array([idx[max(0, i - 6):i + 1].mean() for i in te]))
        Y.append(y[te])
    Pm = np.concatenate(Pm); Pp = np.concatenate(Pp); Y = np.concatenate(Y)
    lab = (Y > 0).astype(float)
    return dict(model_rmse=round(M.rmse(Pm, Y), 4), pers_rmse=round(M.rmse(Pp, Y), 4),
                model_auc=round(M.auc(Pm, lab), 3), pers_auc=round(M.auc(Pp, lab), 3),
                pos_rate=round(float(lab.mean()), 4))

_KEYS = feat_ext.feature_keys(days)
_X = M.matrix(days, _KEYS)
_IDX_STORE = _idx(days, causal=False)
_IDX_CAUSAL = _idx(days, causal=True)

def _fold_prefix(s):
    sub = _build(feat_ext.causal_thresholds(_base[:int(len(days) * s)]))
    return M.matrix(sub, feat_ext.feature_keys(sub)), _idx(sub)

ARMS = {
    "as_shipped":        (lambda s: (_X, _IDX_STORE),  dict(thresholds={k: round(v, 6) for k, v in CTH.items()},
                                                            target="n_haz（记录口径，含中心化残差）")),
    "causal_target":     (lambda s: (_X, _IDX_CAUSAL), dict(thresholds={k: round(v, 6) for k, v in CTH.items()},
                                                            target="n_haz_t（严格因果口径）")),
    "prefix_thresholds": (_fold_prefix,                dict(thresholds="每一折只用训练前缀重算 p90",
                                                            target="n_haz_t（严格因果口径）")),
}
tp_rows = {}
for arm, (make, meta) in ARMS.items():
    tp_rows[arm] = dict(meta, horizons={h: _run(make, h) for h in HEAD})
    r = tp_rows[arm]["horizons"]
    print("[leak] 阈值/标签口径 %-17s " % arm
          + " | ".join("%dd AUC %.3f 对 %.3f" % (h, r[h]["model_auc"], r[h]["pers_auc"]) for h in HEAD))

# how far the prefix thresholds sit from the record ones, and how many days change hazard count
n = len(days)
tp_th = {("前缀 %.0f%%" % (100 * s)): {k: round(v, 6) for k, v in
                                       feat_ext.causal_thresholds(_base[:int(n * s)]).items()} for s in FOLDS}
_shift = sum(1 for a, b in zip(days, _build(feat_ext.causal_thresholds(_base[:int(n * FOLDS[0])])))
             if a["n_haz_t"] != b["n_haz_t"])
_tp_win = {arm: sum(1 for h in HEAD if tp_rows[arm]["horizons"][h]["model_auc"] > tp_rows[arm]["horizons"][h]["pers_auc"])
           for arm in ARMS}
ok = (dmax < EPS) and not missing_any and not leaked
verdict = "PASS" if ok else "FAIL"
out = dict(task="model inputs are strictly causal (no feature reads day t+1 or later)",
           protocol="rebuild every model column from the raw inputs of the truncated prefix 0..T with the record's causal thresholds, then compare with the stored value",
           n_days=n, feature_count=len(FEATS), causal_thresholds={k: round(v, 6) for k, v in CTH.items()},
           cuts=rows, max_abs_diff=dmax, missing_columns=missing_any,
           analysis_cols_excluded=an_rows, analysis_cols_in_features=leaked,
           analysis_leak_days_last8=bad,
           threshold_and_label_arms=dict(
               protocol="same 4 walk-forward folds (train 55/65/75/85% of the record, test = the next 180 days) and the same ridge + inner-window lambda as pipeline/skill_regression.py; only the threshold calibration and the target definition change",
               horizons=list(HEAD), folds=["%.2f" % s for s in FOLDS],
               arms=tp_rows,
               folds_above_persistence=_tp_win,
               prefix_thresholds=tp_th,
               hazard_days_changed_vs_record_thresholds=_shift,
               note="as_shipped 一列用来验证这次重实现能复现 skill_regression.py 的主表；prefix_thresholds 与 causal_target 两列量化「阈值用的是全记录 p90」与「标签用的是中心化残差」这两条通道各值多少"),
           verdict=verdict)
json.dump(out, open(P("data", "processed", "leakage_audit.json"), "w", encoding="utf-8", newline="\n"), ensure_ascii=False, indent=1)
print("")
print("LEAKAGE AUDIT %s：%d 个模型列在 %d 个截断点全部可由「只用过去数据」复现，最大偏差 %.3e；回顾性分析列最大偏差 %.4f（已排除在模型之外），最后 8 天有 %d 天无法用前缀复现"
      % (verdict, len(FEATS), len(cuts), dmax, max(r["max_abs_diff"] for r in an_rows), bad))
print("  两条通道各自的代价（4 个时效里仍高于持续预报的个数）：as_shipped %d/4，prefix_thresholds %d/4，causal_target %d/4；换成训练前缀阈值后，全记录里有 %d 天的灾害计数会改变"
      % (_tp_win["as_shipped"], _tp_win["prefix_thresholds"], _tp_win["causal_target"], _shift))
if not ok:
    print("  FAIL 细节：missing=%s leaked=%s" % (missing_any, leaked))
    sys.exit(1)
