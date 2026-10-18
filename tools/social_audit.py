#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""社交分享元数据审计（纯标准库、离线、不联网）。

第 43 轮加的：成品页此前只有 charset / description / viewport / theme-color，
**一条 Open Graph 或 Twitter Card 都没有**。而 docs/06 的四条推文、LinkedIn 帖、
小红书笔记都在分享同一个网址（https://sloilmarve.github.io/reef-sentinel/）——
分享出去只会是一条裸链接：没有标题、没有摘要、没有卡片图。六项权重里
「传播与公众采纳」占 15%，评委与公众第一次看到这个项目，往往就是那条链接的预览。

这个脚本核对四件事：
1) 页面 <head> 里 15 个分享标签齐全，且每个绝对地址都从 site.json 的 site_url 现算
   （换域名不用手改页面；域名改了不重建，这里立刻红）；
2) 卡片图 demo/og.jpg 真实存在、真的是 JPEG、真实尺寸就是标签里声明的 1200×630
   （用标准库解析 JPEG 的 SOF 段，不装 Pillow、不调 ffprobe），且体积在抓取器安全区内；
3) 分享文案里**不含任何日期**——卡片是随包提交的静态图，不跟着每日刷新走，
   写死快照日会在云端第一次刷新后变成假话；
4) 卡片与元数据这件事在材料里有落点：docs/01（第 6 节可实测清单）、docs/02（工具表 +
   卡片来源与「页面自身不引用它」）、docs/06（分享时的样子）、00_提交包说明.md（包内
   多出来的这个文件是什么）、DEPLOY.md（为什么它不随每日刷新变）。

用法：python tools/social_audit.py [--json]
"""
import io
import json
import os
import re
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTER = os.path.dirname(ROOT)


def _first(*cands):
    """项目内 → 上一级：提交包把 00_提交包说明.md 放在压缩包顶层（见 tools/plan_audit.py）。"""
    for p in cands:
        if os.path.isfile(p):
            return p
    return cands[0]


PAGE = os.path.join(ROOT, "demo", "index.html")
OGIMG = os.path.join(ROOT, "demo", "og.jpg")
SITE = os.path.join(ROOT, "site.json")
DOC01 = os.path.join(ROOT, "docs", "01_项目说明.md")
DOC02 = os.path.join(ROOT, "docs", "02_数据与AI说明.md")
DOC06 = os.path.join(ROOT, "docs", "06_作品帖与发布草稿.md")
DEPLOY = os.path.join(ROOT, "DEPLOY.md")
PACK00 = _first(os.path.join(ROOT, "00_提交包说明.md"), os.path.join(OUTER, "00_提交包说明.md"))

TOOL_ROW = "tools/social_audit.py"
# docs/01 的正文按 Windows 习惯写 `python tools\social_audit.py`，docs/02 的工具表写正斜杠
TOOL_ROW_WIN = "tools\\social_audit.py"
# 卡片图尺寸：1200×630 是 X / Facebook / LinkedIn / Slack 的 summary_large_image 比例（1.91:1）
CARD_W, CARD_H = 1200, 630
CARD_MAX_BYTES = 300 * 1000          # 抓取器安全区（多数平台上限 5 MB，这里留足余量）
DESC_MAX = 200                       # og:description 在卡片上只显示两行，200 字符以内
REQUIRED = (
    "og:type", "og:site_name", "og:title", "og:description", "og:url", "og:image",
    "og:image:width", "og:image:height", "og:image:alt", "og:locale", "og:locale:alternate",
    "twitter:card", "twitter:title", "twitter:description", "twitter:image",
    "twitter:image:alt",
)
DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
URL_RE = re.compile(r"^https?://")


def _read(path):
    if not os.path.isfile(path):
        return None
    with io.open(path, encoding="utf-8") as f:
        return f.read()


def head_of(html):
    i = html.find("</head>")
    return html[:i] if i > 0 else html


def metas(html):
    """把 <head> 里的 <meta> 收成 {键: 值}：property 优先，其次 name。"""
    out = {}
    for m in re.finditer(r"<meta\b[^>]*>", head_of(html)):
        tag = m.group(0)
        key = re.search(r'(?:property|name)="([^"]+)"', tag)
        val = re.search(r'content="([^"]*)"', tag)
        if key and val:
            out[key.group(1)] = val.group(1)
    return out


def jpeg_size(path):
    """标准库解析 JPEG 尺寸：扫段找 SOF0/1/2/3（不装 Pillow、不调 ffprobe）。

    返回 (width, height, kind)；不是 JPEG 或缺 SOF 时返回 (None, None, kind)。
    """
    if not os.path.isfile(path):
        return None, None, "missing"
    b = io.open(path, "rb").read()
    if b[:2] != b"\xff\xd8":
        return None, None, "not-jpeg"
    i, n = 2, len(b)
    while i + 3 < n:
        if b[i] != 0xFF:
            i += 1
            continue
        marker = b[i + 1]
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
            i += 2
            continue
        if i + 4 > n:
            break
        seg = struct.unpack(">H", b[i + 2:i + 4])[0]
        if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
                      0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
            if i + 9 > n:
                break
            h, w = struct.unpack(">HH", b[i + 5:i + 9])
            return w, h, "jpeg-SOF%02X" % marker
        i += 2 + seg
    return None, None, "no-SOF"


def facts():
    html = _read(PAGE) or ""
    doc01 = _read(DOC01) or ""
    doc02 = _read(DOC02) or ""
    doc06 = _read(DOC06) or ""
    deploy = _read(DEPLOY) or ""
    pack00 = _read(PACK00) or ""
    try:
        site = json.load(io.open(SITE, encoding="utf-8"))
    except Exception:
        site = {}
    site_url = str(site.get("site_url", "")).strip()
    base = site_url.rstrip("/")

    m = metas(html)
    title = re.search(r"<title>(.*?)</title>", html, re.S)
    title = title.group(1).strip() if title else ""
    long_desc = m.get("description", "")
    og_img_url = base + "/og.jpg" if base else ""
    w, h, kind = jpeg_size(OGIMG)
    abs_urls = sorted({v for v in m.values() if URL_RE.match(v)})

    f = {
        "site_url": site_url,
        "site_url_ok": bool(base) and site_url.startswith("https://"),
        "meta_total": len(m),
        "og_count": len([k for k in m if k.startswith("og:")]),
        "twitter_count": len([k for k in m if k.startswith("twitter:")]),
        "missing": [k for k in REQUIRED if not str(m.get(k, "")).strip()],
        "og_url": m.get("og:url", ""),
        "og_image": m.get("og:image", ""),
        "twitter_image": m.get("twitter:image", ""),
        "og_title": m.get("og:title", ""),
        "page_title": title,
        "og_desc_len": len(m.get("og:description", "")),
        "long_desc_len": len(long_desc),
        "desc_is_short_variant": 0 < len(m.get("og:description", "")) < len(long_desc),
        "meta_has_date": bool(DATE_RE.search(" ".join(
            str(m.get(k, "")) for k in REQUIRED))),
        "abs_urls": abs_urls,
        "abs_outside_site": [u for u in abs_urls if base and not u.startswith(base + "/")],
        "link_tags": html.lower().count("<link"),
        "card_exists": os.path.isfile(OGIMG),
        "card_bytes": os.path.getsize(OGIMG) if os.path.isfile(OGIMG) else 0,
        "card_kind": kind,
        "card_w": w,
        "card_h": h,
        "card_ratio": round((w / float(h)), 3) if w and h else None,
        "card_ok_size": (w, h) == (CARD_W, CARD_H),
        "card_within_bytes": 0 < os.path.getsize(OGIMG) <= CARD_MAX_BYTES if os.path.isfile(OGIMG) else False,
        "declared_w": m.get("og:image:width", ""),
        "declared_h": m.get("og:image:height", ""),
        "doc01_share": ("分享" in doc01 or "Open Graph" in doc01)
        and (TOOL_ROW in doc01 or TOOL_ROW_WIN in doc01),
        "doc02_tool": TOOL_ROW in doc02 or TOOL_ROW_WIN in doc02,
        "doc02_card": all(s in doc02 for s in ("og.jpg", "1200×630", "build-og.mjs", "非官方预警")),
        "doc06_share": ("卡片" in doc06 or "预览" in doc06) and base + "/" in doc06.replace("https://sloilmarve.github.io/reef-sentinel", base),
        "pack00_card": "og.jpg" in pack00,
        "deploy_card": "og.jpg" in deploy and ("每日刷新" in deploy or "不随" in deploy),
    }
    return f


def audit(f=None):
    f = f or facts()
    bad = []
    if not f["site_url_ok"]:
        bad.append("site.json 的 site_url 不是 https 绝对地址：%r（分享标签里的地址全从它现算）"
                   % f["site_url"])
    if f["missing"]:
        bad.append("分享标签缺 %d 个：%s" % (len(f["missing"]), "、".join(f["missing"])))
    if f["og_url"] and f["og_url"] != f["site_url"].rstrip("/") + "/":
        bad.append("og:url 与 site.json 不一致：%r" % f["og_url"])
    if f["og_image"] != f["site_url"].rstrip("/") + "/og.jpg":
        bad.append("og:image 不是 site_url + /og.jpg：%r" % f["og_image"])
    if f["twitter_image"] != f["og_image"]:
        bad.append("twitter:image 与 og:image 不是同一张：%r" % f["twitter_image"])
    if f["og_title"] != f["page_title"]:
        bad.append("og:title 与页面 <title> 不一致：%r vs %r" % (f["og_title"], f["page_title"]))
    if not f["desc_is_short_variant"]:
        bad.append("og:description 没有比页面 meta description 更短（%d vs %d 字符）："
                   "卡片上只显示两行，短版才不被截断"
                   % (f["og_desc_len"], f["long_desc_len"]))
    if f["og_desc_len"] > DESC_MAX:
        bad.append("og:description 长 %d 字符，超过 %d（卡片只显示两行）"
                   % (f["og_desc_len"], DESC_MAX))
    if f["meta_has_date"]:
        bad.append("分享标签里出现了日期：卡片是随包提交的静态图、不随每日刷新变，"
                   "写死快照日会在云端第一次刷新后变成假话")
    if f["abs_outside_site"]:
        bad.append("页面 <head> 里有 %d 个不属于本站的绝对地址：%s"
                   % (len(f["abs_outside_site"]), "、".join(f["abs_outside_site"][:3])))
    if f["link_tags"]:
        bad.append("页面出现 %d 个 <link> 标签（单文件离线页不允许）" % f["link_tags"])
    if not f["card_exists"]:
        bad.append("分享卡片 demo/og.jpg 不存在（og:image 指向它，抓取器会 404）")
    elif f["card_kind"] == "not-jpeg":
        bad.append("demo/og.jpg 不是 JPEG（抓取器对 PNG/JPEG 最稳）")
    elif f["card_w"] is None:
        bad.append("demo/og.jpg 读不出尺寸：%s" % f["card_kind"])
    else:
        if not f["card_ok_size"]:
            bad.append("卡片真实尺寸 %s×%s，应为 %d×%d（与 og:image:width/height 必须一致）"
                       % (f["card_w"], f["card_h"], CARD_W, CARD_H))
        if f["declared_w"] != str(f["card_w"]) or f["declared_h"] != str(f["card_h"]):
            bad.append("标签声明的尺寸 %s×%s 与文件真实尺寸 %s×%s 不一致"
                       % (f["declared_w"], f["declared_h"], f["card_w"], f["card_h"]))
    if not f["card_within_bytes"]:
        bad.append("卡片 %d 字节，超过 %d 字节的安全区" % (f["card_bytes"], CARD_MAX_BYTES))
    if not f["doc01_share"]:
        bad.append("docs/01 第 6 节没有「分享预览」这一条，或没点名 %s" % TOOL_ROW)
    if not f["doc02_tool"]:
        bad.append("docs/02 工具表没有 %s" % TOOL_ROW)
    if not f["doc02_card"]:
        bad.append("docs/02 没写清卡片的来源与边界（需要 og.jpg / 1200×630 / build-og.mjs / 非官方预警）")
    if not f["doc06_share"]:
        bad.append("docs/06 没有写「链接分享出去是什么样子」（发帖的人需要知道）")
    if not f["pack00_card"]:
        bad.append("00_提交包说明.md 没交代包内多出来的 demo/og.jpg 是什么")
    if not f["deploy_card"]:
        bad.append("DEPLOY.md 没写 og.jpg 不随每日刷新变（否则线上页面更新后卡片看起来过期）")
    return f, bad


def main():
    as_json = "--json" in sys.argv[1:]
    f, bad = audit()
    if as_json:
        print(json.dumps({"facts": f, "bad": bad}, ensure_ascii=False, indent=2))
        return 1 if bad else 0
    print(u"分享元数据审计（离线）：")
    for k in ("site_url", "meta_total", "og_count", "twitter_count", "og_title", "page_title",
              "og_desc_len", "long_desc_len", "og_url", "og_image", "card_bytes", "card_kind",
              "card_w", "card_h", "card_ratio", "card_ok_size", "card_within_bytes",
              "abs_urls", "abs_outside_site", "link_tags", "meta_has_date",
              "doc01_share", "doc02_tool", "doc02_card", "doc06_share", "pack00_card",
              "deploy_card"):
        print("  %-20s %s" % (k, f.get(k)))
    if bad:
        print("")
        for b in bad:
            print(u"FAIL %s" % b)
        return 1
    print("")
    print(u"RESULT ALL PASS（%d 个分享标签全部指向 site.json 的同一域名；"
          u"卡片 demo/og.jpg 是真实 %d×%d JPEG、%d 字节，与声明尺寸一致；"
          u"分享文案零日期，不会随每日刷新变成假话；docs/01、docs/02、docs/06、"
          u"00_提交包说明.md、DEPLOY.md 五处落点齐全）"
          % (len(REQUIRED), f["card_w"], f["card_h"], f["card_bytes"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
