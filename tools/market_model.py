#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""市场与可持续性的算术复核（纯标准库、不联网、不需要浏览器）。

把《项目说明》第 7 节「价格与规模的假设」乘一遍：年维护人力 → 机会成本 → 订阅收入区间
→ 盈亏平衡需要几家 → 一次性迁移服务与报告档的单位经济学 → 付费托管的替换成本。
工具只做算术，不替代向本地询价；所有价格与转化率都是**假设**，因此输出里也照此标注。

用法：
    python tools\\market_model.py            # 打印事实表并逐条断言 docs/01 与成品页
    python tools\\market_model.py --json     # 只输出 JSON
"""

import argparse
import io
import json
import math
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOC01 = "docs/01_项目说明.md"
PAGE = os.path.join("demo", "index.html")

# ---------------------------------------------------------------------------
# 假设：全部来自《项目说明》第 7 节的价格与规模表（本工具不改这些数，只乘）
# ---------------------------------------------------------------------------
SUB_USD_MONTH_LOW, SUB_USD_MONTH_HIGH = 30.0, 80.0        # 美元/月/店
SHOPS_REACHABLE_LOW, SHOPS_REACHABLE_HIGH = 20, 50         # 仙本那可触达的潜店/度假村
CONVERT_LOW, CONVERT_HIGH = 0.05, 0.10                     # 假设付费转化率
MIGRATION_USD_LOW, MIGRATION_USD_HIGH = 300.0, 800.0       # 美元/站点（一次性）
MIGRATION_SITES_YEAR_LOW, MIGRATION_SITES_YEAR_HIGH = 1, 3  # 每年新站点数
REPORT_USD_QUARTER_LOW, REPORT_USD_QUARTER_HIGH = 500.0, 2000.0  # 美元/季
REPORT_CLIENTS_LOW, REPORT_CLIENTS_HIGH = 1, 2             # 报告档客户数
HOURS_PER_WEEK, WEEKS_PER_YEAR = 2.0, 52                   # 维护投入
LABOR_USD_HOUR = 20.0                                      # 注意力的机会成本口径（不是市场价）
PAID_HOSTING_USD_MONTH = 5.0                               # 超出免费层后最便宜的静态托管 + CDN
MIGRATION_LABOR_HOURS_LOW, MIGRATION_LABOR_HOURS_HIGH = 8.0, 16.0  # 换站迁移的人力复核工时
QUARTERS_PER_YEAR = 4
MONTHS_PER_YEAR = 12


def _read(rel):
    """读材料。解压后的提交包里 00_提交包说明.md 位于 ai4climate/ 的上一层，
    与 tools/consistency_audit.py 的 readp() 保持同一套回退规则。"""
    p = os.path.join(ROOT, rel)
    if not os.path.exists(p):
        p = os.path.join(os.path.dirname(ROOT), rel)
    with io.open(p, encoding="utf-8") as fh:
        return fh.read()


def _plain(text):
    """去掉 markdown 加粗，避免 ** 把数字与单位切开导致子串比较失败。"""
    return text.replace("**", "")


def _f(x, n=2):
    return ("%." + str(n) + "f") % x


def facts():
    f = {}
    f["annual_hours"] = HOURS_PER_WEEK * WEEKS_PER_YEAR
    f["labor_usd_year"] = f["annual_hours"] * LABOR_USD_HOUR
    f["paying_shops_low"] = max(1, int(math.floor(SHOPS_REACHABLE_LOW * CONVERT_LOW + 0.5)))
    f["paying_shops_high"] = max(1, int(math.floor(SHOPS_REACHABLE_HIGH * CONVERT_HIGH + 0.5)))
    f["sub_usd_year_low"] = f["paying_shops_low"] * SUB_USD_MONTH_LOW * MONTHS_PER_YEAR
    f["sub_usd_year_high"] = f["paying_shops_high"] * SUB_USD_MONTH_HIGH * MONTHS_PER_YEAR
    f["migration_usd_year_low"] = MIGRATION_USD_LOW * MIGRATION_SITES_YEAR_LOW
    f["migration_usd_year_high"] = MIGRATION_USD_HIGH * MIGRATION_SITES_YEAR_HIGH
    f["report_usd_year_low"] = REPORT_USD_QUARTER_LOW * QUARTERS_PER_YEAR * REPORT_CLIENTS_LOW
    f["report_usd_year_high"] = REPORT_USD_QUARTER_HIGH * QUARTERS_PER_YEAR * REPORT_CLIENTS_HIGH
    f["break_even_shops_low_price"] = int(
        math.ceil(f["labor_usd_year"] / (SUB_USD_MONTH_LOW * MONTHS_PER_YEAR)))
    f["break_even_shops_high_price"] = int(
        math.ceil(f["labor_usd_year"] / (SUB_USD_MONTH_HIGH * MONTHS_PER_YEAR)))
    f["convert_needed_low_price"] = f["break_even_shops_low_price"] / SHOPS_REACHABLE_HIGH
    f["convert_needed_high_price"] = f["break_even_shops_high_price"] / SHOPS_REACHABLE_LOW
    f["sub_low_covers_labor"] = f["sub_usd_year_low"] >= f["labor_usd_year"]
    f["sub_high_covers_labor"] = f["sub_usd_year_high"] >= f["labor_usd_year"]
    f["paid_hosting_usd_year"] = PAID_HOSTING_USD_MONTH * MONTHS_PER_YEAR
    f["hosting_covered_by_one_shop"] = (
        SUB_USD_MONTH_LOW * MONTHS_PER_YEAR) / f["paid_hosting_usd_year"]
    f["migration_usd_hour_low"] = MIGRATION_USD_LOW / MIGRATION_LABOR_HOURS_HIGH
    f["migration_usd_hour_high"] = MIGRATION_USD_HIGH / MIGRATION_LABOR_HOURS_LOW
    return f


def claims(f):
    """(标签, 《项目说明》里必须出现的字符串) —— 文档数字必须等于现算数字。"""
    return [
        ("年维护人力", "104 小时/年"),
        ("注意力机会成本单价", "20 美元/小时"),
        ("机会成本合计", "2,080 美元/年"),
        ("订阅收入年度区间", "360 到 4,800 美元/年"),
        ("盈亏平衡（低档价）", "低档价要 6 家"),
        ("盈亏平衡（高档价）", "高档价要 3 家"),
        ("低档价所需转化率", "12%"),
        ("高档价所需转化率", "15%"),
        ("迁移档年度区间", "300 到 2,400 美元"),
        ("报告档年度区间", "2,000 到 16,000 美元"),
        ("付费托管替换成本", "60 美元/年"),
        ("工具入口", "tools\\market_model.py"),
        ("假设声明（不是已验证收入）", "未经市场验证的设计假设"),
    ]


def page_claims(f):
    """(标签, 成品页里必须出现的字符串) —— 页面上那句可持续性摘要必须与算术一致。"""
    return [
        ("页面：年维护人力", "104 小时/年"),
        ("页面：机会成本单价", "20 美元/小时"),
        ("页面：机会成本合计", "2,080 美元/年"),
        ("页面：订阅收入区间", "360 到 4,800 美元/年"),
        ("页面：低档价盈亏平衡", "低档价要 6 家"),
        ("页面：高档价盈亏平衡", "高档价要 3 家"),
        ("页面：假设声明", "不是已验证收入"),
    ]


def audit(doc=None, docs=True):
    f = facts()
    bad = []
    if f["annual_hours"] != 104.0:
        bad.append("年维护人力应为 104 小时/年，现算 %s" % _f(f["annual_hours"]))
    if (f["paying_shops_low"], f["paying_shops_high"]) != (1, 5):
        bad.append("假设付费店数应为 1 到 5 家，现算 %d 到 %d"
                   % (f["paying_shops_low"], f["paying_shops_high"]))
    if (f["sub_usd_year_low"], f["sub_usd_year_high"]) != (360.0, 4800.0):
        bad.append("订阅收入区间应为 360 到 4,800 美元/年，现算 %s 到 %s"
                   % (_f(f["sub_usd_year_low"], 0), _f(f["sub_usd_year_high"], 0)))
    if (f["migration_usd_year_low"], f["migration_usd_year_high"]) != (300.0, 2400.0):
        bad.append("迁移档年度区间应为 300 到 2,400 美元，现算 %s 到 %s"
                   % (_f(f["migration_usd_year_low"], 0), _f(f["migration_usd_year_high"], 0)))
    if (f["report_usd_year_low"], f["report_usd_year_high"]) != (2000.0, 16000.0):
        bad.append("报告档年度区间应为 2,000 到 16,000 美元，现算 %s 到 %s"
                   % (_f(f["report_usd_year_low"], 0), _f(f["report_usd_year_high"], 0)))
    if (f["break_even_shops_low_price"], f["break_even_shops_high_price"]) != (6, 3):
        bad.append("盈亏平衡店数应为低档价 6 家 / 高档价 3 家，现算 %d / %d"
                   % (f["break_even_shops_low_price"], f["break_even_shops_high_price"]))
    if abs(f["convert_needed_low_price"] - 0.12) > 1e-9 or abs(f["convert_needed_high_price"] - 0.15) > 1e-9:
        bad.append("打平所需转化率应为 12% / 15%，现算 %s / %s"
                   % (_f(f["convert_needed_low_price"] * 100, 0), _f(f["convert_needed_high_price"] * 100, 0)))
    if f["sub_low_covers_labor"]:
        bad.append("按低档价与假设转化率，订阅收入不应覆盖人力机会成本（诚实结论被推翻）")
    if not f["sub_high_covers_labor"]:
        bad.append("按高档价与假设转化率，订阅收入应覆盖人力机会成本")
    if f["hosting_covered_by_one_shop"] < 5.0:
        bad.append("一家订阅应至少覆盖 5 倍付费托管成本，现算 %s 倍" % _f(f["hosting_covered_by_one_shop"], 1))
    if not (15.0 <= f["migration_usd_hour_low"] <= 20.0):
        bad.append("换站迁移低端有效时薪应在 15 到 20 美元/小时之间（诚实口径），现算 %s"
                   % _f(f["migration_usd_hour_low"]))
    if f["migration_usd_hour_high"] < 80.0:
        bad.append("换站迁移高端有效时薪应不低于 80 美元/小时，现算 %s"
                   % _f(f["migration_usd_hour_high"]))

    if docs:
        text = _plain(_read(doc or DOC01))
        for label, needle in claims(f):
            if needle not in text:
                bad.append("%s：%s 里找不到「%s」" % (label, doc or DOC01, needle))
        page = _read(PAGE)
        for label, needle in page_claims(f):
            if needle not in page:
                bad.append("%s：成品页里找不到「%s」" % (label, needle))
    return f, bad


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--no-docs", action="store_true")
    args = ap.parse_args(argv)
    f, bad = audit(docs=not args.no_docs)
    if args.json:
        print(json.dumps({"facts": f, "failures": bad}, ensure_ascii=False, indent=2))
        return 1 if bad else 0
    print("=== 市场与可持续性算术（全部价格与转化率都是假设，不是已验证收入）===")
    print("  年维护人力              %s 小时/年（%.0f 小时/周 × %d 周）"
          % (_f(f["annual_hours"], 0), HOURS_PER_WEEK, WEEKS_PER_YEAR))
    print("  注意力机会成本          %s 美元/年（按 %s 美元/小时计价）"
          % (_f(f["labor_usd_year"], 0), _f(LABOR_USD_HOUR, 0)))
    print("  假设付费店数            %d 到 %d 家（可触达 %d 到 %d 家 × %s 到 %s 转化）"
          % (f["paying_shops_low"], f["paying_shops_high"], SHOPS_REACHABLE_LOW,
             SHOPS_REACHABLE_HIGH, _f(CONVERT_LOW * 100, 0), _f(CONVERT_HIGH * 100, 0)))
    print("  订阅收入                %s 到 %s 美元/年（%s 到 %s 美元/月/店）"
          % (_f(f["sub_usd_year_low"], 0), _f(f["sub_usd_year_high"], 0),
             _f(SUB_USD_MONTH_LOW, 0), _f(SUB_USD_MONTH_HIGH, 0)))
    print("  盈亏平衡（覆盖机会成本）低档价 %d 家 / 高档价 %d 家（占可触达的 %s%% / %s%%）"
          % (f["break_even_shops_low_price"], f["break_even_shops_high_price"],
             _f(f["convert_needed_low_price"] * 100, 0), _f(f["convert_needed_high_price"] * 100, 0)))
    print("  订阅档是否覆盖机会成本  低档价 %s / 高档价 %s"
          % ("是" if f["sub_low_covers_labor"] else "否", "是" if f["sub_high_covers_labor"] else "否"))
    print("  迁移档                  %s 到 %s 美元/年；按 %s 到 %s 小时复核 → %s 到 %s 美元/小时"
          % (_f(f["migration_usd_year_low"], 0), _f(f["migration_usd_year_high"], 0),
             _f(MIGRATION_LABOR_HOURS_LOW, 0), _f(MIGRATION_LABOR_HOURS_HIGH, 0),
             _f(f["migration_usd_hour_low"]), _f(f["migration_usd_hour_high"], 0)))
    print("  报告档                  %s 到 %s 美元/年（%s 到 %s 美元/季 × %d 到 %d 家）"
          % (_f(f["report_usd_year_low"], 0), _f(f["report_usd_year_high"], 0),
             _f(REPORT_USD_QUARTER_LOW, 0), _f(REPORT_USD_QUARTER_HIGH, 0),
             REPORT_CLIENTS_LOW, REPORT_CLIENTS_HIGH))
    print("  付费托管替换成本        %s 美元/年（%s 美元/月）→ 一家订阅覆盖 %s 倍"
          % (_f(f["paid_hosting_usd_year"], 0), _f(PAID_HOSTING_USD_MONTH, 0),
             _f(f["hosting_covered_by_one_shop"], 1)))
    if bad:
        print("")
        print("RESULT FAIL（%d 项）:" % len(bad))
        for b in bad:
            print("  - " + b)
        return 1
    print("")
    print("RESULT ALL PASS（《项目说明》第 7 节与成品页上的每个市场数字都由假设现算，且口径一致）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
