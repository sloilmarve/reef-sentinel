#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""无障碍审计（纯标准库、离线、不联网）。

第 42 轮加的：此前成品页只有一个 lang 属性（<html lang="zh-CN">），
而页面里有一整块 1.6 万字符的英文摘要、一行英文 Track 标签、7 行拉丁文照片署名。
读屏软件会全部按中文发音读英文，WCAG 3.1.2（Language of Parts）不通过，
而 docs/01 第 6 节写着「每一条都可实测」却完全没有这一项。

这个脚本用 HTMLParser 走一遍 DOM 栈，判定「纯拉丁文本节点」（≥40 字符、零汉字、
≥30 个拉丁字母）是否落在带 lang="en" 的祖先里，并把此前几轮口头声明过的无障碍事实
（alt / scope / 滚动区可聚焦可命名 / 地标 / details-summary / viewport 可缩放 /
章节序号不进读屏）一并变成可核对的数字。任何一条不成立就退出 1。

用法：python tools/a11y_audit.py [--json]
"""
import io
import json
import os
import re
import sys
from html.parser import HTMLParser

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGE = os.path.join(ROOT, "demo", "index.html")
CSS = os.path.join(ROOT, "pipeline", "page_assets", "report.css")
DOC01 = os.path.join(ROOT, "docs", "01_项目说明.md")
DOC02 = os.path.join(ROOT, "docs", "02_数据与AI说明.md")

HAN = re.compile(u"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
LAT = re.compile(r"[A-Za-z]")
# 网址没有「语言」：读屏软件会按 URL 逐段朗读，给它标 lang 反而更糟。
# 所以裸网址（含 http(s):// 或常见域名后缀的整段）不参与语言标注判定。
URL_ONLY = re.compile(r"^(?:https?://|www\.)\S+$"
                      r"|^[\w.-]+\.(?:com|org|net|gov|io|club|php|html|api)(?:/\S*)?$")
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link",
        "meta", "param", "source", "track", "wbr"}
SKIP_TEXT = {"script", "style"}

# 纯拉丁文本节点的判定门槛（放在这里是为了让审计报告能解释自己）
MIN_CHARS = 40
MIN_LATIN = 30

EXPECT = {"img": 8, "th": 95, "tw": 17, "details": 15, "secnum": 6,
          "main": 1, "footer": 1, "lang_en_min": 9}


def _read(path):
    if not os.path.isfile(path):
        return None
    with io.open(path, encoding="utf-8") as f:
        return f.read()


class _Dom(HTMLParser):
    """把页面走一遍，记录判定无障碍需要的少量事实（不做通用 DOM 实现）。"""

    def __init__(self):
        HTMLParser.__init__(self, convert_charrefs=True)
        self.stack = []          # [{tag, lang, cls}]
        self.html_lang = None
        self.title_chars = 0
        self.viewport = None
        self.texts = []          # (text, eff_lang, tag, cls)
        self.imgs = []           # alt
        self.th = []             # scope
        self.tw = []             # attrs dict
        self.details = []        # {'id','lang','summary'}
        self.secnum = []         # aria-hidden value
        self.langs = []          # 每个元素的 lang 属性值（含空值）
        self.landmarks = {"main": 0, "footer": 0}
        self._in_summary = []    # 栈：当前 details 是否已遇到 summary
        self._skip = 0

    # ---- 栈辅助 ----
    def _eff_lang(self):
        for d in reversed(self.stack):
            if d.get("lang"):
                return d["lang"]
        return self.html_lang

    def _cur(self):
        return self.stack[-1] if self.stack else {}

    def _cls(self, attrs):
        return (attrs.get("class") or "").split()

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if "lang" in a:
            self.langs.append(a.get("lang"))
        if tag == "html":
            self.html_lang = a.get("lang")
        if tag == "meta" and (a.get("name") or "").lower() == "viewport":
            self.viewport = a.get("content") or ""
        if tag == "img":
            self.imgs.append(a.get("alt"))
        if tag == "th":
            self.th.append(a.get("scope"))
        if "tw" in self._cls(a):
            self.tw.append(a)
        if "secnum" in self._cls(a):
            self.secnum.append(a.get("aria-hidden"))
        if tag in ("main", "footer"):
            self.landmarks[tag] += 1
        if tag == "details":
            self.details.append({"id": a.get("id"), "lang": a.get("lang"), "summary": 0})
        if tag == "summary" and self.details:
            self.details[-1]["summary"] += 1
        if tag in SKIP_TEXT:
            self._skip += 1
        if tag not in VOID:
            self.stack.append({"tag": tag, "lang": a.get("lang"),
                               "cls": self._cls(a)})

    def handle_startendtag(self, tag, attrs):
        # 自闭合写法（本页的 meta / img 全是 <.../>）：当成开始标签记账，
        # 但不能把栈弄乱——开始标签若压了栈，这里立刻弹回去。
        n = len(self.stack)
        self.handle_starttag(tag, attrs)
        if len(self.stack) > n:
            del self.stack[n:]

    def handle_endtag(self, tag):
        if tag in SKIP_TEXT and self._skip:
            self._skip -= 1
            return
        if tag in VOID:
            return
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i]["tag"] == tag:
                del self.stack[i:]
                return

    def handle_data(self, data):
        if self._skip:
            return
        if not data or not data.strip():
            return
        cur = self._cur()
        if cur.get("tag") == "title":
            self.title_chars += len(data.strip())
            return
        self.texts.append((data.strip(), self._eff_lang(), cur.get("tag", ""),
                           " ".join(cur.get("cls") or [])))


def _latin_unmarked(texts):
    """返回落在非 en 祖先里的纯拉丁文本节点（裸网址除外）。"""
    out = []
    for t, lang, tag, cls in texts:
        if len(t) < MIN_CHARS:
            continue
        if len(LAT.findall(t)) < MIN_LATIN:
            continue
        if HAN.search(t):
            continue
        if URL_ONLY.match(t):
            continue
        if lang == "en":
            continue
        out.append({"tag": tag, "cls": cls, "lang": lang, "chars": len(t),
                    "text": t[:90]})
    return out


def facts(page=None, css=None, doc01=None, doc02=None):
    html = _read(PAGE) if page is None else page
    csstext = _read(CSS) if css is None else css
    d1 = _read(DOC01) if doc01 is None else doc01
    d2 = _read(DOC02) if doc02 is None else doc02
    if html is None:
        return {"_missing": PAGE}
    p = _Dom()
    p.feed(html)
    p.close()
    texts = p.texts
    unmarked = _latin_unmarked(texts)
    marked = [t for t, lang, _, _ in texts
              if lang == "en" and len(t) >= MIN_CHARS and len(LAT.findall(t)) >= MIN_LATIN]
    han_in_en = sum(len(HAN.findall(t)) for t, lang, _, _ in texts if lang == "en")
    f = {
        "page_bytes": len(html.encode("utf-8")),
        "html_lang": p.html_lang,
        "title_chars": p.title_chars,
        "viewport": p.viewport or "",
        "viewport_ok": bool(p.viewport) and "width=device-width" in p.viewport
                       and "user-scalable=no" not in p.viewport
                       and "maximum-scale" not in p.viewport,
        "lang_en_attrs": sum(1 for v in p.langs if v == "en"),
        "latin_nodes": len(unmarked) + len(marked),
        "latin_marked": len(marked),
        "latin_unmarked": len(unmarked),
        "latin_unmarked_chars": sum(u["chars"] for u in unmarked),
        "latin_unmarked_head": [u["text"] for u in unmarked[:3]],
        "han_in_en": han_in_en,
        "img": len(p.imgs),
        "img_alt_empty": sum(1 for a in p.imgs if not (a or "").strip()),
        "th": len(p.th),
        "th_scope": sum(1 for s in p.th if s == "col"),
        "tw": len(p.tw),
        "tw_role": sum(1 for a in p.tw if a.get("role") == "region"),
        "tw_tabindex": sum(1 for a in p.tw if (a.get("tabindex") or "") == "0"),
        "tw_label": sum(1 for a in p.tw if (a.get("aria-label") or "").strip()),
        "tw_label_han": sum(1 for a in p.tw if HAN.search(a.get("aria-label") or "")),
        "details": len(p.details),
        "details_summary": sum(1 for d in p.details if d["summary"] == 1),
        "details_lang_en": sum(1 for d in p.details if d["lang"] == "en"),
        "en_block_id": sum(1 for d in p.details if d["id"] == "en" and d["lang"] == "en"),
        "main": p.landmarks["main"],
        "footer": p.landmarks["footer"],
        "secnum": len(p.secnum),
        "secnum_aria_hidden": sum(1 for v in p.secnum if v == "true"),
        "secnum_css_hidden": bool(
            re.search(r"\.secnum[^{}]*\{[^}]*display\s*:\s*none", html)),
        "css_lang_rule": bool(re.search(r":lang\(en\)\s*\{", csstext or "")),
        "css_focus_visible": bool(re.search(r"focus-visible", csstext or "")),
        "doc01_lang": bool(d1 and ("语言标注" in d1 and "WCAG 3.1.2" in d1)),
        "doc01_tool": bool(d1 and "tools\\a11y_audit.py" in d1),
        "doc02_tool": bool(d2 and "tools/a11y_audit.py" in d2),
    }
    return f


def audit(page=None, css=None, doc01=None, doc02=None):
    f = facts(page, css, doc01, doc02)
    bad = []
    if f.get("_missing"):
        return f, ["找不到成品页：%s" % f["_missing"]]
    e = EXPECT

    if f["html_lang"] != "zh-CN":
        bad.append("根元素语言标注不是 zh-CN：%r" % f["html_lang"])
    if f["latin_unmarked"]:
        bad.append("有 %d 个纯拉丁文本节点（%d 字符）没标 lang=\"en\"（WCAG 3.1.2），"
                   "例如：%s" % (f["latin_unmarked"], f["latin_unmarked_chars"],
                                " ｜ ".join(f["latin_unmarked_head"])))
    if f["lang_en_attrs"] < e["lang_en_min"]:
        bad.append("lang=\"en\" 只有 %d 处，少于 %d（英文摘要 + 首屏英文行 + 7 行署名）"
                   % (f["lang_en_attrs"], e["lang_en_min"]))
    if f["en_block_id"] != 1:
        bad.append("英文摘要折叠块（<details id=\"en\">）没有标 lang=\"en\"（命中 %d 个）"
                   % f["en_block_id"])
    if f["han_in_en"]:
        bad.append("标成 lang=\"en\" 的元素里含 %d 个汉字（语言标注标反了）" % f["han_in_en"])
    if f["img"] != e["img"] or f["img_alt_empty"]:
        bad.append("图片 alt 不齐：%d 张图，其中 %d 张 alt 为空（应为 %d 张全有）"
                   % (f["img"], f["img_alt_empty"], e["img"]))
    if f["th"] != e["th"] or f["th_scope"] != e["th"]:
        bad.append("表头 scope 不齐：%d 个 th，%d 个 scope=\"col\"（应为 %d 个全有）"
                   % (f["th"], f["th_scope"], e["th"]))
    if f["tw"] != e["tw"]:
        bad.append("表格容器 %d 个，应为 %d 个" % (f["tw"], e["tw"]))
    for k, want in (("tw_role", "region"), ("tw_tabindex", "0"), ("tw_label", "非空 aria-label"),
                    ("tw_label_han", "含中文的 aria-label")):
        if f[k] != e["tw"]:
            bad.append("表格容器 %s 只有 %d/%d 个（键盘可达且可命名：WCAG 2.1.1 / 4.1.2）"
                       % (want, f[k], e["tw"]))
    if f["main"] != e["main"] or f["footer"] != e["footer"]:
        bad.append("地标不齐：main %d、footer %d（应为 %d / %d）"
                   % (f["main"], f["footer"], e["main"], e["footer"]))
    if f["details"] != e["details"] or f["details_summary"] != f["details"]:
        bad.append("折叠块 %d 个、其中 %d 个有且只有一个 summary（应为 %d 个全有）"
                   % (f["details"], f["details_summary"], e["details"]))
    if f["secnum"] != e["secnum"] or not (f["secnum_css_hidden"]
                                          or f["secnum_aria_hidden"] == e["secnum"]):
        bad.append("章节序号 %d 个，但既没有 .secnum{display:none} 也没有 %d 个 "
                   "aria-hidden=\"true\"（编号会进读屏）"
                   % (f["secnum"], e["secnum"]))
    if not f["viewport_ok"]:
        bad.append("viewport 允许缩放（WCAG 1.4.4）：%r" % f["viewport"])
    if not f["css_lang_rule"]:
        bad.append("report.css 里没有 :lang(en) 规则（英文段落没有显式拉丁字体栈）")
    if not f["css_focus_visible"]:
        bad.append("report.css 里没有 :focus-visible 规则（键盘焦点看不见）")
    if not f["doc01_lang"]:
        bad.append("docs/01 第 6 节的无障碍清单没有「语言标注 / WCAG 3.1.2」这一条")
    if not f["doc01_tool"]:
        bad.append("docs/01 没有点名 tools\\a11y_audit.py")
    if not f["doc02_tool"]:
        bad.append("docs/02 工具表没有 tools/a11y_audit.py")
    return f, bad


def main():
    as_json = "--json" in sys.argv[1:]
    f, bad = audit()
    if as_json:
        print(json.dumps({"facts": f, "bad": bad}, ensure_ascii=False, indent=2))
        return 1 if bad else 0
    print("无障碍审计（离线）：")
    for k in ("page_bytes", "html_lang", "lang_en_attrs", "latin_nodes", "latin_marked",
              "latin_unmarked", "latin_unmarked_chars", "han_in_en", "img", "img_alt_empty",
              "th", "th_scope", "tw", "tw_role", "tw_tabindex", "tw_label", "tw_label_han",
              "details", "details_summary", "details_lang_en", "main", "footer",
              "secnum", "secnum_aria_hidden", "secnum_css_hidden", "viewport_ok",
              "css_lang_rule",
              "css_focus_visible", "doc01_lang", "doc01_tool", "doc02_tool"):
        print("  %-22s %s" % (k, f.get(k)))
    if bad:
        print("")
        for b in bad:
            print("FAIL %s" % b)
        return 1
    print("")
    print(u"RESULT ALL PASS（%d 个纯拉丁文本节点全部落在 lang=\"en\" 里，"
          u"英文摘要块 %d 处标注、无汉字误标；%d 张图 alt、%d 个表头 scope、"
          u"%d 个滚动区 role+tabindex+aria-label、%d 个折叠块 summary、"
          u"%d 个章节序号 display:none 不进读屏、viewport 允许缩放、"
          u"CSS 有 :lang(en) 与 :focus-visible）"
          % (f["latin_nodes"], f["lang_en_attrs"], f["img"], f["th"], f["tw"],
             f["details"], f["secnum"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
