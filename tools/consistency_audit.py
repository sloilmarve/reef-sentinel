# -*- coding: utf-8 -*-
"""材料数字一致性审计（v2）：从 data/processed 的事实产物反推应出现的数字，再回扫文档。

用法： python tools/consistency_audit.py   （退出码 0 = 一致，1 = 有不一致）
v2 变化：按每份文档自己的数字精度核对；过期数字改为上下文感知（"2026-10-14 → 2026-10-15" 这类历史实测表述不算过期）。
"""
import json, os, re as _re, sys
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
_lamavg = {k: sum(la["horizons"][h]["per_lam"][k]["auc"] for h in ("1", "3", "7", "14")) / 4.0 for k in la["horizons"]["1"]["per_lam"]}
V["lam_avg5"] = "%.3f" % _lamavg["5"]
V["lam_avg_peak"] = "%.3f" % max(_lamavg.values())
V["lam_avg_min"] = "%.3f" % min(_lamavg.values())
_sem = [s for s in ms["sites"] if s["slug"] == "semporna"][0]["skill"]
V["ms_sem14_model"] = "%.3f" % _sem["14"]["model_auc"]
V["ms_sem14_pers"] = "%.3f" % _sem["14"]["pers_auc"]
V["ms_gap_min"] = "%.3f" % min(s["skill"][h]["model_auc"] - s["skill"][h]["pers_auc"] for s in ms["sites"] for h in ("1", "3", "7", "14"))
V["lk_feats"] = "%d" % lk["feature_count"]
V["lk_cuts"] = "%d" % len(lk["cuts"])
V["lk_max"] = "%g" % lk["max_abs_diff"]
V["lk_analysis_max"] = "%.3f" % lk["analysis_cols_excluded"][0]["max_abs_diff"]
V["lk_leak_days"] = "%d" % lk["analysis_leak_days_last8"]

EXPECT = [
    ("docs/01_项目说明.md", [V["days"] + " 天", V["sst_p90"], V["m1_3"], V["m3_3"], V["m7_3"], V["m14_3"],
                              V["d1"], V["d7"], V["end"], V["ref_secs"], V["c2024"], V["sst2026"],
                              V["noaa_glob"], V["noaa_pac"], V["noaa_rows"], V["ms_days"], V["ms_sites"],
                              V["cov_lo"], V["cov_hi"], V["q80_lo"], V["q80_hi"],
                              V["mhw_events"], V["mhw_pctl"], V["mhw_rho"], V["pp_score_semporna"],
                               V["bf_pr_auc"], V["bf_pr_auc_rule"], V["bf_base"], V["vs_hit"], V["vs_bias"], V["vs_r"], V["vs2_bias"], V["vs2_r"], V["sop_n"], V["hot2025"], V["hot2026"], V["zero_share"], "严格只用当日及以前", "66 个特征"]),
    ("docs/02_数据与AI说明.md", [V["days"], V["start"], V["end"], V["sst_p90"], V["m1"], V["p1"], V["m3"], V["p3"],
                                  V["m7"], V["p7"], V["m14"], V["p14"], V["noaa_glob"],
                                  V["ms_days"], V["ms_auc1_max"], V["ms_auc1_palau"], V["ms_auc3_min"], V["ms_bunaken_rmse3"], V["ms_bunaken_auc3"],
                                  V["cov_lo"], V["cov_hi"], V["q80_lo"], V["q80_hi"],
                                  V["cov_surge_days"], V["cov_sst_days"], V["tie_p90_wh"], V["comp_gt"],
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
                                    "无前视泄漏", "surge_trail", "sl_still_trail", "事后分析量", "最大偏差 0.011", "66 个特征", "leakage_audit.py"]),
    ("docs/03_90天验证计划.md", [V["rs_m1"], V["rs_p1"], V["rs_c1"], V["rs_f1"], V["rs_m3"], V["rs_m5"], V["rs_m7"],
                                  V["rs_f3"], V["rs_f5"], V["rs_f7"], V["blend_rmse1"], V["blend_rmse3"], V["blend_rmse7"], V["blend_rmse14"], V["blend_beta1"],
                                  V["lam_avg5"], V["lam_avg_peak"], V["lam_avg_min"], V["cov_lo"], V["cov_hi"], V["q80_lo"], V["q80_hi"],
                                  V["ms_sem14_model"], V["ms_sem14_pers"], V["ms_gap_min"],
                                  V["ab_base1"], V["ab_base3"], V["ab_base7"], V["ab_base14"], V["ab_extlam5_14"],
                                  V["ab_baseinner_auc3"], V["ab_baseinner_auc7"], V["ab_gain1"], V["ab_gain3"], V["ab_gain7"], V["ab_gain14"],
                                  V["vs2_r"], "特征无前视泄漏", "leakage_audit.py", "66 个特征", "事后分析量", "截断",
                                   V["m1"], V["m3"], V["m7"], V["m14"]]),
    ("docs/04_演示视频逐字稿与分镜.md", ["02:56", "741 字", "8 个镜头", V["sop_n"], "8 天预报"]),
    ("docs/05_报名表与提交清单.md", [V["days"], V["start"], V["d1"], V["d3"], V["d7"], V["d14"], V["noaa_glob"], V["noaa_pac"], V["zero_share"]]),
    ("docs/06_作品帖与发布草稿.md", [V["days"], V["d1"], V["d3"], V["d7"], V["d14"], V["m3"], V["m7"], V["m14"],
                                    V["comp_gt"], V["c2024"], V["ref_secs"], V["noaa_glob"], V["noaa_pac"], V["noaa_early"], V["noaa_rows"],
                                    V["bf_pr_auc"], V["bf_pr_auc_rule"], V["bf_base"], V["vs_hit"], V["vs_bias"], V["vs_r"], V["zero_share"]]),
    ("README.md", [V["days"], V["sst_p90"], V["m1"], V["m7"], V["d1"], V["end"], V["ref_secs"], V["ms_days"], V["ms_auc1_max"], V["cov_lo"], V["cov_hi"], V["lam400_rmse14"], V["lam400_auc3"], V["blend_rmse1"], V["blend_gain1"], V["blend_gain14"], V["bf_pr_auc"], V["bf_pr_auc_rule"], V["mhw_events"], V["mhw_pctl"], V["pp_score_semporna"], V["pp_palau_mhw"], V["pp_longest"], V["ev_hit"], V["ev_lift"], V["sop_n"], V["vs_overlap"], V["vs_bias"], V["vs_r"], V["vs2_bias"], V["vs2_r"], V["vs_dhw"], V["zero_share"]]),
    ("00_提交包说明.md", [V["days"], V["m1"], V["m7"], V["p1"], V["ms_days"], V["ms_auc1_max"], V["cov_lo"], V["cov_hi"], V["q80_lo"], V["q80_hi"], V["lam400_rmse14"], V["blend_rmse1"], V["blend_gain1"], V["bf_pr_auc"], V["bf_pr_auc_rule"], V["mhw_events"], V["pp_score_semporna"], V["pp_w4"], V["pp_palau_mhw"], V["ev_hit"], V["ev_lift"], V["vs_overlap"], V["vs_bias"], V["vs_r"], V["vs2_bias"], V["vs2_r"], V["vs_dhw"], V["vs_mmm_off"], V["zero_share"], V["video_len"]]),
]

STALE = {"1444": "旧记录期天数", "30.654": "旧海温 p90", "30.65 °C": "旧海温 p90（应为 30.667）", "72.8%": "旧 0 值占比", "实测约 6 秒": "旧刷新耗时", "1,411": "旧逐日海温天数（应为 1,412）", "7.5 秒": "旧刷新耗时（应为约 30 秒）", "（至 10-15）": "旧年度表头（记录期已到 10-16）", "0.1461": "旧 1 天模型 RMSE（应为 0.1406）", "0.1550": "旧消融基础配置 RMSE", "0.1744": "旧消融基础配置 RMSE", "0.1719": "旧消融基础配置 RMSE", "0.1717": "旧消融基础配置 RMSE", "0.1695": "旧 λ=5 的 3 天 RMSE", "0.1726": "旧 λ=5 的 14 天 RMSE", "0.1456": "旧 λ=400 的 1 天 RMSE", "0.1601": "旧 λ=400 的 7 天 RMSE", "0.1632": "旧 λ=400 的 14 天 RMSE", "0.477": "旧 9 格最低 AUC", "58 个特征": "旧特征数（应为 66）", "40 特征": "旧特征数（应为 49 / 66）", "1,403": "旧跨站点天数（应为 1,404）", "0.9550": "旧保护优先级得分（应为 0.9604）", "1,405": "旧海平面覆盖天数（应为 1,406）", "0.550 对 0.410": "旧 9 格最低 AUC 对比（应为 0.558 对 0.404）", "0.818": "旧 1 天分类器 AUC（应为 0.819）", "0.843": "旧 3 天持续预报 AUC（应为 0.840）", "0.902": "旧 7 天持续预报 AUC（应为 0.900）", "0.947": "旧 14 天持续预报 AUC（应为 0.945）", "0.776 / 0.800 / 0.744": "旧跨站点 1 天 AUC（应为 0.779 / 0.801 / 0.742）", "12 格全部高于": "旧跨站点全胜表述（现为 11/12）", "12 of 12 cells": "旧跨站点全胜表述（现为 11 of 12）", "只赢 0.011": "旧窄优势表述（现为低 0.004）",}
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
if _su:
    _site_ok = (_su in _demo_html) and (_su in readp("README.md")) and (_su in d3txt) and (_su in readp("00_提交包说明.md"))
    _site_msg = "已部署：公开网址同时出现在 site.json / 成品页 / README / docs/03 / 00_提交包说明（" + _su + "）"
else:
    _site_ok = ("在线地址：" not in _demo_html) and ("单文件离线页" in _demo_html)
    _site_msg = "未部署：site.json 的 site_url 为空，成品页页脚如实写「单文件离线页」，不编造网址"
# 注意：下面这些针是拆开拼出来的，不然本文件自己就会命中自己（这条检查会扫描本项目所有文本文件）
BAD_PATH_PAT = ("deepseek-" + "harness", "dsh-" + "home", "dsh-" + "runtimes", "slo" + "il")
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
_d4_shots = _re.findall(r"（(\d+) 秒 / (\d+) 字）", d4txt)
_d4_chars = sum(int(c) for _s, c in _d4_shots)
_d4_secs = sum(int(s) for s, _c in _d4_shots)
_d4_ok = (len(_d4_shots) == 8 and _d4_chars == 741 and _d4_secs == 176
          and "02:56" in d4txt and int(round(_d4_chars / 4.2)) == _d4_secs)
_d4_msg = ("演示视频逐字稿自洽：%d 个镜头、旁白 %d 字、合计 %d 秒（= 02:56），与 4.2 字/秒 口播速度一致"
           % (len(_d4_shots), _d4_chars, _d4_secs)) if _d4_ok else (
           "演示视频逐字稿与总时长不自洽：%d 个镜头 / %d 字 / %d 秒（应为 8 / 741 / 176，且含 02:56）"
           % (len(_d4_shots), _d4_chars, _d4_secs))

_d0 = readp("00_提交包说明.md")
_d0_cards = ["消融：两个改动各自值多少", "白化预警：把「规则识别」升级为「学习模型」", "白化热压力：本地监测与识别", "保护与恢复优先级", "官方对照：NOAA CRW 白化预警区占比"]
_n_h2 = len(_re.findall(r"<h2>", _demo_html))
_d0_ok = all(_c in _d0 for _c in _d0_cards) and _n_h2 == 17
_d0_msg = ("提交包说明的卡片清单与成品页一致（页内 17 张卡，最新几张都在清单里）" if _d0_ok else
           "提交包说明的卡片清单与成品页不一致（页内 %d 张卡，应 17 张，且清单要含最新几张）" % _n_h2)

_allpicks = [int(x) for h in ("1", "3", "7", "14") for x in dash["metrics"][h]["inner_lambda"]]
_mode_lam = max(sorted(set(_allpicks)), key=_allpicks.count)
_dash_hot = {y["year"]: y["hot_days"] for y in dash["yearly"]}
_bw_hot = {str(y["year"]): y["hot_days"] for y in bw["yearly"]}
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
    (os.path.exists(os.path.join(ROOT, "tools", "reviewer_repro.py")) and "reviewer_repro.py" in d2txt and "reviewer_repro.py" in d3txt and "reviewer_repro.py" in readp("tools/preflight.py"),
     "评审视角复算 tools/reviewer_repro.py 已实现、写进 docs/02 与 docs/03，并作为最后一步并入 tools/preflight.py"),
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
            if bad in line:
                fails.append("%s:%d 过期 %s" % (rel, i, bad))
                print("  FAIL %s:%d %s（%s）" % (rel, i, bad, why))
        if "2026-10-14" in line and not any(t in line for t in CTX_OK):
            fails.append("%s:%d 过期日期 2026-10-14" % (rel, i))
            print("  FAIL %s:%d 含旧结束日 2026-10-14（无历史语境）" % (rel, i))
        if "2026/10/14" in line:
            fails.append("%s:%d 过期 NOAA 日期" % (rel, i))
            print("  FAIL %s:%d 含旧 NOAA 日期 2026/10/14" % (rel, i))
if not fails:
    print("  OK   七份文档均无过期数字")
print()
if fails:
    print("RESULT %d 处不一致：" % len(fails))
    for f in fails:
        print("  - " + f)
    sys.exit(1)
print("RESULT ALL CONSISTENT")
