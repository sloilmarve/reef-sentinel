#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""免费层的容量算术：把「零边际成本能撑多少用户」算成可复算的数字。

纯标准库，只读仓库里的文件 + 公开的免费层额度，不联网。

口径与来源（额度写在下面的常量里，官方改了额度就改这里，断言会跟着失败）：
- GitHub Pages 的带宽是「软限额」100 GB/月（官方文档写明 soft limit，不是合同承诺）。
- GitHub 建议仓库体积 1 GB 以下。
- GitHub Actions 免费额度 2,000 分钟/月。
- 一次全量刷新的墙钟时间取本机两次实测值（37 秒 / 143 秒，与 docs/01 第 7 节同一口径）。
- 稳态每天的上游请求数**从代码里数出来**：每个取数脚本的 URL 模板数 × 该脚本循环的坐标数。

跑法：python tools\\cost_model.py [--json]
"""

import argparse
import gzip
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGE = os.path.join(ROOT, "demo", "index.html")
RAW = os.path.join(ROOT, "data", "raw")
BACKUP = os.path.join(RAW, "_backup_before_refresh")
DOCS01 = os.path.join(ROOT, "docs", "01_项目说明.md")

# ---- 公开额度（软限额）与实测值 -------------------------------------------------
PAGES_BANDWIDTH_BYTES = 100 * 1000 ** 3      # 100 GB/月
REPO_GUIDE_BYTES = 1 * 1000 ** 3             # 1 GB
ACTIONS_FREE_MINUTES = 2000                  # 分钟/月
REFRESH_SECONDS_SLOW = 143.0                 # 本机实测（最慢一次）
REFRESH_SECONDS_FAST = 37.0                  # 本机实测（最快一次）
DAYS_PER_MONTH = 30

# 每天参与刷新的取数脚本（顺序与 pipeline/refresh.py 的 STEPS 一致）
FETCH_SCRIPTS = (
    ("fetch_open_meteo.py", "本站驱动：海洋逐小时 / 气象归档 / 近实时补齐"),
    ("fetch_multisite.py", "三个站点的同一套日驱动（跨站迁移复核）"),
    ("fetch_forecast_drivers.py", "未来 14 天数値预报驱动（浪 / 雨 / 海温 / 水位）"),
    ("fetch_noaa_vs.py", "NOAA CRW 两个区域虚拟站点逐日序列"),
)
EXPECT_REQUESTS = 13


def _read(path):
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        return fh.read()


def page_facts():
    data = open(PAGE, "rb").read()
    gz = gzip.compress(data, 9)
    return {
        "page_bytes": len(data),
        "page_gzip_bytes": len(gz),
        "page_gzip_pct": 100.0 * len(gz) / len(data),
    }


def _templates(src):
    """代码里出现的上游 URL 模板（按 host + 目录去重，去掉查询串与占位符）。"""
    keys = set()
    for m in re.finditer(r"https://([a-z0-9.\-]+)(/[^\s\"'?]*)", src):
        host, path = m.group(1), m.group(2)
        if "open-meteo.com" not in host and "noaa.gov" not in host:
            continue
        path = re.sub(r"<[^>]*>", "", path)          # 注释里的 <slug> 占位
        path = path.split("%s")[0].rsplit("/", 1)[0] + "/"
        keys.add(host + path)
    return keys


def _site_count(src):
    """SITES / STATIONS 这类坐标列表里的元组个数；没有就当作 1 个坐标。"""
    for m in re.finditer(r"(?m)^([A-Z_]+) = \[", src):
        name = m.group(1)
        if "SITE" not in name and "STATION" not in name:
            continue
        depth = 0
        for i in range(m.end() - 1, len(src)):        # 从 '[' 开始配平括号
            if src[i] == "[":
                depth += 1
            elif src[i] == "]":
                depth -= 1
                if depth == 0:
                    body = src[m.end():i]
                    n = len(re.findall(r"\(", body))
                    return n if n else 1
    return 1


def request_facts():
    rows = []
    total = 0
    for name, why in FETCH_SCRIPTS:
        path = os.path.join(ROOT, "pipeline", name)
        src = _read(path)
        tpl = len(_templates(src))
        sites = _site_count(src)
        n = tpl * sites
        total += n
        rows.append({"script": name, "why": why, "templates": tpl, "sites": sites, "requests": n})
    return total, rows


def _deltas():
    """上一轮刷新的备份与当前 raw 文件逐名比对，得到一次刷新的净增量。"""
    if not os.path.isdir(BACKUP):
        return None, []
    cur = {}
    for fn in os.listdir(RAW):
        p = os.path.join(RAW, fn)
        if os.path.isfile(p):
            cur[fn] = os.path.getsize(p)
    out = []
    for fn in sorted(os.listdir(BACKUP)):
        p = os.path.join(BACKUP, fn)
        if os.path.isfile(p) and fn in cur:
            d = cur[fn] - os.path.getsize(p)
            if d > 0:
                out.append({"file": fn, "bytes": d})
    return sum(x["bytes"] for x in out), out


def repo_bytes():
    total = 0
    for base, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in (".git", "__pycache__", ".edge", "_backup_before_refresh")]
        for fn in files:
            if fn.endswith(".pyc"):
                continue
            try:
                total += os.path.getsize(os.path.join(base, fn))
            except OSError:
                pass
    return total


def audit(page=None, docs=True):
    facts = {}
    failures = []
    facts.update(page_facts())

    gz = facts["page_gzip_bytes"]
    facts["views_per_month"] = PAGES_BANDWIDTH_BYTES // gz
    facts["daily_users"] = facts["views_per_month"] // DAYS_PER_MONTH
    facts["bandwidth_used_by_one_view"] = gz

    total, rows = request_facts()
    facts["requests_per_refresh"] = total
    facts["request_rows"] = rows
    facts["actions_minutes_per_month_slow"] = REFRESH_SECONDS_SLOW / 60.0 * DAYS_PER_MONTH
    facts["actions_minutes_per_month_fast"] = REFRESH_SECONDS_FAST / 60.0 * DAYS_PER_MONTH
    facts["actions_free_minutes"] = ACTIONS_FREE_MINUTES

    growth, items = _deltas()
    facts["growth_per_refresh_bytes"] = growth
    facts["growth_items"] = items
    if growth is not None:
        facts["growth_per_year_bytes"] = int(growth * 365)
    facts["repo_bytes"] = repo_bytes()
    facts["cash_cost_per_year"] = 0

    # ---- 断言 ------------------------------------------------------------------
    if not (0 < facts["page_gzip_bytes"] < facts["page_bytes"]):
        failures.append("页面 gzip 体积不合理（%d / %d）" % (facts["page_gzip_bytes"], facts["page_bytes"]))
    if facts["page_gzip_pct"] >= 90.0:
        failures.append("页面 gzip 压缩率异常：%.1f%%" % facts["page_gzip_pct"])
    if facts["views_per_month"] < 20000:
        failures.append("免费带宽撑不到 2 万次访问/月：%d" % facts["views_per_month"])
    if facts["daily_users"] < 500:
        failures.append("免费带宽撑不到 500 名每日用户：%d" % facts["daily_users"])
    if total != EXPECT_REQUESTS:
        failures.append("稳态每天上游请求数变了：代码里数出 %d，断言写的是 %d（请同步 docs/01 第 7 节）"
                        % (total, EXPECT_REQUESTS))
    if facts["actions_minutes_per_month_slow"] > ACTIONS_FREE_MINUTES / 10.0:
        failures.append("Actions 用量超过免费额度的十分之一：%.0f 分钟/月" % facts["actions_minutes_per_month_slow"])
    if growth is None:
        facts["growth_skip"] = ("解压后的提交包里没有 data/raw/_backup_before_refresh（上一轮备份不进包），"
                                "跳过存储增量这一项；页面体积、带宽容量、请求数与 Actions 用量照常核")
    elif growth > 100000:
        failures.append("一次刷新的净增量过大（%d 字节），免费仓库会很快变大" % growth)

    if docs:
        doc = _read(DOCS01)
        need = [
            ("{:,} 字节".format(facts["page_bytes"]),
             "docs/01 第 7 节没写单页原始字节数（改完页面必须同步，否则这条会失败）"),
            ("%d 次请求" % total, "docs/01 第 7 节没写稳态请求数"),
            ("%.2f MB" % (gz / 1e6), "docs/01 第 7 节没写单页 gzip 体积"),
            ("%.1f 万次" % (facts["views_per_month"] / 1e4), "docs/01 第 7 节没写每月可支撑访问量"),
            ("{:,} 名".format(facts["daily_users"] // 100 * 100), "docs/01 第 7 节没写可支撑的每日用户数"),
            ("tools\\cost_model.py", "docs/01 第 7 节没给出复算命令"),
        ]
        for s, why in need:
            if s not in doc:
                failures.append("%s（缺 %s）" % (why, s))
        for bad in ("约 6 到 8 次请求", "30 到 90 分钟/月"):
            if bad in doc:
                failures.append("docs/01 第 7 节还留着未复算的旧写法：%s" % bad)
    return facts, failures


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--no-docs", action="store_true")
    args = ap.parse_args()
    facts, failures = audit(docs=not args.no_docs)
    if args.json:
        print(json.dumps({"facts": facts, "failures": failures}, ensure_ascii=False, indent=2))
        return 1 if failures else 0

    print("== 免费层容量算术 ==")
    print("  单页原始 %d 字节 / gzip 后 %d 字节（%.2f MB，压缩到 %.1f%%）"
          % (facts["page_bytes"], facts["page_gzip_bytes"], facts["page_gzip_bytes"] / 1e6, facts["page_gzip_pct"]))
    print("  100 GB/月软限额 → 约 %.1f 万次访问/月 → 约 %s 名每日用户"
          % (facts["views_per_month"] / 1e4, "{:,}".format(facts["daily_users"] // 100 * 100)))
    print("== 每天的上游请求（从代码数出来）==")
    for r in facts["request_rows"]:
        print("  %-28s 模板 %d × 坐标 %d = %d 次   %s"
              % (r["script"], r["templates"], r["sites"], r["requests"], r["why"]))
    print("  合计 %d 次/天" % facts["requests_per_refresh"])
    print("== 算力与存储 ==")
    print("  Actions：%.0f 到 %.0f 分钟/月（免费 %d 分钟/月）"
          % (facts["actions_minutes_per_month_fast"], facts["actions_minutes_per_month_slow"], ACTIONS_FREE_MINUTES))
    if facts["growth_per_refresh_bytes"] is not None:
        print("  一次刷新的净增量 %d 字节 → 约 %.2f MB/年（仓库现 %.1f MB，建议上限 1 GB）"
              % (facts["growth_per_refresh_bytes"], facts["growth_per_year_bytes"] / 1e6, facts["repo_bytes"] / 1e6))
    else:
        print("  SKIP " + facts.get("growth_skip", ""))
    print("  现金支出 %d 元/年" % facts["cash_cost_per_year"])

    for f in failures:
        print("  FAIL " + f)
    print("")
    if failures:
        print("RESULT FAIL %d" % len(failures))
        return 1
    print("RESULT ALL PASS（单页体积、免费带宽容量、上游请求数、Actions 用量与存储增量都可复算）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
