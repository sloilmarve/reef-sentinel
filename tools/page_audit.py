#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""page_audit.py - 离线复核成品页的可核对声明（纯标准库、不需要浏览器、不联网）。

为什么需要这个脚本：
`docs/01_项目说明.md` 的「数据伦理、隐私与无障碍」一节写了若干**可核对数字**
（8 张图全部有替代文本、95 个表头全部带 scope、17 个横滚容器带 role/tabindex/aria-label、
14 个折叠块、8 个日期标签）以及「打开页面不发出任何外部请求」这条隐私声明。
这些声明不能只靠自我描述 —— 评委应当在提交包内用一条命令复核它。
本脚本就是那条命令：直接读 `demo/index.html` 的字节，数出来，逐条断言。

用法：
    python tools\\page_audit.py            # 打印事实表 + RESULT ALL PASS / RESULT FAIL n
    python tools\\page_audit.py --json      # 额外输出机器可读的事实（供别的脚本复用）

范围说明：这里只做**静态可判**的部分。键盘可达性、焦点环、390 px 下点击区 ≥ 32 px
这类需要布局的能力，由浏览器端交互验收脚本负责（见 .taste-skill/test-interaction.mjs）。
"""
import argparse
import json
import re
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAGE = ROOT / "demo" / "index.html"
DATA = ROOT / "data" / "processed"

# 期望值：与 docs/01 第 6 节「数据伦理、隐私与无障碍」、00_提交包说明.md 第 1 节的公开数字一一对应
EXPECT = {
    "script": 1,          # 单文件：整页只有一个内联脚本
    "outbound_links": 3,  # 页脚可见链接：在线地址 / 在线版 / 源码（点击才离开，不自动请求）
    "img": 8,             # 8 张图（7 张实景照片 + 1 张 NOAA 官方对照图）
    "th": 95,             # 表头数量
    "tw": 17,             # 表格容器（第 58 轮起窄屏改为逐行清单，不再横向滚动）
    "details": 15,        # 折叠块（第 37 轮新增「高风险应用的四个必须说明」、第 40 轮新增「依据与来源」）
    "day": 8,             # 未来 8 天日期标签
    "h2": 6,              # 六个板块
    "h3": 11,             # 11 张卡
    "secnum": 6,          # 审计用序号（视觉隐藏，保留在 DOM 里供校验）
    "ignore": 7,          # taste-skill-ignore 门禁抑制标记：清理源码注释时必须原样留下（第 58 轮）
}


def _count(pat, text):
    return len(re.findall(pat, text))


def facts_of(html):
    """数出页面里所有可核对的静态事实。"""
    imgs = re.findall(r"<img\b[^>]*>", html)
    tws = re.findall(r'<div class="tw"[^>]*>', html)
    days = re.findall(r'<div class="day">', html)
    return {
        "bytes": len(html.encode("utf-8")),
        "chars": len(html),
        "script": _count(r"<script", html),
        "link": _count(r"<link", html),
        "iframe": _count(r"<iframe", html),
        "form": _count(r"<form", html),
        "external_src": _count(r'src="https?://', html),
        "css_url_http": _count(r"url\(https?://", html),
        "css_import": _count(r"@import", html),
        # 可见链接（<a href>）：点开才会离开本页，不产生任何自动请求；页脚刻意保留在线版与源码地址
        "outbound_links": _count(r'<a [^>]*href="https?://', html),
        "storage_api": _count(r"(?:localStorage|sessionStorage|document\.cookie|indexedDB)", html),
        "network_api": _count(r"(?:fetch\(|XMLHttpRequest|sendBeacon|WebSocket|EventSource)", html),
        "img": len(imgs),
        "img_alt": sum(1 for t in imgs if re.search(r'alt="[^"]+"', t)),
        "img_inline": sum(1 for t in imgs if "data:image" in t),
        "th": _count(r"<th\b", html),
        "th_scope": sum(1 for t in re.findall(r"<th\b[^>]*>", html) if "scope=" in t),
        "tw": len(tws),
        "tw_region": sum(1 for t in tws if 'role="region"' in t),
        "tw_tabindex": sum(1 for t in tws if 'tabindex="0"' in t),
        "tw_label": sum(1 for t in tws if re.search(r'aria-label="[^"]+"', t)),
        # 窄屏把表格展成逐行清单（report.css ≤620px）：每个数据格都要有生成器写下的列名 data-l，
        # 少一个那一格在手机上就没有标签。列名来自首行表头，见 pipeline/editorial.py 的 _scope。
        "td": _count(r"<td\b", html),
        "td_data_l": sum(1 for t in re.findall(r"<td\b[^>]*>", html) if "data-l=" in t),
        "details": _count(r"<details\b", html),
        "summary": _count(r"<summary\b", html),
        "day": len(days),
        "day_parts": sum(1 for d in re.findall(r'<div class="day">.*?</div>', html, re.S)
                         if 'class="d"' in d and 'class="lv' in d and 'class="t"' in d),
        "h2": _count(r"<h2\b", html),
        "h3": _count(r"<h3\b", html),
        "secnum": _count(r'class="secnum"', html),
        # 门禁抑制标记：带这个字样的注释是载荷不是说明 —— 第 58 轮做「成品页不留改版日志」时
        # 一次删掉了 .hero-scrim 里的抑制标记，lint.mjs 当场从 0 FAIL 变 1 FAIL（[gradient]）。
        # 数量在这里钉住，以后谁再清理注释都会立刻被这条拦住。
        "ignore": _count(r"taste-skill-ignore", html),
        "data_image": _count(r"data:image", html),
        "woff2": _count(r"woff2", html),
        # 手机横滚：300 根柱各 1px 最小宽 + 1px 间距，在窄屏比容器还宽，会把整页撑出横向滚动
        # （390px 视口实测文档 635px）。第 51 轮在 ≤1000px 去掉间距、允许次像素宽；
        # 离线只能查「规则在不在」，几何要跑 .taste-skill/diag-r51-overflow.mjs 逐宽度量。
        "bars_gap0": 1 if ".bars{gap:0}" in html else 0,
        "bars_minw0": 1 if ".bar{min-width:0}" in html else 0,
        "aria_live": _count(r"aria-live", html),
        # 国际评委入口：README.en.md 承诺「英文摘要在顶栏 EN 里一点就到」。
        # 链接与目标都数一遍，并把「EN 在导航里」也查掉 —— 它以前挂在 .updated 里，
        # 而那一行在 ≤620px 被整条隐藏，手机上就再也没有英文入口了。
        "en_link": _count(r'<a [^>]*href="#en"', html),
        "en_target": _count(r'<details\b[^>]*id="en"', html),
        "en_in_nav": 1 if re.search(r'<nav class="navlinks">(?:(?!</nav>).)*href="#en"', html, re.S) else 0,
        "lang_zh": 1 if re.search(r'<html lang="zh', html) else 0,
        "title": 1 if re.search(r"<title>[^<]+</title>", html) else 0,
        "viewport": 1 if 'name="viewport"' in html else 0,
    }


def _load(name):
    """读一份 data/processed 产物；缺文件返回 None（由调用方决定是失败还是跳过）。"""
    p = DATA / name
    if not p.is_file():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def en_block(html):
    """取出英文摘要块（details id="en"）的 HTML。"""
    m = re.search(r'<details\b[^>]*id="en"[^>]*>(.*?)</details>', html, re.S)
    return m.group(1) if m else ""


def en_evidence(html):
    """英文摘要要能单独站住：它引用的每个数字都拿 data/processed 现算一遍。

    为什么单独查这一块：页面正文是中文，国际评委能读到的就是这一段（顶栏 EN 一点就到）。
    所以它不能只有「部署与成本」这种叙述，必须把「模型样本外到底行不行、泄漏怎么查的、
    跨站能不能迁移、许可怎么放、哪里不安全」写清楚 —— 而且写的数字必须与产物一致，
    不能是出稿时手抄的一份。
    """
    facts = {}
    bad = []
    block = en_block(html)
    if not block:
        return {"en_block_chars": 0}, ['英文摘要块不存在（<details id="en">）']
    text = re.sub(r"<[^>]+>", "", block)
    facts["en_block_chars"] = len(text)

    def need_in(s, why):
        if s not in text:
            bad.append("英文摘要缺少 %r（%s）" % (s, why))

    D = _load("dashboard_data.json")
    MS = _load("multisite_transfer.json")
    LK = _load("leakage_audit.json")
    CMP = _load("compound_label_audit.json")

    if D is None:
        bad.append("读不到 data/processed/dashboard_data.json，无法复核英文摘要里的模型数字")
    else:
        M = D.get("metrics", {})
        for h in ("1", "3", "7", "14"):
            m = M.get(h, {})
            for key, why in (("model_auc", "模型排序 AUC"), ("pers_auc", "持续预报排序 AUC"),
                             ("model_rmse", "模型 RMSE"), ("pers_rmse", "持续预报 RMSE")):
                if key not in m:
                    bad.append("dashboard_data.json 的 metrics[%s] 没有 %s" % (h, key))
                    continue
                need_in(("%.3f" if key.endswith("auc") else "%.4f") % m[key],
                        "%s 天 %s（须与产物现算一致）" % (h, why))

    if MS is None:
        bad.append("读不到 data/processed/multisite_transfer.json，无法复核跨站迁移结论")
    else:
        cells = [(s, h) for s in MS.get("sites", []) for h in ("1", "3", "7", "14")]
        wins = sum(1 for s, h in cells if s["skill"][h]["model_auc"] > s["skill"][h]["pers_auc"])
        need_in("%d of %d" % (wins, len(cells)),
                "跨站迁移胜出格数（3 站 × 4 时效，须与产物现算一致）")

    if LK is None:
        bad.append("读不到 data/processed/leakage_audit.json，无法复核泄漏审计结论")
    else:
        arm = LK.get("threshold_and_label_arms", {})
        chg = arm.get("hazard_days_changed_vs_record_thresholds")
        nd = LK.get("n_days")
        if chg is None or not nd:
            bad.append("leakage_audit.json 里没有 hazard_days_changed_vs_record_thresholds / n_days")
        else:
            need_in("%d of %s" % (chg, format(int(nd), ",")),
                    "训练前缀阈值下灾害计数改变的天数（须与产物现算一致）")
            need_in("(%.1f%%)" % (chg / float(nd) * 100), "同一结论的百分比")

    if CMP is None:
        bad.append("读不到 data/processed/compound_label_audit.json，无法复核复合灾害标签那一档")
    else:
        by_h = CMP.get("by_h", {})
        m7, p7 = by_h.get("7", {}), None
        if m7:
            need_in("%.3f" % m7["model_auc"], "复合灾害标签 7 天排序 AUC（最弱那一档）")
            need_in("%.3f" % m7["pers_auc"], "复合灾害标签 7 天持续预报 AUC")
        pos = by_h.get("1", {}).get("pos")
        if pos is None:
            bad.append("compound_label_audit.json 的 by_h['1'] 没有 pos")
        else:
            need_in("on only %d out-of-sample positive days" % pos,
                    "复合灾害标签的样本外正类天数（提示抽样噪声）")

    # 诚实负结果、安全边界、开放许可与可复现入口 —— 缺哪条国际评委就得自己猜
    for s, why in (("0.495", "被弃用的二元分类器样本外 AUC（诚实负结果）"),
                   ("MetMalaysia", "安全使用边界（以官方发布为准）"),
                   ("Sabah Parks", "安全使用边界（以官方发布为准）"),
                   ("MIT", "代码与文档的开放许可"),
                   ("CC BY 4.0", "衍生数据的开放许可"),
                   ("CC BY-SA", "内嵌实景照片的许可（与 CC BY 4.0 是两回事，必须分开写）"),
                   ("public domain", "上游数据不二次授权"),
                   ("plan_audit.py", "验证计划里的数字可现算复核"),
                   ("reviewer_repro.py", "成品页可逐字节复算")):
        need_in(s, why)

    if facts["en_block_chars"] < 3000:
        bad.append("英文摘要只剩 %d 字（国际评委能读到的全部内容，不得再缩水）"
                   % facts["en_block_chars"])
    return facts, bad


def settlement_gate(html):
    """核「窗口结算」这段披露：该出现时必须出现，不该出现时不许出现。

    为什么单独查它：这段披露由 `pipeline/editorial.py` 在版面层插入，触发条件是
    「最近一次海洋热浪的起点落在学习模型 as-of 起 28 天内」。第 37 轮页面正文新增
    一句「数据窗口 2022-11-01 至 2026-10-16」后，版面层当时那条宽松的「任意 A 至 B」
    正则被记录期那一段抢走，结算披露被**静默删掉** —— 页面照常出片、所有旧门禁照常
    全绿，只有人眼逐行比对才看得见。所以这里把触发条件从产物现算一遍，两个方向都断言：
    条件成立而页面没有这段 = FAIL（披露被吞）；条件不成立而页面有这段 = FAIL（口径过期）。
    """
    facts = {}
    bad = []
    BF = _load("bleach_forecast.json")
    BW = _load("bleaching_watch.json")
    if BF is None or BW is None:
        return {"settle_expected": -1}, ["读不到 bleach_forecast.json / bleaching_watch.json，无法复核窗口结算披露"]
    events = BW.get("events") or []
    asof = (BF.get("now") or {}).get("date") or ""
    if not events or not asof:
        return {"settle_expected": -1}, ["bleaching_watch.json 没有 events 或 bleach_forecast.json 没有 now.date"]
    try:
        d0 = date.fromisoformat(asof)
    except ValueError:
        return {"settle_expected": -1}, ["bleach_forecast.json 的 now.date 不是 ISO 日期：%r" % asof]
    last = events[-1]
    start, end = str(last.get("start")), str(last.get("end"))
    win_end = (d0 + timedelta(days=int(BF.get("label", {}).get("horizon_days") or 28))).isoformat()
    expected = 1 if asof <= start <= win_end else 0
    facts["settle_expected"] = expected
    facts["settle_window"] = "%s..%s" % (asof, win_end)
    facts["settle_event"] = "%s..%s" % (start, end)
    facts["settle_in_page"] = 1 if "窗口结算" in html else 0
    if expected and not facts["settle_in_page"]:
        bad.append("窗口结算披露被吞掉了：最近一次热浪 %s 的起点落在 as-of %s 起 %s 天内（%s），"
                   "页面里却没有「窗口结算」这一段（版面层触发条件或正文措辞被改动了）"
                   % (start, asof, win_end, facts["settle_window"]))
    if not expected and facts["settle_in_page"]:
        bad.append("窗口结算披露口径过期：最近一次热浪 %s 的起点不在 as-of %s 起 %s 天内，"
                   "页面里却仍有「窗口结算」这一段" % (start, asof, win_end))
    if expected:
        for s in (start, end, asof, win_end):
            if s not in html:
                bad.append("窗口结算披露里缺日期 %s（必须写清预测窗口与实际事件区间）" % s)
    return facts, bad


def risk_disclosure(html):
    """核官方规则点名的高风险四项披露：数据来源 / 模型不确定性 / 可能出错 / 安全使用边界。

    为什么单独查它：评审规则对灾害预警、生态识别这类高风险应用写死了四件必须说明的事
    （data provenance, model uncertainty, possible errors, safe-use boundaries）。
    页面正文以前只在别处零散提过两件，没有一处按规则自己的四个名字成段回答 ——
    第 37 轮补了这一段（`pipeline/build_static.py` 的 `_risk`），并且不展开也能在页脚
    看到结论摘要。这里把「四个名字都在同一段里、页脚也有摘要」钉成可复核断言。
    """
    facts = {}
    bad = []
    m = re.search(r'<details\b[^>]*>(?:(?!</details>).)*?高风险应用(?:(?!</details>).)*?</details>', html, re.S)
    if not m:
        bad.append("找不到「高风险应用」折叠块（官方规则点名要求成段说明的四件事）")
        facts["risk_block_chars"] = 0
        return facts, bad
    block = m.group(0)
    facts["risk_block_chars"] = len(re.sub(r"<[^>]+>", "", block))
    for s in ("数据来源", "模型不确定性", "可能出错", "安全使用边界"):
        if s not in block:
            bad.append("高风险披露段里缺「%s」（规则点名的四件事之一）" % s)
    # 不展开也要能看到结论：页脚那一条 .sub 必须把四项名字与两个最要紧的负结果写出来
    foot = html[html.rfind('<footer class="foot'):]
    if "高风险应用的四项必须说明" not in foot:
        bad.append("页脚没有高风险四项的摘要（折叠块默认收起，评委不展开就看不到）")
    for s in ("0.495", "0.364"):
        if s not in foot:
            bad.append("页脚高风险摘要缺关键数字 %s（被弃用的二元 AUC / 白化 PR-AUC）" % s)
    facts["risk_in_foot"] = 1 if "高风险应用的四项必须说明" in foot else 0
    return facts, bad


def refs_disclosure(html):
    """核「依据与来源」折叠块：方法出处与上游产品是否逐条可打开核对。

    为什么单独查它：评审规则要求高风险应用交代数据来源，评委最常问的是
    「p90 / 海洋热浪 / MMM / DHW 这些定义从哪来」。页面正文以前只有裸名字
    （Hobday、MMM、DHW），没有一个 DOI 或产品页链接 —— 第 40 轮补了这一段
    （`pipeline/build_static.py` 的 `_refs`），页脚另有一条不展开也看得到的摘要。
    `tools/refs_audit.py` 会把这一段的字符串与 docs/02 第七节逐条比对；
    这里只钉页面自己的结构与要素。
    """
    facts = {}
    bad = []
    m = re.search(r'<details\b[^>]*id="refs"[^>]*>(.*?)</details>', html, re.S)
    if not m:
        bad.append('找不到「依据与来源」折叠块（<details id="refs">）')
        facts["refs_block_chars"] = 0
        facts["refs_entries"] = 0
        facts["refs_dois"] = 0
        return facts, bad
    block = m.group(0)
    inner = m.group(1)
    facts["refs_block_chars"] = len(re.sub(r"<[^>]+>", "", block))
    facts["refs_entries"] = inner.count('class="sub"')
    facts["refs_dois"] = len(re.findall(r"doi:10\.\d{4,9}/\S+", block))
    if facts["refs_entries"] != 8:
        bad.append("「依据与来源」条目数 = %d，期望 8（方法定义 / 白化热压力 / 官方引用方式 / ERA5 / 取数入口与许可 / 复合事件 / 岭回归 / 照片）" % facts["refs_entries"])
    if facts["refs_dois"] < 7:
        bad.append("「依据与来源」里的 DOI 只有 %d 个，期望至少 7 个（Hobday 2016/2018、Liu 2014、Skirving 2020、Hersbach 2020、Copernicus 数据集、Zscheischler 2018、Hoerl & Kennard 1970）" % facts["refs_dois"])
    for s in ("Wikimedia Commons", "CC BY-SA", "LICENSE 第 4 条"):
        if s not in block:
            bad.append("「依据与来源」缺照片署名要素：%s" % s)
    foot = html[html.rfind('<footer class="foot'):]
    facts["refs_in_foot"] = 1 if "依据与来源：" in foot else 0
    if not facts["refs_in_foot"]:
        bad.append("页脚没有「依据与来源」摘要（折叠块默认收起，评委不展开就看不到）")
    for s in ("Hobday et al. 2016/2018", "CC BY 4.0", "docs/02 第七节"):
        if s not in foot:
            bad.append("页脚依据摘要缺 %s" % s)
    return facts, bad


def audit(html):
    """返回 (facts, failures)。failures 为空即全部通过。"""
    f = facts_of(html)
    bad = []

    def need(key, want, why):
        if f[key] != want:
            bad.append("%s = %s，期望 %s（%s）" % (key, f[key], want, why))

    # 隐私与自足：单文件、不联网、不收集
    need("script", EXPECT["script"], "整页只应有一个内联脚本")
    for key, why in (("link", "不得外链样式表/字体"), ("iframe", "不得内嵌外部页面"),
                     ("form", "不得有表单（不收集用户数据）"),
                     ("external_src", "不得引用任何 http(s) 资源"),
                     ("css_url_http", "CSS 不得引用外部 URL"),
                     ("css_import", "CSS 不得 @import"),
                     ("storage_api", "不得使用 Cookie / 本地存储"),
                     ("network_api", "不得发起网络请求（fetch/XHR/WebSocket）")):
        need(key, 0, why)
    need("outbound_links", EXPECT["outbound_links"],
         "只允许页脚那几条可见链接（点击才离开本页，不产生自动请求）")

    # 无障碍：替代文本、表头 scope、横滚容器、折叠块、日期标签
    if f["img_alt"] != f["img"] or f["img_inline"] != f["img"]:
        bad.append("图片替代文本/内联数不齐：img=%d alt=%d inline=%d（每张图都要有 alt 且内联）"
                   % (f["img"], f["img_alt"], f["img_inline"]))
    need("img", EXPECT["img"], "7 张实景照片 + 1 张 NOAA 官方对照图")
    if f["th_scope"] != f["th"]:
        bad.append("表头 scope 不齐：th=%d 带 scope=%d（每个表头都要有 scope）" % (f["th"], f["th_scope"]))
    need("th", EXPECT["th"], "表头总数（docs/01 第 6 节公开数字）")
    need("tw", EXPECT["tw"], "表格容器（窄屏逐行展开）")
    if f["td_data_l"] != f["td"]:
        bad.append("数据格列名不齐：td=%d 带 data-l=%d（窄屏逐行清单里没标签的格子会只剩数字）"
                   % (f["td"], f["td_data_l"]))
    for key, why in (("tw_region", '每个表格容器都要 role="region"'),
                     ("tw_tabindex", '每个表格容器都要 tabindex="0"（键盘可聚焦）'),
                     ("tw_label", "每个表格容器都要中文 aria-label")):
        if f[key] != f["tw"]:
            bad.append("%s = %d，表格容器共 %d（%s）" % (key, f[key], f["tw"], why))
    need("details", EXPECT["details"], "折叠块总数")
    for key, why in (("bars_gap0", "窄屏柱带必须去掉 1px 间距（否则整页横向滚动）"),
                     ("bars_minw0", "窄屏柱必须允许次像素宽")):
        need(key, 1, why)
    if f["summary"] != f["details"]:
        bad.append("折叠块与 summary 数不齐：details=%d summary=%d" % (f["details"], f["summary"]))
    need("ignore", EXPECT["ignore"], "门禁抑制标记 taste-skill-ignore（清理注释时不得删掉）")
    need("day", EXPECT["day"], "未来 8 天日期标签")
    if f["day_parts"] != f["day"]:
        bad.append("日期标签结构不齐：day=%d 三件套齐全=%d" % (f["day"], f["day_parts"]))

    # 结构：板块 / 卡片 / 审计序号 / 语言与视口
    need("h2", EXPECT["h2"], "六个板块")
    need("h3", EXPECT["h3"], "11 张卡")
    need("secnum", EXPECT["secnum"], "审计用序号（DOM 保留、视觉隐藏）")
    for key, why in (("lang_zh", "页面语言必须声明"), ("title", "必须有标题"),
                     ("viewport", "必须有 viewport（移动端）")):
        need(key, 1, why)
    if f["data_image"] != f["img"]:
        bad.append("data:image 数 %d 与 img 数 %d 不一致" % (f["data_image"], f["img"]))
    if f["woff2"] < 1:
        bad.append("字体没有内联（woff2 = %d）" % f["woff2"])
    if f["aria_live"] < 1:
        bad.append("没有 aria-live 读出区")

    # 国际评委入口（README.en.md 的承诺：英文摘要从顶栏 EN 一点就到）
    if f["en_link"] != 1 or f["en_target"] != 1 or f["en_in_nav"] != 1:
        bad.append("顶栏 EN 入口不完整：链接=%d 目标=%d 在导航内=%d（英文摘要必须能从顶栏直接点到）"
                   % (f["en_link"], f["en_target"], f["en_in_nav"]))
    if "Summary for international reviewers" not in html:
        bad.append("英文摘要块的标题不见了（README.en.md 承诺页面上有这一块）")

    # 英文摘要必须能单独站住：引用的数字与 data/processed 现算一致
    ef, ebad = en_evidence(html)
    f.update(ef)
    bad.extend(ebad)

    # 窗口结算披露：触发条件从产物现算，两个方向都断言（第 37 轮被静默吞掉过）
    sf, sbad = settlement_gate(html)
    f.update(sf)
    bad.extend(sbad)

    # 官方规则点名的高风险四项披露（数据来源 / 模型不确定性 / 可能出错 / 安全使用边界）
    rf, rbad = risk_disclosure(html)
    f.update(rf)
    bad.extend(rbad)

    # 方法出处（第 40 轮）：每个方法名与每个上游产品都要能打开核对
    xf, xbad = refs_disclosure(html)
    f.update(xf)
    bad.extend(xbad)
    return f, bad


def main():
    ap = argparse.ArgumentParser(description="离线复核成品页的可核对声明")
    ap.add_argument("--page", default=str(PAGE), help="成品页路径（默认 demo/index.html）")
    ap.add_argument("--json", action="store_true", help="额外打印机器可读的事实 JSON")
    args = ap.parse_args()

    p = Path(args.page)
    if not p.is_file():
        print("RESULT FAIL 1\n  找不到成品页：%s" % p)
        return 1
    html = p.read_text(encoding="utf-8")
    f, bad = audit(html)

    print("=== 成品页事实（%s）===" % p)
    order = ["bytes", "chars", "script", "link", "external_src", "network_api", "storage_api",
             "form", "outbound_links", "img", "img_alt", "th", "th_scope", "tw", "tw_region", "tw_label",
             "details", "summary", "day", "day_parts", "h2", "h3", "secnum",
             "data_image", "woff2", "aria_live", "en_link", "en_target", "en_in_nav", "en_block_chars",
             "settle_expected", "settle_in_page", "settle_window", "settle_event",
             "risk_block_chars", "risk_in_foot",
             "refs_block_chars", "refs_entries", "refs_dois", "refs_in_foot"]
    for k in order:
        print("  %-14s %s" % (k, f[k]))
    if args.json:
        print(json.dumps(f, ensure_ascii=False, sort_keys=True))
    if bad:
        print("\n=== 不一致 ===")
        for b in bad:
            print("  FAIL %s" % b)
        print("RESULT FAIL %d" % len(bad))
        return 1
    print("\nRESULT ALL PASS（%d 项事实与 docs/01 第 6 节的公开数字一致）" % len(order))
    return 0


if __name__ == "__main__":
    sys.exit(main())
