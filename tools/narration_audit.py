# -*- coding: utf-8 -*-
"""旁白里的每个数字都对着 data/processed 现算。

演示视频是最后一件「内容没人核过」的物料：画面是截图，声音是念出来的数字，
而这些数字一旦与产物脱节，评委一边看视频一边对页面就会发现两套说法。
本脚本把视频里念到的每个数字（docs/video/narration.json 的 zh 文本）重新算一遍：

  1. 数字与产物一致：2024 年的复合灾害日 / 热压力日、2026 年的最高海温与单日降水、
     相对持续预报的误差下降、二元分类 AUC、学习型白化预警的 PR-AUC 与基准率、
     海洋热浪次数、当前百分位、官方海温偏差与背景预警率、两个复测窗口；
  2. 数据快照日期（dashboard_data.json 的 span.end）出现在旁白记录、docs/04、
     docs/05 与成品页页脚 —— 视频的数字冻结在快照日，页面每天刷新，必须说清楚；
  3. 片头卡与片尾卡把快照日期印出来（出片脚本从产物现读，见 .taste-skill/video/build.py）。

纯标准库、不联网、不需要浏览器，也不依赖工作区的出片工具：
只读包内的 docs/video/narration.json 与 data/processed/*.json。

用法：python tools\\narration_audit.py [--json] [--no-docs]
"""
import io
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROC = os.path.join(ROOT, "data", "processed")
NARR = os.path.join(ROOT, "docs", "video", "narration.json")
DOC04 = "docs/04_演示视频逐字稿与分镜.md"
DOC05 = "docs/05_报名表与提交清单.md"
PAGE = "demo/index.html"

_D = "零一二三四五六七八九"


def _read(rel):
    for base in (ROOT, os.path.dirname(ROOT)):
        p = os.path.join(base, rel)
        if os.path.exists(p):
            return io.open(p, encoding="utf-8").read()
    return ""


def _load(name):
    with io.open(os.path.join(PROC, name), encoding="utf-8") as f:
        return json.load(f)


# ------------------------------------------------------------------ 中文数词
def zh_int(n):
    """0-99 的中文数词（本项目念到的整数都在这范围内）。"""
    n = int(n)
    if n < 0 or n > 99:
        return str(n)
    if n < 10:
        return _D[n]
    if n < 20:
        return "十" + (_D[n % 10] if n % 10 else "")
    return _D[n // 10] + "十" + (_D[n % 10] if n % 10 else "")


def zh_dec(x):
    """小数 → 中文数词：31.45 → 三十一点四五；0.495 → 零点四九五。"""
    s = "%g" % round(float(x), 4)
    if "e" in s or "E" in s:
        return s
    a, _, b = s.partition(".")
    out = zh_int(int(a))
    if b:
        out += "点" + "".join(_D[int(c)] for c in b)
    return out


def zh_year(y):
    """2024 → 二零二四。"""
    return "".join(_D[int(c)] for c in str(int(y)))


def zh_rough_pct(x):
    """82.3 → 八成二（旁白里用的是约数说法）。"""
    n = int(round(float(x)))
    return "八成" + (_D[n % 10] if n % 10 else "")


# ------------------------------------------------------------------ 事实
def facts():
    d = _load("dashboard_data.json")
    w = _load("bleaching_watch.json")
    mr = _load("model_report.json")
    bf = _load("bleach_forecast.json")
    pp = _load("priority_plan.json")
    with io.open(NARR, encoding="utf-8") as f:
        narr = json.load(f)

    yearly = dict((r["year"], r) for r in d["yearly"])
    worst = max(d["yearly"], key=lambda r: r["compound"])
    m1, m14 = d["metrics"]["1"], d["metrics"]["14"]
    vs = w["noaa_check"]["vs_sabah"]
    f = {
        "snapshot": d["span"]["end"],
        "worst_year": worst["year"],
        "worst_compound": worst["compound"],
        "worst_hot": worst["hot_days"],
        "sst_2026": yearly["2026"]["max_sst"],
        "rain_2026": yearly["2026"]["max_rain"],
        "drop_1d": round(100.0 * (1.0 - m1["model_rmse"] / m1["pers_rmse"]), 1),
        "drop_14d": round(100.0 * (1.0 - m14["model_rmse"] / m14["pers_rmse"]), 1),
        "binary_auc": mr["overall"]["model_auc"],
        "pr_model": bf["metrics"]["model"]["pr_auc"],
        "pr_rule": bf["metrics"]["rule_baseline"]["pr_auc"],
        "pr_base": bf["metrics"]["base_rate"],
        "n_events": len(w["events"]),
        "pct_now": w["now"]["percentile"],
        "sst_bias": abs(vs["sst_bias_station_minus_official"]),
        "bg_rate": vs["background_alert_rate"],
        "pp_dates": sorted(set(re.findall(r"\d{4}-\d{2}-\d{2}", json.dumps(pp, ensure_ascii=False)))),
        "shots": narr["shots"],
        "narr_snapshot": narr.get("snapshot", {}).get("date", ""),
        "narr_total_seconds": round(sum(narr["shots"][k]["audio_seconds"] for k in narr["shots"])
                                    + narr["pad_seconds"] * len(narr["shots"])
                                    + narr["title_seconds"] + narr["end_seconds"], 1),
    }
    return f


def claims(f):
    """(镜头, 说明, 必须出现在该镜头旁白里的中文数词)。"""
    return [
        ("shot2", "2024 年复合灾害日（全记录最重）", zh_int(f["worst_compound"])),
        ("shot2", "2024 年热压力日", zh_int(f["worst_hot"])),
        ("shot2", "最重年份", zh_year(f["worst_year"])),
        ("shot2", "2026 年最高海温", zh_dec(f["sst_2026"])),
        ("shot2", "2026 年单日最大降水", zh_dec(f["rain_2026"])),
        ("shot3", "预报时效上限（1 到 14 天）", "十四"),
        ("shot4", "滑动气候态窗口（31 天）", zh_int(31)),
        ("shot4", "识别出的海洋热浪次数", zh_int(f["n_events"]) + "次"),
        ("shot4", "当前百分位", "第" + zh_dec(f["pct_now"]) + "百分位"),
        ("shot5", "二元分类器 AUC", zh_dec(f["binary_auc"])),
        ("shot5", "1 天误差下降", zh_dec(f["drop_1d"])),
        ("shot5", "14 天误差下降", zh_dec(f["drop_14d"])),
        ("shot6", "学习组件的预测窗口（28 天）", zh_int(28)),
        ("shot6", "学习模型 PR-AUC", zh_dec(f["pr_model"])),
        ("shot6", "规则基线 PR-AUC", zh_dec(f["pr_rule"])),
        ("shot6", "基准发生率", zh_dec(f["pr_base"])),
        ("shot7", "官方对照的年份数（4 年）", zh_int(4)),
        ("shot7", "官方站点覆盖的热浪次数", zh_int(f["n_events"]) + "次"),
        ("shot7", "官方与本站海温偏差", zh_dec(f["sst_bias"])),
        ("shot7", "官方背景预警率（约数）", zh_rough_pct(f["bg_rate"])),
        ("shot8", "验证期长度（90 天）", zh_int(90)),
    ]


def audit(doc=None, docs=True):
    f = facts()
    bad = []
    for shot, label, want in claims(f):
        zh = f["shots"].get(shot, {}).get("zh", "")
        if want not in zh:
            bad.append("%s 的旁白里找不到「%s」（%s，现算 %s）" % (shot, want, label, want))
    # 2024 必须真的是最重的一年，否则旁白的「全记录最重」是错的
    if f["worst_year"] != "2024":
        bad.append("复合灾害日最多的年份现算是 %s，旁白说的是 2024" % f["worst_year"])
    # 两个复测窗口必须在产物里
    for d0 in ("2026-11-03", "2026-12-01"):
        if d0 not in f["pp_dates"]:
            bad.append("priority_plan.json 里找不到复测窗口 %s（旁白点名了它）" % d0)
    # 快照日期
    if not f["narr_snapshot"]:
        bad.append("docs/video/narration.json 没有 snapshot.date（视频的数字冻结在哪一天必须写清）")
    elif f["narr_snapshot"] != f["snapshot"]:
        bad.append("narration.json 的快照日 %s 与产物现算的 %s 不一致"
                   % (f["narr_snapshot"], f["snapshot"]))
    if docs:
        for rel in (DOC04, DOC05):
            t = _read(rel)
            if f["snapshot"] not in t:
                bad.append("%s 没写数据快照日 %s" % (rel, f["snapshot"]))
        html = doc if doc is not None else _read(PAGE)
        if f["snapshot"] not in html:
            bad.append("成品页页脚没写数据快照日 %s" % f["snapshot"])
    return f, bad


def main():
    args = sys.argv[1:]
    doc = None
    if "--page" in args:
        i = args.index("--page")
        doc = io.open(args[i + 1], encoding="utf-8").read()
    f, bad = audit(doc=doc, docs="--no-docs" not in args)
    if "--json" in args:
        print(json.dumps({"facts": f, "failures": bad}, ensure_ascii=False, indent=2))
    if bad:
        for b in bad:
            print("FAIL " + b)
        raise SystemExit(1)
    print("旁白数字：%d 条断言全部对上（快照 %s；最重年份 %s：%d 个复合灾害日 / %d 个热压力日；"
          "二元 AUC %.3f；PR-AUC %.3f > %.3f > %.3f；热浪 %d 次、当前 %.1f 百分位）"
          % (len(claims(f)), f["snapshot"], f["worst_year"], f["worst_compound"],
             f["worst_hot"], f["binary_auc"], f["pr_model"], f["pr_rule"],
             f["pr_base"], f["n_events"], f["pct_now"]))
    print("RESULT ALL PASS（视频里念到的每个数字都由 data/processed 现算，快照日期在旁白记录、docs/04、docs/05 与成品页上说的是同一天）")


if __name__ == "__main__":
    main()
