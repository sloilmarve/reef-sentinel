# -*- coding: utf-8 -*-
"""Which columns the early-warning model reads, and the strictly causal recipe behind them.

Two things this module settles:

1. the model reads the CURRENT-DAY LEVEL of every driver, weather and sea-level
   variable as well as the rolling / memory / seasonal blocks.  A walk-forward
   comparison (same folds, same ridge, regularisation chosen inside each training
   window) showed the levels improve skill at every shipped horizon.  The levels are
   exactly what the Open-Meteo forecast endpoints deliver for the coming days, so
   pipeline/fetch_forecast_drivers.py mirrors the archive variable list and the model
   sees the same columns in training and at inference time.

2. every model-facing column is STRICTLY CAUSAL.  The still-water level is a TRAILING
   25-day mean (window t-24 .. t) and the hazard index the memory features count is
   rebuilt from those trailing columns, so no feature of day t reads day t+1 or later.
   The record still carries its centred non-tidal residual as the RETROSPECTIVE
   ANALYSIS the model is verified against - the standard analysis-vs-forecast split -
   and pipeline/leakage_audit.py proves the separation by rebuilding the feature matrix
   from truncated prefixes and comparing every column value.

pipeline/model.py holds the ridge fit itself and the inner-window lambda search.
"""
import math
from datetime import date

from ssum import ssum   # naive accumulation, see pipeline/ssum.py (3.12 changed sum() semantics)

TRAIL_W = 25          # trailing window (days) behind the still-water level

# current-day level of every variable the historical record carries
RAW_LEVELS = (
    "wh_max", "precipitation_sum", "surge_trail",
    "sst_mean", "sst_max",
    "sl_mean", "sl_max", "sl_min", "sl_range", "sl_still_trail",
    "wp_mean", "ww_mean", "oc_mean",
    "temperature_2m_mean", "wind_speed_10m_max", "wind_gusts_10m_max",
    "relative_humidity_2m_mean",
)

# ---------- strictly causal building blocks (past-only windows) ----------

def pct(vals, p):
    """Record percentile - the thresholds are a definition calibrated on the record."""
    v = sorted(x for x in vals if x is not None)
    return v[min(len(v) - 1, int(round(p * (len(v) - 1))))]

def mean(vals):
    vals = [v for v in vals if v is not None]
    return (ssum(vals) / len(vals)) if vals else None

def add_levels(days):
    """Trailing still-water level and the non-tidal residual built from it."""
    n = len(days)
    for i, r in enumerate(days):
        r["sl_still_trail"] = mean([days[j].get("sl_mean")
                                    for j in range(max(0, i - TRAIL_W + 1), i + 1)])
        r["surge_trail"] = (r["sl_mean"] - r["sl_still_trail"]) \
            if (r.get("sl_mean") is not None and r["sl_still_trail"] is not None) else None
    return days

def causal_thresholds(days, tp=0.90):
    return {k: pct([r.get(k) for r in days], tp)
            for k in ("wh_max", "precipitation_sum", "surge_trail")}

def add_causal_index(days, TH=None, tp=0.90):
    """The three-driver hazard index the MEMORY features count, from causal columns."""
    if TH is None:
        TH = causal_thresholds(days, tp)
    for r in days:
        r["h_wave_t"] = 1 if (r.get("wh_max") or -1) >= TH["wh_max"] else 0
        r["h_rain_t"] = 1 if (r.get("precipitation_sum") or -1) >= TH["precipitation_sum"] else 0
        r["h_surge_t"] = 1 if (r.get("surge_trail") or -1) >= TH["surge_trail"] else 0
        r["n_haz_t"] = r["h_wave_t"] + r["h_rain_t"] + r["h_surge_t"]
        r["compound_t"] = 1 if r["n_haz_t"] >= 2 else 0
    return TH

def roll(days, i, key, w, how="mean"):
    vals = [days[j].get(key) for j in range(max(0, i - w + 1), i + 1)]
    vals = [v for v in vals if v is not None]
    if not vals:
        return None
    return max(vals) if how == "max" else ssum(vals) / len(vals)

def add_rolls(days):
    """Seasonal terms + rolling means / maxima / anomalies, all windows ending at t."""
    for i, r in enumerate(days):
        d0 = date.fromisoformat(r["date"])
        r["doy_sin"] = math.sin(2 * math.pi * d0.timetuple().tm_yday / 365.25)
        r["doy_cos"] = math.cos(2 * math.pi * d0.timetuple().tm_yday / 365.25)
        for key, tag in (("wh_max", "wave"), ("precipitation_sum", "rain"),
                         ("surge_trail", "surge"), ("sst_mean", "sst")):
            for w in (3, 7, 14, 30):
                r["f_%s_%dd_mean" % (tag, w)] = roll(days, i, key, w, "mean")
                r["f_%s_%dd_max" % (tag, w)] = roll(days, i, key, w, "max")
        for tag, key in (("wave", "wh_max"), ("rain", "precipitation_sum"), ("surge", "surge_trail")):
            m30 = roll(days, i, key, 30, "mean")
            r["f_%s_anom30" % tag] = (r.get(key) - m30) if (m30 is not None and r.get(key) is not None) else None
    return days

def add_memory(days):
    """Recent hazard memory, counted from the CAUSAL index (never the analysis one)."""
    for i, r in enumerate(days):
        for tag in ("h_wave", "h_rain", "h_surge"):
            for w in (3, 7, 14):
                r["m_%s_%dd" % (tag, w)] = sum(days[j][tag + "_t"] for j in range(max(0, i - w + 1), i + 1))
        r["m_nhaz_7d"] = sum(days[j]["n_haz_t"] for j in range(max(0, i - 6), i + 1))
        r["m_compound_14d"] = sum(days[j]["compound_t"] for j in range(max(0, i - 13), i + 1))
        r["m_gap"] = next((k for k in range(0, 200) if i - k >= 0 and days[i - k]["compound_t"]), 200)
    return days

def add_all(days, TH=None, tp=0.90):
    """Levels -> causal index -> rolling block -> memory.  Returns the causal thresholds."""
    add_levels(days)
    TH = add_causal_index(days, TH, tp)
    add_rolls(days)
    add_memory(days)
    return TH

def feature_keys(days, min_present=None):
    """Rolling / memory / seasonal features + current-day levels.

    A column qualifies when it is present on at least 95% of the record.  A strict
    "no gaps" rule would silently drop the whole SST block (the marine record starts
    2022-11-23, i.e. 22 days into the window) and the first 24 days of the trailing
    sea-level block - and those are the two columns coral bleaching actually depends on.
    Missing cells are imputed from the training mean inside pipeline/model.py, so a
    late-starting column costs nothing.
    """
    if min_present is None:
        min_present = int(len(days) * 0.95)
    base = [k for k in days[len(days) // 2]
            if k.startswith("f_") or k.startswith("m_") or k.startswith("doy_")]
    keys = base + [k for k in RAW_LEVELS if k in days[len(days) // 2]]
    return [k for k in keys if sum(1 for r in days if r.get(k) is not None) >= min_present]
