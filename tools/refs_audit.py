# -*- coding: utf-8 -*-
"""工具：方法与出处的离线核对（第 40 轮）

成品页「方法与验证」里有一段「依据与来源」折叠说明（`<details id="refs">`），
`docs/02_数据与AI说明.md` 第七节有同一份清单。这个脚本把两边逐条比对。

它只比字符串、不联网：出处本身是在 Crossref / DataCite / 上游产品页上人工核过的
（核对日期 2026-10-18，逐条结论写进 docs/02 第七节），这里钉的是「同一批出处是否
同时出现在成品页与文档里、每个 DOI 是否成形且唯一、每个方法名是否都有出处、
许可写法是否与 LICENSE 一致」—— 评审规则要求高风险应用交代数据来源，评委最常
问的就是「p90 / 海洋热浪 / MMM / DHW 这些定义从哪来」。

跑法：python tools\\refs_audit.py [--json]
"""
import argparse
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGE = os.path.join(ROOT, "demo", "index.html")
DOC01 = os.path.join(ROOT, "docs", "01_项目说明.md")
DOC02 = os.path.join(ROOT, "docs", "02_数据与AI说明.md")
LICENSE = os.path.join(ROOT, "LICENSE")

VERIFIED_ON = "2026-10-18"          # DOI / 许可的核对日期（人工在 Crossref / DataCite / 产品页上核过）
DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$")
SEC7_HEAD = "## 七、依据与来源"

# 每条出处：id / 类别 / 必须出现的标识串 / 书目串（URL 类为 None）/ 许可 / 它是什么
REFS = [
    {"id": "hobday2016", "kind": "doi", "ident": "doi:10.1016/j.pocean.2015.12.014",
     "cite": "Hobday et al. 2016, Progress in Oceanography 141: 227-238",
     "what": "海洋热浪定义（逐日异常超过阈值且持续 5 天以上）"},
    {"id": "hobday2018", "kind": "doi", "ident": "doi:10.5670/oceanog.2018.205",
     "cite": "Hobday et al. 2018, Oceanography 31(2)",
     "what": "海洋热浪分级与命名"},
    {"id": "liu2014", "kind": "doi", "ident": "doi:10.3390/rs61111579",
     "cite": "Liu et al. 2014, Remote Sensing 6(11): 11579-11606",
     "what": "CRW 5 km 热压力产品（HotSpot / DHW）"},
    {"id": "skirving2020", "kind": "doi", "ident": "doi:10.3390/rs12233856",
     "cite": "Skirving et al. 2020, Remote Sensing 12(23): 3856",
     "what": "CoralTemp 与 CRW v3.1 产品族"},
    {"id": "hersbach2020", "kind": "doi", "ident": "doi:10.1002/qj.3803",
     "cite": "Hersbach et al. 2020, Quarterly Journal of the Royal Meteorological Society 146(730): 1999-2049",
     "what": "ERA5 再分析"},
    {"id": "cds_era5", "kind": "doi", "ident": "doi:10.24381/cds.adbb2d47",
     "cite": "doi:10.24381/cds.adbb2d47",
     "what": "ERA5 单层小时数据集（Copernicus CDS）", "licence": "CC-BY"},
    {"id": "zscheischler2018", "kind": "doi", "ident": "doi:10.1038/s41558-018-0156-3",
     "cite": "Zscheischler et al. 2018, Nature Climate Change 8(6): 469-477",
     "what": "复合事件风险框架"},
    {"id": "hoerl1970", "kind": "doi", "ident": "doi:10.1080/00401706.1970.10488634",
     "cite": "Hoerl & Kennard 1970, Technometrics 12(1): 55-67",
     "what": "岭回归"},
    {"id": "crw_method", "kind": "url", "ident": "coralreefwatch.noaa.gov/product/5km/methodology.php",
     "cite": None, "what": "CRW 5 km v3.1 方法页（MMM / HotSpot / DHW / 预警等级）"},
    {"id": "crw_cite", "kind": "url", "ident": "coralreefwatch.noaa.gov/satellite/docs/recommendations_crw_citation.php",
     "cite": None, "what": "CRW 官方引用建议（按书目格式署名并注明版本与取数日）"},
    {"id": "openmeteo_docs", "kind": "url", "ident": "open-meteo.com/en/docs/marine-weather-api",
     "cite": None, "what": "Open-Meteo Marine 取数入口"},
    {"id": "openmeteo_licence", "kind": "url", "ident": "open-meteo.com/en/licence",
     "cite": None, "what": "Open-Meteo 许可（数据 CC BY 4.0）", "licence": "CC BY 4.0"},
]

# 只在 docs/02 第七节里给出（成品页不需要展开到归档地址）
DOCS_ONLY = [
    ("https://www.ncei.noaa.gov/access/metadata/landing-page/bin/iso?id=gov.noaa.nodc:CRW-5km-HeatStressProducts",
     "CRW 5 km 热应力产品的 NCEI 归档入口"),
]

# 每个方法名都必须有出处：组名 → 出处 id 列表（全部要出现在成品页与 docs/02 第七节）
METHODS = [
    ("海洋热浪定义与分级", ["hobday2016", "hobday2018"]),
    ("白化热压力（MMM / HotSpot / DHW / 白化预警等级）", ["crw_method", "liu2014", "skirving2020"]),
    ("官方产品的引用方式", ["crw_cite"]),
    ("ERA5 再分析", ["hersbach2020", "cds_era5"]),
    ("取数入口与许可", ["openmeteo_docs", "openmeteo_licence"]),
    ("复合事件", ["zscheischler2018"]),
    ("岭回归与验证协议", ["hoerl1970"]),
]

DOC_ENTRIES = 8        # docs/02 第七节的条目数（与成品页折叠块一一对应）


def _read(path):
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def sec7(doc):
    """取 docs/02 第七节（到文件末）。"""
    i = doc.find(SEC7_HEAD)
    return "" if i < 0 else doc[i:]


def facts(page, doc, lic):
    d = sec7(doc)
    dois = [r for r in REFS if r["kind"] == "doi"]
    by_id = {r["id"]: r for r in REFS}

    def _ok(rid):
        r = by_id[rid]
        needles = [r["ident"]] + ([r["cite"]] if r["cite"] else [])
        return all(s in page for s in needles) and all(s in d for s in needles)

    return {
        "refs": len(REFS),
        "dois": len(dois),
        "urls": len(REFS) - len(dois),
        "page_doi_mentions": page.count("doi:"),
        "doc_entries": len(re.findall(r"^- \*\*", d, re.M)),
        "sec7_chars": len(d),
        "groups": len(METHODS),
        "methods_with_source": sum(1 for _, ids in METHODS if all(_ok(i) for i in ids)),
        "verified_on": VERIFIED_ON,
    }


def audit(page=None, doc=None, lic=None):
    """返回 (facts, failures)。failures 为空即全部通过。"""
    page = _read(PAGE) if page is None else page
    doc = _read(DOC02) if doc is None else doc
    lic = _read(LICENSE) if lic is None else lic
    doc01 = _read(DOC01)
    bad = []
    f = facts(page, doc, lic)

    d = sec7(doc)
    if not d:
        bad.append("docs/02 里找不到「%s」（方法与出处必须与成品页同源）" % SEC7_HEAD)

    # ① 每条出处的标识串与书目串都要同时出现在成品页与 docs/02 第七节
    for r in REFS:
        if r["kind"] == "doi":
            raw = r["ident"][len("doi:"):]
            if not DOI_RE.match(raw):
                bad.append("DOI 不成形：%s（应为 10.xxxx/yyy）" % r["ident"])
        if r["ident"] not in page:
            bad.append("成品页「依据与来源」缺标识串 %s（%s）" % (r["ident"], r["what"]))
        if r["ident"] not in d:
            bad.append("docs/02 第七节缺标识串 %s（%s）" % (r["ident"], r["what"]))
        if r["cite"]:
            if r["cite"] not in page:
                bad.append("成品页缺书目串「%s」（%s）" % (r["cite"], r["what"]))
            if r["cite"] not in d:
                bad.append("docs/02 第七节缺书目串「%s」（%s）" % (r["cite"], r["what"]))
        if r.get("licence"):
            if r["licence"] not in page:
                bad.append("成品页缺许可写法「%s」（%s）" % (r["licence"], r["what"]))
            if r["licence"] not in d:
                bad.append("docs/02 第七节缺许可写法「%s」（%s）" % (r["licence"], r["what"]))

    # ② DOI 唯一，且成品页里的 doi: 出现次数 = DOI 条数 + 1（页脚摘要重复了数据集 DOI）
    dois = [r["ident"] for r in REFS if r["kind"] == "doi"]
    if len(set(dois)) != len(dois):
        bad.append("成品页里有重复 DOI：%s" % dois)
    want = len(dois) + 1
    if f["page_doi_mentions"] != want:
        bad.append("成品页 doi: 出现 %d 次，期望 %d 次（8 条出处 + 页脚摘要里的数据集 DOI）"
                   % (f["page_doi_mentions"], want))

    # ③ 每个方法名都有出处（成品页与 docs/02 都要齐）——按出处 id 取它的标识串与书目串来查
    by_id = {r["id"]: r for r in REFS}

    def _needles(rid):
        r = by_id[rid]
        return [r["ident"]] + ([r["cite"]] if r["cite"] else [])

    for name, ids in METHODS:
        miss_p = [i for i in ids if any(s not in page for s in _needles(i))]
        miss_d = [i for i in ids if any(s not in d for s in _needles(i))]
        if miss_p or miss_d:
            bad.append("方法「%s」的出处不齐：成品页缺 %s，docs/02 缺 %s" % (name, miss_p or "无", miss_d or "无"))

    # ④ docs/02 第七节的条目数与成品页折叠块一一对应
    if f["doc_entries"] != DOC_ENTRIES:
        bad.append("docs/02 第七节条目数 = %d，期望 %d（与成品页 8 条一一对应）"
                   % (f["doc_entries"], DOC_ENTRIES))
    for s, why in DOCS_ONLY:
        if s not in d:
            bad.append("docs/02 第七节缺 %s（%s）" % (s, why))

    # ⑤ 出处是核过的，不是编的：文档里要写清核对日期与核对渠道
    for s in ("Crossref", "DataCite", VERIFIED_ON):
        if s not in d:
            bad.append("docs/02 第七节没写核对渠道 / 日期（缺 %s）：出处必须说明是怎么核的" % s)

    # ⑥ 照片署名与许可（LICENSE 第 4 条 + 页脚版权页）
    for s in ("Wikimedia Commons", "CC BY-SA"):
        if s not in page:
            bad.append("成品页缺照片署名要素 %s" % s)
        if s not in d:
            bad.append("docs/02 第七节缺照片署名要素 %s" % s)
        if s not in lic:
            bad.append("LICENSE 缺照片署名要素 %s" % s)
    if "LICENSE 第 4 条" not in page:
        bad.append("成品页「依据与来源」没把照片指向 LICENSE 第 4 条")
    for s in ("依据与来源", "tools\\refs_audit.py"):
        if s not in doc01:
            bad.append("docs/01 没写「%s」（评委在项目说明里也要能找到这条线索）" % s)
    if "tools/refs_audit.py" not in doc:
        bad.append("docs/02 工具表里没有 tools/refs_audit.py 一行")

    # ⑦ 位置：折叠块在 p6 里、且在英文摘要之后（页面末尾 —— 演示视频的 pan 坐标不受影响）
    i_refs = page.find('id="refs"')
    if i_refs < 0:
        bad.append('成品页没有 <details id="refs">（依据与来源折叠块）')
    else:
        if i_refs < page.find('id="p6"'):
            bad.append("「依据与来源」不在「方法与验证」板块里")
        if i_refs < page.find('id="en"'):
            bad.append("「依据与来源」跑到了英文摘要之前（应放在页面最末，避免改动演示视频的分镜坐标）")
        if page.count('id="refs"') != 1:
            bad.append('成品页 <details id="refs"> 出现 %d 次，期望 1 次' % page.count('id="refs"'))

    return f, bad


def main():
    ap = argparse.ArgumentParser(description="离线核对方法与出处（成品页 ↔ docs/02 第七节）")
    ap.add_argument("--json", action="store_true", help="额外打印机器可读的事实 JSON")
    args = ap.parse_args()
    f, bad = audit()
    print("=== 方法与出处 ===")
    for k in ("refs", "dois", "urls", "page_doi_mentions", "doc_entries", "sec7_chars",
              "groups", "methods_with_source", "verified_on"):
        print("  %-20s %s" % (k, f[k]))
    if args.json:
        print(json.dumps(f, ensure_ascii=False, sort_keys=True))
    if bad:
        print("\n=== 不一致 ===")
        for b in bad:
            print("  FAIL %s" % b)
        print("RESULT FAIL %d" % len(bad))
        return 1
    print("\nRESULT ALL PASS（%d 条出处的书目串与 DOI / 产品页链接在成品页与 docs/02 第七节逐条对得上，"
          "%d 组方法各有出处，许可写法与 LICENSE 一致，核对日期 %s）"
          % (f["refs"], f["groups"], f["verified_on"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
