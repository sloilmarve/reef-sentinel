#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""社区作品帖与平台分版草稿的机械核对（纯标准库、不联网、不需要浏览器）。

「传播与公众采纳」这 15% 的物料，是《作品帖与发布草稿》里可以直接复制粘贴的文案。
文案看起来没法自动检查，其实每一条都能查：

1. 平台的字数上限（X 的加权 280、小红书标题 20 与正文 1,000）；
2. 文案自己声明的字数（「约 N 字 / 约 N 词」）必须与正文实测相符；
3. 每个平台的版本都必须保留一条局限说明（这是这份材料自己定的纪律）；
4. 每个平台的版本都必须留下一条可执行的链接（在线版或源码仓库）；
5. 不得出现手机号、不得承诺 90 天内做不到的事（材料第七节的红线）；
6. 文案里的公开数字必须与成品页一致（文案与页面各说一套，是公众最容易发现的错）；
7. 文案里的关键数字必须与 data/processed 现算一致（复合灾害日 44 天 / 3.0% / 2024 年 15 天）。

X 的字符计数用官方口径：URL 一律按 23 个字符计，东亚全角字符按 2 个计。

用法：
    python tools\\outreach_audit.py            # 打印事实表并逐条断言
    python tools\\outreach_audit.py --json     # 只输出 JSON
"""

import argparse
import io
import json
import os
import re
import sys
import unicodedata

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOC06 = "docs/06_作品帖与发布草稿.md"
PAGE = os.path.join("demo", "index.html")
DASH = os.path.join("data", "processed", "dashboard_data.json")

X_LIMIT = 280                 # X / Twitter 单条上限（加权字符）
X_URL_WEIGHT = 23             # X 把任何 URL 一律算 23 个字符
XHS_TITLE_LIMIT = 20          # 小红书标题上限（材料自己声明「标题 ≤20 字」）
XHS_BODY_LIMIT = 1000         # 小红书正文上限
LEN_TOL = 0.10                # 声明的字数允许 ±10%

PAGE_URL = "sloilmarve.github.io/reef-sentinel"
REPO_URL = "github.com/sloilmarve/reef-sentinel"
COMMUNITY_URL = "deepseek.club/community/ai4climate"

# 每个平台的版本都必须至少命中一个「局限」信号（材料第八节的通用纪律）
LIMIT_SIGNALS = ("局限", "如实", "不藏", "噪声", "AUC 0.495", "0.495",
                 "within noise", "state openly", "dropped", "honest")

# 第七节的红线：不得泄露隐私、不得承诺 90 天内做不到的事
RED_LINES = (
    (r"1[3-9]\d{9}", "疑似手机号"),
    (r"微信号|QQ 号|身份证", "疑似隐私信息"),
    (r"覆盖整个沙巴|覆盖全部沙巴|全部沙巴|即将覆盖", "承诺了 90 天内做不到的事"),
)

# 文案里的公开数字 → 成品页上可接受的写法（页面用四舍五入的地方在这里登记）
PAGE_ECHO = (
    ("1,446", ("1,446",)),
    ("20.8%", ("20.8%",)),
    ("17.2%", ("17.2%",)),
    ("15.4%", ("15.4%",)),
    ("8.9%", ("8.9%",)),
    ("0.1406", ("0.1406",)),
    ("0.1776", ("0.1776", "0.178")),
    ("0.796 / 0.665 / 0.600 / 0.615", ("0.796 / 0.665 / 0.600 / 0.615",)),
    ("0.495", ("0.495",)),
    ("0.364", ("0.364",)),
    ("0.311", ("0.311",)),
    ("0.242", ("0.242",)),
    ("0.013", ("0.013",)),
    ("0.717", ("0.717",)),
    ("15,178", ("15,178", "15178")),
    ("72.3%", ("72.3%",)),
    ("66 个特征", ("66 个特征",)),
)

URL_RE = re.compile(r"https?://\S+|(?:sloilmarve\.github\.io|github\.com|deepseek\.club)/\S+")


# ---------------------------------------------------------------------------
# 读与算
# ---------------------------------------------------------------------------
def _read(rel):
    """读材料。解压后的提交包里 00_提交包说明.md 位于 ai4climate/ 的上一层，
    与 tools/consistency_audit.py 的 readp() 保持同一套回退规则。"""
    p = os.path.join(ROOT, rel)
    if not os.path.exists(p):
        p = os.path.join(os.path.dirname(ROOT), rel)
    with io.open(p, encoding="utf-8") as fh:
        return fh.read()


def _sections(text):
    """按 ## / ### 标题切块，键是标题原文。"""
    out, cur = {}, None
    for line in text.splitlines():
        m = re.match(r"^#{2,3} (.+)$", line)
        if m:
            cur = m.group(1).strip()
            out[cur] = []
        elif cur is not None:
            out[cur].append(line)
    return dict((k, "\n".join(v)) for k, v in out.items())


def _sec(secs, prefix):
    for k, v in secs.items():
        if k.startswith(prefix):
            return v
    return ""


def _head(secs, prefix):
    """标题本身也是材料的一部分：「约 650 字」「280 字符内」都写在标题里。"""
    for k in secs:
        if k.startswith(prefix):
            return k
    return ""


def _unquote(t):
    """去掉引用符号与加粗，避免 ** 把数字与单位切开导致比较失败。"""
    t = re.sub(r"^>\s?", "", t, flags=re.M)
    return t.replace("**", "")


def _zh_count(t):
    """中文字数口径：汉字数 + 拉丁/数字串的个数（「1,446」算 1 个字）。"""
    cjk = len(re.findall(r"[\u4e00-\u9fff]", t))
    tok = len(re.findall(r"[A-Za-z0-9][A-Za-z0-9.,%°/-]*", t))
    return cjk + tok


def _copy_text(*chunks):
    """只把「会被读者看到的那几段」拼起来：红线检查不能去查写着红线的规矩本身。"""
    return "\n".join(chunks)


def _words(t):
    return len([w for w in t.split() if re.search(r"[A-Za-z]", w)])


def _weighted(s):
    """X 的加权字符数：URL 记 23，全角字符记 2。"""
    s = URL_RE.sub("U" * X_URL_WEIGHT, s)
    n = 0
    for ch in s:
        n += 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
    return n


def _stated(text, unit):
    m = re.search(r"约\s*([\d,]+)\s*" + unit, text)
    return int(m.group(1).replace(",", "")) if m else None


def facts():
    """把文案里可以被机器量出来的东西全量出来。"""
    doc = _read(DOC06)
    page = _read(PAGE)
    secs = _sections(doc)

    zh = _unquote(_sec(secs, "二、正文"))
    en = _unquote(_sec(secs, "三、英文短版"))
    xhs = _sec(secs, "8.1 小红书")
    x = _unquote(_sec(secs, "8.2 X"))
    li = _unquote(_sec(secs, "8.3 LinkedIn"))

    posts = [(int(a), b.strip()) for a, b in re.findall(r"^(\d)\. (.+)$", _unquote(x), re.M)]
    mtitle = re.search(r"标题\*\*：(.+)", xhs) or re.search(r"标题：(.+)", xhs)
    title = mtitle.group(1).strip() if mtitle else ""
    body = xhs.split("**正文**：")[-1]

    d = json.loads(_read(DASH))
    comp = d["series"]["compound"]
    haz = sum(comp)
    days = len(comp)
    worst = None
    for y in d["yearly"]:
        v = y.get("compound_days", y.get("compound"))
        if worst is None or (v or 0) > worst[1]:
            worst = (str(y.get("year")), v or 0)

    f = {
        "x_posts": len(posts),
        "x_lengths": [len(t) for _, t in posts],
        "x_weighted": [_weighted(t) for _, t in posts],
        "x_limit": X_LIMIT,
        "x_states_limit": "280 字符" in _head(secs, "8.2 X"),
        "xhs_title": title,
        "xhs_title_len": len(title),
        "xhs_body_chars": len(re.sub(r"\s", "", body)),
        "zh_stated": _stated(_head(secs, "二、正文"), "字"),
        "zh_measured": _zh_count(zh),
        "li_stated": _stated(_head(secs, "8.3 LinkedIn"), "词"),
        "li_measured": _words(li),
        "en_words": _words(en),
        "days": days,
        "hazard_days": haz,
        "hazard_pct": round(100.0 * haz / days, 1),
        "worst_year": worst[0],
        "worst_year_days": worst[1],
        "page_url": PAGE_URL in doc,
        "repo_url": REPO_URL in doc,
        "community_url": COMMUNITY_URL in doc,
        "retired_dashboard_link": "dashboard.html" in doc,
        "sections_with_limit": [n for n, t in (("二", zh), ("三", en), ("8.1", xhs),
                                               ("8.2", x), ("8.3", li))
                                if any(s in t for s in LIMIT_SIGNALS)],
        "sections_with_link": [n for n, t in (("8.1", xhs), ("8.2", x), ("8.3", li))
                               if PAGE_URL in t or REPO_URL in t],
        "red_lines": [(msg, line.strip()[:40]) for pat, msg in RED_LINES
                      for line in _copy_text(zh, en, xhs, x, li,
                                             _sec(secs, "8.4")).splitlines()
                      if re.search(pat, line)],
        "echo_missing_in_copy": [t for t, _ in PAGE_ECHO if t not in doc],
        "echo_missing_in_page": [(t, forms) for t, forms in PAGE_ECHO
                                 if not any(v in page for v in forms)],
        "page_bytes": len(page.encode("utf-8")),
    }
    return f


# ---------------------------------------------------------------------------
# 断言
# ---------------------------------------------------------------------------
def audit(doc=None):
    """返回 (facts, failures)。"""
    f = facts()
    bad = []

    if f["x_posts"] != 4:
        bad.append("X thread 应有 4 条，实际 %d 条" % f["x_posts"])
    if not f["x_states_limit"]:
        bad.append("8.2 的标题里没有声明「280 字符」上限")
    for i, (w, raw) in enumerate(zip(f["x_weighted"], f["x_lengths"]), 1):
        if w > X_LIMIT:
            bad.append("X 第 %d 条加权 %d 字符（原始 %d），超过上限 %d" % (i, w, raw, X_LIMIT))
    if f["xhs_title_len"] > XHS_TITLE_LIMIT:
        bad.append("小红书标题 %d 字，超过材料自己声明的 %d 字：%s"
                   % (f["xhs_title_len"], XHS_TITLE_LIMIT, f["xhs_title"]))
    if f["xhs_body_chars"] > XHS_BODY_LIMIT:
        bad.append("小红书正文 %d 字（不含空白），超过平台上限 %d"
                   % (f["xhs_body_chars"], XHS_BODY_LIMIT))

    for label, stated, measured, unit in (
            ("二、正文", f["zh_stated"], f["zh_measured"], "字"),
            ("8.3 LinkedIn", f["li_stated"], f["li_measured"], "词")):
        if stated is None:
            bad.append("%s 的标题里没有声明「约 N %s」，无法核对" % (label, unit))
        elif abs(measured - stated) > max(1.0, LEN_TOL * stated):
            bad.append("%s 声明「约 %d %s」，实测 %d %s（相差 %.0f%%，超过 ±%d%%）"
                       % (label, stated, unit, measured, unit,
                          100.0 * abs(measured - stated) / stated, int(LEN_TOL * 100)))

    want_limit = ["二", "三", "8.1", "8.2", "8.3"]
    for n in want_limit:
        if n not in f["sections_with_limit"]:
            bad.append("第 %s 节的版本里没有保留任何一条局限说明（材料第八节的通用纪律）" % n)
    for n in ["8.1", "8.2", "8.3"]:
        if n not in f["sections_with_link"]:
            bad.append("第 %s 节的版本里没有在线版或源码链接，读者无法行动" % n)

    if not f["community_url"]:
        bad.append("材料里没有作品帖的发布地址 %s" % COMMUNITY_URL)
    if not f["page_url"]:
        bad.append("材料里没有在线版地址 %s" % PAGE_URL)
    if not f["repo_url"]:
        bad.append("材料里没有源码仓库地址 %s" % REPO_URL)
    if f["retired_dashboard_link"]:
        bad.append("材料里还留着已下线的 dashboard.html 链接")
    for msg, line in f["red_lines"]:
        bad.append("触到第七节的红线（%s）：%s" % (msg, line))

    for t in f["echo_missing_in_copy"]:
        bad.append("成品页上的公开数字「%s」在文案里找不到（文案与页面各说一套）" % t)
    for t, forms in f["echo_missing_in_page"]:
        bad.append("文案里的公开数字「%s」在成品页上找不到（可接受的写法：%s）"
                   % (t, " 或 ".join(forms)))

    if f["days"] != 1446 or "1,446" not in _read(DOC06):
        bad.append("记录期天数与产物/文案不一致：产物 %d 天" % f["days"])
    if f["hazard_days"] != 44 or "44 天" not in _read(DOC06):
        bad.append("复合灾害日数与产物/文案不一致：产物 %d 天" % f["hazard_days"])
    if abs(f["hazard_pct"] - 3.0) > 0.05 or "3.0%" not in _read(DOC06):
        bad.append("复合灾害日占比与产物/文案不一致：产物 %.1f%%" % f["hazard_pct"])
    if "%s 年" % f["worst_year"] not in _read(DOC06) or "%d 天" % f["worst_year_days"] not in _read(DOC06):
        bad.append("「复合灾害日最多的年份」与产物/文案不一致：产物 %s 年 %d 天"
                   % (f["worst_year"], f["worst_year_days"]))
    return f, bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--no-docs", action="store_true")
    a = ap.parse_args()
    f, bad = audit()
    if a.json:
        sys.stdout.write(json.dumps({"facts": f, "failures": bad}, ensure_ascii=False, indent=2))
        return 1 if bad else 0
    if a.no_docs:
        return 1 if bad else 0
    print("== docs/06_作品帖与发布草稿.md 的可核对事实")
    print("  %-22s %s" % ("X thread", "%d 条，加权 %s（上限 %d）"
                          % (f["x_posts"], "/".join(str(x) for x in f["x_weighted"]), f["x_limit"])))
    print("  %-22s %s" % ("小红书标题", "%d 字（上限 %d）" % (f["xhs_title_len"], XHS_TITLE_LIMIT)))
    print("  %-22s %d 字（不含空白）" % ("小红书正文", f["xhs_body_chars"]))
    print("  %-22s 声明约 %s 字 / 实测 %d 字" % ("中文正文", f["zh_stated"], f["zh_measured"]))
    print("  %-22s 声明约 %s 词 / 实测 %d 词" % ("LinkedIn", f["li_stated"], f["li_measured"]))
    print("  %-22s %d 天 / 复合灾害日 %d 天（%.1f%%）/ 最重年份 %s 年 %d 天"
          % ("产物现算", f["days"], f["hazard_days"], f["hazard_pct"],
             f["worst_year"], f["worst_year_days"]))
    print("  %-22s %s" % ("保留局限说明", "/".join(f["sections_with_limit"])))
    print("  %-22s %s" % ("带可执行链接", "/".join(f["sections_with_link"])))
    print("  %-22s 文案 %d 项、页面 %d 项"
          % ("数字与页面一致", len(PAGE_ECHO) - len(f["echo_missing_in_copy"]),
             len(PAGE_ECHO) - len(f["echo_missing_in_page"])))
    for b in bad:
        print("  FAIL %s" % b)
    if bad:
        print("\nRESULT %d 处不一致（文案要能被机器读完，也要经得起公众照着做）" % len(bad))
        return 1
    print("\nRESULT ALL PASS（平台上限、声明字数、局限说明、链接、红线与公开数字全部对得上）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
