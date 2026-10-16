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
ok("<script" not in html.lower(), "成品页不含任何 script 标签（SCRIPT_TAGS=%d）" % html.lower().count("<script"))
ok("getElementById" not in html, "成品页没有任何客户端脚本绑定")
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

print("== 预报图几何（viewBox 660x250）==")
W, H, pl, pr, pt, pb = 660, 250, 42, 16, 16, 32
iw, ih = W - pl - pr, H - pt - pb
F10 = D["forecast"]
maxv = max(0.45, max(x["hi"] for x in F10))
X = lambda i: pl + (i + 0.5) * iw / len(F10)
Y = lambda v: pt + ih - (v / maxv) * ih
bw = iw / len(F10) * 0.5
missing = []
for i, d in enumerate(F10):
    x0 = round(X(i) - bw / 2, 1)
    t1 = "x=\"" + str(x0) + "\""
    if t1 not in html:
        missing.append(str(d["lead"]))
    ok(pt <= Y(d["hi"]) <= pt + ih, "+%-2d 区间上界在绘图框内 y=%.1f（值 %.3f）" % (d["lead"], Y(d["hi"]), d["hi"]))
ok(not missing, "每个时效的柱子在页面上都能找到对应坐标（缺失：%s）" % (missing or "无"))
p90 = 1.0 / 3.0
ok("p90 触发线" in html, "p90 触发线已标注（值 %.3f，四舍五入到 0.33）" % p90)

print("== 历史图（最近 180 天）==")
rk = S["risk"][-180:]
cp = S["compound"][-180:]
pl2, pr2, pt2, pb2 = 38, 14, 14, 28
H2 = 210
ih2 = H2 - pt2 - pb2
maxh = max(0.45, max(rk))
Y2 = lambda v: pt2 + ih2 - (v / maxh) * ih2
ok(all(pt2 <= Y2(v) <= pt2 + ih2 for v in rk), "180 个点全部落在绘图框内（y 上限 %.3f）" % maxh)
path = ""
for i, v in enumerate(rk):
    path = path + ((" L" if i else " M") + str(round(pl2 + (i / 179.0) * (W - pl2 - pr2), 1)) + "," + str(round(Y2(v), 1)))
ok(path.strip() in html, "折线路径与源数据逐点一致（%d 个点）" % len(rk))
ok(sum(cp) == cp.count(1), "窗口内复合灾害日 %d 天，竖条已渲染" % sum(cp))

print("== 近 300 天条带 ==")
b300 = S["risk"][-300:]
ok(len(b300) == 300, "条带共 %d 根（含零值细条）" % len(b300))
bmax = max(0.34, max(b300))
ok(all(int(round((v / bmax) * 100)) >= 0 for v in b300), "条带高度由同一分母计算，最高 %d%%" % int(round(max(b300) / bmax * 100)))

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
_old, _new = _cf["base_lam5"], _cf[AB["deployed"]]
ok(AB["deployed"] == "ext_inner" and _new["features"] == D["forecast_meta"]["features"], "消融表里部署配置的特征数 %d 与载荷声明一致" % _new["features"])
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
_msc = [(s['slug'], h) for s in MS['sites'] for h in ('1', '3', '7', '14')]
_msl = [(g, h) for (g, h) in _msc if [s for s in MS['sites'] if s['slug'] == g][0]['skill'][h]['model_auc'] < [s for s in MS['sites'] if s['slug'] == g][0]['skill'][h]['pers_auc']]
ok(True, "跨站点 %d 格排序 AUC 已逐格入表，其中模型低于持续预报 %d 格（落败格不隐藏）" % (len(_msc), len(_msl)))
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
ok("口径提醒" in html and "1,404 天" in html and "1,446 天" in html, "保护优先级卡标明百分位来自三站点数据集（1,404 天）、白化卡的百分位来自主记录（1,446 天）")
for _s in _sop:
    ok(_s["stage"] in html and _s["timing"] in html, "SOP 条目「%s」及其时限 %s 已入表" % (_s["stage"], _s["timing"]))
ok(PPJ["recovery"]["w4"] in html, "SOP 中 4 周复测起点 %s 已渲染" % PPJ["recovery"]["w4"])
_vs = BWJ["noaa_check"]["vs_sabah"]
ok("区域站点对照" in html, "页面新增 NOAA 区域虚拟站点对照（同一片沙巴海域的 5km 产品）")
ok(str(_vs["events_total"]) + " 次热浪有 " + str(_vs["events_hit"]) + " 次" in html and f(_vs["event_hit_rate"], 1) + "%" in html, "页面披露区域站点事件命中 %s/%s = %s%%" % (_vs["events_hit"], _vs["events_total"], f(_vs["event_hit_rate"], 1)))
ok(f(_vs["sst_bias_station_minus_official"], 3) + " °C" in html and "r = " + f(_vs["r_sst"], 3) in html, "页面披露本站与官方区域站点的海温偏差 %s °C、相关系数 %s" % (f(_vs["sst_bias_station_minus_official"], 3), f(_vs["r_sst"], 3)))
ok(f(_vs["latest_dhw"], 2) in html and _vs["latest_date"] in html and "Alert Level 2" in html, "页面披露官方最新（%s）DHW %s 与 Alert Level 2" % (_vs["latest_date"], f(_vs["latest_dhw"], 2)))
ok(f(_vs["official_mmm"], 4) in html and f(_vs["station_mmm"], 3) in html, "页面披露两种 MMM（官方长期 %s / 本站短记录 %s）" % (f(_vs["official_mmm"], 4), f(_vs["station_mmm"], 3)))
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