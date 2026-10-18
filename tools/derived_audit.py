#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""派生百分比审计：材料里每写一个"算出来的百分比"，都从产物现算一遍。

为什么要有这个脚本（第 36 轮）：
    成品页写「只有 1 天的 14.5% 是实的」，`data/processed/blend_audit.json`
    里存的是 14.49，而 README、项目说明、数据与AI说明、报名表、作品帖、
    提交包说明 6 份材料里写的是 **14.4%** —— 同一个括号（0.1406 对 0.1644）
    在旁边写着，任何人拿计算器一按就知道 14.4 是错的。三处三个答案，
    而此前没有任何门禁看这类"派生值"：已有的审计核对的是**事实**（几天、
    几度、几个事件），不是**由事实算出来的百分比**。

做法：
    - 事实全部从 data/processed 现算（dashboard_data.json / blend_audit.json /
      index_variant_audit.json）；
    - 断言句按句式抓取（中文与英文各一套），把抓到的数字与现算值比对，
      允许"按现算值四舍五入"或"按产物里已存的百分比四舍五入"两种口径，
      但**不允许**第三种；
    - 页面、README.md、README.en.md、docs/01、docs/02、docs/03、docs/05、
      docs/06、00_提交包说明.md 都在扫描范围内。

用法：
    python tools/derived_audit.py            # 人类可读
    python tools/derived_audit.py --json     # 机器可读
    python tools/derived_audit.py --no-docs  # 只看成品页
"""

import io
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROC = os.path.join(ROOT, "data", "processed")
PAGE = os.path.join("demo", "index.html")
HORIZONS = ("1", "3", "7", "14")

SURFACES = (
    PAGE,
    "README.md",
    "README.en.md",
    os.path.join("docs", "01_项目说明.md"),
    os.path.join("docs", "02_数据与AI说明.md"),
    os.path.join("docs", "03_90天验证计划.md"),
    os.path.join("docs", "05_报名表与提交清单.md"),
    os.path.join("docs", "06_作品帖与发布草稿.md"),
    "00_提交包说明.md",
)

# 必须在指定材料里出现的固定串（值本身也由现算校对，见 _seq_checks）
MUST_HAVE_ZERO_SHARE = (PAGE, "README.md",
                        os.path.join("docs", "05_报名表与提交清单.md"),
                        os.path.join("docs", "06_作品帖与发布草稿.md"))
MUST_HAVE_AUC = (PAGE, "README.md", "README.en.md",
                 os.path.join("docs", "05_报名表与提交清单.md"),
                 os.path.join("docs", "06_作品帖与发布草稿.md"),
                 "00_提交包说明.md")
# 气候平均 AUC 只在引用了完整对照的几份材料里要求
MUST_HAVE_AUC_CLIM = (PAGE, "README.md",
                      os.path.join("docs", "05_报名表与提交清单.md"),
                      "00_提交包说明.md")

# 已经写错过的说法（换汤不换药的写法都列上，避免"改一处漏一处"）
BANNED = (
    "相对常数均值低 14.4%",
    "14.4% over the constant mean",
    "14.4% versus the constant mean",
    "14.4%（0.1406 对 0.1644）",
)

# 句式：中文「相对常数均值低 14.5%（0.1406 对 0.1644）」
RE_ZH_FLAT = re.compile(r"相对常数均值低\s*([0-9]+(?:\.[0-9]+)?)%")
RE_ZH_FLAT_PAIR = re.compile(
    r"相对常数均值低\s*[0-9]+(?:\.[0-9]+)?%（([0-9.]+)\s*对\s*([0-9.]+)）")
# 句式：英文「14.5% over the constant mean」/「14.5% versus the constant mean」
RE_EN_FLAT = re.compile(
    r"([0-9]+(?:\.[0-9]+)?)%\s+(?:over|versus)\s+the\s+constant\s+mean")
# 句式：英文「20.8% over persistence」
RE_EN_PERS = re.compile(
    r"([0-9]+(?:\.[0-9]+)?)%\s+(?:over|versus)\s+persistence")
# 句式：中文「分别低 20.8% / 17.2% / 15.4% / 8.9%」
# 必须紧跟在「持续预报」后面（页面上还有「上一版配置…分别降低 1.7% / 1.7% /
# 2.8% / 5.0%」这种别的量，光看「低 N% / N% / N% / N%」会误报）
RE_ZH_PERS_SEQ = re.compile(
    r"持续预报[^。\n]{0,14}?低\s*\**\s*([0-9]+(?:\.[0-9]+)?)%\s*/\s*"
    r"([0-9]+(?:\.[0-9]+)?)%\s*/\s*([0-9]+(?:\.[0-9]+)?)%\s*/\s*"
    r"([0-9]+(?:\.[0-9]+)?)%")
# 句式：中文「相对持续预报低 20.8%（0.1406 对 0.1776）」
RE_ZH_PERS_ONE = re.compile(r"相对持续预报低\s*([0-9]+(?:\.[0-9]+)?)%")
RE_ZH_PERS_PAIR = re.compile(
    r"相对持续预报低\s*[0-9]+(?:\.[0-9]+)?%（([0-9.]+)\s*对\s*([0-9.]+)）")
# 页面句式：「误差下降 20.8% / 17.2% / 15.4% / 8.9%」
RE_ZH_PERS_DROP = re.compile(
    r"误差下降\s*\**\s*([0-9]+(?:\.[0-9]+)?)%\s*/\s*"
    r"([0-9]+(?:\.[0-9]+)?)%\s*/\s*([0-9]+(?:\.[0-9]+)?)%\s*/\s*"
    r"([0-9]+(?:\.[0-9]+)?)%")
# RMSE 表里的「+N%」优势列
RE_PLUS_CELL = re.compile(r">\+([0-9]+(?:\.[0-9]+)?)%<")
# 句式：页面「收缩后相对常数均值的优势是 14.49% / 3.11% / 0.70% / 1.54%」
RE_ZH_BLEND_SEQ = re.compile(
    r"收缩后相对常数均值的优势是\s*([0-9]+(?:\.[0-9]+)?)%\s*/\s*"
    r"([0-9]+(?:\.[0-9]+)?)%\s*/\s*([0-9]+(?:\.[0-9]+)?)%\s*/\s*"
    r"([0-9]+(?:\.[0-9]+)?)%")
# 句式：页面「只有 1 天的 14.5% 是实的」/「只有 1 天低 14.5% 是实的」
RE_ZH_ONE_DAY = re.compile(r"只有 1 天(?:的|低)\s*([0-9]+(?:\.[0-9]+)?)%")
# 句式：「3 / 7 / 14 天只赢 0.0051 / 0.0011 / 0.0025」
RE_ZH_GAP = re.compile(
    r"3 / 7 / 14 天只赢\s*([0-9.]+)\s*/\s*([0-9.]+)\s*/\s*([0-9.]+)")


def _read(rel):
    """先按仓库根找，再按上一层找（提交包把 00_提交包说明.md 放在上一层）。"""
    for base in (ROOT, os.path.dirname(ROOT)):
        p = os.path.join(base, rel)
        if os.path.exists(p):
            return io.open(p, encoding="utf-8").read()
    return ""


def _load(rel):
    p = os.path.join(PROC, rel)
    return json.load(io.open(p, encoding="utf-8"))


def _f(x, n):
    return ("%." + str(n) + "f") % x


def _dp(written):
    return len(written.split(".")[1]) if "." in written else 0


def _accept(written, candidates):
    """写的数是否等于某个候选值（按写法自身的小数位数四舍五入）。"""
    dp = _dp(written)
    try:
        w = float(written)
    except ValueError:
        return False
    for c in candidates:
        if c is None:
            continue
        if abs(w - round(float(c), dp)) < 1e-9:
            return True
    return False


def facts():
    d = _load("dashboard_data.json")
    b = _load("blend_audit.json")
    v = _load("index_variant_audit.json")
    m = d["metrics"]
    f = {"horizons": list(HORIZONS), "surfaces": {}}
    for h in HORIZONS:
        x = m[h]
        f["rmse_" + h] = {"model": x["model_rmse"], "pers": x["pers_rmse"],
                          "clim": x["clim_rmse"], "flat": x["flat_rmse"]}
        f["drop_pers_" + h] = 100.0 * (1 - x["model_rmse"] / x["pers_rmse"])
        f["drop_clim_" + h] = 100.0 * (1 - x["model_rmse"] / x["clim_rmse"])
        f["drop_flat_" + h] = 100.0 * (1 - x["model_rmse"] / x["flat_rmse"])
        f["blend_rmse_" + h] = x.get("blend_rmse")
        f["blend_gap_" + h] = (None if x.get("blend_rmse") is None
                               else x["flat_rmse"] - x["blend_rmse"])
        f["auc_" + h] = {"model": x["model_auc"], "pers": x["pers_auc"],
                         "clim": x["clim_auc"]}
        # 收缩口径：产物里存了 gain_vs_flat_pct（页面直接引用它）
        bb = b.get(h) or {}
        f["blend_gain_" + h] = bb.get("gain_vs_flat_pct")
        f["blend_beta_" + h] = bb.get("beta_star", x.get("blend_beta"))
    f["zero_share"] = v["variants"]["three_driver"]["zero_share_pct"]
    return f


def audit(doc=None, docs=True):
    """返回 (facts, failures)。doc 可传页面 HTML 以避免重复读盘。"""
    f = facts()
    bad = []
    text = {}

    def get(rel):
        if rel == PAGE and doc is not None:
            return doc
        if rel not in text:
            text[rel] = _read(rel)
        return text[rel]

    def where(rel):
        return "成品页" if rel == PAGE else rel

    # ---------- 1) 常数均值：1 天的优势，中文与英文句式都抓 ----------
    for rel in SURFACES:
        if rel != PAGE and not docs:
            continue
        s = get(rel)
        for mt in RE_ZH_FLAT.finditer(s):
            w = mt.group(1)
            if not _accept(w, (f["drop_flat_1"], f["blend_gain_1"])):
                bad.append("%s：写「相对常数均值低 %s%%」，现算是 %.2f%%（收缩口径 %.2f%%）"
                           % (where(rel), w, f["drop_flat_1"], f["blend_gain_1"]))
        for mt in RE_ZH_FLAT_PAIR.finditer(s):
            a, b = mt.group(1), mt.group(2)
            ea, eb = _f(f["rmse_1"]["model"], _dp(a)), _f(f["rmse_1"]["flat"], _dp(b))
            if a != ea or b != eb:
                bad.append("%s：括号里写「%s 对 %s」，现算应为「%s 对 %s」"
                           % (where(rel), a, b, ea, eb))
        for mt in RE_EN_FLAT.finditer(s):
            w = mt.group(1)
            if not _accept(w, (f["drop_flat_1"], f["blend_gain_1"])):
                bad.append("%s：写「%s%% over/versus the constant mean」，现算是 %.2f%%"
                           % (where(rel), w, f["drop_flat_1"]))

    # ---------- 2) 持续预报：单值与四值序列 ----------
    for rel in SURFACES:
        if rel != PAGE and not docs:
            continue
        s = get(rel)
        for mt in RE_EN_PERS.finditer(s):
            if not _accept(mt.group(1), (f["drop_pers_1"],)):
                bad.append("%s：写「%s%% over persistence」，现算是 %.2f%%"
                           % (where(rel), mt.group(1), f["drop_pers_1"]))
        for mt in RE_ZH_PERS_ONE.finditer(s):
            if not _accept(mt.group(1), (f["drop_pers_1"],)):
                bad.append("%s：写「相对持续预报低 %s%%」，现算是 %.2f%%"
                           % (where(rel), mt.group(1), f["drop_pers_1"]))
        for mt in RE_ZH_PERS_PAIR.finditer(s):
            a, b = mt.group(1), mt.group(2)
            ea = _f(f["rmse_1"]["model"], _dp(a))
            eb = _f(f["rmse_1"]["pers"], _dp(b))
            if a != ea or b != eb:
                bad.append("%s：括号里写「%s 对 %s」，现算应为「%s 对 %s」"
                           % (where(rel), a, b, ea, eb))
        for mt in RE_ZH_PERS_SEQ.finditer(s):
            for i, h in enumerate(HORIZONS):
                w = mt.group(i + 1)
                if not _accept(w, (f["drop_pers_" + h],)):
                    bad.append("%s：序列第 %d 个写 %s%%，现算是 %.2f%%（%s 天相对持续预报）"
                               % (where(rel), i + 1, w, f["drop_pers_" + h], h))
        # 页面句式：「都低于持续预报（误差下降 20.8% / 17.2% / 15.4% / 8.9%）」
        for mt in RE_ZH_PERS_DROP.finditer(s):
            for i, h in enumerate(HORIZONS):
                w = mt.group(i + 1)
                if not _accept(w, (f["drop_pers_" + h],)):
                    bad.append("%s：写「误差下降 … 第 %d 个 %s%%」，%s 天现算是 %.2f%%"
                               % (where(rel), i + 1, w, h, f["drop_pers_" + h]))
        # 页面 RMSE 表的「+N%」列：每个格子都要等于某个时效的持续预报优势
        for mt in RE_PLUS_CELL.finditer(s):
            w = mt.group(1)
            if not any(_accept(w, (f["drop_pers_" + h],)) for h in HORIZONS):
                bad.append("%s：表里写「+%s%%」，四个时效现算是 %s"
                           % (where(rel), w,
                              " / ".join("%.1f%%" % f["drop_pers_" + h]
                                         for h in HORIZONS)))

    # ---------- 3) 收缩口径：四值序列、1 天单值、3/7/14 的绝对差 ----------
    for rel in SURFACES:
        if rel != PAGE and not docs:
            continue
        s = get(rel)
        for mt in RE_ZH_BLEND_SEQ.finditer(s):
            for i, h in enumerate(HORIZONS):
                w = mt.group(i + 1)
                if not _accept(w, (f["blend_gain_" + h], f["drop_flat_" + h])):
                    bad.append("%s：收缩序列第 %d 个写 %s%%，现算是 %.2f%%"
                               % (where(rel), i + 1, w, f["blend_gain_" + h]))
        for mt in RE_ZH_ONE_DAY.finditer(s):
            w = mt.group(1)
            if not _accept(w, (f["blend_gain_1"], f["drop_flat_1"])):
                bad.append("%s：写「只有 1 天的 %s%% 是实的」，现算是 %.2f%%"
                           % (where(rel), w, f["blend_gain_1"]))
        for mt in RE_ZH_GAP.finditer(s):
            got = [mt.group(i + 1) for i in range(3)]
            cands = [[_f(f["blend_gap_" + h], _dp(got[i])) for i, h in enumerate(("3", "7", "14"))],
                     [_f(f["rmse_" + h]["flat"] - f["rmse_" + h]["model"], _dp(got[i]))
                      for i, h in enumerate(("3", "7", "14"))]]
            if not any(all(got[i] == c[i] for i in range(3)) for c in cands):
                bad.append("%s：写「3 / 7 / 14 天只赢 %s」，现算收缩口径 %s、未收缩口径 %s"
                           % (where(rel), " / ".join(got), " / ".join(cands[0]),
                              " / ".join(cands[1])))

    # ---------- 4) 固定串：零值占比与两组 AUC 序列 ----------
    f["zero_share_str"] = _f(f["zero_share"], 1) + "%"
    f["auc_model_str"] = " / ".join(_f(f["auc_" + h]["model"], 3) for h in HORIZONS)
    f["auc_pers_str"] = " / ".join(_f(f["auc_" + h]["pers"], 3) for h in HORIZONS)
    f["auc_clim_str"] = " / ".join(_f(f["auc_" + h]["clim"], 3) for h in HORIZONS)

    for rel in SURFACES:
        if rel != PAGE and not docs:
            continue
        s = get(rel)
        for banned in BANNED:
            if banned in s:
                bad.append("%s：仍出现过期说法「%s」" % (where(rel), banned))

    if docs:
        for rel in MUST_HAVE_ZERO_SHARE:
            if f["zero_share_str"] not in get(rel):
                bad.append("%s：缺少零值占比「%s」（现算自 index_variant_audit.json）"
                           % (where(rel), f["zero_share_str"]))
        for rel in MUST_HAVE_AUC:
            s = get(rel)
            norm = re.sub(r"\s+", " ", s)
            for label, canon in (("模型", f["auc_model_str"]),
                                 ("持续预报", f["auc_pers_str"])):
                tight = canon.replace(" ", "")
                if canon in norm or tight in norm.replace(" ", ""):
                    continue
                # README.en.md 用表格写「模型 / 持续预报」成对出现，也接受
                pair_list = ["%s / %s" % (_f(f["auc_" + h]["model"], 3),
                                          _f(f["auc_" + h]["pers"], 3))
                             for h in HORIZONS]
                if all(p in norm for p in pair_list):
                    continue
                bad.append("%s：缺少%s AUC 序列「%s」（现算自 dashboard_data.json）"
                           % (where(rel), label, canon))
        for rel in MUST_HAVE_AUC_CLIM:
            norm = re.sub(r"\s+", " ", get(rel))
            tight = f["auc_clim_str"].replace(" ", "")
            if f["auc_clim_str"] not in norm and tight not in norm.replace(" ", ""):
                bad.append("%s：缺少气候平均 AUC 序列「%s」（现算自 dashboard_data.json）"
                           % (where(rel), f["auc_clim_str"]))

    # 页面上的收缩系数也要与产物一致
    if docs or doc is not None:
        s = get(PAGE)
        mt = re.search(r"β\* = ([0-9.]+)(?: / ([0-9.]+))?(?: / ([0-9.]+))?(?: / ([0-9.]+))?", s)
        if mt:
            got = [g for g in mt.groups() if g]
            exp = [_f(f["blend_beta_" + h], 1) for h in HORIZONS]
            if got != exp:
                bad.append("成品页：收缩系数写「%s」，现算应为「%s」"
                           % (" / ".join(got), " / ".join(exp)))

    return f, bad


def main():
    argv = sys.argv[1:]
    as_json = "--json" in argv
    docs = "--no-docs" not in argv
    doc = None
    if "--page" in argv:
        doc = io.open(argv[argv.index("--page") + 1], encoding="utf-8").read()
    f, bad = audit(doc=doc, docs=docs)
    if as_json:
        print(json.dumps({"facts": f, "failures": bad}, ensure_ascii=False,
                         indent=1))
        return 0 if not bad else 1
    print("派生百分比审计  derived_audit")
    print("  1 天相对持续预报        %.2f%%" % f["drop_pers_1"])
    print("  四个时效相对持续预报    " + " / ".join("%.2f%%" % f["drop_pers_" + h] for h in HORIZONS))
    print("  1 天相对常数均值        %.2f%%（收缩口径 %.2f%%）"
          % (f["drop_flat_1"], f["blend_gain_1"]))
    print("  收缩口径相对常数均值    " + " / ".join("%.2f%%" % f["blend_gain_" + h] for h in HORIZONS))
    print("  收缩后 3/7/14 绝对差    " + " / ".join("%.4f" % f["blend_gap_" + h] for h in ("3", "7", "14")))
    print("  零值占比（三驱动口径）  " + f["zero_share_str"])
    print("  排序 AUC（模型 / 持续 / 气候）")
    print("    " + f["auc_model_str"])
    print("    " + f["auc_pers_str"])
    print("    " + f["auc_clim_str"])
    if bad:
        print("\n=== 失败 %d 项 ===" % len(bad))
        for b in bad:
            print("  FAIL " + b)
        return 1
    print("\nRESULT ALL PASS（材料里每个派生百分比都由 data/processed 现算，"
          "页面 / README / 文档说的是同一个数）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
