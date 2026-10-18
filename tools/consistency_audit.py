# -*- coding: utf-8 -*-
"""材料数字一致性审计（v2）：从 data/processed 的事实产物反推应出现的数字，再回扫文档。

用法： python tools/consistency_audit.py   （退出码 0 = 一致，1 = 有不一致）
v2 变化：按每份文档自己的数字精度核对；过期数字改为上下文感知（"2026-10-14 → 2026-10-15" 这类历史实测表述不算过期）。
"""
import hashlib, json, os, re as _re, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROC = os.path.join(ROOT, "data", "processed")

def load(name):
    with open(os.path.join(PROC, name), encoding="utf-8") as fh:
        return json.load(fh)

dash = load("dashboard_data.json")
feat = load("semporna_features.json")
noaa = load("noaa_crw_panel.json")
ms = load("multisite_transfer.json")
ia = load("interval_audit.json")
lk = load("leakage_audit.json")
span, thr, now = dash["span"], feat["thresholds"], dash["now"]
yl = {str(y["year"]): y for y in dash["yearly"]}

V = {}
V["days"] = "{:,}".format(span["days"])
V["start"] = span["start"]
V["end"] = span["end"]
V["sst_p90"] = "%.3f" % thr["sst"]["p90"]
for h in ("1", "3", "7", "14"):
    m = dash["metrics"][h]
    V["m" + h] = "%.4f" % m["model_rmse"]
    V["p" + h] = "%.4f" % m["pers_rmse"]
    V["c" + h] = "%.4f" % m["clim_rmse"]
    V["d" + h] = "%.1f%%" % ((m["pers_rmse"] - m["model_rmse"]) / m["pers_rmse"] * 100.0)
    V["m" + h + "_3"] = "%.3f" % m["model_rmse"]
for h in ("1", "3", "7", "14"):
    _m = dash["metrics"][h]
    V["auc_m" + h] = "%.3f" % _m["model_auc"]
    V["auc_p" + h] = "%.3f" % _m["pers_auc"]
    V["auc_c" + h] = "%.3f" % _m["clim_auc"]

V["ref_secs"] = "30"
V["video_len"] = "2 分 56 秒"
V["noaa_end"] = "2026-10-13"
V["c2024"] = str(yl["2024"]["compound"])
V["hot2024"] = str(yl["2024"]["hot_days"])
V["hot2025"] = str(yl["2025"]["hot_days"])
V["hot2026"] = str(yl["2026"]["hot_days"])
V["sst2026"] = "%.2f" % yl["2026"]["max_sst"]
rec = max(noaa["annual"], key=lambda a: a.get("global_max", 0.0))
V["noaa_year"] = str(rec["year"])
V["noaa_glob"] = "%.2f%%" % (rec["global_max"] * 100.0)
V["noaa_pac"] = "%.2f%%" % (rec["pacific_max"] * 100.0)
early = [a for a in noaa["annual"] if int(a["year"]) <= 2000]
V["noaa_early"] = "%.2f%%" % (max(a["global_max"] for a in early) * 100.0)
V["noaa_rows"] = "{:,}".format(noaa["n_rows"])
V["ms_days"] = format(ms["sites"][0]["days"], ",")
V["ms_sites"] = str(len(ms["sites"]))
V["ms_auc1_max"] = "%.3f" % max(s["skill"]["1"]["model_auc"] for s in ms["sites"])
V["ms_auc1_palau"] = "%.3f" % [s for s in ms["sites"] if s["slug"] == "palau"][0]["skill"]["1"]["model_auc"]
V["ms_auc3_min"] = "%.3f" % min(s["skill"]["3"]["model_auc"] for s in ms["sites"])
V["ms_bunaken_rmse3"] = "%.4f" % [s for s in ms["sites"] if s["slug"] == "bunaken"][0]["skill"]["3"]["model_rmse"]
V["ms_bunaken_auc3"] = "%.3f" % [s for s in ms["sites"] if s["slug"] == "bunaken"][0]["skill"]["3"]["model_auc"]
for _s in ms["sites"]:
    for _h in ("1", "3", "7", "14"):
        V["ms_pers_" + _s["slug"] + _h] = "%.3f" % _s["skill"][_h]["pers_auc"]
_swc = min(ms["threshold_sweep"], key=lambda c: c["h3"]["model_auc"])
V["sw_low_model"] = "%.3f" % _swc["h3"]["model_auc"]
V["sw_low_pers"] = "%.3f" % _swc["h3"]["pers_auc"]

V["cov_lo"] = "%.1f%%" % min(v["coverage_1sigma"] for v in ia.values())
V["cov_hi"] = "%.1f%%" % max(v["coverage_1sigma"] for v in ia.values())
V["q80_lo"] = "%.2f" % min(v["q80_multiplier"] for v in ia.values())
V["q80_hi"] = "%.2f" % max(v["q80_multiplier"] for v in ia.values())
la = load("lambda_audit.json")
V["cov_surge_days"] = format(sum(1 for _d in feat["days"] if _d.get("sl_mean") is not None), ",")
V["cov_sst_days"] = format(sum(1 for _d in feat["days"] if _d.get("sst_mean") is not None), ",")
V["tie_p90_wh"] = "0.400000"
V["comp_gt"] = "39 天"
_zh = sum(1 for _d in feat["days"] if _d.get("n_haz", 0) == 0)
V["zero_share"] = "%.1f%%" % (_zh * 100.0 / len(feat["days"]))
V["lam5_auc3"] = "%.3f" % la["horizons"]["3"]["per_lam"]["5"]["auc"]
V["lam400_auc3"] = "%.3f" % la["horizons"]["3"]["per_lam"]["400"]["auc"]
V["lam400_rmse14"] = "%.4f" % la["horizons"]["14"]["per_lam"]["400"]["rmse"]
ba = load("blend_audit.json")
for _h in ("1", "3", "7", "14"):
    V["blend_rmse" + _h] = "%.4f" % ba[_h]["blend_rmse"]
    V["blend_gain" + _h] = "%.2f%%" % ba[_h]["gain_vs_flat_pct"]
V["blend_beta1"] = "%.1f" % ba["1"]["beta_star"]
bfc = load("bleach_forecast.json")
V["bf_pr_auc"] = "%.3f" % bfc["metrics"]["model"]["pr_auc"]
V["bf_pr_auc_rule"] = "%.3f" % bfc["metrics"]["rule_baseline"]["pr_auc"]
V["bf_base"] = "%.3f" % bfc["metrics"]["base_rate"]
V["bf_roc"] = "%.3f" % bfc["metrics"]["model"]["roc_auc"]
V["bf_prob"] = "%.3f" % bfc["now"]["prob_mhw_28d"]
V["bf_pos"] = "%.1f%%" % (bfc["label"]["positive_rate"] * 100.0)
bw = load("bleaching_watch.json")
pp = load("priority_plan.json")
V["mhw_events"] = str(len(bw["events"])) + " 次"
V["mhw_anom_p90"] = "%.4f" % bw["baseline"]["anom_p90"]
V["mhw_pctl"] = "%.1f%%" % bw["now"]["percentile"]
V["mhw_tier"] = bw["now"]["tier_txt"]
V["mhw_last_days"] = str(bw["now"]["last_event"]["days"]) + " 天"
V["bw_hot_now"] = str(bw["now"]["hot_days"]) + " 天"
V["bleach_cum"] = "%.3f" % bw["now"]["cum_anom"]
V["pp_heat_semporna"] = "%.3f" % pp["sites"][0]["heat_cum_84d"]
V["mhw_r_year"] = "%.3f" % bw["noaa_check"]["r_year_pearson"]
V["mhw_rho"] = "%.3f" % bw["noaa_check"]["r_year_spearman"]
V["mhw_r_month"] = "%.3f" % bw["noaa_check"]["r_cum_pacific"]
_psc = {s["slug"]: s for s in pp["sites"]}
V["pp_score_semporna"] = "%.4f" % _psc["semporna"]["score"]
V["pp_score_palau"] = "%.4f" % _psc["palau"]["score"]
V["pp_score_bunaken"] = "%.4f" % _psc["bunaken"]["score"]
V["pp_risk_p90"] = "%.3f" % pp["thresholds"]["risk_p90"]
V["pp_w4"] = pp["recovery"]["w4"]
V["pp_w8"] = pp["recovery"]["w8"]
V["pp_windows"] = str(len(pp["windows"])) + " 天"
V["pp_semporna_mhw"] = str(_psc["semporna"]["mhw_events"]) + " 次 / " + str(_psc["semporna"]["mhw_days"]) + " 天"
V["pp_palau_mhw"] = str(_psc["palau"]["mhw_events"]) + " 次 / " + str(_psc["palau"]["mhw_days"]) + " 天"
V["pp_bunaken_mhw"] = str(_psc["bunaken"]["mhw_events"]) + " 次 / " + str(_psc["bunaken"]["mhw_days"]) + " 天"
V["pp_longest"] = max(_psc.values(), key=lambda s: s["strongest"]["days"])["strongest"]["start"]
_evl = bw["noaa_check"]["event_level"]
V["ev_overlap"] = "{:,}".format(_evl["overlap_days"])
V["ev_off90"] = "%.5f" % _evl["noaa_pacific_p90_pct"]
V["ev_hit"] = "%.1f%%" % _evl["event_hit_rate"]
V["ev_lag"] = "%.1f" % _evl["mean_peak_lag_days"]
V["ev_lift"] = "%.2f" % _evl["lift"]
V["sop_n"] = str(len(pp["sop"])) + " 条"
_vsc = bw["noaa_check"]["vs_sabah"]
V["vs_overlap"] = "{:,}".format(_vsc["overlap_days"])
V["vs_hit"] = "%.1f%%" % _vsc["event_hit_rate"]
V["vs_bias"] = "%.3f" % abs(_vsc["sst_bias_station_minus_official"])
V["vs_r"] = "%.3f" % _vsc["r_sst"]
V["vs_dhw"] = "%.2f" % _vsc["latest_dhw"]
V["vs_mmm_off"] = "%.4f" % _vsc["official_mmm"]
V["vs_mmm_st"] = "%.3f" % _vsc["station_mmm"]
V["vs_alertdays"] = "{:,}".format(_vsc["alert_days"]["ge1"])
_vsp = bw["noaa_check"]["vs_sites"]
_pal = [s for s in _vsp if "Palau" in s["site"]][0]
V["vs2_overlap"] = "{:,}".format(_pal["overlap_days"])
V["vs2_bias"] = "%.3f" % abs(_pal["bias_station_minus_official"])
V["vs2_r"] = "%.3f" % _pal["r_sst"]
V["vs2_hot"] = str(_pal["hot_days"])
V["vs2_bg"] = "%.1f%%" % _pal["background_alert_rate"]
ab = load("ablation_audit.json")
_abc = {c["id"]: c["by_h"] for c in ab["configs"]}
V["ab_oldfeat"] = str(ab["features_base"])
V["ab_newfeat"] = str(ab["features_ext"])
for _h in ("1", "3", "7", "14"):
    V["ab_base" + _h] = "%.4f" % _abc["base_lam5"][_h]["rmse"]
    V["ab_gain" + _h] = "%.1f%%" % ((_abc["base_lam5"][_h]["rmse"] - _abc["ext_inner"][_h]["rmse"]) / _abc["base_lam5"][_h]["rmse"] * 100.0)
V["ab_extlam5_14"] = "%.4f" % _abc["ext_lam5"]["14"]["rmse"]
V["ab_baseinner_auc3"] = "%.3f" % _abc["base_inner"]["3"]["auc"]
V["ab_baseinner_auc7"] = "%.3f" % _abc["base_inner"]["7"]["auc"]
rs = load("regression_skill.json")
for _h in ("1", "3", "5", "7"):
    V["rs_m" + _h] = "%.4f" % rs[_h]["model_rmse"]
    V["rs_f" + _h] = "%.4f" % rs[_h]["flat_rmse"]
V["rs_p1"] = "%.4f" % rs["1"]["pers_rmse"]
V["rs_c1"] = "%.4f" % rs["1"]["clim_rmse"]
def _nsum(_xs):
    """朴素逐项累加：审计要独立复算，不共用被审代码（pipeline/ssum.py）。"""
    _t = 0.0
    for _x in _xs:
        _t += float(_x)
    return _t
_lamavg = {k: _nsum(la["horizons"][h]["per_lam"][k]["auc"] for h in ("1", "3", "7", "14")) / 4.0 for k in la["horizons"]["1"]["per_lam"]}
V["lam_avg5"] = "%.3f" % round(_lamavg["5"], 3)
V["lam_avg_peak"] = "%.3f" % round(max(_lamavg.values()), 3)
V["lam_avg_min"] = "%.3f" % round(min(_lamavg.values()), 3)
_sem = [s for s in ms["sites"] if s["slug"] == "semporna"][0]["skill"]
V["ms_sem14_model"] = "%.3f" % _sem["14"]["model_auc"]
V["ms_sem14_pers"] = "%.3f" % _sem["14"]["pers_auc"]
V["ms_gap_min"] = "%.3f" % min(s["skill"][h]["model_auc"] - s["skill"][h]["pers_auc"] for s in ms["sites"] for h in ("1", "3", "7", "14"))
V["lk_feats"] = "%d" % lk["feature_count"]
V["lk_cuts"] = "%d" % len(lk["cuts"])
V["lk_max"] = "%g" % lk["max_abs_diff"]
V["lk_analysis_max"] = "%.3f" % lk["analysis_cols_excluded"][0]["max_abs_diff"]
V["lk_leak_days"] = "%d" % lk["analysis_leak_days_last8"]
V["sop_today_stage"] = pp["today"]["stage"]
V["sop_today_n"] = "%d" % len(pp["today"]["active"])
V["sop_max_upper"] = "%.3f" % pp["today"]["max_upper"]
V["pp_first_window"] = pp["windows"][0]["date"]
V["win_max_upper"] = "%.3f" % max(w["upper"] for w in pp["windows"])
V["win_high_n"] = "%d" % len([w for w in pp["windows"] if w["upper"] > pp["thresholds"]["risk_p95"]])
V["win_high_dates"] = " / ".join(sorted(w["date"] for w in pp["windows"] if w["upper"] > pp["thresholds"]["risk_p95"]))
_de = load("driver_error_audit.json")
V["de_obs1"] = "%.4f" % _de["horizons"]["1"]["rmse_obs"]
V["de_pers1"] = "%.4f" % _de["horizons"]["1"]["rmse_persist_drivers"]
V["de_gap1"] = "%.1f" % _de["horizons"]["1"]["rmse_gap_pct"]
V["de_ci1"] = "%.4f" % _de["horizons"]["1"]["rmse_gap_ci95"]
V["de_auc1"] = "%.3f" % _de["horizons"]["1"]["auc_obs"]
V["de_auc1p"] = "%.3f" % _de["horizons"]["1"]["auc_persist_drivers"]
V["de_auc3g"] = "%.3f" % abs(_de["horizons"]["3"]["auc_gap"])
V["de_gap14"] = "%.1f" % _de["horizons"]["14"]["rmse_gap_pct"]
V["de_auc14g"] = "%.3f" % _de["horizons"]["14"]["auc_gap"]
_iv = load("index_variant_audit.json")
V["iv_n"] = "%d" % (len(_iv["variants"]) * 4)
V["iv_win"] = "%d" % (len(_iv["variants"]) * 4 - len(_iv["flat_or_persistence_losses"]))
V["iv_fails"] = "%d" % len(_iv["flat_or_persistence_losses"])
V["iv_gap_two"] = "%.4f" % _iv["variants"]["two_driver"]["mean_auc_gap"]
V["iv_gap_dep"] = "%.4f" % _iv["variants"]["three_driver"]["mean_auc_gap"]
V["iv_gap_four"] = "%.4f" % _iv["variants"]["four_driver"]["mean_auc_gap"]
V["iv_gap_p85"] = "%.4f" % _iv["variants"]["three_driver_p85"]["mean_auc_gap"]
V["iv_gap_p95"] = "%.4f" % _iv["variants"]["three_driver_p95"]["mean_auc_gap"]
V["iv_zero_two"] = "%.1f%%" % _iv["variants"]["two_driver"]["zero_share_pct"]
V["iv_zero_dep"] = "%.1f%%" % _iv["variants"]["three_driver"]["zero_share_pct"]
V["iv_zero_four"] = "%.1f%%" % _iv["variants"]["four_driver"]["zero_share_pct"]
V["iv_zero_p85"] = "%.1f%%" % _iv["variants"]["three_driver_p85"]["zero_share_pct"]
V["iv_zero_p95"] = "%.1f%%" % _iv["variants"]["three_driver_p95"]["zero_share_pct"]
V["iv_fail_rmse7"] = "%.4f" % _iv["variants"]["two_driver"]["by_h"]["7"]["model_rmse"]
V["iv_fail_flat7"] = "%.4f" % _iv["variants"]["two_driver"]["by_h"]["7"]["flat_rmse"]
V["iv_fail_auc14"] = "%.4f" % _iv["variants"]["two_driver"]["by_h"]["14"]["model_auc"]
V["iv_fail_pers14"] = "%.4f" % _iv["variants"]["two_driver"]["by_h"]["14"]["pers_auc"]
V["iv_fail_p85auc"] = "%.4f" % _iv["variants"]["three_driver_p85"]["by_h"]["14"]["model_auc"]
V["iv_fail_p85pers"] = "%.4f" % _iv["variants"]["three_driver_p85"]["by_h"]["14"]["pers_auc"]
_cp = load("compound_label_audit.json")
V["cp_pos"] = "%d" % _cp["by_h"]["1"]["pos"]
V["cp_base"] = "%.3f" % _cp["by_h"]["1"]["base_rate"]
V["cp_auc1"] = "%.3f" % _cp["by_h"]["1"]["model_auc"]
V["cp_pr1"] = "%.3f" % _cp["by_h"]["1"]["model_pr_auc"]
V["cp_lift1"] = "%.1f" % _cp["by_h"]["1"]["lift_vs_base"]
V["cp_auc7"] = "%.3f" % _cp["by_h"]["7"]["model_auc"]
V["cp_pers7"] = "%.3f" % _cp["by_h"]["7"]["pers_auc"]
V["cp_pr7"] = "%.3f" % _cp["by_h"]["7"]["model_pr_auc"]
V["cp_perspr7"] = "%.3f" % _cp["by_h"]["7"]["pers_pr_auc"]
_s2 = load("s2_hindcast.json")
def _s2u(_h, _i):
    return _s2["by_h"][str(_h)]["upper_bound"][_i]
V["s2_base"] = "%.2f" % _s2["base_rate_pct"]
V["s2_line"] = "%.3f" % _s2["page_line"]
V["s2_h1_n"] = "%d" % _s2u(1, 0)["n_trigger"]
V["s2_h1_hit"] = "%d" % _s2u(1, 0)["hit"]
V["s2_h1_prec"] = "%.1f" % _s2u(1, 0)["precision_pct"]
V["s2_h1_rec"] = "%.1f" % _s2u(1, 0)["recall_pct"]
V["s2_h1_lift"] = "%.2f" % _s2u(1, 0)["lift_vs_base"]
V["s2_lift_lo"] = "%.2f" % min(_s2u(_h, 0)["lift_vs_base"] for _h in range(5, 9))
V["s2_lift_hi"] = "%.2f" % max(_s2u(_h, 0)["lift_vs_base"] for _h in range(5, 9))
V["s2_hi_zero"] = "%d" % len([_h for _h in range(1, 9) if _s2u(_h, 2)["n_trigger"] == 0])
V["s2_hi_prec_lo"] = "%.1f" % min(_s2u(_h, 0)["precision_pct"] for _h in range(1, 9))
V["s2_hi_prec_hi"] = "%.1f" % max(_s2u(_h, 0)["precision_pct"] for _h in range(1, 9))

_fb = load("engagement_report.json")
_flog = load("engagement_log.json")
def _fb_monday(_s):
    import datetime as _dt
    _y, _m, _d = [int(_x) for _x in str(_s).strip().split("-")]
    _dd = _dt.date(_y, _m, _d)
    return _dd - _dt.timedelta(days=_dd.isoweekday() - 1)
def _fb_recheck(_lg):
    """审计不复用被审代码：自己按 ISO 周重算 S3 的连续周数与 S4 的完整事件数，再与结算产物比。"""
    _per = {}
    for _r in _lg.get("s3", []):
        _per.setdefault(str(_r.get("org", "")).strip(), set()).add(_fb_monday(_r.get("date")))
    _best = 0
    for _org, _ds in _per.items():
        _ws = sorted(_ds)
        _run = 1 if _ws else 0
        _mx = 1 if _ws else 0
        for _a, _b in zip(_ws, _ws[1:]):
            _run = _run + 1 if (_b - _a).days == 7 else 1
            _mx = max(_mx, _run)
        _best = max(_best, _mx)
    _n4 = len([_r for _r in _lg.get("s4", [])
               if str(_r.get("change", "")).strip() and str(_r.get("basis", "")).strip()
               and str(_r.get("outcome", "")).strip()])
    _tol = [_r.get("tolerance") for _r in _lg.get("s5", []) if isinstance(_r.get("tolerance"), int)]
    _obs = [_r.get("false_alarms") for _r in _lg.get("s5", []) if isinstance(_r.get("false_alarms"), int)]
    return _best, _n4, (max(_tol) if _tol else None), (max(_obs) if _obs else None)
_fb_rc = _fb_recheck(_flog)
V["fb_verdict"] = _fb["verdict"]
V["fb_s3_best"] = "%d" % _fb["s3"]["best_run"]
V["fb_s3_orgs"] = "%d" % _fb["s3"]["n_orgs"]
V["fb_s3_need"] = "%d" % _fb["s3"]["need_weeks"]
V["fb_s4_n"] = "%d" % _fb["s4"]["n"]
V["fb_s4_need"] = "%d" % _fb["s4"]["need"]
V["fb_s5_verdict"] = _fb["s5"]["verdict"]
V["py_env"] = "3.10"   # 实际锁定的解释器（云端 workflow 与本地实测一致）
# ---- 第 68 轮补：区域虚拟站点 CSV 由审计独立重算（评审第 3 / 6 条），以及 README 步骤次序检查 ----
def _vs_recalc(rel):
    _mx = 0.0; _n = 0; _a = 0
    for _ln in open(os.path.join(ROOT, rel), encoding="utf-8", errors="replace").read().split(chr(10)):
        _c = _ln.split(",")
        if len(_c) < 8 or not _c[0].startswith("20"):
            continue
        _n += 1
        _mx = max(_mx, float(_c[6]))
        _a += 1 if int(float(_c[7])) >= 1 else 0
    return _mx, _n, _a
_vs1 = _vs_recalc("data/external/noaa_crw/vs_sabah_daily.csv")
_vs2 = _vs_recalc("data/external/noaa_crw/vs_palau_daily.csv")
V["vs_maxdhw"] = "%.2f" % _vs1[0]
V["vs2_dhw"] = "%.2f" % _vs2[0]
V["vs_alert_share"] = "%.1f" % (100.0 * _vs1[2] / _vs1[1])
V["page_kb"] = "%.1f" % (os.path.getsize(os.path.join(ROOT, "demo", "index.html")) / 1024.0)
_rd_txt = open(os.path.join(ROOT, "README.md"), encoding="utf-8").read()
_rdp = lambda sub: _rd_txt.find(sub)
# ---- 第 69 轮补：独立评审（53cd528f）9 条缺陷的审计针：模型输入构成 / 累计强度 / 取等号天数 / 链条步数 / 三站点热暴露 ----
_feat_days = json.load(open(os.path.join(ROOT, "data", "processed", "semporna_features.json"), encoding="utf-8"))["days"]
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
import feat_ext as _fex
sys.path.insert(0, os.path.join(ROOT, "tools"))
import page_audit as _pa
import media_audit as _ma
import cost_model as _cm
import plan_audit as _pla
import market_model as _mk
import outreach_audit as _oa
import script_audit as _sa
import license_audit as _la
import narration_audit as _na
import derived_audit as _da
import snapshot_audit as _sna
import portability_audit as _ptb
import refs_audit as _ra
import deploy_audit as _dep
import a11y_audit as _a11y
import social_audit as _soc
import push_audit as _pu
import qa_audit as _qa
_fk = _fex.feature_keys(_feat_days)
V["fk_total"] = "%d" % len(_fk)
V["fk_wave"] = "%d" % len([k for k in _fk if k.startswith("f_wave")])
V["fk_rain"] = "%d" % len([k for k in _fk if k.startswith("f_rain")])
V["fk_surge"] = "%d" % len([k for k in _fk if k.startswith("f_surge")])
V["fk_sst"] = "%d" % len([k for k in _fk if k.startswith("f_sst")])
V["raw_levels"] = "%d" % len(_fex.RAW_LEVELS)
V["raw_centred"] = "%d" % len([k for k in ("surge", "sl_still", "sl_anom") if k in _fex.RAW_LEVELS])
_sg_col = [d["surge_trail"] for d in _feat_days if d.get("surge_trail") is not None]
_sst_col = [d["sst_mean"] for d in _feat_days if d.get("sst_mean") is not None]
V["tie_surge"] = "%d" % len([x for x in _sg_col if x == _fex.pct(_sg_col, 0.90)])
V["tie_sst"] = "%d" % len([x for x in _sst_col if x == _fex.pct(_sst_col, 0.90)])
V["bleach_cum_max"] = "%.4f" % max(e["cum_intensity"] for e in bw["events"])
V["bleach_cum_pp"] = "%.4f" % pp["sites"][0]["strongest"]["cum_intensity"]
_pd = {s["slug"]: s for s in pp["sites"]}
V["pp_heat_palau"] = "%.3f" % _pd["palau"]["heat_cum_84d"]
V["pp_heat_bunaken"] = "%.3f" % _pd["bunaken"]["heat_cum_84d"]
_ref = open(os.path.join(ROOT, "pipeline", "refresh.py"), encoding="utf-8").read()
_ref_blk = _ref.split("STEPS = [", 1)[1].split(chr(10) + "]", 1)[0]
_ref_lines = [l for l in _ref_blk.splitlines() if l.strip().startswith("(")]
V["refresh_steps"] = "%d" % len(_ref_lines)
V["lam_step"] = "%d" % ([i for i, l in enumerate(_ref_lines, 1) if "lambda_audit" in l] or [0])[0]

EXPECT = [
    ("docs/01_项目说明.md", [V["days"] + " 天", V["sst_p90"], V["m1_3"], V["m3_3"], V["m7_3"], V["m14_3"],
                              V["d1"], V["d7"], V["end"], V["ref_secs"], V["c2024"], V["sst2026"],
                              V["noaa_glob"], V["noaa_pac"], V["noaa_rows"], V["ms_days"], V["ms_sites"],
                              V["cov_lo"], V["cov_hi"], V["q80_lo"], V["q80_hi"],
                              V["mhw_events"], V["mhw_pctl"], V["mhw_rho"], V["pp_score_semporna"],
                               V["bf_pr_auc"], V["bf_pr_auc_rule"], V["bf_base"], V["vs_hit"], V["vs_bias"], V["vs_r"], V["vs2_bias"], V["vs2_r"], V["sop_n"], V["hot2025"], V["hot2026"], V["zero_share"], "严格只用当日及以前", "66 个特征", V["auc_p1"], V["auc_p3"], V["auc_p7"], V["auc_p14"], V["auc_c1"], V["auc_c3"], V["auc_c7"], V["auc_c14"], V["de_pers1"], V["de_ci1"], V["de_auc1p"], V["de_auc14g"], V["vs_alert_share"] + "%", "样本过小"]),
    ("docs/02_数据与AI说明.md", [V["days"], V["start"], V["end"], V["sst_p90"], V["m1"], V["p1"], V["m3"], V["p3"],
                                  V["m7"], V["p7"], V["m14"], V["p14"], V["noaa_glob"],
                                  V["ms_days"], V["ms_auc1_max"], V["ms_auc1_palau"], V["ms_auc3_min"], V["ms_bunaken_rmse3"], V["ms_bunaken_auc3"],
                                  V["cov_lo"], V["cov_hi"], V["q80_lo"], V["q80_hi"],
                                  V["cov_surge_days"], V["cov_sst_days"], V["tie_p90_wh"], V["comp_gt"], V["cp_pos"], V["cp_base"], V["cp_auc7"], V["cp_pers7"], V["cp_pr7"], V["cp_perspr7"],
                                  V["lam5_auc3"], V["lam400_auc3"], V["lam400_rmse14"],
                                  V["blend_rmse1"], V["blend_rmse3"], V["blend_rmse7"], V["blend_rmse14"], V["blend_beta1"], V["blend_gain1"], V["blend_gain14"],
                                  V["bf_pr_auc"], V["bf_pr_auc_rule"], V["bf_base"], V["bf_roc"], V["bf_prob"], V["bf_pos"],
                                  V["ab_base1"], V["ab_base3"], V["ab_base7"], V["ab_base14"],
                                  V["ab_extlam5_14"], V["ab_baseinner_auc3"], V["ab_baseinner_auc7"],
                                  V["ab_gain1"], V["ab_gain3"], V["ab_gain7"], V["ab_gain14"],
                                  V["mhw_events"], V["mhw_anom_p90"], V["mhw_pctl"], V["mhw_tier"], V["mhw_last_days"],
                                  V["mhw_r_year"], V["mhw_rho"], V["mhw_r_month"],
                                  V["pp_score_semporna"], V["pp_score_palau"], V["pp_score_bunaken"],
                                  V["pp_risk_p90"], V["pp_w4"], V["pp_w8"], V["pp_windows"],
                                   V["pp_semporna_mhw"], V["pp_palau_mhw"], V["pp_bunaken_mhw"], V["pp_longest"], V["ev_overlap"], V["ev_off90"], V["ev_hit"], V["ev_lag"], V["ev_lift"], V["sop_n"],
                                   V["vs_overlap"], V["vs_bias"], V["vs_r"], V["vs2_bias"], V["vs2_r"], V["vs_dhw"], V["vs_mmm_off"], V["vs_mmm_st"], V["vs_alertdays"], V["bw_hot_now"], V["zero_share"],
                                    "无前视泄漏", "surge_trail", "sl_still_trail", "事后分析量", "最大偏差 0.011", "66 个特征", "leakage_audit.py", "今天适用", "两条轴", V["bleach_cum"], V["pp_heat_semporna"], V["pp_first_window"], "按上界升序排", "80% 经验半宽", V["auc_p1"], V["auc_p3"], V["auc_p7"], V["auc_p14"], V["auc_c1"], V["auc_c3"], V["auc_c7"], V["auc_c14"], V["ms_pers_semporna1"], V["ms_pers_semporna3"], V["ms_pers_semporna7"], V["ms_pers_semporna14"], V["ms_pers_bunaken1"], V["ms_pers_bunaken3"], V["ms_pers_bunaken7"], V["ms_pers_bunaken14"], V["ms_pers_palau1"], V["ms_pers_palau3"], V["ms_pers_palau7"], V["ms_pers_palau14"], V["sw_low_model"], V["sw_low_pers"], V["de_gap1"], V["de_ci1"], V["de_auc3g"], V["de_auc14g"], V["iv_win"] + " 格", V["iv_fails"] + " 格", "20 个（定义 × 时效）格", V["iv_gap_two"], V["iv_gap_dep"], V["iv_gap_four"], V["iv_gap_p85"], V["iv_gap_p95"], V["iv_zero_two"], V["iv_zero_dep"], V["iv_zero_four"], V["iv_zero_p85"], V["iv_zero_p95"], V["iv_fail_rmse7"], V["iv_fail_flat7"], V["iv_fail_auc14"], V["iv_fail_pers14"], V["iv_fail_p85auc"], V["iv_fail_p85pers"], "index_variant_audit.py", "1.0%–7.6%", V["s2_base"] + "%", V["s2_h1_lift"] + " 倍", V["s2_h1_rec"] + "%", "0.49–1.55 倍", "低于背景率", "s2_hindcast.py", "settle_forecast.py", "priority_plan.json", "risk_p95", "pending", "tools/feedback_log.py", "engagement_log.json", "engagement_report.json", "S3 / S4 / S5", "两个结算器自检", "pipeline/ssum.py", "朴素累加器", "Python 3.10", "主表配置／报告口径", "1.0 从未出现", "在每日链条里", "抓未来 14 天", "1,421 天 =", "仅 4 个年份", "训练前缀重算"]),
    ("docs/03_90天验证计划.md", [V["rs_m1"], V["rs_p1"], V["rs_c1"], V["rs_f1"], V["rs_m3"], V["rs_m5"], V["rs_m7"],
                                  V["rs_f3"], V["rs_f5"], V["rs_f7"], V["blend_rmse1"], V["blend_rmse3"], V["blend_rmse7"], V["blend_rmse14"], V["blend_beta1"],
                                  V["lam_avg5"], V["lam_avg_peak"], V["lam_avg_min"], V["cov_lo"], V["cov_hi"], V["q80_lo"], V["q80_hi"],
                                  V["ms_sem14_model"], V["ms_sem14_pers"], V["ms_gap_min"],
                                  V["ab_base1"], V["ab_base3"], V["ab_base7"], V["ab_base14"], V["ab_extlam5_14"],
                                  V["ab_baseinner_auc3"], V["ab_baseinner_auc7"], V["ab_gain1"], V["ab_gain3"], V["ab_gain7"], V["ab_gain14"],
                                  V["vs2_r"], "特征无前视泄漏", "leakage_audit.py", "66 个特征", "事后分析量", "截断", "今天适用", "危险指数轴与热压力轴",
                                   V["m1"], V["m3"], V["m7"], V["m14"], "1.0%–7.6%", V["s2_h1_n"] + " 次触发", V["s2_h1_hit"] + " /", V["s2_h1_prec"] + "%", V["s2_h1_rec"] + "%", V["s2_h1_lift"] + " 倍", V["s2_base"] + "%", "已撤回", "2.07–3.68 倍", "0.49–1.55 倍", "低于背景率", "priority_plan.json", "risk_p95", "s2_hindcast.py", "feedback_log.py", "engagement_log.json", "engagement_report.json", "--add-s3", "--add-s4", "--add-s5", "ISO 周", "实际误报 ≤ 门槛", "连续 4 周", "--selftest", "Python 3.10", "pipeline/ssum.py", V["vs2_dhw"], V["vs_alert_share"] + "%", "仅 4 个年份", "主表配置", "部署口径", "0.1402 / 0.1588 / 0.1635 / 0.1663"]),
    ("docs/04_演示视频逐字稿与分镜.md", ["02:56", "8 个镜头", V["sop_n"], "8 天预报", "第九十二点二百分位", "百分之二十点八到百分之八点九"]),
    ("docs/05_报名表与提交清单.md", [V["days"], V["start"], V["d1"], V["d3"], V["d7"], V["d14"], V["noaa_glob"], V["noaa_pac"], V["zero_share"], "仅 4 个年份", "低于背景率", "02:56", V["auc_p1"], V["auc_p3"], V["auc_p7"], V["auc_p14"], V["auc_c1"], V["auc_c3"], V["auc_c7"], V["auc_c14"]]),
    ("docs/06_作品帖与发布草稿.md", [V["days"], V["d1"], V["d3"], V["d7"], V["d14"], V["m3"], V["m7"], V["m14"],
                                    V["comp_gt"], V["c2024"], V["ref_secs"], V["noaa_glob"], V["noaa_pac"], V["noaa_early"], V["noaa_rows"],
                                    V["bf_pr_auc"], V["bf_pr_auc_rule"], V["bf_base"], V["vs_hit"], V["vs_bias"], V["vs_r"], V["zero_share"], V["auc_p1"], V["auc_p3"], V["auc_p7"], V["auc_p14"], V["vs_alert_share"] + "%", "方向一致"]),
    ("README.md", [V["days"], V["sst_p90"], V["m1"], V["m7"], V["d1"], V["end"], V["ref_secs"], V["ms_days"], V["ms_auc1_max"], V["cov_lo"], V["cov_hi"], V["lam400_rmse14"], V["lam400_auc3"], V["blend_rmse1"], V["blend_gain1"], V["blend_gain14"], V["bf_pr_auc"], V["bf_pr_auc_rule"], V["mhw_events"], V["mhw_pctl"], V["pp_score_semporna"], V["pp_palau_mhw"], V["pp_longest"], V["ev_hit"], V["ev_lift"], V["sop_n"], V["vs_overlap"], V["vs_bias"], V["vs_r"], V["vs2_bias"], V["vs2_r"], V["vs_dhw"], V["zero_share"], V["auc_p1"], V["auc_p3"], V["auc_p7"], V["auc_p14"], V["auc_c1"], V["auc_c3"], V["auc_c7"], V["auc_c14"], V["ms_pers_semporna1"], V["ms_pers_semporna3"], V["ms_pers_semporna7"], V["ms_pers_semporna14"], V["ms_pers_bunaken1"], V["ms_pers_bunaken3"], V["ms_pers_bunaken7"], V["ms_pers_bunaken14"], V["ms_pers_palau1"], V["ms_pers_palau3"], V["ms_pers_palau7"], V["ms_pers_palau14"], "Python 3.10", "pipeline/ssum.py", "评审视角复算", "reviewer_repro.py", V["vs_alert_share"] + "%", "报告口径", "部署口径", "4 折", "02:56", "HORIZON = 8", "不可直接互比"]),
    ("00_提交包说明.md", [V["days"], V["m1"], V["m7"], V["p1"], V["ms_days"], V["ms_auc1_max"], V["cov_lo"], V["cov_hi"], V["q80_lo"], V["q80_hi"], V["lam400_rmse14"], V["blend_rmse1"], V["blend_gain1"], V["bf_pr_auc"], V["bf_pr_auc_rule"], V["mhw_events"], V["pp_score_semporna"], V["pp_w4"], V["pp_palau_mhw"], V["ev_hit"], V["ev_lift"], V["vs_overlap"], V["vs_bias"], V["vs_r"], V["vs2_bias"], V["vs2_r"], V["vs_dhw"], V["vs_mmm_off"], V["zero_share"], V["video_len"], "评审视角复算", "逐字节比对", V["vs_alert_share"] + "%", "报告口径的主表配置", "部署口径", "不构成独立验证", V["auc_p1"], V["auc_p3"], V["auc_p7"], V["auc_p14"], V["auc_c1"], V["auc_c3"], V["auc_c7"], V["auc_c14"]]),
    ("docs/01_项目说明.md", ["25 步"]),
    ("docs/02_数据与AI说明.md", ["同样进入模型", "增水的滚动统计", "f_surge_anom30", V["bleach_cum_max"], "增水与海温各 2 天", "refresh.py 第 10 步", V["pp_heat_palau"], V["pp_heat_bunaken"], "3 天（0.1600）低于常数均值", "训练前缀重算", "threshold_and_label_arms"]),
    ("docs/03_90天验证计划.md", ["5 天与基线基本打平", "显著高于 82.3% 的背景预警率", "也低 0.0007（噪声量级）"]),
    ("README.md", ["driver_error_audit.py", "index_variant_audit.py", "compound_label_audit.py", "# 16) 三项补充审计", "# 18) 全量核验"]),
]

STALE = {"排序 AUC 全部高于持续预报": "错误的全胜宣言（跨站点 12 格里仙本那 14 天落败，页与文档都不得再出现）", "0.540 对 0.578": "旧的跨站点 14 天叙事（现按数据现算为 0.580 对 0.584）", "0.288": "旧窗口上界最高值（应为 0.351，随数据变）", "1444": "旧记录期天数", "30.654": "旧海温 p90", "按时效放大": "旧的区间叙事（区间倍数逐时效标定，并不随时效单调变宽）", "30.65 °C": "旧海温 p90（应为 30.667）", "72.8%": "旧 0 值占比", "实测约 6 秒": "旧刷新耗时", "1,411": "旧逐日海温天数（应为 1,412）", "7.5 秒": "旧刷新耗时（应为约 30 秒）", "（至 10-15）": "旧年度表头（记录期已到 10-16）", "0.1461": "旧 1 天模型 RMSE（应为 0.1406）", "0.1550": "旧消融基础配置 RMSE", "0.1744": "旧消融基础配置 RMSE", "0.1719": "旧消融基础配置 RMSE", "0.1717": "旧消融基础配置 RMSE", "0.1695": "旧 λ=5 的 3 天 RMSE", "0.1726": "旧 λ=5 的 14 天 RMSE", "0.1456": "旧 λ=400 的 1 天 RMSE", "0.1601": "旧 λ=400 的 7 天 RMSE", "0.1632": "旧 λ=400 的 14 天 RMSE", "0.477": "旧 9 格最低 AUC", "58 个特征": "旧特征数（应为 66）", "58 features": "旧特征数（英文版，应为 66）", "0.587 / 0.429 / 0.433 / 0.583": "旧持续预报 AUC（现为 0.585 / 0.438 / 0.437 / 0.583）", "0.443 / 0.439 / 0.441 / 0.461": "旧气候平均 AUC（现为 0.457 / 0.453 / 0.457 / 0.474）", "0.600 / 0.627 / 0.621": "旧跨站点持续预报 AUC 序列（现为 0.592 / 0.624 / 0.616）", "0.777/0.635/0.634/0.613": "旧英文版 AUC 序列（现为 0.795/0.665/0.600/0.615）", "0.558 对 0.404": "旧 9 格最低 AUC 对比（现为 0.558 对 0.411）", "40 特征": "旧特征数（应为 49 / 66）", "1,403": "旧跨站点天数（应为 1,404）", "0.9550": "旧保护优先级得分（应为 0.9604）", "1,405": "旧海平面覆盖天数（应为 1,406）", "0.550 对 0.410": "旧 9 格最低 AUC 对比（应为 0.558 对 0.404）", "0.818": "旧 1 天分类器 AUC（应为 0.819）", "0.843": "旧 3 天持续预报 AUC（应为 0.840）", "0.902": "旧 7 天持续预报 AUC（应为 0.900）", "0.947": "旧 14 天持续预报 AUC（应为 0.945）", "0.776 / 0.800 / 0.744": "旧跨站点 1 天 AUC（应为 0.779 / 0.801 / 0.742）", "12 格全部高于": "旧跨站点全胜表述（现为 11/12）", "12 of 12 cells": "旧跨站点全胜表述（现为 11 of 12）", "只赢 0.011": "旧窄优势表述（现为低 0.004）", "18.218": "旧 84 天累计热异常（主记录现为 18.222，三站点表为 18.221）", "驱动自身的误差未单独传播": "旧的纯文字披露（现已量化：1 天 +9.9%、3 天排序 AUC 掉 0.081、14 天持续值略好 −1.9%）", "削弱增水驱动": "旧的错误解释（p85 变体并未去掉增水，只是阈值下移）", "数值天气预报驱动本身的误差没有单独传播": "旧的纯文字披露（见 docs/02 第 3.6.1 节，已量化）","0.1619 / 0.1624": "旧的 λ=1600 十四天 RMSE（实为 0.1611，0.1624 属 λ=400）", "0.1631 对 0.1637": "旧括号里混进 λ 网格与收缩口径的数字（应为主表 0.1603 对 0.1637）", "0.1613 对 0.1635": "旧括号里混进收缩后 RMSE（应为主表 0.1624 对 0.1635）", "0.1624 对 0.1638": "旧括号里混进主表 7 天值（应为 0.1615 对 0.1638）", "0.0034 / 0.0011 / 0.0023": "旧的常数均值差（满幅口径应为 0.0035 / 0.0011 / 0.0024）", "0.0034/0.0011/0.0023": "同上（英文材料里的写法）", "低 0.0011–0.0034": "旧的差值区间（应为低 0.0011–0.0035）", "only 0.0011–0.0034": "同上（英文材料里的写法）", "14.4%（0.1406 对 0.1644）": "旧的一日满幅口径百分比（1 − 0.1406 / 0.1644 = 14.46%，应写 14.5%；第 36 轮由 tools/derived_audit.py 复算抓到）", "实测约 30 秒": "旧的整链耗时表述（已统一为两次实测 37 秒 / 143 秒）", "30 到 45 秒": "旧的整链耗时表述（本机两次实测 37 秒与 143 秒，差异几乎全来自上游 API 响应）", "实际出现复合灾害的比例 ≥ 50%": "旧的 S2 判据（已撤回：2/3 高档线 8 个时效触发 0 次，1/3 线精确率仅 1.2%–7.6%）", "上界达到高危险档而实际成灾": "旧的 S2 措辞（已改为 p95 触发线 + 提升倍数 / 召回率）", "结算（RMSE / 区间覆盖率 / S2 命中率）": "旧的结算器说明（现为精确率 / 召回率 / 提升倍数 + s2_verdict）", "HIGH = 2.0 / 3.0": "旧的写死高档线（现读 priority_plan.json 的 risk_p95）", "Python 3.12 + numpy": "旧的解释器版本表述（本项目锁 Python 3.10，与云端 workflow 一致）", "第九十二点一百分位": "旧的档位数字（应为 92.2%）", "百分之十二点八到百分之五": "旧的降幅数字（应为 20.8% 到 8.9%）", "约 687 KB": "旧的成品页体积（实测约 0.7 MB）", "不在每日链条里": "旧的 lambda_audit.py 描述（它在 refresh.py 的链条里）", "抓未来 10 天": "旧的抓取窗口（实为 14 天，只用前 8 天）", "2:50": "旧的视频时长（统一为 02:56）", "最受鼓舞的一次交叉验证": "旧的过度宣称（2024 只是方向一致，不构成独立验证）", "两条独立来源指向同一年": "旧的过度宣称（2025 紧随其后，量纲也不同）", "部署配置四个时效": "旧的口径混用（那行是报告口径的主表配置）", "内窗 CV 选 λ（部署）": "旧的口径混用（该配置是主表配置／报告口径）", "当前部署配置在": "旧的口径混用（报告口径的主表配置）", "与 NOAA 官方的年际排序完全一致": "旧的过度宣称（只有 4 个年份，样本过小）", "与 NOAA 官方年际排序完全一致": "旧的过度宣称（只有 4 个年份，样本过小）"}
STALE.update({
    "8.1795": "旧的最强热浪累计强度（bleaching_watch.json 实为 8.1793）",
    "增水 0 天，海温 1 天": "旧的取等号天数（按未舍入分位数复算为增水 2 / 海温 2）",
    "被名字显式排除": "旧的 f_surge 特征描述（代码实际含 f_surge 9 个）",
    "当日原始变量水平 | 18": "旧的原始水平个数（RAW_LEVELS 实为 17）",
    "其中 10 步": "旧的 refresh 链步数（实为 25 步）",
    "第 23 步": "旧的 lambda_audit 步号（实为第 10 步）",
    "全部高于常数均值基线": "旧的错误结论（λ=5 的 3 天 0.1600 低于常数均值 0.1637）",
    "都高于常数均值 0.1637": "旧的错误结论（3 天 0.1630 低于 0.1637）",
    "5 天与 7 天反而略高于常数均值": "旧的 4 折表述（5 天 0.1716 对 0.1718 打平）",
    "≥ 10/13": "旧的 S6 判据（低于 82.3% 背景率下的随机期望 10.7/13）",
    "| 2 | 帕劳岩岛 Palau Rock Islands | 0.046 |": "旧的三站点热暴露（应为 0.050）",
    "| 3 | Bunaken | 0.702 |": "旧的三站点热暴露（应为 0.701）",
    "常数均值基线在三天以上更强": "旧的演示旁白（主表四个时效的 RMSE 都低于常数均值基线）",
    "优势只有千分之一量级": "旧口径混淆（千分之几是收缩校准相对满幅预报的增益，不是相对常数均值）",
    "无需额外调度": "旧的与 SOP 表冲突的首屏建议（热压力轴今天有动作适用）",
    "关注周报即可": "旧的与 SOP 表冲突的受众建议（度假村 / 政府）",
    "与 NOAA 完全一致": "过强的年际排序表述（4 个年份含 1 个部分年，样本太小）",
    "弃用了分类器": "过强的弃用表述（弃用的是未来 7 天复合灾害分类器；白化仍在用 28 天二元概率模型）",
    "1 到 4 天达标": "旧的 S2 回溯表述（1–4 天提升倍数达标，但召回只有 1 天档 90.9% 越线）",
    "30.655": "旧的海温 p90 快照（model_report.json 实存 30.654）",
    "无 JavaScript": "绝对化声明（页面内置一小段脚本：导航高亮 / 日期读出 / 折叠展开；统一写「禁用或无需 JavaScript 也能读全部数字」）",
    "约 6 到 8 次请求": "手写的上游请求数（现由 tools/cost_model.py 从代码结构数出：3 站 × 2 接口 + 本站 3 + 未来驱动 2 + NOAA 对照 2 = 13 次/天）",
    "30 到 90 分钟/月": "手写的 Actions 用量（现按本机实测的 37 秒 / 143 秒算为 18 到 72 分钟/月）",
    "30 to 45 seconds": "旧的英文整链耗时表述（现为 37 to 143 seconds，差异几乎全来自上游 API 响应；英文材料与成品页英文摘要都不得再出现）",
    "112 个表头": "旧的表头计数（成品页现有 95 个 <th>，全部带 scope；由包内 tools/page_audit.py 逐项复核）",
    "1.2% 到 7.6%": "旧的精确率区间（现由 pipeline/s2_hindcast.py 从 by_h 现算为 1.0% 到 7.6%）",
    "0.795 / 0.665 / 0.600 / 0.615": "旧的主表四时效排序 AUC（现算 0.796 / 0.665 / 0.600 / 0.615；0.795 只属于消融表 ext_lam5 行）",
    "1,402 天": "旧的帕劳官方站点重叠期（bleaching_watch.json 现算 1,403 天）",
})
# 成品页也要扫过期数字（第 58 轮补：1,403 / 72.8% / 0.658 这一类漏网正是从「只扫文档」逃掉的）。
# 例外：30.654 是三站点数据集（1,404 天）里仙本那自己的海温 p90，与主记录（1,446 天）的 30.667 是两个口径，页面上并列出现是正确行为。
STALE_PAGE = {k: v for k, v in STALE.items() if k != "30.654"}
CTX_OK = ("→", "前移", "实测", "历史", "区域站点", "official station")

fails = []
print("=== 事实（%d 项）===" % len(V))
for k, v in V.items():
    print("  %-10s %s" % (k, v))
print()
print("=== 文档数字核对 ===")
for rel, lits in EXPECT:
    path = os.path.join(ROOT, rel)
    if not os.path.exists(path):
        path = os.path.join(os.path.dirname(ROOT), rel)  # 解压后：00_提交包说明.md 在 ai4climate/ 的上一层
    if not os.path.exists(path):
        fails.append(rel + " 不存在")
        print("  MISS " + rel)
        continue
    text = open(path, encoding="utf-8").read()
    miss = [x for x in lits if x not in text]
    if miss:
        fails.append("%s 缺少 %s" % (rel, " / ".join(miss)))
        print("  FAIL %-26s 缺少: %s" % (rel, " / ".join(miss)))
    else:
        print("  OK   %-26s %d 项齐" % (rel, len(lits)))
print()
print("=== 代码常量 ↔ 文档表述（防“文档说的 ≠ 代码做的”）===")
def readp(rel):
    p = os.path.join(ROOT, rel)
    if not os.path.exists(p):
        p = os.path.join(os.path.dirname(ROOT), rel)  # 解压后顶层那份 00_提交包说明.md
    return open(p, encoding="utf-8").read()
bf = readp("pipeline/build_features.py")
bd = readp("pipeline/build_dashboard.py")
d2txt = readp("docs/02_数据与AI说明.md")
pf = readp("tools/paper_forecast.py")
r3txt = readp("pipeline/refresh.py")
d3txt = readp("docs/03_90天验证计划.md")
d4txt = readp("docs/04_演示视频逐字稿与分镜.md")
dash_end = dash["span"]["end"]
arch_brief = os.path.exists(os.path.join(ROOT, "data", "processed", "archive", "daily_brief_" + dash_end + ".txt"))
fe = readp("pipeline/feat_ext.py")
bst = readp("pipeline/build_static.py")
_site_path = os.path.join(ROOT, "site.json")
_site = {}
if os.path.exists(_site_path):
    try:
        _site = json.load(open(_site_path, encoding="utf-8"))
    except Exception:
        _site = {}
_su = str(_site.get("site_url", "")).strip()
_demo_html = readp("demo/index.html")
# 成品页可核对事实（与包内 tools/page_audit.py 用同一套断言，评委可离线复算）
_pa_facts, _pa_bad = _pa.audit(_demo_html)
# 演示视频可核对事实（纯标准库解析 MP4；视频不在解压后的提交包里时 skip 为真）
_ma_facts, _ma_bad, _ma_skip = _ma.audit()
# 免费层容量算术（单页 gzip 体积、带宽能撑多少访问、上游请求数、Actions 用量、存储增量）
_cm_facts, _cm_bad = _cm.audit()
# 《90 天验证计划》可核对事实（每个数字都由 data/processed 现算，评委可离线复算）
_pla_facts, _pla_bad = _pla.audit()
_mk_facts, _mk_bad = _mk.audit()
# 社区文案可核对事实（平台字数上限、声明字数、局限说明、链接、红线、公开数字与页面一致）
_oa_facts, _oa_bad = _oa.audit()
# 演示视频文字材料可核对事实（docs/04 逐字稿 = docs/video/narration.json = docs/05 时间轴）
_sa_facts, _sa_bad = _sa.audit()
# 许可声明可核对事实（7 张照片署名在页脚与 LICENSE 里逐张一致；MIT / CC BY 4.0 / CC BY-SA 切分到处一样）
_la_facts, _la_bad = _la.audit(_demo_html)
# 视频旁白里念到的数字可核对事实（与 data/processed 现算值逐条一致；快照日期在四处材料里同一天）
_na_facts, _na_bad = _na.audit(_demo_html)
# 派生百分比可核对事实（材料里「相对常数均值低 14.5%」这类由 RMSE 现算的百分比逐条复算）
_da_facts, _da_bad = _da.audit(_demo_html)
# 快照一致性可核对事实（随包原始观测不越过快照日，两张主观测表正好覆盖到那天）
_sna_facts, _sna_bad = _sna.audit()
# 行尾与打包一致性可核对事实（文本写盘全部钉住 LF；随包文本文件除两个 .bat 外无 CR；
# 提交包每个条目与磁盘逐字节相同——「第三方离线复算出同一串字节」这句话的证据）
_ptb_facts, _ptb_bad = _ptb.audit()
_ra_facts, _ra_bad = _ra.audit(_demo_html)
# 上线链路可核对事实（三种触发、云端解释器版本、刷新链顺序、部署不依赖刷新成功、声明落点）
_dep_facts, _dep_bad = _dep.audit()
# 无障碍可核对事实（语言标注、alt / scope / 滚动区 / 折叠块 summary / 章节序号不进读屏 / 可缩放）
_a11y_facts, _a11y_bad = _a11y.audit()
# 分享元数据可核对事实（16 个 OG / Twitter 标签、同域绝对地址、卡片真实尺寸与体积、文案无日期、五处落点）
_soc_facts, _soc_bad = _soc.audit()
# 推送命令可核对事实（lease 命令、理由、确认三步、与本机 git 引用的真实分歧对账）
_pu_facts, _pu_bad = _pu.audit()
# 答辩与追问准备可核对事实（题数、覆盖维度、出处可打开、节号对得上、答案里的数字全部来自已冻结材料、四处落点）
_qa_facts, _qa_bad = _qa.audit()
# 一键刷新的环境自检可核对事实（第 49 轮）：直接调 tools/check_env.py 的函数，验证它真能
# 认出缺失的包、真的把发行名映射到导入名；再看启动器与四处落点有没有接上。
_ce_facts = {
    "exists": os.path.exists(os.path.join(ROOT, "tools", "check_env.py")),
    "missing_detected": False, "numpy_found": False, "alias_ok": False,
    "launcher_calls": False, "launcher_offers_install": False,
    "req_coding": False, "launcher_yes": False,
    "readme": False, "docs01": False, "docs02": False, "pack00": False,
    "pin": "2.2.6",
}
if _ce_facts["exists"]:
    import check_env as _ce  # 与本文件同在 tools/ 下，启动器跑的也是它
    _ce_facts["missing_detected"] = (_ce.check_module("definitely-not-installed-xyz")[0] == "missing")
    _ce_facts["numpy_found"] = (_ce.check_module("numpy")[0] in ("ok", "drift"))
    _ce_facts["alias_ok"] = (_ce.import_name("python-docx") == "docx"
                             and _ce.import_name("numpy") == "numpy"
                             and _ce.import_name("PyYAML") == "yaml")
    _launch_txt = readp("tools/launch.ps1")
    _ce_facts["launcher_calls"] = ("check_env.py" in _launch_txt and "--require" in _launch_txt
                                   and "Probe-Env" in _launch_txt)
    _ce_facts["launcher_offers_install"] = "pip install -r" in _launch_txt
    _ce_facts["readme"] = "check_env.py" in readp("README.md")
    _ce_facts["docs01"] = "check_env.py" in readp("docs/01_项目说明.md")
    _ce_facts["docs02"] = "tools/check_env.py" in d2txt
    _ce_facts["pack00"] = "check_env.py" in readp("00_提交包说明.md")
    _ce_facts["pin"] = _ce.pins().get("numpy", "2.2.6")
    # 第 50 轮：requirements.txt 是 UTF-8 且带中文注释，pip 的 auto_decode 在没有 BOM 也
    # 没有 PEP 263 声明时会退回 locale 编码（中文 Windows = GBK），`pip install -r` 当场崩。
    # 声明必须落在前两行，所以这里只看前两行。
    _ce_facts["req_coding"] = any(
        _ln.strip().startswith("# -*- coding:") for _ln in readp("requirements.txt").splitlines()[:2])
    # 非交互（脚本 / CI）时不能等按键：-Yes 直接装。没有它，安装这条路在脚本里永远走不到。
    _ce_facts["launcher_yes"] = ("[switch]$Yes" in _launch_txt)
_demo_bytes = open(os.path.join(ROOT, "demo", "index.html"), "rb").read()
_demo_cr = _demo_bytes.count(b"\r")
# README 里逐字写着「sha256 前 16 位仍是 XXXX」：这条值必须等于页面的实际字节哈希（第 58 轮补）
_sha_now = hashlib.sha256(_demo_bytes).hexdigest()[:16]
_sha_claim = _re.findall(r"当前成品页 sha256 前 16 位 = ([0-9a-f]{16})", readp("README.md"))
# 行尾策略：.gitattributes 必须把文本文件钉成 LF。Git for Windows 默认 core.autocrlf=true，
# 不钉住的话刚 clone 出来的成品页会带 CR —— README 里那条「sha256 前 16 位」和本文件的行尾断言
# 就会在评委的电脑上无故变红，而项目本身没有任何问题。
_ga_lines = [ln.strip() for ln in readp(".gitattributes").splitlines()]
_ga_lf = any(ln.startswith("*") and "text=auto" in ln and "eol=lf" in ln for ln in _ga_lines)
_ga_bat = any(ln.startswith("*.bat") and "eol=crlf" in ln for ln in _ga_lines)
if _su:
    _site_ok = (_su in _demo_html) and (_su in readp("README.md")) and (_su in d3txt) and (_su in readp("00_提交包说明.md"))
    _site_msg = "已部署：公开网址同时出现在 site.json / 成品页 / README / docs/03 / 00_提交包说明（" + _su + "）"
else:
    _site_ok = ("在线地址：" not in _demo_html) and ("单文件离线页" in _demo_html)
    _site_msg = "未部署：site.json 的 site_url 为空，成品页页脚如实写「单文件离线页」，不编造网址"
# 注意：下面这些针是拆开拼出来的，不然本文件自己就会命中自己（这条检查会扫描本项目所有文本文件）
BAD_PATH_PAT = ("deepseek-" + "harness", "dsh-" + "home", "dsh-" + "runtimes", chr(92) + "slo" + "il")
SCAN_EXT = (".py", ".md", ".bat", ".json", ".txt", ".yml", ".yaml", ".html")
_leak = []
for _dp, _dn, _fn in os.walk(ROOT):
    _dn[:] = [d for d in _dn if d not in (".edge", "__pycache__", "_backup_before_refresh", ".git", "data")]
    for _f in _fn:
        if not _f.endswith(SCAN_EXT):
            continue
        try:
            _t = open(os.path.join(_dp, _f), encoding="utf-8", errors="ignore").read()
        except Exception:
            continue
        for _pat in BAD_PATH_PAT:
            if _pat in _t:
                _leak.append(os.path.relpath(os.path.join(_dp, _f), ROOT) + " <- " + _pat)
_no_leak = len(_leak) == 0
_no_leak_msg = "项目里不含本机专有路径（" + " / ".join(BAD_PATH_PAT) + "）" if _no_leak else ("发现本机路径泄漏: " + "; ".join(_leak[:5]))
au_txt = open(os.path.abspath(__file__), encoding="utf-8").read()
sc = readp("tools/submission_selfcheck.py")
pk = readp("tools/pack_submission.py")
_zip_layout_ok = ("os.path.dirname(ROOT), rel" in au_txt) and ("ai4climate/00_提交包说明.md" in sc) and ("TOP not in packed" in pk)
_wf_path = os.path.join(ROOT, ".github", "workflows", "daily_refresh.yml")
_wf_copy = os.path.join(os.path.dirname(ROOT), "提交包", "B类上线_workflow内容.txt")
if os.path.exists(_wf_path) and os.path.exists(_wf_copy):
    def _rd(p):
        return open(p, encoding="utf-8").read().replace("\r\n", "\n").strip()
    _wf_same = _rd(_wf_path) == _rd(_wf_copy)
    _wf_msg = ("上线 workflow 与 提交包/B类上线_workflow内容.txt 逐字一致（主人照抄的是同一份）"
               if _wf_same else
               "上线 workflow 与 提交包/B类上线_workflow内容.txt 不一致（改了一边忘了另一边）")
elif os.path.exists(_wf_path):
    _wf_same, _wf_msg = True, "上线 workflow 存在（提交包不在同级目录，跳过逐字比对）"
else:
    _wf_same, _wf_msg = False, "缺少 .github/workflows/daily_refresh.yml（每日自动更新无法上线）"
_d4_ok = (_sa_bad == [] and _sa_facts["n_heads"] == 8 and _sa_facts["chars_total"] > 700
          and "02:56" in d4txt and _sa_facts["en_total"] == _sa_facts["cues_total"] >= 40)
_d4_msg = ("演示视频逐字稿自洽：8 个镜头、旁白 %d 字、%d 条中文字幕分句与 %d 条英文译文一一对应、合计 %.1f 秒（= 02:56），由 tools/script_audit.py 逐条核对"
           % (_sa_facts["chars_total"], _sa_facts["cues_total"], _sa_facts["en_total"], _sa_facts["video_total"])) if _d4_ok else (
           "演示视频逐字稿与随包记录不自洽：%d 个镜头 / %d 字 / %.1f 秒（tools/script_audit.py 报 %d 项失败）"
           % (_sa_facts["n_heads"], _sa_facts["chars_total"], _sa_facts["video_total"], len(_sa_bad)))

_d0 = readp("00_提交包说明.md")
_d0_cards = ["今日海况与热压力", "今日作业建议", "未来 8 天窗口", "未来 8 天逐日风险档位（触发线 0.333）", "危险指数预报（数值天气预报驱动 · 80% 经验区间）", "珊瑚白化监测与预警", "白化热压力：本地监测与识别", "未来 4 周白化风险", "预测截止日与口径", "保护与恢复优先级", "保护与恢复优先级与作业窗口", "历史记录与官方对照", "历史回看", "年度热压力与复合灾害记录", "官方对照", "方法与验证", "模型验证表", "参数选择与消融", "本页的诚实清单", "NOAA 官方交叉印证", "数据、阈值与模型的完整说明", "落地与影响：使用方、成本与 90 天验证", "Summary for international reviewers (English)", "共 11 张卡"]
_n_h2 = len(_re.findall(r"<h2>", _demo_html))
_n_h3 = len(_re.findall(r"<h3>", _demo_html))
_d0_ok = all(_c in _d0 for _c in _d0_cards) and _n_h2 == 6 and _n_h3 == 11
_d0_msg = ("提交包说明的卡片清单与成品页一致（页内 6 个板块 / 11 张卡，最新几张都在清单里）" if _d0_ok else
           "提交包说明的卡片清单与成品页不一致（页内 %d 个板块 / %d 张卡，应 6 / 11，且清单要含最新几张）" % (_n_h2, _n_h3))

_allpicks = [int(x) for h in ("1", "3", "7", "14") for x in dash["metrics"][h]["inner_lambda"]]
_mode_lam = max(sorted(set(_allpicks)), key=_allpicks.count)
_dash_hot = {y["year"]: y["hot_days"] for y in dash["yearly"]}
_bw_hot = {str(y["year"]): y["hot_days"] for y in bw["yearly"]}
_pf_blk = readp("tools/preflight.py").split("STEPS = [", 1)[1].split(chr(10) + "]", 1)[0]
_pf_n = sum(1 for _l in _pf_blk.splitlines() if _l.strip().startswith("("))
_ms_win_n = len([1 for _s in ms["sites"] for _h in ("1", "3", "7", "14") if _s["skill"][_h]["model_auc"] > _s["skill"][_h]["pers_auc"]])
_ms_loss = [(_s, _h) for _s in ms["sites"] for _h in ("1", "3", "7", "14") if _s["skill"][_h]["model_auc"] <= _s["skill"][_h]["pers_auc"]]

_vs_csv = os.path.join(ROOT, "data", "external", "noaa_crw", "vs_sabah_daily.csv")
_vs_last = None
if os.path.exists(_vs_csv):
    _vr = [l for l in open(_vs_csv, encoding="utf-8").read().strip().splitlines() if l and not l.startswith("#")]
    if _vr:
        _vp = _vr[-1].split(",")
        _vs_last = (_vp[0], "%.2f" % float(_vp[6]), int(_vp[7]))

def _tie_auc_test():
    """排序 AUC 必须只由数据决定：并列值取平均秩，等于逐对定义，且与样本顺序无关。"""
    try:
        sys.path.insert(0, os.path.join(ROOT, "pipeline"))
        import model as _mdl
        import ssum as _ssm
        assert _ssm.ssum([0.753, 0.644, 0.617, 0.62]) == 2.6340000000000003, "ssum 必须是朴素逐项加法（3.12 的 sum() 会得到 2.634）"
        assert "from ssum import ssum" in bst, "build_static.py 必须从 pipeline/ssum.py 引入朴素累加"
        import random as _rnd
        _rnd.seed(7)
        _p = [_rnd.choice([0.0, 0.5, 1.0, 1.5, 3.0]) for _ in range(240)]
        _l = [_rnd.choice([0, 1]) for _ in range(240)]
        _num = 0.0
        for _i in range(len(_p)):
            if _l[_i] != 1:
                continue
            for _j in range(len(_p)):
                if _l[_j] != 0:
                    continue
                _num += 1.0 if _p[_i] > _p[_j] else (0.5 if _p[_i] == _p[_j] else 0.0)
        _npos = sum(_l); _nneg = len(_l) - _npos
        _brute = _num / float(_npos * _nneg)
        _got = _mdl.auc(_p, _l)
        _rev = list(range(len(_p)))[::-1]
        _got2 = _mdl.auc([_p[_i] for _i in _rev], [_l[_i] for _i in _rev])
        _small = _mdl.auc([1, 1, 2, 2, 3], [0, 1, 0, 1, 1])
        return (abs(_got - _brute) < 1e-9 and abs(_got2 - _brute) < 1e-9
                and abs(_small - 2.0 / 3.0) < 1e-12)
    except Exception:
        return False
_tie_ok = _tie_auc_test()

# --- docs/04 演示逐字稿：镜头声明字数与秒数交给 tools/script_audit.py 逐段对账（第 30 轮起）---
_d4t = readp("docs/04_演示视频逐字稿与分镜.md")


def _x_thread_lines():
    """docs/06 §8.2 的四条推文（标题承诺每条 ≤ 280 字符）。"""
    _seg = readp("docs/06_作品帖与发布草稿.md").split("### 8.2")[1].split("### 8.3")[0]
    return [_l for _l in _seg.split(chr(10)) if _l[:3] in ("1. ", "2. ", "3. ", "4. ")]


CODE_CHECKS = [
    ('range(max(0, i-12), min(len(days), i+13))' in bf and '25 天中心滚动均值' in d2txt,
     "静水位窗口 = 25 天（代码 range(i-12, i+13)；docs/02 表述一致）"),
    ('0.62,0.75,0.88' in bd and '3 折' in d2txt,
     "对外主表折数 = 3 折 0.62/0.75/0.88（docs/02 表述一致）"),
    ('TRAIL_W = 25' in fe and 'surge_trail' in fe and 'sl_still_trail' in fe and 'surge_trail' in d2txt and 'sl_still_trail' in d2txt,
     "静水位与增水已改用过去 25 天的因果口径（feat_ext 的 TRAIL_W = 25 / surge_trail / sl_still_trail，docs/02 表述一致）"),
    ('min_present' in fe and '0.95' in fe and 'f_sst' in d2txt and '95%' in d2txt,
     "特征筛选改用 95% 存在率、海温滚动特征已进入模型一事已写进 pipeline/feat_ext.py 与 docs/02"),
    ('paper_forecast.py' in r3txt and 'forecast_log.jsonl' in pf and 'forecast_log.jsonl' in d3txt,
     "90 天验证 S1 的每日存档已落到代码与 docs/03（paper_forecast.py 在 refresh 链里，台账名一致）"),
    (arch_brief,
     "S1 的冻结简报已在 data/processed/archive/ 生成（对应数据窗口末日 " + dash_end + "）"),
    ('settle_forecast.py' in d3txt and os.path.exists(os.path.join(ROOT, 'tools', 'settle_forecast.py')),
     "S1 的结算器 tools/settle_forecast.py 已实现并写进 docs/03"),
    (os.path.exists(os.path.join(ROOT, 'tools', 'preflight.py')) and 'preflight.py' in readp('docs/05_报名表与提交清单.md'),
     "提交前一键自检 tools/preflight.py 已实现并写进 docs/05"),
    ('site.json' in bst and os.path.exists(_site_path),
     "在线地址的唯一来源 site.json 存在，且 build_static.py 会读它（改网址不用手改 HTML）"),
    (_site_ok, _site_msg),
    (_no_leak, _no_leak_msg),
    ('bleaching_watch.py' in r3txt and 'priority_plan.py' in r3txt and 'bleaching_watch.json' in bst and 'priority_plan.json' in bst,
     "白化识别与保护优先级两个模块既在 refresh 链里，也被成品页读取"),
    ('本地监测与识别' in _demo_html and '保护与恢复优先级' in _demo_html,
     "成品页已含「白化热压力：本地监测与识别」与「保护与恢复优先级」两张卡"),
    (_zip_layout_ok,
     "解压后的布局也支持：顶层 00_提交包说明.md 在 ai4climate/ 上一层时，审计 / 自检 / 重新打包都不会报假错"),
    (_wf_same, _wf_msg),
    (_d4_ok, _d4_msg),
    (_d0_ok, _d0_msg),
    ('ablation_audit.py' in r3txt and '消融' in d2txt and '消融' in d3txt and os.path.exists(os.path.join(ROOT, 'data', 'processed', 'ablation_audit.json')),
     "特征与选参消融既在 refresh 链里、也有产物，且 docs/02 与 docs/03 都写了它"),
    (_dash_hot == _bw_hot,
     "年度热压力日在成品页年度表与白化识别卡里逐年相同（同一个 p90 事实来源，2026 = %s 天）" % _dash_hot.get("2026")),
    (str(int(dash["forecast_meta"]["lam"])) == str(_mode_lam),
     "成品页部署的 λ = 主表逐折内窗 CV 挑出值的众数（%s；逐折挑出 %s）" % (_mode_lam, " / ".join(str(x) for x in _allpicks))),
    (abs(float(bw["baseline"]["sst_p90"]) - float(dash["thresholds"]["sst"]["p90"])) < 1e-9,
     "白化识别的海温 p90 与 build_features 的 p90 完全一致（%.3f）" % dash["thresholds"]["sst"]["p90"]),
    (len(bw["noaa_check"]["vs_sites"]) >= 2 and "Palau" in str(bw["noaa_check"]["vs_sites"]) and "404" in d2txt,
     "官方逐日对照覆盖两个独立站点（Sabah / Palau）；布纳肯无官方虚拟站点文件（HTTP 404）已在 docs/02 披露"),
    (_pf_n == 6 and "一键自检 6 步" in d2txt and "6 步全过" in d3txt and "6 步全绿" in readp("00_提交包说明.md")
     and "一键自检 7 步" not in d2txt and "7 步全过" not in d3txt and "7 步全绿" not in readp("00_提交包说明.md"),
     "一键自检判定链与 tools/preflight.py 的 STEPS 一致（%d 步，全部离线、不改动提交物），docs/02 / docs/03 / 00 都写 6 步" % _pf_n),
    ('leakage_audit.py' in r3txt and os.path.exists(os.path.join(ROOT, 'data', 'processed', 'leakage_audit.json')),
     "前视泄漏审计 leakage_audit.py 在 refresh 链里，且有产物 data/processed/leakage_audit.json"),
    (lk["verdict"] == "PASS" and lk["max_abs_diff"] < 1e-9 and not lk["analysis_cols_in_features"] and lk["feature_count"] == dash["forecast_meta"]["features"],
     "泄漏审计 PASS：%d 个截断点上重建全部 %d 个特征、最大绝对偏差 %g，三个居中分析列未进入模型特征" % (len(lk["cuts"]), lk["feature_count"], lk["max_abs_diff"])),
    ("前视泄漏" in d2txt and "严格因果" in d2txt and "事后分析量" in d2txt and "leakage_audit.py" in d2txt,
     "docs/02 写明特征严格因果、无前视泄漏（分析口径与预报口径的拆分与验证方式）"),
    ("2024-06-12" in d2txt and "2025-01-29" in d2txt and "1,406" in d2txt,
     "docs/02 如实披露海平面/增水的两段缺测（2024-06-12 起 7 天、2025-01-29 起 11 天，共 18 天）与缺测日不计该项压力的处理"),
    ("口径说明" in d2txt and "1,404 天" in d2txt and "1,446 天" in d2txt and "口径提醒" in _demo_html,
     "保护优先级百分位（三站点数据集 1,404 天）与白化识别百分位（主记录 1,446 天）的记录口径差异，已在 docs/02 与成品页并列标注"),
    (all(s in r3txt for s in ("fetch_multisite.py", "multisite_check.py", "diagnose.py")) and "在每日链条里" in d2txt,
     "跨站点取数与复核（fetch_multisite.py / multisite_check.py）与分类器诊断（diagnose.py）都已并入 refresh 链，docs/02 工具表也写明"),
    ("已被取代" in readp("tools/noaa_access_probe/fetch_vs_sabah.py") and "pipeline/fetch_noaa_vs.py" in readp("tools/noaa_access_probe/fetch_vs_sabah.py") and "不再单独运行" in d2txt,
     "官方虚拟站点抓取的探路脚本已标注被 pipeline/fetch_noaa_vs.py 取代、只作过程证据（docs/02 工具表也写明不再单独运行）"),
    (os.path.exists(os.path.join(ROOT, "tools", "reviewer_repro.py")) and "reviewer_repro.py" in d2txt and "reviewer_repro.py" in d3txt and "reviewer_repro.py" in readp("tools/preflight.py")
     and "reviewer_repro.py" in readp("README.md") and "评审视角复算" in readp("00_提交包说明.md")
     and "逐字节比对" in readp("00_提交包说明.md"),
     "评审视角复算 tools/reviewer_repro.py 已实现、写进 docs/02 / docs/03 / README / 00（第 7 步离线重跑 + 逐字节比对），并作为最后一步并入 tools/preflight.py"),
    (V["zero_share"] in _demo_html and "72.8%" not in _demo_html and V["win_max_upper"] in _demo_html
     and V["win_high_n"] + " 天" in _demo_html and all(_d in _demo_html for _d in V["win_high_dates"].split(" / ")),
     "成品页窗口说明用数据现算的 0 值占比与上界最高值（不再写死 72.8%），越线天数与日期一致"),
    (all("active" in _s and _s.get("active_reason") for _s in pp["sop"]) and bool(pp["today"]["stage"]) and "今天适用" in _demo_html and "两个不同的轴" in _demo_html,
     "SOP 每条都带 active 标记与适用原因，页面标出今天适用哪一档（%s，%s 条）并区分两条轴" % (pp["today"]["stage"], len(pp["today"]["active"]))),
    (V["ms_days"] in _demo_html and "1,403" not in _demo_html,
     "成品页跨站点卡的天数从数据现算（%s 天），不再写死 1,403" % V["ms_days"]),
    (_ms_win_n == len(ms["sites"]) * 4 - len(_ms_loss) and ("%d 格排序 AUC 高于持续预报" % _ms_win_n) in _demo_html
     and (("排序 AUC 全部高于持续预报" not in _demo_html) if _ms_loss else True)
     and all("%.3f" % _s["skill"][_h]["model_auc"] in _demo_html and "%.3f" % _s["skill"][_h]["pers_auc"] in _demo_html for _s, _h in _ms_loss),
     "成品页跨站点排序 AUC 的胜负按数据现算（%d / %d 格高于持续预报，落败 %d 格如实列出）" % (_ms_win_n, len(ms["sites"]) * 4, len(_ms_loss))),
    (bool(_vs_last) and _vs_last[0] in _demo_html and _vs_last[1] in _demo_html
     and (("Alert Level 2" in _demo_html) if _vs_last[2] == 4 else True),
     "成品页披露的官方最新 DHW 与原始 CSV 末行逐字一致（%s / DHW %s / ALERT %s）" % (_vs_last if _vs_last else ("-", "-", "-"))),
    (_tie_ok,
     "排序 AUC 对并列值取平均秩：与逐对定义一致、与样本顺序无关（不再依赖排序实现，跨机器可复现）"),
    (V["lam_avg_min"] + " 到 " + V["lam_avg_peak"] in _demo_html and "0.658 到" not in _demo_html,
     "成品页 λ 平均 AUC 区间与数据现算一致（%s 到 %s；先四舍五入再格式化，不受 CPython 版本影响）" % (V["lam_avg_min"], V["lam_avg_peak"])),
    ('round(float(v), k)' in bst,
     "成品页的数值格式化先四舍五入再格式化（0.6585 这类三位小数中点值在不同 CPython 版本上会印出不同结果）"),
    (_demo_cr == 0,
     "成品页行尾是纯 LF（本地 Windows 与云端 Linux 产出的字节才能一致；当前 CR 个数 %d。"
     "若是在 Windows 上刚 clone 就跑到这里，先跑一次 pipeline/build_static.py 重建页面，"
     "或把 core.autocrlf 设为 false 后重新检出）" % _demo_cr),
    (_ga_lf and _ga_bat,
     "行尾策略钉在 .gitattributes 里（* text=auto eol=lf，*.bat 保持 CRLF）："
     "在 Windows 上按默认 core.autocrlf=true clone 出来的页面与仓库里的字节一致"),
    # 第 58 轮补的真比对：此前这里只有「行尾策略钉住了」这一条，文案却宣称「README 那条 sha256
    # 在任何机器上都对得上」—— 比对代码根本不存在，于是 README 里写着上一版页面的哈希也照样全绿
    # （审计实测：README 写 48c06a6f…，页面实际是 165b2960…）。现在把两边比一次。
    (bool(_sha_claim) and set(_sha_claim) == {_sha_now},
     "README 的「sha256 前 16 位」与成品页实际字节一致（README 写 %s，页面实测 %s）："
     "每次改动成品页都要一起更新 —— 演练记录、提交包内页面、线上页面必须同一串字节"
     % (" / ".join(sorted(set(_sha_claim))) or "（README 里没找到）", _sha_now)),
    ("driver_error_audit.py" in r3txt and os.path.exists(os.path.join(ROOT, "data", "processed", "driver_error_audit.json")),
     "驱动误差审计 driver_error_audit.py 在 refresh 链里，且有产物 data/processed/driver_error_audit.json"),
    (_de["n_days"] == dash["span"]["days"]
     and all(abs(_de["horizons"][_h]["rmse_obs"] - dash["metrics"][_h]["model_rmse"]) < 5e-5 for _h in ("1", "3", "7", "14")),
     "驱动误差审计的观测端点与主表同一协议（1 天 %s == 主表 %.4f，14 天 %s == 主表 %.4f）"
     % (V["de_obs1"], dash["metrics"]["1"]["model_rmse"], "%.4f" % _de["horizons"]["14"]["rmse_obs"], dash["metrics"]["14"]["model_rmse"])),
    (V["de_pers1"] in _demo_html and V["de_gap1"] + "%" in _demo_html and V["de_gap14"] + "%" in _demo_html
     and V["de_ci1"] in _demo_html and V["de_auc3g"] in _demo_html and V["de_auc14g"] in _demo_html
     and "驱动自身的误差未单独传播" not in _demo_html,
     "成品页与脚注把驱动误差量化进页（1 天 %s 对 %s、+%s%%；3 天排序 AUC 掉 %s；14 天 %s%%），不再只说「未单独传播」"
     % (V["de_obs1"], V["de_pers1"], V["de_gap1"], V["de_auc3g"], V["de_gap14"])),
    ("3.6.1" in d2txt and "driver_error_audit.py" in d2txt and "不据此改动部署配置" in d2txt
     and "已单独量化" in readp("docs/01_项目说明.md") and "已单独量化" in readp("README.md"),
     "docs/02 新增 3.6.1 节（驱动误差量化的方法与两个端点），docs/01 与 README 同步改为已量化口径"),
    ("index_variant_audit.py" in r3txt and os.path.exists(os.path.join(ROOT, "data", "processed", "index_variant_audit.json")),
     "指数定义敏感性审计 index_variant_audit.py 在 refresh 链里，且有产物 data/processed/index_variant_audit.json"),
    (("复现" in _iv["selfcheck"]) and all(abs(_iv["variants"][_iv["deployed_variant"]]["by_h"][_h]["model_rmse"] - dash["metrics"][_h]["model_rmse"]) < 5e-5 for _h in ("1", "3", "7", "14")),
     "指数定义审计自证：部署定义逐时效复现主表（1 天 %s == 主表 %.4f，共 %d 种定义）" % ("%.4f" % _iv["variants"]["three_driver"]["by_h"]["1"]["model_rmse"], dash["metrics"]["1"]["model_rmse"], len(_iv["variants"]))),
    (V["iv_win"] + " 格同时优于常数均值与持续预报" in _demo_html and V["iv_fails"] + " 格" in _demo_html
     and all(_n in _demo_html for _n in ("2 驱动（去增水）", "3 驱动（部署）", "4 驱动（加海温）", "3 驱动 · p85", "3 驱动 · p95")),
     "成品页指数定义敏感性表按数据现算（%s 个格里 %s 格仍胜、%s 格落败，五种定义都入表）" % (V["iv_n"], V["iv_win"], V["iv_fails"])),
    ("3.6.2" in d2txt and "index_variant_audit.py" in d2txt and "相对同定义基线" in d2txt and "跨定义不能直接比 AUC" in _demo_html,
     "docs/02 新增 3.6.2 节（指数定义敏感性：五种定义同一协议），成品页写明跨定义不能直接比 AUC"),
    ("compound_label_audit.py" in r3txt and os.path.exists(os.path.join(ROOT, "data", "processed", "compound_label_audit.json")),
     "复合灾害日标签审计 compound_label_audit.py 在 refresh 链里，且有产物 data/processed/compound_label_audit.json"),
    (("复现" in _cp["selfcheck"]) and all(abs(_cp["by_h"][_h]["model_rmse_index"] - dash["metrics"][_h]["model_rmse"]) < 5e-5 for _h in ("1", "3", "7", "14")),
     "复合灾害日审计自证：同一 3 折协议只换标签，模型 RMSE 逐时效复现主表（1 天 %s）" % ("%.4f" % _cp["by_h"]["1"]["model_rmse_index"])),
    (V["cp_pos"] + " 天，占 " in _demo_html and V["cp_base"] in _demo_html and V["cp_auc7"] in _demo_html
     and V["cp_pers7"] in _demo_html and V["cp_pr7"] in _demo_html and V["cp_perspr7"] in _demo_html,
     "成品页公开复合灾害日标签下的排序能力（样本外正类 %s 天 / %s，最弱的 7 天 %s 对 %s 也入页）" % (V["cp_pos"], V["cp_base"], V["cp_auc7"], V["cp_pers7"])),
    ("3.6.3" in d2txt and "compound_label_audit.py" in d2txt and "复合灾害日" in d2txt and "不是" in d2txt,
     "docs/02 新增 3.6.3 节（把排序标签换成产品主打的复合灾害日再评一次）"),
    ("p90 与 p95 因此重合在同一条线" in _demo_html and "超过 1.0 时截断在 1.0" in _demo_html
     and "由上界越线触发" in _demo_html and "不是点预报越线" in _demo_html,
     "成品页披露触发线口径：指数只有三档（0 / 0.333 / 0.667）、p90 与 p95 重合在同一条线、窗口「高」档由上界越线触发而不是点预报，并写明上界在 1.0 截断"),
    ("口径提示（主表 ≠ 部署模型）" in d2txt and "7 天那一档几乎打平" in d2txt and "只报数值、不做显著性宣称" in d2txt
     and "部署口径" in d2txt,
     "docs/02 写明主表（报告口径）≠ 成品页部署模型；3.6.3 节写明 7 天那一档几乎打平、样本太少只报数值不做显著性宣称"),
    ("同一站点存在多套海温 p90 与窗口" in d2txt and "年尺度 Spearman = 1.000 只有 4 个年份" in d2txt
     and "13/13 命中" in d2txt and "82.3%" in d2txt,
     "docs/02 第五节新增第 8 / 9 / 10 条披露（多套海温 p90 与窗口、年尺度相关只有 4 个年份、13/13 命中的判据与背景率）"),
    ("**S7**" in readp("docs/05_报名表与提交清单.md") and "7 条" in readp("docs/05_报名表与提交清单.md")
     and "PR-AUC" in readp("docs/05_报名表与提交清单.md"),
     "docs/05 的成功标准改为引用 docs/03 的 7 条（S1–S7），不再另立一套"),
    ("边际成本 = 一次取数 + 一个坐标" in readp("docs/01_项目说明.md")
     and "保留上一份、打印 WARN" in readp("docs/01_项目说明.md")
     and "pipeline/fetch_multisite.py:27" in readp("docs/01_项目说明.md")
     and "零费用、零服务器" in readp("docs/06_作品帖与发布草稿.md")
     and "加一行坐标" in readp("docs/06_作品帖与发布草稿.md"),
     "市场可持续性写明可复核的边际成本（新站点 = 一次取数 + 一个坐标，已在三站验证）与故障行为（保留上一份数据、页面不中断）"),
    (len(_x_thread_lines()) == 4 and all(len(_l) <= 280 for _l in _x_thread_lines())
     and "无 JavaScript" not in readp("docs/06_作品帖与发布草稿.md")
     and "无需 JavaScript 也能读全部数字" in readp("docs/06_作品帖与发布草稿.md"),
     "docs/06 §8.2 四条推文各自 ≤ 280 字符（标题承诺「每条控制在 280 字符内」），且交付句写成「无需 / 禁用 JavaScript 也能读全部数字」——页面内置一小段脚本，不能说「无 JavaScript」"),
    (_pa_bad == [] and _pa_facts["th"] == 95 and _pa_facts["img"] == _pa_facts["img_alt"] == 8
     and _pa_facts["tw"] == 17 and _pa_facts["details"] == 15 and _pa_facts["day"] == 8
     and _pa_facts["settle_expected"] == _pa_facts["settle_in_page"] == 1
     and ("%d 个表头" % _pa_facts["th"]) in readp("docs/01_项目说明.md")
     and ("%d 张图" % _pa_facts["img"]) in readp("docs/01_项目说明.md")
     and ("%d 个表格容器" % _pa_facts["tw"]) in readp("docs/01_项目说明.md")
     and ("%d 个折叠说明" % _pa_facts["details"]) in readp("docs/01_项目说明.md")
     and ("%d 个日期标签" % _pa_facts["day"]) in readp("docs/01_项目说明.md")
     and "tools\\page_audit.py" in readp("docs/01_项目说明.md")
     and ".taste-skill/a11y.mjs" not in readp("docs/01_项目说明.md"),
     "成品页的无障碍 / 隐私声明由包内 python tools\\page_audit.py 离线复核（audit() 零失败），docs/01 报的 8 张图 / 95 个表头 / 17 个表格容器 / 15 个折叠块（含高风险四项说明与依据与来源） / 8 个日期标签与页面实际计数逐项一致，「窗口结算」披露的触发条件（最近一次热浪起点落在 as-of 起 28 天内）与页面是否印出这一段两个方向都一致，且不再指向包外的 .taste-skill/a11y.mjs"),
    (_ma_skip is not None or _ma_bad == [],
     "演示视频的时长 / 体积 / 分辨率 / 编码与材料里写的数字逐条一致（tools/media_audit.py 纯标准库解析 MP4，不用 ffprobe；视频不在解压后的提交包里时自动跳过）："
     + (_ma_skip or "%.2f 秒 / %d bytes / %d×%d / %s + %s"
        % (_ma_facts["seconds"], _ma_facts["bytes"], _ma_facts["width"], _ma_facts["height"],
           _ma_facts["video_codec"], "mp4a" if _ma_facts["has_aac"] else "?"))),
    (_cm_bad == []
     and ("%.2f MB" % (_cm_facts["page_gzip_bytes"] / 1e6)) in _demo_html
     and ("%.1f 万次" % (_cm_facts["views_per_month"] / 1e4)) in _demo_html
     and ("{:,} 名".format(_cm_facts["daily_users"] // 100 * 100)) in _demo_html
     and ("%d 次上游请求" % _cm_facts["requests_per_refresh"]) in _demo_html,
     "免费层容量算术：单页 gzip %.2f MB、100 GB/月软限额约合 %.1f 万次访问（约 %s 名每日用户）、每天 %d 次上游请求、Actions %.0f 到 %.0f 分钟/月、一次刷新净增 %d 字节 —— 成品页与 docs/01 第 7 节写的是同一组数字，由 tools/cost_model.py 复算（页面里的体积与容量由生成器按页面自身现算，不写死）"
     % (_cm_facts["page_gzip_bytes"] / 1e6, _cm_facts["views_per_month"] / 1e4,
        "{:,}".format(_cm_facts["daily_users"] // 100 * 100), _cm_facts["requests_per_refresh"],
        _cm_facts["actions_minutes_per_month_fast"], _cm_facts["actions_minutes_per_month_slow"],
        _cm_facts["growth_per_refresh_bytes"] or 0)),
    (_pla_bad == []
     and _pla_facts["s2_verdict_ok"]
     and "1.2% 到 7.6%" not in open(os.path.join(ROOT, "pipeline", "s2_hindcast.py"), encoding="utf-8").read(),
     "《90 天验证计划》引用的每个数字都由 data/processed 现算（λ 峰值 λ=100、精确率区间 %.1f%%–%.1f%%、消融报告口径 0.796 / 0.665 / 0.600 / 0.615、两站重叠 1,410 / 1,403 天），由 tools/plan_audit.py 逐条核对；s2_hindcast.py 的精确率区间由 by_h 现算，不再写死"
     % _pla_facts["s2_prec"]),
     ("零费用、零服务器、无需 GPU" in _demo_html and "换一个新站点只需在站点列表里加一行坐标" in _demo_html
     and "最坏情况是「数字还是昨天的」" in _demo_html and "37 秒" in _demo_html and "143 秒" in _demo_html
     and "30 到 45 秒" not in _demo_html
     and "37 to 143 seconds" in _demo_html and "30 to 45 seconds" not in _demo_html,
     "成品页脚注写明运行成本与故障行为（零费用零服务器、两次实测 37 秒 / 143 秒、新站点一行坐标、取数失败保留上一份），英文摘要同样写 37 to 143 seconds"),
     (_mk_bad == []
     and "104 小时/年" in _demo_html and "20 美元/小时" in _demo_html
     and "低档价要 6 家" in _demo_html and "高档价要 3 家" in _demo_html,
     "市场与可持续性的算术由 tools/market_model.py 从假设现算（年维护 104 小时、机会成本 2,080 美元/年、订阅 360 到 4,800 美元/年、低档价要 6 家 / 高档价要 3 家打平），docs/01 第 7 节与成品页同步"),
     (_oa_bad == []
     and _oa_facts["x_posts"] == 4 and max(_oa_facts["x_weighted"]) <= _oa_facts["x_limit"]
     and _oa_facts["xhs_title_len"] <= 20 and "dashboard.html" not in readp("docs/06_作品帖与发布草稿.md"),
     "社区文案由 tools/outreach_audit.py 逐条核对（X 四条加权 %s 字符以内、小红书标题 %d 字、每个平台都保留一条局限说明与可执行链接、不出现手机号与做不到的承诺、文案里的公开数字与成品页一致）"
     % ("/".join(str(x) for x in _oa_facts["x_weighted"]), _oa_facts["xhs_title_len"])),
     (_sa_bad == [] and _sa_facts["n_heads"] == 8 and _sa_facts["chars_total"] > 700
     and _sa_facts["en_total"] == _sa_facts["cues_total"] and _sa_facts["cues_total"] >= 40,
     "演示视频的文字材料由 tools/script_audit.py 逐条核对（docs/04 的 8 段逐字稿与随包的 docs/video/narration.json 逐字相同、标题里的字数与秒数都是实测、时间轴与 docs/05 一致、%d 条中文字幕分句与 %d 条英文译文一一对应）"
     % (_sa_facts["cues_total"], _sa_facts["en_total"])),
     (_la_bad == [] and _la_facts["page_credits"] == 7 and _la_facts["license_credits"] == 7
     and _la_facts["page_authors"] == _la_facts["license_authors"]
     and not _la_facts["page_banned"] and _la_facts["en_has_photos_sa"]
     and not _la_facts["docs_missing"],
     "许可声明由 tools/license_audit.py 逐条核对（7 张照片的摄影者与许可版本在成品页页脚与 LICENSE 第 4 条里逐张一致；代码与文档 MIT、本项目自有的数据/图表/页面文字 CC BY 4.0、内嵌照片 CC BY-SA 的切分在 %d 份材料里说的是同一件事，没有任何材料把整页笼统写成 CC BY-SA）"
     % _la_facts["docs_present"]),
     (_na_bad == [] and _na_facts["narr_snapshot"] == _na_facts["snapshot"]
     and _na_facts["worst_year"] == "2024" and _na_facts["n_events"] >= 10,
     "视频旁白里念到的每个数字由 tools/narration_audit.py 现算核对（21 条中文数词断言；最重年份 %s：%d 个复合灾害日 / %d 个热压力日；二元 AUC %.3f；PR-AUC %.3f > %.3f > %.3f；热浪 %d 次、当前 %.1f 百分位；数据快照 %s 在旁白记录、docs/04、docs/05 与成品页上同一天）"
     % (_na_facts["worst_year"], _na_facts["worst_compound"], _na_facts["worst_hot"],
        _na_facts["binary_auc"], _na_facts["pr_model"], _na_facts["pr_rule"],
        _na_facts["pr_base"], _na_facts["n_events"], _na_facts["pct_now"],
        _na_facts["snapshot"])),
     (_da_bad == [] and abs(_da_facts["drop_pers_1"] - 20.81) < 0.01
     and abs(_da_facts["zero_share"] - 72.3) < 0.05,
     "派生百分比由 tools/derived_audit.py 现算复算（1 天相对持续预报 %.1f%%；1 天相对常数均值 %.2f%%；收缩后四个时效 %.2f%% / %.2f%% / %.2f%% / %.2f%%；零值占比 %.1f%%；排序 AUC %s 对持续预报 %s 对气候平均 %s——七份材料与成品页说的是同一个数）"
     % (_da_facts["drop_pers_1"], _da_facts["drop_flat_1"], _da_facts["blend_gain_1"],
        _da_facts["blend_gain_3"], _da_facts["blend_gain_7"], _da_facts["blend_gain_14"],
        _da_facts["zero_share"], _da_facts["auc_model_str"], _da_facts["auc_pers_str"],
        _da_facts["auc_clim_str"])),
     (_sna_bad == [] and _sna_facts["feat_last"] == _sna_facts["snap"]
      and _sna_facts["obs_overshoot"] == []
      and _sna_facts["drivers_first"] == _sna_facts["drivers_expected_first"],
      "随包原始观测与数据快照日一致，由 tools/snapshot_audit.py 核对（快照日 %s；%d 张观测表最大日期 %s；特征表末日 %s；预报驱动首日 %s——观测一旦越过快照日，评委按文档离线复算就会算出另一张页面）"
      % (_sna_facts["snap"], _sna_facts["n_tables"], _sna_facts["obs_last"],
         _sna_facts["feat_last"], _sna_facts["drivers_first"])),
     (_ptb_bad == [] and _ptb_facts["unpinned"] == [] and _ptb_facts["crlf"] == []
      and _ptb_facts["page_cr"] == 0 and _ptb_facts["pack_missing"] == []
      and _ptb_facts["pack_crlf"] == [] and _ptb_facts["pack_mismatch"] == [],
      "行尾与打包一致，由 tools/portability_audit.py 核对（%d 处文本写盘全部钉住 LF；随包 %d 个文本文件除两个刻意 CRLF 的 .bat 外无 CR；成品页 CR %s；提交包 %d 个条目与磁盘内容一致——Windows 的文本模式写盘会偷偷把 \\n 翻成 \\r\\n，不钉住的话评委 clone 出来的仓库与提交包就不是同一串字节；包不在时这一条按 SKIP 处理）"
      % (_ptb_facts["writers"], _ptb_facts["text_files"], _ptb_facts["page_cr"],
         _ptb_facts["zip_entries"])),
     (_ra_bad == [] and _ra_facts["methods_with_source"] == _ra_facts["groups"]
      and _ra_facts["doc_entries"] == 8 and _ra_facts["dois"] == 8
      and _ra_facts["page_doi_mentions"] == _ra_facts["dois"] + 1,
      "方法与出处由 tools/refs_audit.py 核对（%d 条出处：%d 个 DOI + %d 个产品页链接；%d 组方法各有出处；成品页「依据与来源」与 docs/02 第七节逐条对得上，核对日期 %s——规则要求高风险应用交代数据来源，评委最常问的就是「p90 / 海洋热浪 / MMM / DHW 这些定义从哪来」）"
      % (_ra_facts["refs"], _ra_facts["dois"], _ra_facts["urls"],
         _ra_facts["groups"], _ra_facts["verified_on"])),
     (_dep_bad == [] and _dep_facts["myt"] == "06:10" and "main" in _dep_facts["push_branches"]
      and _dep_facts["py_version"] == "3.10" and _dep_facts["verify_last"]
      and _dep_facts["build_before_verify"] and _dep_facts["guard_always"]
      and _dep_facts["deploy_ref_main"] and _dep_facts["deploy_doc"]["retired"] == [],
      "上线链路由 tools/deploy_audit.py 核对（定时 %s = 马来西亚时间 %s / push 到 %s 立刻部署 / 手动 Run workflow；云端解释器钉在 %s；刷新链 %d 步且 verify_demo.py 收尾；deploy 作业 always() + 排除 cancelled + 机器人 actor 判断，checkout 钉 ref: main —— 刷新失败也照样把 main 上那一版上线，而机器人自己的 push 不会自激；「每天 06:10（马来西亚时间）」在成品页与 %d 份材料里齐全。第 41 轮真的抓到过：工作流只有定时触发，而 Pages 源是 GitHub Actions，推分支根本不上线，最坏要等满 24 小时，而提交截止是 2026-10-19 24:00 CST）"
      % (_dep_facts["cron"], _dep_facts["myt"], _dep_facts["push_branches"],
         _dep_facts["py_version"], _dep_facts["refresh_steps"], len(_dep_facts["claims"]) - 1)),
     (_a11y_bad == [] and _a11y_facts["latin_unmarked"] == 0
      and _a11y_facts["lang_en_attrs"] == 9 and _a11y_facts["han_in_en"] == 0
      and _a11y_facts["img_alt_empty"] == 0 and _a11y_facts["th_scope"] == _a11y_facts["th"]
      and _a11y_facts["tw_label_han"] == _a11y_facts["tw"]
      and _a11y_facts["details_summary"] == _a11y_facts["details"],
      "无障碍与语言标注由 tools/a11y_audit.py 核对（%d 个纯拉丁文本节点全部落在 %d 处 en 语言标注里，标成 en 的部分零汉字误标；%d 张图 alt、%d 个表头 scope、%d 个横滚容器 role + tabindex + 中文 aria-label、%d 个折叠块 summary、%d 个章节序号由 CSS 隐藏不进读屏、viewport 允许缩放、CSS 里有 :lang(en) 与 :focus-visible。第 42 轮真的抓到过：全页只有一个 lang 属性，一整块 1.6 万字符的英文摘要与 7 行拉丁文照片署名会被读屏软件按中文发音读，而 docs/01 写着「每一条都可实测」却没有这一条）"
      % (_a11y_facts["latin_nodes"], _a11y_facts["lang_en_attrs"], _a11y_facts["img"],
         _a11y_facts["th"], _a11y_facts["tw"], _a11y_facts["details"],
         _a11y_facts["secnum"])),
     (_soc_bad == [] and _soc_facts["card_ok_size"] and not _soc_facts["meta_has_date"]
      and not _soc_facts["abs_outside_site"] and _soc_facts["link_tags"] == 0
      and _soc_facts["og_title"] == _soc_facts["page_title"],
      "分享预览由 tools/social_audit.py 核对（%d 个 Open Graph / Twitter Card 标签齐全且全部指向 site.json 的 %s；og:title 与页面 <title> 一致、og:description %d 字符比页面 meta description 更短；卡片 demo/og.jpg 真实 %d×%d JPEG、%d 字节，与 og:image:width/height 一致；分享文案零日期——卡片不随每日刷新变，写死快照日会变成假话；页面里 <link> 计数 0，单文件规则不变。第 43 轮真的抓到过：四条推文、LinkedIn 帖与小红书笔记分享的都是同一个网址，而页面里 og: 与 twitter: 标签一个都没有，分享出去只有一条裸链接）"
      % (len(_soc.REQUIRED), _soc_facts["site_url"], _soc_facts["og_desc_len"],
         _soc_facts["card_w"], _soc_facts["card_h"], _soc_facts["card_bytes"])),
     (_pu_bad == [] and _pu_facts["deploy_lease_cmd"] and _pu_facts["deploy_plain_cmd"]
      and _pu_facts["preflight_lease_cmd"] and _pu_facts["wf_push_trigger"]
      and _pu_facts["doc01_cmd"] and _pu_facts["doc01_tool"] and _pu_facts["doc02_tool"]
      # 仓库外的《如何上线新版演示页.md》不在提交包里：评审视角解压复算时它
      # 根本不存在，所以这里按"有才查"处理（与 push_audit 自己的 SKIP 约定一致）。
      and (_pu_facts["guide_lease_cmd"] if _pu_facts["guide_exists"] else True)
      and not _pu_facts["deploy_false_claims"] and not _pu_facts["guide_false_claims"],
      "推送命令由 tools/push_audit.py 核对（DEPLOY.md 与仓库外《如何上线新版演示页.md》给的都是 %s，并写出被拒的普通命令与 %d 条理由、%d 步确认；tools/preflight.py 结尾给用户的待办也是同一条并指向 DEPLOY.md；工作流必须有 push 触发；docs/01 与 docs/02 有落点；再把文档说的与本机 git 引用对账——origin/main 多出的提交必须是预期的 %s。第 44 轮真的抓到过：origin/main 已被机器人推进到 daily refresh 2026-10-17，旧说明同时写着「快进关系」与「报 non-fast-forward 就 rebase origin/main」，照它做必然推不上去，而提交截止是 2026-10-19 24:00（CST））"
      % (_pu.LEASE_CMD, len(_pu.WHY_NEEDED), len(_pu.CHECK_STEPS),
         _pu_facts["bot_subject"])),
     (_qa_bad == [] and _qa_facts["doc01_landing"] and _qa_facts["doc02_tool"]
      and _qa_facts["pack00_landing"] and _qa_facts["readme_landing"],
      "答辩与追问准备由 tools/qa_audit.py 核对（docs/07 的 %d 道问答覆盖 %d 个评审维度、%d 条出处全部能在被引文件里打开、引用的节号对得上标题（「第 5 节」与「五、」算同一节）、答案里出现的 %d 个数字全部来自已冻结材料而不是新编的；四处落点同时在位：docs/01 的当场核对入口、docs/02 的工具表、00_提交包说明的附四、README 的文件树。第 45/46 轮真的抓到过三处：落点断言找「问答」而文档写的是「答辩与追问准备」、答案里写了材料中根本没有的「176.48 秒」、把「五、」当成「第 5 节」判成出处打不开）"
      % (_qa_facts["questions"], len(_qa_facts["buckets_ok"]), _qa_facts["src_paths"],
         _qa_facts["nums_in_answers"])),
     (_ce_facts["exists"] and _ce_facts["missing_detected"] and _ce_facts["numpy_found"]
      and _ce_facts["alias_ok"] and _ce_facts["launcher_calls"]
      and _ce_facts["launcher_offers_install"] and _ce_facts["readme"]
      and _ce_facts["docs01"] and _ce_facts["docs02"] and _ce_facts["pack00"]
      and _ce_facts["req_coding"] and _ce_facts["launcher_yes"],
      "一键刷新的环境自检由 tools/check_env.py 核对（解释器 ≥3.10、标准库之外唯一的运行时依赖 numpy==%s；缺失的包能认出来并给出可复制的安装命令，发行名 python-docx / PyYAML 也能映射到正确的导入名 docx / yaml；tools/launch.ps1 在刷新前用它把 py / python / python3 逐个真跑一次再选，缺依赖时问一句要不要现在装；四处落点在位：README 的「数据怎么更新」、docs/01 的当场核对入口、docs/02 工具表、00_提交包说明的一键刷新段。第 49 轮真的抓到过：更新数据.bat 只查解释器版本、不查 numpy，评委在没装 numpy 的机器上双击会拿到一段 ImportError 回溯，而 00_提交包说明与 docs/06 都向评委承诺「双击即可一键刷新」；同一轮还发现 py 启动器在本机指向 Python 3.13.9 + numpy 2.3.5，而钉住的 2.2.6 装在 PATH 的 python 3.10.11 上，按旧的 py 优先顺序会默默用漂移的解释器刷新。第 50 轮又在一个真的没装 numpy 的 venv 上实测，抓到两个只有真跑才会暴露的缺陷：① requirements.txt 是 UTF-8 且带中文注释，既没有 BOM 也没有 PEP 263 编码声明，pip 的 auto_decode 于是退回 locale 编码（中文 Windows 上是 GBK），`pip install -r requirements.txt` 当场 UnicodeDecodeError —— 也就是说启动器给出的补救命令本身就装不上，而评委的机器大概率就是中文 Windows；② 非交互（stdin 被重定向）时启动器一律按「不装」处理，安装这条路在脚本与 CI 里永远走不到，于是加了 -Yes）"
      % _ce_facts["pin"]),
     ("Summary for international reviewers (English)" in _demo_html and "byte-for-byte" in _demo_html
     and "no GPU, no server" in _demo_html,
     "成品页尾附英文摘要（面向国际评委）：站点 / 数据 / 指标 / 模型 / 白化 / 部署成本 / 可复现 / 诚实声明八段，关键数字全部现算"),
     ('s2_hindcast.py' in r3txt and os.path.exists(os.path.join(ROOT, "data", "processed", "s2_hindcast.json")),
      "S2 判据回溯检验 s2_hindcast.py 在 refresh 链里，且有产物 data/processed/s2_hindcast.json"),
     (_s2["selfcheck"]["verdict"] == "PASS"
      and all(abs(_m["audit"] - _m["dashboard"]) < 5e-5 for _m in _s2["selfcheck"]["metrics"])
      and all(abs(_i["sigma_diff"]) < 1e-3 and abs(_i["q80_diff"]) < 1e-3 for _i in _s2["selfcheck"]["interval"]),
      "S2 回溯自证：逐时效 RMSE 复现主表（1 天 %s）、sigma 与 q80 倍数复现区间审计（8 档），判定 %s"
      % ("%.4f" % _s2["selfcheck"]["metrics"][0]["audit"], _s2["selfcheck"]["verdict"])),
     (V["s2_hi_zero"] + " 个时效" in d3txt and "已撤回" in d3txt and "提升 ≥ 2 倍" in d3txt and "召回 ≥ 80%" in d3txt and V["s2_line"] in d3txt,
      "docs/03 的 S2 判据改为可测的提升倍数 + 召回率，写明触发线 %s（= 成品页「高」档线）与旧写法已撤回（2/3 线 %s 个时效 0 次触发）" % (V["s2_line"], V["s2_hi_zero"])),
     ("**S2** 校准度（上界越过 p95 线" in readp("docs/05_报名表与提交清单.md")
      and "实际出现复合灾害的比例 ≥ 50%" not in readp("docs/05_报名表与提交清单.md"),
      "docs/05 的 S2 表述与 docs/03 同步（p95 线 + 提升倍数 + 召回率），不再写旧的 ≥ 50% 口径"),
     ('trigger_line' in readp("tools/settle_forecast.py") and 'risk_p95' in readp("tools/settle_forecast.py") and 'DEFAULT_LINE' in readp("tools/settle_forecast.py"),
      "结算器与成品页共用同一条触发线（tools/settle_forecast.py 的 trigger_line 读 priority_plan.json 的 risk_p95，取不到才回退 DEFAULT_LINE）"),
     ("低于背景率" in d2txt and "S2 判据原写法不可达" in d2txt and "s2_hindcast.py" in d2txt and "risk_p95" in d2txt and "534 天" in d2txt,
      "docs/02 第五节新增第 11 条披露（S2 原判据不可达、长时效提升低于背景率、结算器与页面共用 risk_p95）"),
     (os.path.exists(os.path.join(ROOT, "tools", "feedback_log.py"))
      and "S3_WEEKS = 4" in readp("tools/feedback_log.py") and "S4_MIN = 3" in readp("tools/feedback_log.py"),
      "S3 / S4 的达标线写在 tools/feedback_log.py 里（连续 4 个 ISO 周 / 3 条原计划-依据-结果齐全的事件），口径唯一"),
     (os.path.exists(os.path.join(ROOT, "data", "processed", "engagement_log.json"))
      and os.path.exists(os.path.join(ROOT, "data", "processed", "engagement_report.json")),
      "S3–S5 的台账与结算产物都在（engagement_log.json / engagement_report.json）"),
     ("feedback_log.py" in d3txt and "engagement_log.json" in d3txt and "engagement_report.json" in d3txt
      and "--add-s3" in d3txt and "--add-s4" in d3txt and "--add-s5" in d3txt and "ISO 周" in d3txt,
      "docs/03 的 S3 / S4 / S5 三行点名了台账与结算器（tools/feedback_log.py + engagement_log.json + engagement_report.json）"),
     ("tools/feedback_log.py" in d2txt and "engagement_report.json" in d2txt and "两个结算器自检" in d2txt,
      "docs/02 工具表写入了 S3–S5 的台账与结算器，preflight 那行也改成两个结算器自检"),
     ('["tools/feedback_log.py", "--selftest"]' in _pf_blk and _pf_n == 6,
      "preflight 第 5 步同时跑两个结算器自检（S1/S2 与 S3–S5），判定链仍为 %d 步" % _pf_n),
     (_fb_rc[0] == _fb["s3"]["best_run"] and _fb_rc[1] == _fb["s4"]["n"]
      and _fb_rc[2] == _fb["s5"]["tolerance_max"] and _fb_rc[3] == _fb["s5"]["false_alarms_max"],
      "审计独立复算 S3–S5 判定（自己按 ISO 周重算，不复用被审代码）：最长连续 %d 周、完整事件 %d 条、门槛 %s / 误报 %s，与 engagement_report.json 一致"
      % (_fb_rc[0], _fb_rc[1], _fb_rc[2], _fb_rc[3])),
     (V["fb_verdict"] == "pending" and V["fb_s3_best"] == "0" and V["fb_s4_n"] == "0",
      "没有外部记录时不写成达标：engagement_report.json 现为 pending（S3 最长 0 周 / S4 0 条 / S5 无记录）"),
    (('Python ' + V["py_env"]) in readp("README.md") and ('Python ' + V["py_env"]) in d2txt and ('Python ' + V["py_env"]) in d3txt
     and 'ssum.py' in readp("README.md") and 'ssum.py' in d2txt and 'ssum.py' in d3txt
     and 'Python 3.12 + numpy' not in readp("README.md") and 'Python 3.12 + numpy' not in d3txt,
     '运行环境写的是实际锁定的解释器（Python %s：README / docs/02 / docs/03 三处一致，并说明 pipeline/ssum.py 的朴素累加器），旧的 3.12 表述已清掉' % V["py_env"]),
     ("report_config" in readp("pipeline/ablation_audit.py") and '"deployed"' not in readp("pipeline/ablation_audit.py") and "AB['report_config']" in readp("pipeline/build_static.py") and 'AB["report_config"]' in readp("pipeline/verify_demo.py"),
      "消融审计的配置键已改名 report_config：报告口径的主表配置不再与部署口径同名混用，三个读取方同步"),
     (-1 < _rdp("# 12) 本地白化识别") < _rdp("# 17) 唯一成品页面") < _rdp("# 18) 全量核验") and -1 < _rdp("# 14) 保护与恢复优先级") < _rdp("# 17) 唯一成品页面"),
      "README 的分步复现次序可照做：成品页（17）排在白化识别（12）与优先级（14）之后，全量核验（18）最后"),
     ("第九十二点二百分位" in readp("docs/04_演示视频逐字稿与分镜.md") and "百分之二十点八到百分之八点九" in readp("docs/04_演示视频逐字稿与分镜.md"),
      "逐字稿里要念出口的两个数字与数据一致（档位 92.2%、降幅 20.8% 到 8.9%）"),
     ("HORIZON = 8" in readp("pipeline/fetch_forecast_drivers.py") and "抓未来 14 天" in d2txt and "未来 14 天" in readp("README.md"),
      "驱动抓取窗口写清楚：抓未来 14 天、页面与结算只用前 8 天（HORIZON = 8）"),
     (("不在每日链条里" not in d2txt) and ("lambda_audit.py" in readp("pipeline/refresh.py")),
      "lambda_audit.py 在每日链条里（refresh.py 的 STEPS 内），文档不再写「研究用、不在每日链条里」"),
     (os.path.exists(os.path.join(ROOT, "data/raw/semporna_sst_hourly_2022_2026.csv")) and not os.path.exists(os.path.join(ROOT, "data/raw/semporna_sst_hourly_2016_2026.csv")) and "semporna_sst_hourly_2022_2026.csv" in readp("pipeline/legacy/build_stress.py"),
      "原始海温 CSV 已改名到 2022_2026（内容确为 2022-11 起），读取方同步"),
     (V["vs2_dhw"] == "9.86" and V["vs_alert_share"] == "82.3",
      "两个官方站点的最大 DHW 与沙巴预警日占比由审计从 CSV 独立重算（沙巴 %s / 帕劳 %s；沙巴 alert >= 1 占 %s%%）" % (V["vs_maxdhw"], V["vs2_dhw"], V["vs_alert_share"])),
     (V["fk_total"] == V["lk_feats"] and V["fk_wave"] == "9" and V["fk_rain"] == "9" and V["fk_surge"] == "9"
      and V["fk_sst"] == "8" and V["raw_levels"] == "17" and V["raw_centred"] == "0"
      and "同样进入模型" in d2txt and "被名字显式排除" not in d2txt and "当日原始变量水平 | 18" not in d2txt
      and "f_surge_anom30" in d2txt,
      "模型输入构成与代码一致：feature_keys 共 %s 个（浪 %s / 雨 %s / 增水 %s / 海温 %s）、RAW_LEVELS %s 个且不含居中列，docs/02 不再写「f_surge 被排除 / 原始水平 18」"
      % (V["fk_total"], V["fk_wave"], V["fk_rain"], V["fk_surge"], V["fk_sst"], V["raw_levels"])),
     (V["bleach_cum_max"] == "8.1793" and V["bleach_cum_pp"] == "8.1794" and V["bleach_cum_max"] in d2txt and "8.1795" not in d2txt,
      "最强热浪累计强度写的是 bleaching_watch.json 的实际值（%s；三站点口径 %s），旧的 8.1795 已清掉" % (V["bleach_cum_max"], V["bleach_cum_pp"])),
     (V["tie_surge"] == "2" and V["tie_sst"] == "2" and "增水与海温各 2 天" in d2txt and "增水 0 天，海温 1 天" not in d2txt,
      "取等号天数按代码的未舍入分位数复算（增水 %s 天 / 海温 %s 天），docs/02 写清了两个口径" % (V["tie_surge"], V["tie_sst"])),
     (V["refresh_steps"] == "25" and V["lam_step"] == "10" and "25 步" in readp("docs/01_项目说明.md")
      and "其中 10 步" not in readp("docs/01_项目说明.md") and "refresh.py 第 10 步" in d2txt and "第 23 步" not in d2txt,
      "refresh 链条步数与代码一致（%s 步，lambda_audit 是第 %s 步），docs/01 与 docs/02 的旧数字已清掉" % (V["refresh_steps"], V["lam_step"])),
     (all(("pipeline" + chr(92) + s) in readp("README.md") for s in ("driver_error_audit.py", "index_variant_audit.py", "compound_label_audit.py"))
      and "# 16) 三项补充审计" in readp("README.md") and "# 18) 全量核验" in readp("README.md"),
      "README 分步复现补齐了成品页硬读的三项审计（driver_error / index_variant / compound_label），干净检出照做不再缺 JSON"),
     ("3 天（0.1600）低于常数均值" in d2txt and "全部高于常数均值基线" not in d2txt and "都高于常数均值 0.1637" not in d2txt
      and "也低 0.0007（噪声量级）" in d3txt and "全部高于常数均值基线" not in bst and "全部高于常数均值基线" not in _demo_html,
      "旧配置 3 天 RMSE 低于常数均值这一事实已在 docs/02 / docs/03 / 成品页生成器三处改正（不再写「全部/都高于」）"),
     ("5 天与基线基本打平" in d3txt and "5 天与 7 天反而略高于常数均值" not in d3txt,
      "docs/03 的 4 折技巧表述与 regression_skill.json 一致（5 天 0.1716 对 0.1718 打平、7 天 0.1725 对 0.1716 略高）"),
     ("显著高于 82.3% 的背景预警率" in d3txt and "≥ 10/13" not in d3txt and "10.7/13" in d3txt,
      "S6 判据收紧为「显著高于 82.3% 背景率」（n=13 时随机期望 10.7/13、P≈0.08），不再写低于随机期望的 ≥ 10/13"),
     (V["pp_heat_palau"] in d2txt and V["pp_heat_bunaken"] in d2txt and V["pp_heat_palau"] in _demo_html and V["pp_heat_bunaken"] in _demo_html,
      "三站点热暴露由 priority_plan.json 现算并与文档/页面一致（帕劳 %s、Bunaken %s）" % (V["pp_heat_palau"], V["pp_heat_bunaken"])),
    (_sa_bad == [] and _sa_facts["chars_total"] > 700,
     "docs/04 八个镜头的声明字数与秒数都与实际旁白逐段一致（合计 %d 字 / %.1f 秒），由 tools/script_audit.py 逐条核对" % (_sa_facts["chars_total"], _sa_facts["video_total"])),
    ("旁白全文 **%d 字**" % _sa_facts["chars_total"] in _d4t,
     "docs/04 声明了旁白全文 %d 字（与逐段字数之和一致）" % _sa_facts["chars_total"]),
    ("三天以上更强" not in _d4t, "docs/04 不得再写「三天以上更强」的错句（主表四个时效的 RMSE 都低于常数均值）"),
    ("千分之一量级" not in _d4t, "docs/04 不得把收缩校准相对满幅预报的增益说成相对常数均值的优势"),

    (_demo_html.count(chr(34) + "secnum" + chr(34)) == 6
     and all(("<span class=" + chr(34) + "secnum" + chr(34) + ">0%d</span>" % _i) in _demo_html for _i in (1, 2, 3, 4, 5, 6))
     and all(_t in _demo_html for _t in ("今日海况与热压力", "未来 8 天窗口", "珊瑚白化监测与预警", "保护与恢复优先级", "历史记录与官方对照", "方法与验证"))
     and _demo_html.count('href="#p') >= 6,
     "成品页六个板块按 01 今日海况与热压力 → 02 未来 8 天窗口 → 03 珊瑚白化监测与预警 → 04 保护与恢复优先级 → 05 历史记录与官方对照 → 06 方法与验证 编号，顶栏有六个锚点导航，卡片用 h3、板块用 h2（6 / 11）"),
    ("用途：为潜水运营商" in _demo_html and "2024 年太平洋白化预警区占比最高达 20.65%" in _demo_html and "为什么做这个：" not in _demo_html and "给谁用：" not in _demo_html and "为什么这件事重要：" not in _demo_html
     and _demo_html.index("用途：为潜水运营商") < _demo_html.index("模型样本外表现、参数与消融"),
     "首屏以「用途」写清受众与问题（含官方 2024 太平洋占比 20.65%），方法与实现细节下移到附录；不得再出现「为什么做这个 / 给谁用 / 为什么这件事重要」式标签"),
    ("另一条轴" in _demo_html and "海况轴" in _demo_html and "热压力轴" in _demo_html and "无需额外调度" not in _demo_html,
     "首屏改成双轴（海况轴 / 热压力轴），删掉与 SOP 表冲突的「度假村 / 政府无需额外调度」"),
    ("模型点预报" in _demo_html and "不是概率、也不是观测档位" in _demo_html,
     "8 天窗口表的连续输出列改名「模型点预报」，并写明不是概率、也不是观测档位"),
    ("0.034517" in _demo_html and "事后居中口径" in _demo_html,
     "增水两个口径并列披露（脚注 0.033 事后居中 / 模型与预报表 0.034517 因果）"),
    ("as-of 2026-09-18" in _demo_html and "28 天回望" in _demo_html,
     "学习模型卡标注 as-of 2026-09-18（标签需 28 天回望，比页面其他数字旧约四周）"),
    ("数据日期 2026/10/13" in _demo_html and "DHW ≥ 4 为 Alert Level 1" in _demo_html and "≥ 8 为 Alert Level 2" in _demo_html,
     "珊瑚大三角官方图补上数据日期与色标含义（引用官方产品必须标日期）"),
    (all(_s in _demo_html for _s in ("S1 台账", "S2 校准", "S3 真实使用", "S4 决策影响", "S5 误报耐受"))
     and "落地与影响：使用方、成本与 90 天验证" in _demo_html and "当前 0 家机构" in _demo_html and "如实报 pending" in _demo_html,
     "「落地与影响」卡列出 90 天验证计划 S1–S5 与当前状态，未记录时如实写 pending、不用 0 充数"),
    ("与 NOAA 完全一致" not in _d4t and "仅四个年份、样本小" in _d4t,
     "docs/04 镜头 7 的年际排序表述已收紧（4 个年份、样本小，不再写「完全一致」）"),
    ("2.07–3.68 倍" in readp("docs/05_报名表与提交清单.md") and "1 到 4 天达标" not in readp("docs/05_报名表与提交清单.md"),
     "docs/05 的 S2 回溯表述按 s2_hindcast.json 写清（提升倍数达标 2.07–3.68 倍，召回只有 1 天档越线）"),
    ("弃用了「未来 7 天是否成灾」这个二元分类器" in readp("docs/06_作品帖与发布草稿.md") and "弃用了分类器" not in readp("docs/06_作品帖与发布草稿.md"),
     "docs/06 把「弃用分类器」限定为未来 7 天复合灾害分类器（白化仍用 28 天二元概率模型）"),
    ("30.654 / 0.034 是 2026-10-15 的旧快照" in d2txt and "30.655" not in d2txt,
     "docs/02 引用的 model_report 快照数字与文件一致（30.654）"),
    ("六个板块" in _d0 and "共 11 张卡" in _d0 and "落地与影响：使用方、成本与 90 天验证" in _d0,
     "00_提交包说明.md 的板块数与卡数已同步为 6 / 11，并列出新增的落地卡"),
    (all(_t in _demo_html for _t in ("本板块三张表，各回答一个问题：", "① 今天该做什么", "② 未来 8 天：哪几天适合安排施工", "③ 三个站点：先去哪个做保护评估"))
     and "触发—响应 SOP" in _demo_html and "表中「今天适用」列标出今天触发的" in _demo_html,
     "04 板块三张表各自写明回答什么问题（① 今天该做什么 / ② 未来 8 天施工窗口 / ③ 跨站保护优先级），SOP 表的触发—响应标题与「今天适用」条数仍在"),
    (all(_t in _demo_html for _t in ("保护次序", "本站记录内百分位", "近 90 天多压力日（天）", "保护优先级得分", "触发条件（本站数据现算）", "时限或日期")),
     "04 板块表头写清含义（保护次序 / 本站记录内百分位 / 多压力日 / 保护优先级得分 / 触发条件（本站数据现算））"),
]
for good, msg in CODE_CHECKS:
    if good:
        print("  OK   " + msg)
    else:
        fails.append("代码与文档脱节：" + msg)
        print("  FAIL " + msg)
print()
print("=== md ↔ docx 一致性（内容，不只是时间戳）===")
try:
    from docx import Document
except Exception as e:
    Document = None
    fails.append("python-docx 不可用：%s" % e)
if Document is not None:
    for rel, lits in EXPECT:
        if not rel.startswith("docs/"):
            continue
        base = os.path.basename(rel).replace(".md", "")
        dx = os.path.join(ROOT, "docs_word", base + ".docx")
        if not os.path.exists(dx):
            fails.append("docx 缺失：" + base + ".docx")
            print("  MISS " + base + ".docx")
            continue
        if os.path.getmtime(dx) < os.path.getmtime(os.path.join(ROOT, rel)) - 1:
            fails.append("%s.docx 比 md 旧（改了 md 忘重生成 Word）" % base)
            print("  FAIL %s.docx 时间戳早于 md" % base)
        doc = Document(dx)
        txt = chr(10).join(p.text for p in doc.paragraphs)
        for tb in doc.tables:
            for row in tb.rows:
                for c in row.cells:
                    txt += chr(10) + c.text
        flat = txt.replace(" ", "")
        miss = [x for x in lits if x not in txt and x.replace(" ", "") not in flat]
        if miss:
            fails.append("%s.docx 内容缺少 %s" % (base, " / ".join(miss)))
            print("  FAIL %-24s docx 缺少: %s" % (base + ".docx", " / ".join(miss[:6])))
        else:
            print("  OK   %-24s %d 项在 Word 里也在" % (base + ".docx", len(lits)))
print()
print("=== 过期数字扫描 ===")
SCAN = ["docs/01_项目说明.md", "docs/02_数据与AI说明.md", "docs/03_90天验证计划.md",
        "docs/04_演示视频逐字稿与分镜.md", "docs/05_报名表与提交清单.md", "docs/06_作品帖与发布草稿.md", "README.md", "00_提交包说明.md"]
for rel in SCAN:
    path = os.path.join(ROOT, rel)
    if not os.path.exists(path):
        continue
    for i, line in enumerate(open(path, encoding="utf-8").read().splitlines(), 1):
        for bad, why in STALE.items():
            if bad not in line:
                continue
            # 例外：30.654 是三站点数据集（1,404 天）里仙本那自己的海温 p90，与主记录（1,446 天）的
            # 30.667 是两个口径，docs/02 第 8 条并列披露是正确行为（页面同理，见 STALE_PAGE）。
            if bad == "30.654" and "多套海温 p90" in line:
                continue
            # 例外：1,403 是帕劳官方虚拟站点的重叠期（bleaching_watch.json 现算），
            # 与跨站点迁移的「各 1,404 天」是两个量，同一行并列披露是正确行为。
            if bad == "1,403" and "帕劳" in line:
                continue
            fails.append("%s:%d 过期 %s" % (rel, i, bad))
            print("  FAIL %s:%d %s（%s）" % (rel, i, bad, why))
        if "2026-10-14" in line and not any(t in line for t in CTX_OK):
            fails.append("%s:%d 过期日期 2026-10-14" % (rel, i))
            print("  FAIL %s:%d 含旧结束日 2026-10-14（无历史语境）" % (rel, i))
        if "2026/10/14" in line:
            fails.append("%s:%d 过期 NOAA 日期" % (rel, i))
            print("  FAIL %s:%d 含旧 NOAA 日期 2026/10/14" % (rel, i))
_demo_path = os.path.join(ROOT, "demo", "index.html")
if os.path.exists(_demo_path):
    for i, line in enumerate(open(_demo_path, encoding="utf-8").read().splitlines(), 1):
        for bad, why in STALE_PAGE.items():
            if bad in line:
                fails.append("demo/index.html:%d 过期 %s" % (i, bad))
                print("  FAIL demo/index.html:%d %s（%s）" % (i, bad, why))
if not fails:
    print("  OK   七份文档均无过期数字")
print()
if fails:
    print("RESULT %d 处不一致：" % len(fails))
    for f in fails:
        print("  - " + f)
    sys.exit(1)
print("RESULT ALL CONSISTENT")
