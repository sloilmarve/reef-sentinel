#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""把《90 天验证计划》(docs/03) 里写下的数字，交给产生它的产物现算核对。

为什么需要它：五份提交材料里，①项目说明 / ③可运行成果 / ④数据与AI说明 都已有机器可核的
判据（tools/page_audit.py 数页面事实、tools/media_audit.py 读视频事实、tools/cost_model.py
算免费层容量），唯独 ⑤《验证计划》里的数字此前全靠手写。一次数据刷新就能让「计划里承诺的
数字」与「产物里现算的数字」分家，而评委当场跑一条命令就能看见。

本工具做两件事：
  1. 从 data/processed 的 15 个产物里现算《验证计划》引用的每一个数字；
  2. 断言这些数字确实写在 docs/03 里（先去掉 markdown 的 ** 再比，避免加粗把数字与单位切开），
     并断言跨文档的「主表 1 天排序 AUC」口径没有回流 —— 0.795 只允许出现在消融表 ext_lam5 行
     （即同一行还含 0.1414），因为主表 1 天 AUC 现算为 0.796。

纯标准库、不联网、不需要浏览器。
用法：
    python tools\\plan_audit.py
    python tools\\plan_audit.py --json
    python tools\\plan_audit.py --no-docs     # 只核产物，不核文档（文档未同步时不判失败）
"""

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROC = ROOT / "data" / "processed"
DOC03 = ROOT / "docs" / "03_90天验证计划.md"

# 会引用「主表 1 天排序 AUC」的文档；其中任何一行出现 0.795 都必须同时含 0.1414（消融表 ext_lam5 行）
CROSS_DOCS = [
    "docs/01_项目说明.md",
    "docs/02_数据与AI说明.md",
    "docs/03_90天验证计划.md",
    "docs/05_报名表与提交清单.md",
    "docs/06_作品帖与发布草稿.md",
    "00_提交包说明.md",
    "README.md",
    "README.en.md",
]
# 必须写出完整四时效主表 AUC 序列的文档
SEQ_DOCS = ["docs/01_项目说明.md", "docs/02_数据与AI说明.md", "docs/03_90天验证计划.md", "README.md"]
LEADS = ("1", "3", "7", "14")
LEADS_4F = ("1", "3", "5", "7")


def _load(name):
    with open(PROC / name, encoding="utf-8") as fh:
        return json.load(fh)


def _read(rel):
    """读材料。解压后的提交包里 00_提交包说明.md 位于 ai4climate/ 的上一层，
    与 tools/consistency_audit.py 的 readp() 保持同一套回退规则。"""
    p = ROOT / rel
    if not p.exists():
        p = ROOT.parent / rel
    with open(p, encoding="utf-8") as fh:
        return fh.read()


def _plain(text):
    """去掉 markdown 加粗，避免 ** 把数字与单位切开导致子串比较失败。"""
    return text.replace("**", "")


def _f(x, n):
    return ("%%.%df" % n) % x


def _seq(vals, n, sep=" / "):
    return sep.join(_f(v, n) for v in vals)


def _thousands(x):
    return "{:,}".format(int(x))


def facts():
    pp = _load("priority_plan.json")
    s2 = _load("s2_hindcast.json")
    rg = _load("regression_skill.json")
    bl = _load("blend_audit.json")
    lam = _load("lambda_audit.json")
    iv = _load("interval_audit.json")
    ms = _load("multisite_transfer.json")
    ab = _load("ablation_audit.json")
    mr = _load("model_report.json")
    lk = _load("leakage_audit.json")
    bw = _load("bleaching_watch.json")
    bf = _load("bleach_forecast.json")
    db = _load("dashboard_data.json")
    dv = _load("driver_error_audit.json")
    iva = _load("index_variant_audit.json")

    f = {}
    # —— 触发线 / SOP ——
    f["risk_p90"] = pp["thresholds"]["risk_p90"]
    f["risk_p95"] = pp["thresholds"]["risk_p95"]
    f["sop_n"] = len(pp["sop"])
    f["active_n"] = len(pp["today"]["active"])

    # —— S2 样本外回溯（3 折前推）——
    hs = sorted(s2["by_h"], key=int)
    ub = [s2["by_h"][h]["upper_bound"] for h in hs]
    f["s2_n_test"] = s2["by_h"]["1"]["n_test"]
    f["s2_base_pct"] = s2["base_rate_pct"]
    f["s2_h1"] = {k: ub[0][0][k] for k in ("n_trigger", "hit", "precision_pct", "recall_pct", "lift_vs_base")}
    precs = [x[0]["precision_pct"] for x in ub if x[0]["precision_pct"] is not None]
    f["s2_prec"] = (min(precs), max(precs))
    lifts = [x[0]["lift_vs_base"] for x in ub]
    f["s2_lift_short"] = (min(lifts[:4]), max(lifts[:4]))
    f["s2_lift_long"] = (min(lifts[4:]), max(lifts[4:]))
    f["s2_below_base"] = sum(1 for x in lifts if x < 1.0)
    f["s2_hi_zero"] = all(x[2]["n_trigger"] == 0 for x in ub)
    # 产物自己的结论句也必须与 by_h 现算的区间一致（区间写在 s2_hindcast.py 里，不能手写）
    f["s2_verdict_range"] = "%.1f%% 到 %.1f%%" % f["s2_prec"]
    f["s2_verdict_ok"] = f["s2_verdict_range"] in s2.get("original_verdict", "")

    # —— 4 折扩展窗前推（regression_skill）——
    f["rg_rmse"] = [rg[h]["model_rmse"] for h in LEADS_4F]
    f["rg_pers"] = rg["1"]["pers_rmse"]
    f["rg_clim"] = rg["1"]["clim_rmse"]
    f["rg_flat"] = rg["1"]["flat_rmse"]
    f["rg_flat_357"] = [rg[h]["flat_rmse"] for h in ("3", "5", "7")]

    # —— 方差收缩校准 ——
    f["bl_beta"] = [bl[h]["beta_star"] for h in LEADS]
    f["bl_rmse"] = [bl[h]["blend_rmse"] for h in LEADS]
    f["bl_flat"] = [bl[h]["flat_rmse"] for h in LEADS]
    f["bl_margin"] = [bl[h]["flat_rmse"] - bl[h]["blend_rmse"] for h in LEADS[1:]]
    f["bl_auc"] = [bl[h]["blend_auc"] for h in LEADS]

    # —— 正则强度扫描 ——
    # 注意：这里必须用朴素逐项累加，不能用 sum()。CPython 3.12 起 sum() 对浮点改用
    # 补偿求和（Neumaier），会把 λ=6400 的四时效均值从 0.6585000000000001 变成 0.6585，
    # 四舍五入后从 0.659 变 0.658 —— 与项目固定 Python 3.10 + pipeline/ssum.py 的口径分家。
    def _nsum(xs):
        t = 0.0
        for x in xs:
            t += float(x)
        return t

    mean_auc = {}
    for lam_v in lam["grid"]:
        vals = [lam["horizons"][h]["per_lam"][str(lam_v)]["auc"] for h in LEADS]
        mean_auc[lam_v] = _nsum(vals) / len(vals)
    f["lam_mean"] = mean_auc
    f["lam_peak_lam"] = max(mean_auc, key=lambda k: mean_auc[k])
    f["lam_peak_auc"] = mean_auc[f["lam_peak_lam"]]
    f["lam_min_auc"] = min(mean_auc.values())
    f["lam_best_per_lead"] = [
        min(lam["horizons"][h]["per_lam"], key=lambda k: lam["horizons"][h]["per_lam"][k]["rmse"])
        for h in LEADS
    ]
    f["lam_rmse_at50"] = [lam["horizons"][h]["per_lam"]["50"]["rmse"] for h in LEADS]

    # —— 区间校准 ——
    covs = [iv[k]["coverage_1sigma"] for k in iv]
    q80s = [iv[k]["q80_multiplier"] for k in iv]
    f["iv_cov"] = (min(covs), max(covs))
    f["iv_q80"] = (min(q80s), max(q80s))

    # —— 跨站点迁移 ——
    grids = []
    for site in ms["sites"]:
        skill = site.get("skill", {})
        for h in LEADS:
            if h in skill:
                grids.append((site["slug"], h, skill[h]["model_auc"], skill[h]["pers_auc"]))
    f["ms_days"] = ms["sites"][0]["days"]
    f["ms_grids"] = len(grids)
    f["ms_wins"] = sum(1 for g in grids if g[2] > g[3])
    losses = [g for g in grids if g[2] <= g[3]]
    f["ms_loss"] = losses[0] if losses else None

    # —— 消融表 ——
    cfg = {c["id"]: c for c in ab["configs"]}
    f["ab_base"] = [cfg["base_lam5"]["by_h"][h]["rmse"] for h in LEADS]
    f["ab_base_auc"] = [cfg["base_lam5"]["by_h"][h]["auc"] for h in LEADS]
    f["ab_report"] = ab["report_config"]
    f["ab_rep_rmse"] = [cfg[ab["report_config"]]["by_h"][h]["rmse"] for h in LEADS]
    f["ab_rep_auc"] = [cfg[ab["report_config"]]["by_h"][h]["auc"] for h in LEADS]
    f["ab_gain_pct"] = [
        100.0 * (cfg["base_lam5"]["by_h"][h]["rmse"] - cfg[ab["report_config"]]["by_h"][h]["rmse"])
        / cfg["base_lam5"]["by_h"][h]["rmse"]
        for h in LEADS
    ]
    f["ab_ext_lam5_14"] = cfg["ext_lam5"]["by_h"]["14"]["rmse"]
    f["ab_base_inner_auc"] = [cfg["base_inner"]["by_h"][h]["auc"] for h in ("3", "7")]

    # —— 学习型白化预警的诚实负结果 ——
    f["mr_auc"] = mr["overall"]["model_auc"]
    f["mr_brier"] = mr["overall"]["model_brier"]
    f["mr_clim"] = (mr["overall"]["clim_auc"], mr["overall"]["clim_brier"])

    # —— 特征无前视泄漏 ——
    f["lk_n_days"] = lk["n_days"]
    f["lk_features"] = lk["feature_count"]
    f["lk_max_abs"] = lk["max_abs_diff"]
    f["lk_leak_days"] = lk["analysis_leak_days_last8"]
    excluded = lk.get("analysis_cols_excluded") or []
    f["lk_centered_max"] = max((c["max_abs_diff"] for c in excluded), default=None)

    # —— 白化识别与官方对照 ——
    nc = bw["noaa_check"]
    el = nc["event_level"]
    vs = nc["vs_sabah"]
    f["bw_events"] = len(bw["events"])
    f["bw_spearman"] = nc["r_year_spearman"]
    f["bw_pearson"] = nc["r_year_pearson"]
    f["bw_event_hit"] = el["event_hit_rate"]
    f["bw_lag"] = el["mean_peak_lag_days"]
    f["bw_sabah_overlap"] = vs["overlap_days"]
    f["bw_sabah_bias"] = abs(vs["sst_bias_station_minus_official"])
    f["bw_sabah_r"] = vs["r_sst"]
    f["bw_sabah_hit"] = (vs["events_hit"], vs["events_total"])
    f["bw_sabah_bg"] = vs["background_alert_rate"]
    f["bw_sabah_lift"] = vs["lift"]
    f["bw_sabah_alert_days"] = vs["alert_days"]
    palau = [s for s in nc["vs_sites"] if s["overlap_days"] != vs["overlap_days"]][0]
    f["bw_palau_overlap"] = palau["overlap_days"]
    f["bw_palau_bias"] = abs(palau["bias_station_minus_official"])
    f["bw_palau_r"] = palau["r_sst"]
    f["bw_palau_max_dhw"] = palau["max_dhw"]

    # —— 学习型白化预警 ——
    bfm = bf["metrics"]["model"]
    f["bf_pr"] = bfm["pr_auc"]
    f["bf_rule"] = bf["metrics"]["rule_baseline"]["pr_auc"]
    f["bf_base"] = bf["metrics"]["base_rate"]
    f["bf_roc"] = bfm["roc_auc"]
    f["bf_folds"] = bf["by_fold"]

    # —— 成品页主表 / 年度病历 ——
    f["db_auc"] = [db["metrics"][h]["model_auc"] for h in LEADS]
    f["db_pers_auc"] = [db["metrics"][h]["pers_auc"] for h in LEADS]
    years = [y for y in db["yearly"] if y["days"] >= 365]
    f["db_compound_full"] = [y["compound"] for y in years]
    f["db_span_days"] = db["span"]["days"]

    # —— 驱动误差审计 ——
    f["dv_auc1"] = dv["horizons"]["1"]["auc_obs"]
    f["dv_persist_auc1"] = dv["horizons"]["1"]["auc_persist_drivers"]

    # —— 指数定义变体 ——
    f["iva_deployed"] = iva["deployed_variant"]
    f["iva_three_auc1"] = iva["variants"]["three_driver"]["by_h"]["1"]["model_auc"]
    f["iva_four_auc1"] = iva["variants"]["four_driver"]["by_h"]["1"]["model_auc"]
    f["iva_four_pers1"] = iva["variants"]["four_driver"]["by_h"]["1"]["pers_auc"]
    return f


def claims(f):
    """(标签, 必须出现在 docs/03 里的字符串) —— 全部由产物现算，不抄文档。"""
    c = []
    h1 = f["s2_h1"]
    c.append(("S2 触发线 p95", _f(f["risk_p95"], 3)))
    c.append(("S2 样本外天数", "%d 天" % f["s2_n_test"]))
    c.append(("S2 1 天触发次数", "%d 次触发" % h1["n_trigger"]))
    c.append(("S2 1 天命中数", "命中 %d" % h1["hit"]))
    c.append(("S2 1 天精确率", "精确率 %.1f%%" % h1["precision_pct"]))
    c.append(("S2 1 天召回率", "召回率 %.1f%%" % h1["recall_pct"]))
    c.append(("S2 1 天提升", "提升 %.2f 倍" % h1["lift_vs_base"]))
    c.append(("S2 背景率", "背景率 %.2f%%" % f["s2_base_pct"]))
    c.append(("S2 精确率区间", "%.1f%%\u2013%.1f%%" % f["s2_prec"]))
    c.append(("S2 短时效提升区间", "%.2f\u2013%.2f 倍" % f["s2_lift_short"]))
    c.append(("S2 长时效提升区间", "%.2f\u2013%.2f 倍" % f["s2_lift_long"]))

    c.append(("4 折 1 天 RMSE", _f(f["rg_rmse"][0], 4)))
    c.append(("4 折 1 天持续预报", _f(f["rg_pers"], 4)))
    c.append(("4 折 1 天气候平均", _f(f["rg_clim"], 4)))
    c.append(("4 折 1 天常数均值", _f(f["rg_flat"], 4)))
    c.append(("4 折 3/5/7 天 RMSE", _seq(f["rg_rmse"][1:], 4)))
    c.append(("4 折 3/5/7 天常数均值", _seq(f["rg_flat_357"], 4)))

    c.append(("收缩系数 β*", _seq(f["bl_beta"], 1)))
    c.append(("收缩后 RMSE", _seq(f["bl_rmse"], 4)))
    c.append(("收缩后对常数均值", _seq(f["bl_flat"], 4)))
    c.append(("收缩后 3/7/14 天优势", _seq(f["bl_margin"], 4)))

    c.append(("λ 扫描峰值", _f(f["lam_peak_auc"], 3)))
    c.append(("λ 扫描峰值位置", "λ = %d" % f["lam_peak_lam"]))
    c.append(("λ 扫描最小值", _f(f["lam_min_auc"], 3)))
    c.append(("λ 扫描逐时效最优", _seq([int(x) for x in f["lam_best_per_lead"]], 0)))
    c.append(("固定 λ=50 的 RMSE", _seq(f["lam_rmse_at50"], 4)))

    c.append(("区间覆盖率区间", "%.1f%% 到 %.1f%%" % f["iv_cov"]))
    c.append(("80% 区间倍数区间", "%.2f 到 %.2f 倍" % f["iv_q80"]))

    c.append(("跨站点天数", "%s 天" % _thousands(f["ms_days"])))
    c.append(("跨站点胜出格数", "%d 格" % f["ms_wins"]))
    if f["ms_loss"]:
        c.append(("跨站点唯一落败格", "%.3f 对 %.3f" % (f["ms_loss"][2], f["ms_loss"][3])))

    c.append(("消融上一版 1 天 RMSE", _f(f["ab_base"][0], 4)))
    c.append(("消融上一版 3 天 RMSE", _f(f["ab_base"][1], 4)))
    c.append(("消融上一版 7/14 天 RMSE", _seq(f["ab_base"][2:], 4)))
    c.append(("消融报告口径 RMSE", _seq(f["ab_rep_rmse"], 4)))
    c.append(("消融报告口径 AUC", _seq(f["ab_rep_auc"], 3)))
    c.append(("消融上一版 AUC", _seq(f["ab_base_auc"], 3)))
    c.append(("消融 RMSE 降幅", _seq(f["ab_gain_pct"], 1, sep="% / ") + "%"))
    c.append(("消融只加特征 14 天", _f(f["ab_ext_lam5_14"], 4)))
    c.append(("消融只用内窗 CV 3/7 天 AUC", _seq(f["ab_base_inner_auc"], 3)))

    c.append(("诚实负结果 AUC", _f(f["mr_auc"], 3)))
    c.append(("诚实负结果 Brier", _f(f["mr_brier"], 3)))
    c.append(("诚实负结果气候基线", "%s / %s" % (_f(f["mr_clim"][0], 3), _f(f["mr_clim"][1], 3))))

    c.append(("泄漏审计天数", _thousands(f["lk_n_days"])))
    c.append(("泄漏审计特征数", "%d 个特征" % f["lk_features"]))
    c.append(("泄漏审计最大偏差", _f(f["lk_max_abs"], 0)))
    c.append(("泄漏审计居中列天数", "%d 天" % f["lk_leak_days"]))
    if f["lk_centered_max"] is not None:
        c.append(("泄漏审计居中列最大偏差", _f(f["lk_centered_max"], 3)))

    c.append(("热浪事件数", "%d 次热浪" % f["bw_events"]))
    c.append(("年度排序 Spearman", "Spearman = %.3f" % f["bw_spearman"]))
    c.append(("年度相关系数", _f(f["bw_pearson"], 3)))
    c.append(("全流域事件级命中率", "%.1f%%" % f["bw_event_hit"]))
    c.append(("官方峰值滞后", "%.1f 天" % f["bw_lag"]))
    c.append(("沙巴站重叠天数", _thousands(f["bw_sabah_overlap"])))
    c.append(("沙巴站事件级命中", "%d/%d" % f["bw_sabah_hit"]))
    c.append(("沙巴站海温偏差", "%.3f °C" % f["bw_sabah_bias"]))
    c.append(("沙巴站相关系数", "r = %.3f" % f["bw_sabah_r"]))
    c.append(("沙巴站背景预警率", "%.1f%%" % f["bw_sabah_bg"]))
    c.append(("沙巴站提升倍数", "%.2f 倍" % f["bw_sabah_lift"]))
    c.append(("帕劳站重叠天数", _thousands(f["bw_palau_overlap"])))
    c.append(("帕劳站海温偏差", "%.3f °C" % f["bw_palau_bias"]))
    c.append(("帕劳站相关系数", "r = %.3f" % f["bw_palau_r"]))
    c.append(("帕劳站最高 DHW", _f(f["bw_palau_max_dhw"], 2)))

    c.append(("白化预警池化 PR-AUC", _f(f["bf_pr"], 3)))
    c.append(("白化预警规则基线", _f(f["bf_rule"], 3)))
    c.append(("白化预警基准发生率", _f(f["bf_base"], 3)))
    c.append(("白化预警 ROC-AUC", _f(f["bf_roc"], 3)))
    # 文档只引用第 3 / 4 折的反例（第 3 折规则 1.000 而模型 0.499，第 4 折两者都是 0.000）
    for i in (2, 3):
        fold = f["bf_folds"][i]
        c.append(("白化预警第 %d 折模型 PR-AUC" % (i + 1), _f(fold["model_pr_auc"], 3)))
        c.append(("白化预警第 %d 折规则 PR-AUC" % (i + 1), _f(fold["rule_pr_auc"], 3)))

    c.append(("SOP 动作条数", "%d 条" % f["sop_n"]))
    c.append(("今日适用条数", "%d 条" % f["active_n"]))

    full_years = f["db_compound_full"]
    c.append(("完整年份复合灾害日下界", "%d 到" % min(full_years)))
    c.append(("完整年份复合灾害日上界", "%d 个复合灾害日" % max(full_years)))
    return c


def audit(doc=None, docs=True):
    f = facts()
    failures = []

    # 产物自洽：跨站点胜出格数 + 主表 1 天 AUC 必须与指数变体审计一致
    if f["ms_wins"] != f["ms_grids"] - 1:
        failures.append("跨站点迁移：%d 个格子里只有 %d 格胜出，与文档口径（仅 1 格落败）不符"
                        % (f["ms_grids"], f["ms_wins"]))
    if abs(f["db_auc"][0] - f["iva_three_auc1"]) > 0.0005:
        failures.append("主表 1 天 AUC（%.4f）与指数变体审计的部署定义（%.4f）不一致"
                        % (f["db_auc"][0], f["iva_three_auc1"]))
    if f["s2_below_base"] != 3:
        failures.append("S2 长时效低于背景率的时效数是 %d，文档写的是 3（5 / 7 / 8 天）" % f["s2_below_base"])
    if not f["s2_hi_zero"]:
        failures.append("以 2/3 为高档线时并非 8 个时效都触发 0 次，文档的撤回理由需要重写")
    if not f["s2_verdict_ok"]:
        failures.append("s2_hindcast.json 的结论句里没有按 by_h 现算的精确率区间「%s」（区间必须由数据推出，不能手写）"
                        % f["s2_verdict_range"])
    if "1.2% 到 7.6%" in _read("pipeline/s2_hindcast.py"):
        failures.append("pipeline/s2_hindcast.py 仍写死旧的精确率区间「1.2% 到 7.6%」，应由 by_h 现算")

    if not docs:
        return f, failures

    text = _plain(doc if doc is not None else DOC03.read_text(encoding="utf-8"))
    for label, need in claims(f):
        if need not in text:
            failures.append("docs/03 缺少或写错：%s（产物现算应为「%s」）" % (label, need))

    # 跨文档：0.795 只允许出现在消融表 ext_lam5 行
    for rel in CROSS_DOCS:
        raw = _read(rel)
        for i, line in enumerate(raw.split(chr(10)), 1):
            if "0.795" in line and "0.1414" not in line:
                failures.append("%s:%d 出现旧的主表 1 天 AUC 0.795（现算 %s），应写 0.796"
                                % (rel, i, _f(f["db_auc"][0], 3)))
            if "0.795/0.665" in line:
                failures.append("%s:%d 出现无空格写法的旧 AUC 序列（0.795/0.665）" % (rel, i))
    live_seq = _seq(f["db_auc"], 3)
    for rel in SEQ_DOCS:
        if live_seq not in _plain(_read(rel)):
            failures.append("%s 未写出主表四时效 AUC 序列「%s」（产物现算）" % (rel, live_seq))
    return f, failures


def main(argv):
    as_json = "--json" in argv
    docs = "--no-docs" not in argv
    f, failures = audit(docs=docs)
    if as_json:
        print(json.dumps({"facts": f, "failures": failures}, ensure_ascii=False, indent=1, default=str))
        return 1 if failures else 0

    print("== 产物现算（data/processed）==")
    print("  触发线 p90 / p95        %s / %s" % (_f(f["risk_p90"], 3), _f(f["risk_p95"], 3)))
    print("  SOP 动作 / 今日适用      %d 条 / %d 条" % (f["sop_n"], f["active_n"]))
    print("  S2 样本外回溯            %d 天，背景率 %.2f%%，1 天档 %d 次触发 / 命中 %d / 精确率 %.1f%% / 召回率 %.1f%% / 提升 %.2f 倍"
          % (f["s2_n_test"], f["s2_base_pct"], f["s2_h1"]["n_trigger"], f["s2_h1"]["hit"],
             f["s2_h1"]["precision_pct"], f["s2_h1"]["recall_pct"], f["s2_h1"]["lift_vs_base"]))
    print("  S2 精确率区间            %.1f%%\u2013%.1f%%（长时效 %d 个低于背景率）" % (f["s2_prec"][0], f["s2_prec"][1], f["s2_below_base"]))
    print("  4 折前推 1 天 RMSE       %s（持续 %s / 气候 %s / 常数均值 %s）"
          % (_f(f["rg_rmse"][0], 4), _f(f["rg_pers"], 4), _f(f["rg_clim"], 4), _f(f["rg_flat"], 4)))
    print("  收缩校准 RMSE / 常数均值 %s / %s" % (_seq(f["bl_rmse"], 4), _seq(f["bl_flat"], 4)))
    print("  λ 扫描平均 AUC           峰值 %s（λ = %d），最低 %s，逐时效最优 λ %s"
          % (_f(f["lam_peak_auc"], 3), f["lam_peak_lam"], _f(f["lam_min_auc"], 3), _seq([int(x) for x in f["lam_best_per_lead"]], 0)))
    print("  区间覆盖率 / 80%% 倍数   %.1f%% 到 %.1f%% / %.2f 到 %.2f 倍"
          % (f["iv_cov"][0], f["iv_cov"][1], f["iv_q80"][0], f["iv_q80"][1]))
    print("  跨站点迁移               %d 天，%d/%d 格排序 AUC 高于持续预报" % (f["ms_days"], f["ms_wins"], f["ms_grids"]))
    print("  消融 上一版 / 报告口径   %s / %s（AUC %s / %s）"
          % (_seq(f["ab_base"], 4), _seq(f["ab_rep_rmse"], 4), _seq(f["ab_base_auc"], 3), _seq(f["ab_rep_auc"], 3)))
    print("  白化识别事件 / Spearman  %d 次 / %.3f（年相关 %.3f，事件级 %.1f%%，滞后 %.1f 天）"
          % (f["bw_events"], f["bw_spearman"], f["bw_pearson"], f["bw_event_hit"], f["bw_lag"]))
    print("  官方站点对照            沙巴 %s 天（偏差 %.3f °C / r = %.3f / 背景 %.1f%%）；帕劳 %s 天（偏差 %.3f °C / r = %.3f）"
          % (_thousands(f["bw_sabah_overlap"]), f["bw_sabah_bias"], f["bw_sabah_r"], f["bw_sabah_bg"],
             _thousands(f["bw_palau_overlap"]), f["bw_palau_bias"], f["bw_palau_r"]))
    print("  白化预警 PR-AUC          %s（规则 %s / 基准 %s，ROC %s）"
          % (_f(f["bf_pr"], 3), _f(f["bf_rule"], 3), _f(f["bf_base"], 3), _f(f["bf_roc"], 3)))
    print("  主表四时效 AUC           %s（持续预报 %s）" % (_seq(f["db_auc"], 3), _seq(f["db_pers_auc"], 3)))

    if failures:
        print("")
        for x in failures:
            print("FAIL " + x)
        print("RESULT %d ITEM(S) NEED ATTENTION" % len(failures))
        return 1
    print("")
    print("RESULT ALL PASS（《验证计划》引用的每个数字都由 data/processed 现算，且与 docs/03 一致）")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
