# -*- coding: utf-8 -*-
# verify_demo.py - 单页静态成品的全量核验：把页面里渲染出来的每个关键数字与几何位置，重新用源数据算一遍并比对。
import base64, json, os, sys
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
P = lambda *a: os.path.join(ROOT, *a)
D = json.load(open(P("data", "processed", "dashboard_data.json"), encoding="utf-8"))
NB = json.load(open(P("data", "processed", "noaa_crw_panel.json"), encoding="utf-8"))
MS = json.load(open(P("data", "processed", "multisite_transfer.json"), encoding="utf-8"))
IA = json.load(open(P("data", "processed", "interval_audit.json"), encoding="utf-8"))
LA = json.load(open(P("data", "processed", "lambda_audit.json"), encoding="utf-8"))
html = open(P("demo", "index.html"), encoding="utf-8").read()
fails = []
def ok(c, msg):
    print(("  OK   " if c else "  FAIL ") + msg)
    if not c:
        fails.append(msg)
def f(v, k=2):
    return ("%." + str(k) + "f") % float(v)

print("== 单页属性 ==")
_n_script = html.lower().count("<script")
ok(_n_script == 1 and 'src="http' not in html.lower() and "<link" not in html.lower(),
   "成品页仅含 1 个内联渐进增强脚本、无任何外链脚本 / 样式（SCRIPT_TAGS=%d，离线可开）" % _n_script)
ok('class="navlinks"' in html and "details.more" in html and "本页怎么读" not in html,
   "渐进增强脚本只做吸顶导航高亮与展开 / 收起，全部内容为预渲染（无 JS 时仍可读）")
ok("getElementById" not in html, "渐进增强脚本为原生 JS、无客户端数据绑定")
ok("dashboard.html" not in html, "页面不再引用交互版页面（项目已收敛为单页）")
ok("teleprompter" not in html, "页面不再引用提词器（已移出项目）")
ok("data:image/png;base64," in html, "官方区域图已内嵌为 data URI（单文件可离线打开）")
SITE_PATH = P("site.json")
ok(os.path.exists(SITE_PATH), "存在 site.json（在线地址的唯一来源）")
SITE = json.load(open(SITE_PATH, encoding="utf-8")) if os.path.exists(SITE_PATH) else {}
_url = str(SITE.get("site_url", "")).strip()
if _url:
    ok(_url in html, "页脚已写在线地址 %s（与 site.json 一致，不靠手改 HTML）" % _url)
else:
    ok("单文件离线页" in html, "尚未部署时页脚如实说明分发形态（单文件离线页）")
    ok("在线地址：" not in html, "尚未部署时页脚不出现空的在线地址")

print("== 载荷一致性 ==")
S = D["series"]
ok(D["span"]["days"] == len(S["date"]), "序列长度 %d == 数据窗口 %d 天" % (len(S["date"]), D["span"]["days"]))
ok(0.0 <= D["now"]["risk"] <= 1.0, "今日危险指数 %.3f 在 [0,1]" % D["now"]["risk"])
FH = D["forecast_meta"]["horizon"]
ok(len(D["forecast"]) == FH and FH >= 5, "预报 %d 个时效（载荷声明的时效数 %d，由海浪预报时效决定）" % (len(D["forecast"]), FH))
ok(D["forecast_meta"]["mode"] == "driven", "预报为数值天气预报驱动（mode=%s，驱动源 %s）" % (D["forecast_meta"]["mode"], D["forecast_meta"]["driver_source"]))
risks = [x["risk"] for x in D["forecast"]]
ok(len(set(risks)) > 1, "逐日预报随预报驱动变化（点预报不再是一条水平线）：%s" % ", ".join("%.3f" % v for v in risks))
ok(all("wh_max" in x and "rain" in x and "sst" in x for x in D["forecast"]), "每个时效都带当日预报驱动（浪 / 雨 / 海温）")
ok(all(x["lo"] <= x["risk"] <= x["hi"] for x in D["forecast"]), "每个预报都满足 lo <= risk <= hi")
ok(D["forecast_meta"]["band"] == "empirical-80", "预报区间口径为经验 80%% 区间（band=%s）" % D["forecast_meta"]["band"])
for x in D["forecast"]:
    kh = min(IA, key=lambda h: abs(int(h) - x["lead"]))
    want = float(IA[kh]["q80_multiplier"]) * float(IA[kh]["sigma"])
    ok(abs(x["half"] - want) <= 0.0011, "第 %d 天区间半宽 %.4f == 标定倍数 %.2f x sigma %.4f" % (x["lead"], x["half"], float(IA[kh]["q80_multiplier"]), float(IA[kh]["sigma"])))
    up = min(x["half"], 1.0 - x["risk"]); dn = min(x["half"], x["risk"])
    ok(abs((x["hi"] - x["risk"]) - up) <= 0.0011 and abs((x["risk"] - x["lo"]) - dn) <= 0.0011, "第 %d 天区间按半宽展开（上 %.3f / 下 %.3f，触及 0 或 1 时如实截断）" % (x["lead"], x["hi"] - x["risk"], x["risk"] - x["lo"]))
ok("80% 经验区间" in html, "页面上写明区间口径为 80% 经验区间")
_th = D["thresholds"]
_cand = [("降水", "rain", _th["rain"]["p90"], 1, " mm"), ("最大波高", "wh_max", _th["wave"]["p90"], 2, " m"), ("风暴增水", "surge", _th["surge"]["p90"], 3, " m")]
_rows = []
for _n, _k, _line, _kk, _u in _cand:
    _t = max(D["forecast"], key=lambda r: r.get(_k) or 0.0)
    _v = _t.get(_k) or 0.0
    _rows.append((_v / _line, _n, _t["date"], _v, _line, _kk, _u))
_rows.sort(key=lambda x: -x[0])
_ld = _rows[0]
ok("距触发线最近的驱动是 " in html and _ld[1] in html and _ld[2] in html and f(_ld[3], _ld[5]) in html and f(_ld[4], _ld[5]) in html and f(_ld[0] * 100, 0) + "%" in html,
   "预报卡点名距触发线最近的驱动（%s %s：%.2f 对 p90 %.2f，达 %.0f%%；三类都未越线则说明全期维持低档）" % (_ld[1], _ld[2], _ld[3], _ld[4], _ld[0] * 100))
_hot = [x for x in D["forecast"] if (x.get("sst") or 0.0) > _th["sst"]["p90"]]
ok(str(len(_hot)) + " 天预报海温高于记录期 p90" in html, "预报卡把热压力单列（%d 天预报海温高于 p90，明示不计入指数）" % len(_hot))
cov_lo = min(v["coverage_1sigma"] for v in IA.values()); cov_hi = max(v["coverage_1sigma"] for v in IA.values())
ok(f(cov_lo, 1) + "%" in html and f(cov_hi, 1) + "%" in html, "页面披露 ±1 RMSE 的实际覆盖率 %s%%-%s%%（高斯名义 68.3%%）" % (f(cov_lo, 1), f(cov_hi, 1)))
for h in ("1", "3", "7", "14"):
    m = D["metrics"][h]
    ok(m["model_rmse"] <= m["pers_rmse"], "h=%-3s 模型 RMSE %.4f 优于持续预报 %.4f（降 %.1f%%）" % (h, m["model_rmse"], m["pers_rmse"], (m["pers_rmse"] - m["model_rmse"]) / m["pers_rmse"] * 100))
    ok("flat_rmse" in m and "model_auc" in m and "pers_auc" in m, "h=%-3s 常数均值基线与排序 AUC 已写入载荷" % h)
    ok(f(m["flat_rmse"], 3) in html, "h=%-3s 常数均值 RMSE %s 已如实入表（与模型同为 %s 时也不隐藏）" % (h, f(m["flat_rmse"], 3), f(m["model_rmse"], 3)))
    ok(f(m["model_auc"], 3) in html and f(m["pers_auc"], 3) in html, "h=%-3s 排序 AUC %s / %s 已入表" % (h, f(m["model_auc"], 3), f(m["pers_auc"], 3)))
    ok(m["model_auc"] > m["pers_auc"], "h=%-3s 排序 AUC 模型 %.3f > 持续预报 %.3f" % (h, m["model_auc"], m["pers_auc"]))

BA = json.load(open(P("data", "processed", "blend_audit.json"), encoding="utf-8"))
ok("收缩系数" in html and "校准后 RMSE" in html, "页面含方差收缩校准对照表（收缩系数 β* / 校准后 RMSE）")
for h in ("1", "3", "7", "14"):
    b = BA[h]; m = D["metrics"][h]
    ok(abs(m["blend_rmse"] - b["blend_rmse"]) < 1e-9 and abs(m["blend_beta"] - b["beta_star"]) < 1e-9, "h=%-3s 载荷里的校准 RMSE %.4f / β*=%.1f 与 blend_audit.json 一致" % (h, b["blend_rmse"], b["beta_star"]))
    ok(f(b["blend_rmse"], 4) in html, "h=%-3s 校准后 RMSE %s 已入表" % (h, f(b["blend_rmse"], 4)))
    ok(b["blend_rmse"] < b["flat_rmse"], "h=%-3s 校准后 RMSE %.4f < 常数均值 %.4f（赢 %.2f%%）" % (h, b["blend_rmse"], b["flat_rmse"], b["gain_vs_flat_pct"]))
ok("成品页仍部署满幅预报" in html, "页面写明成品页仍部署满幅预报、收缩校准只作 RMSE 精度上限对照")

print("== 今日状态卡 ==")
now = D["now"]
for label, s in [("危险指数", f(now["risk"], 2)), ("海温", f(now["sst"], 2)), ("降水", f(now["rain"], 1)), ("波高", f(now["wave"], 2)), ("增水", f(now["surge"], 3)), ("超阈值项", str(now["n_haz"]) + " / 3")]:
    ok(s in html, "页面上出现今日 " + label + " = " + s)

print("== 预报图几何（viewBox 660x258）==")
W, H, pl, pr, pt, pb = 660, 258, 42, 16, 16, 46
iw, ih = W - pl - pr, H - pt - pb
F10 = D["forecast"]
maxv = max(0.45, max(x["hi"] for x in F10))
X = lambda i: pl + (i + 0.5) * iw / len(F10)
Y = lambda v: pt + ih - (v / maxv) * ih
bw = iw / len(F10) * 0.62
missing = []
for i, d in enumerate(F10):
    x0 = round(X(i) - bw / 2, 1)
    t1 = "x=\"" + str(x0) + "\""
    if t1 not in html:
        missing.append(str(d["lead"]))
    xp = round(X(i) - bw * 0.22, 1)
    if ("x=\"" + str(xp) + "\"") not in html:
        missing.append(str(d["lead"]) + "(point)")
    ok(pt <= Y(d["hi"]) <= pt + ih, "+%-2d 区间上界在绘图框内 y=%.1f（值 %.3f）" % (d["lead"], Y(d["hi"]), d["hi"]))
ok(not missing, "每个时效的柱子在页面上都能找到对应坐标（缺失：%s）" % (missing or "无"))
ok("0 0 660 258" in html, "forecast viewBox is 660x258")
p90 = 1.0 / 3.0
ok("p90 触发线" in html, "p90 触发线已标注（值 %.3f，四舍五入到 0.33）" % p90)

print("== 历史回看：近 180 天曲线与近 300 天条带（段 05）==")
_SEQ = D["series"]
ok("历史回看：近 180 天曲线与近 300 天逐日条带" in html, "段 05 已渲染近 180 天曲线与近 300 天逐日条带")
_HN = 180
_hrk = _SEQ["risk"][-_HN:]
_hpl, _hiw = 38, 660 - 38 - 14
_hih = 210 - 14 - 28
_hmv = max(0.45, max(_hrk))
_hX = lambda i: _hpl + (i / (_HN - 1)) * _hiw
_hY = lambda v: 14 + _hih - (v / _hmv) * _hih
_hpath = ""
for _i, _v in enumerate(_hrk):
    _hpath += (" L" if _i else " M") + str(round(_hX(_i), 1)) + "," + str(round(_hY(_v), 1))
ok(_hpath.strip() in html, "近 %d 天危险指数曲线逐点坐标与源数据一致" % _HN)
ok("0 0 660 210" in html, "历史曲线 viewBox is 660x210")
_BN = 300
_brk = _SEQ["risk"][-_BN:]
_bcp = _SEQ["compound"][-_BN:]
_bdt = _SEQ["date"][-_BN:]
_bmv = 0.34
for _v in _brk:
    if _v > _bmv:
        _bmv = _v
_bmiss = []
for _i in range(_BN):
    _hh = max(2, int(round((_brk[_i] / _bmv) * 100)))
    _tip = _bdt[_i] + " 危险指数 " + f(_brk[_i], 2) + ("（复合灾害日）" if _bcp[_i] else "")
    if ("height:" + str(_hh) + "%;background:") not in html or ('title="' + _tip + '"') not in html:
        _bmiss.append(_bdt[_i])
ok(not _bmiss, "近 %d 天逐日条带的高度与提示口径与源数据一致（缺失：%s）" % (_BN, _bmiss or "无"))
ok("background:var(--lv3)" in html and "background:var(--hair2)" in html, "近 300 天条带按危险指数分级实色着色、无半透明失真")
ok(html.count('class="bar"') == _BN, "条带恰好 %d 根逐日柱（页面共 %d 根）" % (_BN, html.count('class="bar"')))

print("== 年度病历表 ==")
for y in D["yearly"]:
    ok(str(y["compound"]) in html and f(y["max_sst"]) in html, "%s 年：复合灾害 %d 天 / 最高海温 %s °C 已渲染" % (y["year"], y["compound"], f(y["max_sst"])))

print("== 官方对照面板 ==")
R = NB["record"]
ok(str(NB["span"][0]) in html and str(NB["span"][1]) in html, "官方数据窗口 %s 至 %s 已标注" % (NB["span"][0], NB["span"][1]))
ok(str(R["global_year"]) + " 记录级" in html, "%d 年记录级标注已渲染（全球峰值 %.5f）" % (R["global_year"], R["global_max"]))
for e in NB["station_table"]:
    ok(f(e["global_max"] * 100, 2) + "%" in html and f(e["pacific_max"] * 100, 2) + "%" in html, "%s 年官方全球峰值 %s%% / 太平洋峰值 %s%% 已入表" % (e["year"], f(e["global_max"] * 100, 2), f(e["pacific_max"] * 100, 2)))
png = P("data", "external", "noaa_crw", "triangle_dhw.png")
expect = "data:image/png;base64," + base64.b64encode(open(png, "rb").read()).decode("ascii")
ok(expect in html, "内嵌区域图与 data/external/noaa_crw/triangle_dhw.png 字节一致（%d 字节）" % os.path.getsize(png))


print("== 跨站点验证面板 ==")
ok("热压力单列" in html, "今日风险卡注明热压力单列、不计入本指数")
ok("λ" in html and "模型选参" in html, "页面渲染了模型选参（λ 敏感性）卡片")
for h in ["1", "3", "7", "14"]:
    r5 = LA["horizons"][h]["per_lam"]["5"]
    r400 = LA["horizons"][h]["per_lam"]["400"]
    ok(f(r5["rmse"], 4) in html and f(r400["rmse"], 4) in html,
       "h=%-3s 的 λ=5 / λ=400 样本外 RMSE %s / %s 已入表" % (h, f(r5["rmse"], 4), f(r400["rmse"], 4)))
ok(f(LA["horizons"]["14"]["per_lam"]["400"]["rmse"], 4) in html, "14 天 λ=400 把 RMSE 压到 %s 的事实已公开" % f(LA["horizons"]["14"]["per_lam"]["400"]["rmse"], 4))
AB = json.load(open(P("data", "processed", "ablation_audit.json"), encoding="utf-8"))
_cf = {c["id"]: c for c in AB["configs"]}
_old, _new = _cf["base_lam5"], _cf[AB["report_config"]]
ok(AB["report_config"] == "ext_inner" and _new["features"] == D["forecast_meta"]["features"], "消融表里部署配置的特征数 %d 与载荷声明一致" % _new["features"])
ok(all(abs(_new["by_h"][h]["rmse"] - D["metrics"][h]["model_rmse"]) <= 0.0002 for h in ("1", "3", "7", "14")), "消融表部署配置的 RMSE 与主表逐时效一致（同一协议、同一模型，互为交叉校验）")
ok(all(_new["by_h"][h]["rmse"] < _old["by_h"][h]["rmse"] for h in ("1", "3", "7", "14")), "消融表显示升级在四个时效都优于上一版配置（%s -> %s）" % ("/".join(f(_old["by_h"][h]["rmse"], 4) for h in ("1", "3", "7", "14")), "/".join(f(_new["by_h"][h]["rmse"], 4) for h in ("1", "3", "7", "14"))))
ok("消融：两个改动各自值多少" in html and f(_old["by_h"]["3"]["rmse"], 4) in html and f(_cf["ext_lam5"]["by_h"]["14"]["rmse"], 4) in html and f(_cf["base_inner"]["by_h"]["7"]["auc"], 3) in html, "页面消融卡同时列出旧配置的落败值与「单独改动不成立」的反例")
ok("内部的交叉验证" in html and "每一折" in html, "页面写明 λ 由训练窗内部交叉验证逐折挑选（不再固定 λ=5）")
ok(str(D["forecast_meta"].get("features")) in html, "页面披露模型特征数 %s（滚动/记忆/季节 + 当日原始变量水平）" % str(D["forecast_meta"].get("features")))
ok("0.495" in html, "诚实清单保留了二元分类器 AUC 0.495 的失败结果")
LK = json.load(open(P("data", "processed", "leakage_audit.json"), encoding="utf-8"))
ok(LK["verdict"] == "PASS" and LK["max_abs_diff"] == 0, "泄漏审计判定 PASS：%d 个截断点上重建全部 %d 个特征，最大绝对偏差 %s" % (len(LK["cuts"]), LK["feature_count"], LK["max_abs_diff"]))
ok(not LK["analysis_cols_in_features"] and len(LK["analysis_cols_excluded"]) == 3, "居中口径的三个分析列（sl_still / sl_anom / surge）确认未进入模型特征")
ok("严格因果" in html and "事后分析量" in html, "诚实清单写明模型输入严格因果、居中口径只作事后分析量")
ok(str(LK["feature_count"]) in html and str(LK["analysis_leak_days_last8"]) in html, "页面披露特征数 %d 与最后 8 天里无法用过去数据复现的 %d 天" % (LK["feature_count"], LK["analysis_leak_days_last8"]))
ok(f(LK["analysis_cols_excluded"][0]["max_abs_diff"], 4) in html, "页面公开被排除的居中分析列的最大偏差 %s（它们不能进模型的直接证据）" % f(LK["analysis_cols_excluded"][0]["max_abs_diff"], 4))
_TL = LK["threshold_and_label_arms"]
_tl_join = lambda arm: " / ".join(f(_TL["arms"][arm]["horizons"][str(h)]["model_auc"], 3) for h in _TL["horizons"])
_tl_win = sum(1 for h in _TL["horizons"] if _TL["arms"]["causal_target"]["horizons"][str(h)]["model_auc"] > _TL["arms"]["causal_target"]["horizons"][str(h)]["pers_auc"])
ok("训练前缀重算" in html and _tl_join("as_shipped") in html and _tl_join("prefix_thresholds") in html and _tl_join("causal_target") in html,
   "诚实清单量化阈值与标签两条口径（%d 个时效）：现用 %s → 只用训练前缀阈值 %s → 严格因果标签 %s"
   % (len(_TL["horizons"]), _tl_join("as_shipped"), _tl_join("prefix_thresholds"), _tl_join("causal_target")))
ok(_tl_win == len(_TL["horizons"]) and str(_TL["hazard_days_changed_vs_record_thresholds"]) + " 天" in html,
   "两条口径都变后仍有 %d/%d 个时效高于持续预报，且页面写明只有 %d 天的灾害计数会改变"
   % (_tl_win, len(_TL["horizons"]), _TL["hazard_days_changed_vs_record_thresholds"]))
_msc = [(s['slug'], h) for s in MS['sites'] for h in ('1', '3', '7', '14')]
_msw = [(g, h) for (g, h) in _msc if [s for s in MS['sites'] if s['slug'] == g][0]['skill'][h]['model_auc'] > [s for s in MS['sites'] if s['slug'] == g][0]['skill'][h]['pers_auc']]
_msl = [(g, h) for (g, h) in _msc if [s for s in MS['sites'] if s['slug'] == g][0]['skill'][h]['model_auc'] < [s for s in MS['sites'] if s['slug'] == g][0]['skill'][h]['pers_auc']]
ok(str(len(_msc)) + " 个格子" in html and str(len(_msw)) + " 格排序 AUC 高于持续预报" in html,
   "页面按数据现算跨站点胜负：%d 格里 %d 格高于持续预报、%d 格落败" % (len(_msc), len(_msw), len(_msl)))
ok(("排序 AUC 全部高于持续预报" not in html) if _msl else True,
   "有落败格时页面不得声称「全部高于持续预报」（当前落败 %d 格）" % len(_msl))

DE = json.load(open(P("data", "processed", "driver_error_audit.json"), encoding="utf-8"))
_dh = DE["horizons"]
ok(DE["n_days"] == D["span"]["days"] and all(abs(_dh[h]["rmse_obs"] - D["metrics"][h]["model_rmse"]) <= 0.00005 for h in ("1", "3", "7", "14")),
   "驱动误差审计的观测端点与主表同一协议、逐时效一致（1 天 %s，特征 %d 个）" % (f(_dh["1"]["rmse_obs"], 4), DE["feature_count"]))
ok(all(abs(_dh[h]["rmse_obs"] - D["metrics"][h]["model_rmse"]) <= 0.0002 and _dh[h]["rmse_gap_ci95"] > 0 for h in ("1", "3", "7", "14")),
   "四个时效都给出配对 95%% 区间（1 天 %s，14 天 %s）" % (f(_dh["1"]["rmse_gap_ci95"], 4), f(_dh["14"]["rmse_gap_ci95"], 4)))
ok(f(_dh["1"]["rmse_persist_drivers"], 4) in html and f(_dh["1"]["rmse_gap_pct"], 1) + "%" in html
   and f(_dh["1"]["rmse_gap_ci95"], 4) in html and f(_dh["14"]["rmse_gap_pct"], 1) + "%" in html and f(abs(_dh["3"]["auc_gap"]), 3) in html,
   "诚实清单公开驱动误差量化的两个端点（1 天 %s%% / 14 天 %s%%、3 天排序 AUC 掉 %s）" % (f(_dh["1"]["rmse_gap_pct"], 1), f(_dh["14"]["rmse_gap_pct"], 1), f(abs(_dh["3"]["auc_gap"]), 3)))
ok("驱动自身的误差未单独传播" not in html, "旧的「驱动误差未单独传播」纯文字披露已被量化结果取代")
IV = json.load(open(P("data", "processed", "index_variant_audit.json"), encoding="utf-8"))
_IVN = {"two_driver": "2 驱动（去增水）", "three_driver": "3 驱动（部署）", "four_driver": "4 驱动（加海温）", "three_driver_p85": "3 驱动 · p85", "three_driver_p95": "3 驱动 · p95"}
_ivd = IV["variants"][IV["deployed_variant"]]
ok(("复现" in IV["selfcheck"]) and all(abs(_ivd["by_h"][h]["model_rmse"] - D["metrics"][h]["model_rmse"]) <= 0.00005 for h in ("1", "3", "7", "14")),
   "指数定义审计自证：部署定义逐时效复现主表（1 天 %s / 14 天 %s，共 %d 种定义）" % (f(_ivd["by_h"]["1"]["model_rmse"], 4), f(_ivd["by_h"]["14"]["model_rmse"], 4), len(IV["variants"])))
_ivn = len(IV["variants"]) * 4
_ivf = IV["flat_or_persistence_losses"]
ok(len(_ivf) == 3 and _ivn - len(_ivf) == 17, "指数换定义后 %d 个（定义 × 时效）格里 %d 格仍同时优于常数均值与持续预报（落败 %d 格）" % (_ivn, _ivn - len(_ivf), len(_ivf)))
for _k in IV["variants"]:
    ok(_IVN[_k] in html and f(IV["variants"][_k]["mean_auc_gap"], 4) in html, "指数定义 %s 的平均 AUC 优势 %s 已入表" % (_IVN[_k], f(IV["variants"][_k]["mean_auc_gap"], 4)))
ok(str(_ivn) + " 个（定义 × 时效）格里有 " + str(_ivn - len(_ivf)) + " 格同时优于常数均值与持续预报" in html, "页面按数据现算指数定义敏感性（%d 格里 %d 格仍胜）" % (_ivn, _ivn - len(_ivf)))
ok("跨定义不能直接比 AUC" in html and f(IV["variants"]["four_driver"]["mean_auc_gap"], 4) in html, "页面写明跨定义不能直接比 AUC（4 驱动优势 %s 反而更小）" % f(IV["variants"]["four_driver"]["mean_auc_gap"], 4))
for _k, _h in _ivf:
    _v = IV["variants"][_k]["by_h"][_h]
    _mm = (f(_v["model_rmse"], 4) + " 对常数均值 " + f(_v["flat_rmse"], 4)) if not _v["beats_flat"] else (f(_v["model_auc"], 3) + " 对持续预报 " + f(_v["pers_auc"], 3))
    ok(_IVN[_k] + " " + _h + " 天" in html and _mm in html, "落败格 %s %s 天（%s）如实入页" % (_k, _h, _mm))
CMP = json.load(open(P("data", "processed", "compound_label_audit.json"), encoding="utf-8"))
_ch = CMP["by_h"]
ok(("复现" in CMP["selfcheck"]) and all(abs(_ch[h]["model_rmse_index"] - D["metrics"][h]["model_rmse"]) <= 0.00005 for h in ("1", "3", "7", "14")),
   "复合灾害日标签审计自证：同一 3 折协议只换标签，模型 RMSE 逐时效复现主表")
ok(all(f(_ch[h]["model_auc"], 3) in html for h in ("1", "3", "7", "14")) and f(_ch["1"]["base_rate"], 3) in html,
   "页面公开复合灾害日标签下的排序能力（样本外正类 %d 天 / %.1f%%，标签定义写清）" % (_ch["1"]["pos"], _ch["1"]["base_rate"] * 100))
ok(f(_ch["7"]["model_pr_auc"], 3) in html and f(_ch["7"]["pers_pr_auc"], 3) in html and f(_ch["7"]["model_auc"], 3) in html,
   "最弱的一档（7 天 AUC %s 对 %s）也如实入页" % (f(_ch["7"]["model_auc"], 3), f(_ch["7"]["pers_auc"], 3)))
for _g, _h in _msl:
    _s = [s for s in MS['sites'] if s['slug'] == _g][0]
    ok(f(_s['skill'][_h]['model_auc'], 3) in html and f(_s['skill'][_h]['pers_auc'], 3) in html,
       "落败格 %s h=%s 的模型 %s 与持续 %s 都如实入页" % (_g, _h, f(_s['skill'][_h]['model_auc'], 3), f(_s['skill'][_h]['pers_auc'], 3)))
ok(len(MS["sites"]) == 3, "跨站点载荷含 %d 个站点" % len(MS["sites"]))
for s in MS["sites"]:
    short = s["site"].split(",")[0]
    ok(short in html, "站点 %s 已入表（%d 天，复合灾害 %d 天）" % (short, s["days"], s["compound_days"]))
    ok(str(s["days"]) in html, "%s 的记录天数 %d 已渲染" % (short, s["days"]))
    ok(f(s["thresholds"]["wh_max"]) in html and f(s["thresholds"]["precipitation_sum"], 1) in html, "%s 的站点自有阈值（浪 %s / 雨 %s）已渲染" % (short, f(s["thresholds"]["wh_max"]), f(s["thresholds"]["precipitation_sum"], 1)))
    for h in ("1", "3", "7", "14"):
        k = s["skill"][h]
        _rel = "模型胜" if k["model_auc"] > k["pers_auc"] else "落败格（如实保留在表里）"
        ok(f(k["model_auc"], 3) in html and f(k["pers_auc"], 3) in html, "%s h=%-3s 排序 AUC %s / %s 已入表（%s）" % (short, h, f(k["model_auc"], 3), f(k["pers_auc"], 3), _rel))
for w in MS["threshold_sweep"]:
    ok(str(w["compound_days"]) in html, "%s p%s 的复合灾害日 %d 已渲染" % (w["slug"], w["p"], w["compound_days"]))
print("== 白化识别与保护恢复优先级 ==")
BW = json.load(open(P("data", "processed", "bleaching_watch.json"), encoding="utf-8"))
PP = json.load(open(P("data", "processed", "priority_plan.json"), encoding="utf-8"))
ok("本地监测与识别" in html, "页面含「白化热压力：本地监测与识别」卡片")
ok("保护与恢复优先级" in html, "页面含「保护与恢复优先级」卡片")
ok(str(len(BW["events"])) + " 次" in html, "本地识别到海洋热浪事件 %d 次（随记录期增长，页面与载荷同源）" % len(BW["events"]))
ok(f(BW["now"]["percentile"], 1) + "%" in html, "页面渲染近 %d 天热异常百分位 %.1f%%" % (BW["now"]["window_days"], BW["now"]["percentile"]))
ok(BW["now"]["tier_txt"] in html, "页面渲染当前热压力档位 %s" % BW["now"]["tier_txt"])
ok(f(BW["baseline"]["anom_p90"], 4) + " °C" in html, "页面披露海洋热浪异常阈值 %.4f °C" % BW["baseline"]["anom_p90"])
ok(f(BW["tier_rule"]["p90"], 3) in html, "页面披露分档 p90 阈值 %.3f 摄氏度天" % BW["tier_rule"]["p90"])
_le = BW["now"]["last_event"]
ok(_le["start"] in html and _le["end"] in html and str(_le["days"]) + " 天" in html, "最近一次热浪 %s 到 %s（%d 天）已渲染" % (_le["start"], _le["end"], _le["days"]))
for _y in BW["yearly"]:
    ok(str(_y["events"]) + " 次 / " + str(_y["mhw_days"]) + " 天" in html, "%d 年海洋热浪 %d 次 / %d 天已渲染" % (_y["year"], _y["events"], _y["mhw_days"]))
_nc = BW["noaa_check"]
ok("rho = " + f(_nc["r_year_spearman"], 3) in html, "页面披露年尺度 Spearman rho = %s" % f(_nc["r_year_spearman"], 3))
ok(f(_nc["r_year_pearson"], 3) in html and f(_nc["r_cum_pacific"], 3) in html, "页面披露年尺度 r = %s、月尺度 r = %s" % (f(_nc["r_year_pearson"], 3), f(_nc["r_cum_pacific"], 3)))
ok("区域级产品无法替代本站逐日判断" in html, "页面写明逐日相关弱（r = %s）与本地识别的价值" % f(_nc["r_hot_pacific"], 3))
_rc = PP["recovery"]
ok(_rc["w4"] in html and _rc["w8"] in html, "恢复窗口 4 周 %s / 8 周 %s 已渲染" % (_rc["w4"], _rc["w8"]))
ok("在窗口内 = " + ("是" if _rc["inside"] else "否") in html, "恢复窗口状态（在窗口内 = %s）已渲染" % ("是" if _rc["inside"] else "否"))
for _w in PP["windows"]:
    ok(_w["date"] in html and f(_w["upper"], 3) in html, "干预窗口第 %d 位 %s 的上界 %s 已渲染" % (_w["rank"], _w["date"], f(_w["upper"], 3)))
ok(f(PP["thresholds"]["risk_p90"], 3) in html, "页面披露危险指数 p90 触发线 %s" % f(PP["thresholds"]["risk_p90"], 3))
for _s in PP["sites"]:
    ok(f(_s["score"], 4) in html and str(_s["multi_days_90d"]) in html, "站点 %s 优先级得分 %s / 多压力日 %d 已渲染" % (_s["slug"], f(_s["score"], 4), _s["multi_days_90d"]))
    ok(str(_s["mhw_events"]) + " 次 / " + str(_s["mhw_days"]) + " 天" in html, "站点 %s 白化识别口径 %d 次 / %d 天已渲染" % (_s["slug"], _s["mhw_events"], _s["mhw_days"]))
ok("简化代理指标" in html, "页面如实注明跨站点多压力日是简化代理指标")
ok("方法换站即可用" in html, "页面写明白化识别方法按同一口径复用到三站")
ok("最强一次热浪" in html and "热浪事件" in html, "三站表含「热浪事件 / 最强一次热浪」列")
_st = [(_s["slug"], _s["strongest"]) for _s in PP["sites"] if _s.get("strongest")]
ok(len(_st) == len(PP["sites"]), "三个站点都识别出最强一次热浪（%d 站）" % len(_st))
for _slug, _g in _st:
    _cell = _g["start"] + " 起 " + str(_g["days"]) + " 天（" + str(_g["category"]) + " 级）"
    ok(_cell in html, "站点 %s 最强一次热浪 %s 已渲染" % (_slug, _cell))
_longest = max(_st, key=lambda t: t[1]["days"])
ok(_longest[1]["days"] >= 5, "三站中最长一次热浪 %s 起 %d 天（%s）满足 Hobday 持续 5 天以上判据" % (_longest[1]["start"], _longest[1]["days"], _longest[0]))
ok(_longest[1]["start"] in html and _longest[1]["category"] in (1, 2, 3, 4), "最长一次热浪的起报日与分级已在页面渲染")
BFJ = json.load(open(P("data", "processed", "bleach_forecast.json"), encoding="utf-8"))
ok("PR-AUC" in html and "学习模型" in html, "页面含学习型白化预警卡（PR-AUC 口径）")
_bfm = BFJ["metrics"]
ok(f(_bfm["model"]["pr_auc"], 3) in html and f(_bfm["rule_baseline"]["pr_auc"], 3) in html, "页面披露学习模型 PR-AUC %s 与现行规则 PR-AUC %s" % (f(_bfm["model"]["pr_auc"], 3), f(_bfm["rule_baseline"]["pr_auc"], 3)))
ok(f(_bfm["base_rate"], 3) in html and f(_bfm["model"]["roc_auc"], 3) in html, "页面同时列出基准发生率 %s 与 ROC-AUC %s" % (f(_bfm["base_rate"], 3), f(_bfm["model"]["roc_auc"], 3)))
ok(_bfm["model"]["pr_auc"] > _bfm["rule_baseline"]["pr_auc"] and _bfm["model"]["pr_auc"] > _bfm["base_rate"], "学习模型 PR-AUC 高于规则与基准发生率（优势有限，页面已写明分折反例）")
ok(f(BFJ["now"]["prob_mhw_28d"], 3) in html, "页面渲染未来 %d 天出现热浪日的模型概率 %s" % (BFJ["label"]["horizon_days"], f(BFJ["now"]["prob_mhw_28d"], 3)))
ok(str(len(BFJ["features"])) + " 个特征" in html, "页面写明特征数 %d（全部为过去可见量）" % len(BFJ["features"]))
for _x in BFJ["by_fold"]:
    ok(f(_x["model_pr_auc"], 3) in html and f(_x["rule_pr_auc"], 3) in html, "第 %d 折 PR-AUC（模型 %s / 规则 %s）已入表" % (_x["fold"], f(_x["model_pr_auc"], 3), f(_x["rule_pr_auc"], 3)))

BWJ = json.load(open(P("data", "processed", "bleaching_watch.json"), encoding="utf-8"))
PPJ = json.load(open(P("data", "processed", "priority_plan.json"), encoding="utf-8"))
_ev = BWJ["noaa_check"]["event_level"]
ok("事件级对照" in html, "页面新增事件级 NOAA 对照说明")
ok(str(_ev["events_total"]) + " 次热浪里 " + str(_ev["events_hit"]) + " 次" in html and f(_ev["event_hit_rate"], 1) + "%" in html, "页面披露事件命中率 %s/%s = %s%%" % (_ev["events_hit"], _ev["events_total"], f(_ev["event_hit_rate"], 1)))
ok(f(_ev["lift"], 2) + " 倍" in html and f(_ev["p_official_given_station"], 1) + "%" in html, "页面披露提升倍数 %s 与站内热浪日落在官方抬升日的比例" % f(_ev["lift"], 2))
_sop = PPJ["sop"]
ok("触发—响应 SOP" in html and str(len(_sop)) + " 条" in html, "页面渲染触发—响应 SOP（%d 条）" % len(_sop))
_ms_days = format(int(PPJ["sites"][0]["n_days"]), ",")
_main_days = format(int(D["span"]["days"]), ",")
ok("口径提醒" in html and (_ms_days + " 天") in html and (_main_days + " 天") in html,
   "保护优先级卡标明百分位来自三站点数据集（%s 天）、白化卡的百分位来自主记录（%s 天）" % (_ms_days, _main_days))
for _s in _sop:
    ok(_s["stage"] in html and _s["timing"] in html, "SOP 条目「%s」及其时限 %s 已入表" % (_s["stage"], _s["timing"]))
ok(PPJ["recovery"]["w4"] in html, "SOP 中 4 周复测起点 %s 已渲染" % PPJ["recovery"]["w4"])
_td = PPJ.get("today", {})
ok("今天适用" in html and "两个不同的轴" in html, "SOP 表标注「今天适用」，并说明危险指数轴与热压力轴的区别")
ok(bool(_td.get("stage")) and _td["stage"] in html and str(len(_td.get("active", []))) + " 条" in html,
   "页面写出今天适用的 SOP 条数（%d 条）与热压力最严一档（%s）" % (len(_td.get("active", [])), _td.get("stage")))
ok(f(_td.get("cum_anom", 0.0), 3) in html and f(_td.get("p90", 0.0), 3) in html,
   "两轴说明里给出热压力累计异常 %s C 天与本站 p90 %s" % (f(_td.get("cum_anom", 0.0), 3), f(_td.get("p90", 0.0), 3)))
ok(all("active" in _s for _s in _sop) and sum(1 for _s in _sop if _s["active"]) == len(_td.get("active", [])),
   "SOP 每条都带 active 标记，且与 today.active 完全一致")

# 方法与出处（第 40 轮）：规则要求高风险应用交代数据来源，评委要能逐条打开核对。
_ref_idents = ["doi:10.1016/j.pocean.2015.12.014", "doi:10.5670/oceanog.2018.205",
               "doi:10.3390/rs61111579", "doi:10.3390/rs12233856", "doi:10.1002/qj.3803",
               "doi:10.24381/cds.adbb2d47", "doi:10.1038/s41558-018-0156-3",
               "doi:10.1080/00401706.1970.10488634",
               "coralreefwatch.noaa.gov/product/5km/methodology.php",
               "coralreefwatch.noaa.gov/satellite/docs/recommendations_crw_citation.php",
               "open-meteo.com/en/docs/marine-weather-api", "open-meteo.com/en/licence"]
ok('id="refs"' in html and all(_s in html for _s in _ref_idents),
   "页面附「依据与来源」折叠块：12 条出处标识串（8 个 DOI + 4 个产品页/许可页链接）逐条可打开核对")
ok(html.find('id="refs"') > html.find('id="en"') > 0,
   "「依据与来源」排在英文摘要之后（页面最末，演示视频的分镜坐标不受影响）")
ok("依据与来源：" in html[html.rfind('<footer class="foot'):],
   "页脚有一条不展开也看得到的「依据与来源」摘要")
ok(all(_s.get("active_reason", "") in html for _s in _sop if _s.get("active")),
   "今天适用的每一条都写出适用原因（%d 条）" % len(_td.get("active", [])))
ok(abs(float(_td.get("max_upper", 0.0)) - max(w["upper"] for w in PPJ["windows"])) < 1e-9,
   "today.max_upper 与窗口上界最大值一致（%s）" % f(_td.get("max_upper", 0.0), 3))
# 第 62 轮：同一个「风险上界」此前由两个模块各算一次 —— 日档位列表取 priority_plan 的 upper
# （v + h，四位小数），预报图取 dashboard 的 hi（三位小数、夹在 0..1），于是同一张卡上并排显示
# 0.301 与 0.302。现在 priority_plan 直接沿用 hi，这条断言逐日钉住两者相等。
_fcmap = {x["date"]: float(x["hi"]) for x in D["forecast"]}
ok(all(abs(float(w["upper"]) - _fcmap.get(w["date"], -1.0)) < 1e-9 for w in PPJ["windows"]),
   "干预窗口的「上界」与预报图用的是同一个数（%d 天逐日相等）" % len(PPJ["windows"]))
_vs = BWJ["noaa_check"]["vs_sabah"]
ok("区域站点对照" in html, "页面新增 NOAA 区域虚拟站点对照（同一片沙巴海域的 5km 产品）")
ok(str(_vs["events_total"]) + " 次热浪有 " + str(_vs["events_hit"]) + " 次" in html and f(_vs["event_hit_rate"], 1) + "%" in html, "页面披露区域站点事件命中 %s/%s = %s%%" % (_vs["events_hit"], _vs["events_total"], f(_vs["event_hit_rate"], 1)))
ok(f(_vs["sst_bias_station_minus_official"], 3) + " °C" in html and "r = " + f(_vs["r_sst"], 3) in html, "页面披露本站与官方区域站点的海温偏差 %s °C、相关系数 %s" % (f(_vs["sst_bias_station_minus_official"], 3), f(_vs["r_sst"], 3)))
ok(f(_vs["latest_dhw"], 2) in html and _vs["latest_date"] in html and "Alert Level 2" in html, "页面披露官方最新（%s）DHW %s 与 Alert Level 2" % (_vs["latest_date"], f(_vs["latest_dhw"], 2)))
ok(f(_vs["official_mmm"], 4) in html and f(_vs["station_mmm"], 3) in html, "页面披露两种 MMM（官方长期 %s / 本站短记录 %s）" % (f(_vs["official_mmm"], 4), f(_vs["station_mmm"], 3)))
ok("官方同一站点最新（" + _vs["latest_date"] + "）的 DHW = " + f(_vs["latest_dhw"], 2) in html,
   "诚实清单里的官方 DHW 也按数据现算（%s / %s），不是抄死的旧值" % (_vs["latest_date"], f(_vs["latest_dhw"], 2)))
ok("短记录暖月均 " + f(BWJ["baseline"]["mmm"], 3) + " °C 对官方长期 MMM " + f(_vs["official_mmm"], 4) + " °C" in html,
   "诚实清单里的两个 MMM 都来自数据（本站 %s / 官方 %s）" % (f(BWJ["baseline"]["mmm"], 3), f(_vs["official_mmm"], 4)))
ok(("Alert Level 2（二级警报）" in html) if int(_vs["latest_alert"]) == 4 else True,
   "官方最新预警级别 %s 以可读名称入页（不写裸数字）" % _vs["latest_alert"])
_vss = BWJ["noaa_check"]["vs_sites"]
ok("跨站官方验证" in html and str(len(_vss)) + " 个官方站点" in html, "页面新增跨站官方验证说明（%d 个官方区域站点）" % len(_vss))
for _s in _vss:
    ok(_s["site"] in html and f(_s["bias_station_minus_official"], 3) + " °C / " + f(_s["r_sst"], 3) in html, "跨站官方表含 %s：偏差 %s °C / r %s" % (_s["site"], f(_s["bias_station_minus_official"], 3), f(_s["r_sst"], 3)))
ok(len(_vss) >= 2 and any("Palau" in s["site"] for s in _vss), "官方对照覆盖第二个独立站点（帕劳），不只在沙巴验证过")

print("== 标签配对 ==")
from html.parser import HTMLParser
VOID = ["meta", "br", "img", "link", "hr", "input", "line", "rect", "path", "circle", "polyline", "polygon", "stop"]
class Chk(HTMLParser):
    def __init__(self):
        HTMLParser.__init__(self)
        self.stack = []
        self.err = []
    def handle_startendtag(self, tag, attrs):
        pass
    def handle_starttag(self, tag, attrs):
        if tag not in VOID:
            self.stack.append(tag)
    def handle_endtag(self, tag):
        if not self.stack:
            self.err.append("extra close " + tag)
            return
        if self.stack[-1] != tag:
            self.err.append("expect " + self.stack[-1] + " got " + tag)
            if tag in self.stack:
                while self.stack and self.stack.pop() != tag:
                    pass
        else:
            self.stack.pop()
c = Chk()
c.feed(html)
ok(not c.stack, "没有未闭合的标签（%s）" % (c.stack[:5] or "无"))
ok(not c.err, "没有错配的标签（%s）" % (c.err[:5] or "无"))

print("")
print("文件 %s | %d 字符 | 离线可开 | http://127.0.0.1:8788/" % (P("demo", "index.html"), len(html)))
if fails:
    print("RESULT FAIL %d 项" % len(fails))
    for m in fails:
        print("  - " + m)
    sys.exit(1)
print("RESULT ALL PASS")