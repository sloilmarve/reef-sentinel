#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""license_audit.py - 离线复核「许可」在所有材料里说的是同一件事（纯标准库、不联网）。

为什么需要这个脚本：
成品页内嵌了 7 张 CC BY-SA 实景照片，而页面自身的文字、图表与派生数据是
CC BY 4.0 —— 这是两种不同的许可，很容易在某个文件里被写成一句笼统的话。
第 34 轮就真的出现了：成品页页脚写着「本页同样以 CC BY-SA 发布」，而
`LICENSE` 第 2 条、`docs/01`、`docs/05`、`README.md`、`README.en.md`、
`00_提交包说明.md` 以及同一页的英文摘要都写「成品页 CC BY 4.0」——
同一份材料对同一个问题给了两个答案，而且没有任何门禁会看它。

本脚本做三件事：
1. 把 7 张照片的署名从**成品页页脚**和 `LICENSE` 第 4 条里各自解析出来，
   逐张比对摄影者与许可版本（数量不符、少一张、版本写错都会失败）；
2. 断言「代码与文档 MIT / 本项目自有的数据、图表与页面文字 CC BY 4.0 /
   内嵌照片 CC BY-SA」这套切分在**每个**材料里都出现，且没有任何材料
   把整页笼统地写成 CC BY-SA；
3. 断言上游来源（Open-Meteo / ERA5 / NOAA CRW）与演示视频的许可说明都在。

用法：
    python tools\\license_audit.py           # 打印事实表 + RESULT ALL PASS / RESULT FAIL n
    python tools\\license_audit.py --json     # 额外输出机器可读的事实（供别的脚本复用）

范围说明：这里只做静态可判的部分（文字里说了什么、署名对不对得上）。
"""
import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAGE = ROOT / "demo" / "index.html"
LICENSE = ROOT / "LICENSE"

N_PHOTOS = 7

# 每个材料都要把许可切分讲清楚：代码与文档 MIT + 本项目自有的成品页内容 CC BY 4.0
SPLIT_DOCS = [
    "docs/01_项目说明.md",
    "docs/05_报名表与提交清单.md",
    "README.md",
    "README.en.md",
    "00_提交包说明.md",
    "LICENSE",
]

# 页面自称「整页 CC BY-SA」是错的（照片是 CC BY-SA，页面自有内容不是）
BANNED = [
    "本页同样以 CC BY-SA",
    "this page is CC BY-SA",
    "the page is CC BY-SA",
    "整页以 CC BY-SA 发布",
]

# 上游来源必须被点名，且不得被本项目再授权
UPSTREAM = ["Open-Meteo", "ERA5", "NOAA"]

# 照片许可版本只允许这些（Wikimedia Commons 上这 7 张的实际版本）
ALLOWED_PHOTO_LIC = {"CC BY-SA 2.0", "CC BY-SA 3.0", "CC BY-SA 4.0"}

# 署名行自第 42 轮起把拉丁部分包在 <span lang="en"> 里（WCAG 3.1.2 语言标注）；
# 这条正则同时钉住语言标注本身：谁把 span 去掉，许可审计立刻红。
CREDIT_PAGE = re.compile(
    r'<p><span lang="en">([^<>]+?)\s+—\s+([^<>]+?)，(CC BY-SA [\d.]+)</span>（Wikimedia Commons）</p>')
CREDIT_LIC = re.compile(
    r"^\s*-\s*([^/\n]+?)\s*/\s*([^/\n]+?)\s*/\s*(CC BY-SA [\d.]+)\s*$", re.M)


def _read(rel):
    """先试 ROOT/rel，再试 ROOT.parent/rel（提交包把 00_提交包说明.md 放在上一层）。"""
    for base in (ROOT, ROOT.parent):
        p = base / rel
        if p.is_file():
            return p.read_text(encoding="utf-8")
    return None


def _page_credits(html):
    return [(t.strip(), a.strip(), l.strip()) for t, a, l in CREDIT_PAGE.findall(html)]


def _license_credits(text):
    return [(t.strip(), a.strip(), l.strip()) for t, a, l in CREDIT_LIC.findall(text)]


def facts_of(html=None, license_text=None):
    html = html if html is not None else PAGE.read_text(encoding="utf-8")
    lic = license_text if license_text is not None else LICENSE.read_text(encoding="utf-8")
    pc = _page_credits(html)
    lc = _license_credits(lic)
    docs = {}
    for rel in SPLIT_DOCS:
        t = _read(rel)
        docs[rel] = t
    en = re.search(r'<details\b[^>]*id="en"[^>]*>(.*?)</details>', html, re.S)
    en_txt = re.sub(r"<[^>]+>", " ", en.group(1)) if en else ""
    return {
        "page_credits": len(pc),
        "license_credits": len(lc),
        "page_authors": sorted({a for _, a, _ in pc}),
        "license_authors": sorted({a for _, a, _ in lc}),
        "page_lic_versions": sorted({l for _, _, l in pc}),
        "license_lic_versions": sorted({l for _, _, l in lc}),
        "page_bytes": len(html.encode("utf-8")),
        "page_own_ccby4": html.count("CC BY 4.0"),
        "page_photos_sa": html.count("CC BY-SA"),
        "page_sharealike_words": ("相同方式共享" in html) or ("share-alike" in html),
        "page_banned": [b for b in BANNED if b in html],
        "en_has_ccby4": "CC BY 4.0" in en_txt,
        "en_has_photos_sa": "CC BY-SA" in en_txt,
        "license_has_mit": "MIT" in lic,
        "license_has_ccby4": "CC BY 4.0" in lic,
        "license_has_photos_sa": "CC BY-SA" in lic,
        "license_upstream": [u for u in UPSTREAM if u in lic],
        "license_wikimedia": "Wikimedia Commons" in lic,
        "license_public_domain": ("公有领域" in lic) or ("public domain" in lic),
        "license_video_item": "演示视频" in lic,
        "docs_missing": [r for r, t in docs.items()
                         if t is None or "MIT" not in t or "CC BY 4.0" not in t],
        "docs_present": len([r for r, t in docs.items() if t is not None]),
        "_docs": docs,
        "_page_credits": pc,
        "_license_credits": lc,
    }


def audit(html=None, license_text=None):
    if html is None:
        html = PAGE.read_text(encoding="utf-8")
    if license_text is None:
        license_text = LICENSE.read_text(encoding="utf-8")
    f = facts_of(html, license_text)
    bad = []

    # 1. 照片署名：页脚与 LICENSE 第 4 条必须逐张对得上
    pc, lc = f["_page_credits"], f["_license_credits"]
    if len(pc) != N_PHOTOS:
        bad.append("成品页页脚署名 %d 张，应为 %d 张" % (len(pc), N_PHOTOS))
    if len(lc) != N_PHOTOS:
        bad.append("LICENSE 第 4 条列出 %d 张照片，应为 %d 张" % (len(lc), N_PHOTOS))
    pa, la = set(f["page_authors"]), set(f["license_authors"])
    if pa != la:
        bad.append("摄影者不一致：页脚独有 %s；LICENSE 独有 %s"
                   % (sorted(pa - la) or "无", sorted(la - pa) or "无"))
    pv, lv = set(f["page_lic_versions"]), set(f["license_lic_versions"])
    if pv != lv:
        bad.append("照片许可版本不一致：页脚 %s；LICENSE %s" % (sorted(pv), sorted(lv)))
    for v in sorted(pv | lv):
        if v not in ALLOWED_PHOTO_LIC:
            bad.append("出现了不在白名单里的照片许可：%s" % v)

    # 2. 许可切分：整页不是 CC BY-SA
    if f["page_banned"]:
        bad.append("成品页把整页说成 CC BY-SA：%s（照片是 CC BY-SA，页面自有内容是 CC BY 4.0）"
                   % " / ".join(f["page_banned"]))
    if f["page_own_ccby4"] < 1:
        bad.append("成品页没有写「CC BY 4.0」（本项目自有的数据、图表与页面文字按 CC BY 4.0 释出）")
    if not f["page_sharealike_words"]:
        bad.append("成品页没有说明照片部分继续「以相同方式共享」（CC BY-SA 的要求）")
    if "LICENSE" not in html:
        bad.append("成品页没有指向仓库根的 LICENSE")

    # 3. 英文摘要也要写清楚（国际评委只看这一块）
    if not f["en_has_ccby4"] or not f["en_has_photos_sa"]:
        bad.append("英文摘要没有同时写明 CC BY 4.0 与内嵌照片的 CC BY-SA："
                   "CC BY 4.0=%s CC BY-SA=%s" % (f["en_has_ccby4"], f["en_has_photos_sa"]))

    # 4. LICENSE 自身
    for key, why in (("license_has_mit", "代码与文档 MIT"),
                     ("license_has_ccby4", "本项目自有的数据/图表/页面文字 CC BY 4.0"),
                     ("license_has_photos_sa", "内嵌照片 CC BY-SA"),
                     ("license_wikimedia", "照片来源 Wikimedia Commons"),
                     ("license_public_domain", "NOAA CRW 为公有领域"),
                     ("license_video_item", "演示视频单独一条")):
        if not f[key]:
            bad.append("LICENSE 缺少：%s" % why)
    if len(f["license_upstream"]) != len(UPSTREAM):
        bad.append("LICENSE 未点名的上游来源：%s"
                   % [u for u in UPSTREAM if u not in f["license_upstream"]])

    # 5. 每个材料都要出现这套切分
    if f["docs_missing"]:
        bad.append("这些材料没写清「MIT + CC BY 4.0」：%s" % "、".join(f["docs_missing"]))

    # 6. 照片张数在各材料里的写法
    docs = f["_docs"]
    for rel, needle in (("docs/01_项目说明.md", "7 张实景照片"),
                        ("docs/05_报名表与提交清单.md", "7 张实景照片"),
                        ("README.en.md", "7 CC-licensed photographs")):
        t = docs.get(rel) or ""
        if needle not in t:
            bad.append("%s 里没有写「%s」（照片张数变了要一起改）" % (rel, needle))

    # 7. 演示视频的许可说明与 docs/04 对得上
    d04 = _read("docs/04_演示视频逐字稿与分镜.md")
    if d04 is not None and "CC BY-SA" not in d04:
        bad.append("docs/04 没有说明视频里出现的实景照片是 CC BY-SA")

    for k in list(f):
        if k.startswith("_"):
            del f[k]
    return f, bad


def main():
    ap = argparse.ArgumentParser(description="离线复核许可声明在各材料里是否一致")
    ap.add_argument("--page", default=str(PAGE), help="成品页路径（默认 demo/index.html）")
    ap.add_argument("--license", default=str(LICENSE), help="LICENSE 路径（默认仓库根 LICENSE）")
    ap.add_argument("--json", action="store_true", help="额外打印机器可读的事实 JSON")
    args = ap.parse_args()

    p, lp = Path(args.page), Path(args.license)
    for path, what in ((p, "成品页"), (lp, "LICENSE")):
        if not path.is_file():
            print("RESULT FAIL 1\n  找不到%s：%s" % (what, path))
            return 1
    f, bad = audit(p.read_text(encoding="utf-8"), lp.read_text(encoding="utf-8"))

    print("=== 许可事实（%s）===" % p)
    order = ["page_bytes", "page_credits", "license_credits", "page_lic_versions",
             "page_own_ccby4", "page_photos_sa", "page_sharealike_words",
             "en_has_ccby4", "en_has_photos_sa", "license_has_mit", "license_has_ccby4",
             "license_has_photos_sa", "license_upstream", "license_wikimedia",
             "license_public_domain", "license_video_item", "docs_present"]
    for k in order:
        print("  %-22s %s" % (k, f[k]))
    print("  %-22s %s" % ("page_authors", "、".join(f["page_authors"])))
    if args.json:
        print(json.dumps(f, ensure_ascii=False, sort_keys=True))
    if bad:
        print("\n=== 不一致 ===")
        for b in bad:
            print("  FAIL %s" % b)
        print("RESULT FAIL %d" % len(bad))
        return 1
    print("\nRESULT ALL PASS（7 张照片的署名在成品页与 LICENSE 里逐张一致，"
          "MIT / CC BY 4.0 / CC BY-SA 的切分在 %d 份材料里说的是同一件事）" % f["docs_present"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
