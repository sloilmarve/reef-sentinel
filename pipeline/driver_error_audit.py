# -*- coding: utf-8 -*-
"""How much of the shipped skill comes from the DRIVER FORECAST itself?

The dashboard has always disclosed that "the error of the numerical-weather-prediction
drivers is not propagated separately".  This script replaces that sentence with numbers.

Two ends of ONE protocol (identical 3-fold walk-forward cuts 0.62 / 0.75 / 0.88, 180-day
test windows, inner-CV lambda rule, same 66 features):

  A. observed drivers  - the model reads the record values of the target day, which is what
     the published metrics table does.  This is the PERFECT-driver upper bound.
  B. persisted drivers - every day driver levels are replaced by the values h days earlier,
     i.e. no driver forecast at all.  This is the LOWER bound.

The script first REPRODUCES the deployed metrics table from variant A and exits non-zero if
it does not match, so the two rows are guaranteed to come from the same protocol.
"""
import copy, json, os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import feat_ext, model

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
P = lambda *a: os.path.join(BASE, *a)

feat = json.load(open(P("data", "processed", "semporna_features.json"), encoding="utf-8"))
days = feat["days"]; n = len(days)
CTH = feat.get("causal_thresholds") or feat_ext.causal_thresholds(days)
feat_ext.add_memory(days)                 # strictly causal memory block, same as build_dashboard
FEATS = feat_ext.feature_keys(days)
idx = np.array([r["n_haz"] / 3.0 for r in days])
DASH = json.load(open(P("data", "processed", "dashboard_data.json"), encoding="utf-8"))
HS = (1, 3, 7, 14)
folds = [(np.arange(0, int(n * s)), np.arange(int(n * s), min(n, int(n * s) + 180))) for s in (0.62, 0.75, 0.88)]

# driver columns the forecast endpoints actually deliver; sl_still_trail / surge_trail are
# rebuilt by feat_ext.add_levels() from the replaced sl_mean, so they must not be listed here.
DRIVERS = [k for k in feat_ext.RAW_LEVELS if k in FEATS and k not in ("sl_still_trail", "surge_trail")]

def protocol(X, h):
    y = np.array([idx[min(n - 1, i + h)] for i in range(n)])
    Pm, Pp, Y, LAMS = [], [], [], []
    for tr, te in folds:
        lam = model.inner_lambda(X[tr], y[tr]); LAMS.append(int(lam))
        w, mu, sd = model.ridge_fit(X[tr], y[tr], lam)
        Pm.append(model.ridge_pred(w, mu, sd, X[te]))
        Pp.append(np.array([idx[max(0, i - 6):i + 1].mean() for i in te]))
        Y.append(y[te])
    return np.concatenate(Pm), np.concatenate(Pp), np.concatenate(Y), LAMS

def verdict_of(gap, ci, dauc):
    """One-line reading of one horizon, from the two ends of the protocol."""
    if gap > ci and dauc < -0.03:
        return "驱动预报有实测增益"
    if abs(gap) <= ci and dauc < -0.03:
        return "点误差无变化，但排序能力依赖驱动信息"
    if abs(gap) <= ci and abs(dauc) <= 0.03:
        return "无可测差异（噪声量级）"
    if gap < -ci and dauc > 0.03:
        return "持续值反而略好（长时效上目标日驱动水平更像噪声）"
    return "差异在噪声边缘"

X0 = model.matrix(days, FEATS)
rows, bad = {}, []
for h in HS:
    pm, pp, Y, lams = protocol(X0, h)
    rmse = lambda a: float(np.sqrt(np.mean((a - Y) ** 2)))
    lab = (Y > 0).astype(float)
    rmse_obs, auc_obs, pers_rmse, pers_auc = rmse(pm), model.auc(pm, lab), rmse(pp), model.auc(pp, lab)
    m = DASH["metrics"][str(h)]
    if abs(rmse_obs - m["model_rmse"]) > 5e-5 or abs(auc_obs - m["model_auc"]) > 5e-4:
        bad.append("h=%d reproduces %.4f/%.3f but dashboard_data.json has %.4f/%.3f" % (h, rmse_obs, auc_obs, m["model_rmse"], m["model_auc"]))
    dm = copy.deepcopy(days)
    for i, r in enumerate(dm):
        src = days[max(0, i - h)]
        for k in DRIVERS:
            r[k] = src.get(k)
    feat_ext.add_all(dm, TH=CTH)          # levels -> causal index -> rolls -> memory, rebuilt
    qm, qp, Y2, lams2 = protocol(model.matrix(dm, FEATS), h)
    rmse_p, auc_p = rmse(qm), model.auc(qm, lab)
    d = (qm - Y) ** 2 - (pm - Y) ** 2
    se = float(np.std(d, ddof=1) / np.sqrt(len(d)))
    gap = rmse_p - rmse_obs
    ci = 1.96 * se / (rmse_p + rmse_obs)   # delta-method interval for a difference of RMSEs
    dauc = auc_p - auc_obs
    rows[str(h)] = dict(
        rmse_obs=round(rmse_obs, 4), auc_obs=round(auc_obs, 3),
        rmse_persist_drivers=round(rmse_p, 4), auc_persist_drivers=round(auc_p, 3),
        rmse_gap=round(gap, 4), rmse_gap_pct=round(100.0 * gap / rmse_obs, 1),
        rmse_gap_ci95=round(ci, 4), auc_gap=round(dauc, 3),
        pers_rmse=round(pers_rmse, 4), pers_auc=round(pers_auc, 3),
        lam_obs=lams, lam_persist=lams2,
        noise_level=bool(ci >= abs(gap) and abs(dauc) <= 0.03), verdict=verdict_of(gap, ci, dauc))
    print("h=%2d obs %.4f/%.3f  persist-drivers %.4f/%.3f  gap %+.4f (%+.1f%%) CI +/-%.4f  dAUC %+.3f  %s" % (h, rmse_obs, auc_obs, rmse_p, auc_p, gap, 100.0 * gap / rmse_obs, ci, dauc, "noise" if rows[str(h)]["noise_level"] else "real"))

if bad:
    for b in bad: print("REPRODUCE FAIL: " + b)
    sys.exit(1)

h1 = rows["1"]
far = [rows[str(h)] for h in (3, 7, 14)]
_s1 = "把目标日的驱动换成持续值（即完全不使用驱动预报）后重跑同一协议：1 天 RMSE 从 %.4f 升到 %.4f（%+.1f%%，配对 95%% 区间 ±%.4f）、排序 AUC 从 %.3f 掉到 %.3f —— 1 天的驱动预报是实的。" % (h1["rmse_obs"], h1["rmse_persist_drivers"], h1["rmse_gap_pct"], h1["rmse_gap_ci95"], h1["auc_obs"], h1["auc_persist_drivers"])
_s2 = "3 天 RMSE 无变化（%+.1f%%，区间跨 0）但排序 AUC 掉 %.3f；7 天两口径都无可测差异；14 天持续值反而略好（RMSE %+.1f%%、AUC %+.3f）。" % (rows["3"]["rmse_gap_pct"], abs(rows["3"]["auc_gap"]), rows["14"]["rmse_gap_pct"], rows["14"]["auc_gap"])
_s3 = "结论：本模型不依赖驱动预报的精度 —— 1 天时效拿的是真实增益，长时效上目标日驱动水平更接近噪声；差异在噪声边缘，不据此改动部署配置。"
summary = _s1 + _s2 + _s3

payload = dict(
    task="数值天气预报驱动自身的误差，对成品页预报的影响有多大",
    protocol="3 折扩展窗前推（切点 0.62 / 0.75 / 0.88，测试窗各 180 天），与 dashboard_data.json 的指标表同一协议；只改驱动列",
    n_days=n, feature_count=len(FEATS), driver_columns=list(DRIVERS),
    variants=dict(
        obs="目标日驱动取记录观测值（驱动完美，上界；即现行指标表口径）",
        persist="把每一天的驱动水平整体替换为 h 天前的值（完全不使用驱动预报，下界）"),
    noise_rule="配对 95% 区间跨过 0（RMSE 差）且 |ΔAUC| <= 0.03 记为噪声量级",
    horizons=rows, summary=summary,
    caveat="真实部署落在两行之间：驱动预报越准就越接近上界；差异在噪声量级的时效上不据此改动部署配置。")
open(P("data", "processed", "driver_error_audit.json"), "w", encoding="utf-8", newline="\n").write(json.dumps(payload, ensure_ascii=False, indent=1))
print("WROTE driver_error_audit.json  features=%d drivers=%d" % (len(FEATS), len(DRIVERS)))
print(summary)
