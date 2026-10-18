#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""快照审计：随包原始观测不得越过数据快照日，否则离线复算会算出另一张页面。

为什么要有这个脚本（第 37 轮）：
    第 37 轮把官方规则点名的高风险四项说明写进成品页时，`tools/preflight.py`
    第 6 步（评审视角复算）突然失败：评委按文档离线重跑，得到的页面与包里
    那张不一样。原因不在模型、也不在页面，而在**随包的原始观测**：
    `data/raw/semporna_marine_hourly.csv` 末行是 2026-10-17T23:00、
    `data/raw/semporna_weather_daily.csv` 末行是 2026-10-17，而
    `data/processed/dashboard_data.json` 的 span.end 与页面数字都停在
    2026-10-16 —— 包里同时装着"快照日之后一天的原始观测"和"快照日的产物"。
    任何人按 `tools/reviewer_repro.py` 的步骤离线重算，都会多出一天
    （1,447 天、21.0%、0.1606 等），页面自然对不上。

    这类错误此前没有任何门禁看得见：`verify_demo.py` 核的是页面与
    `data/processed` 一致，`consistency_audit.py` 核的是文档与产物一致，
    两者都不看"随包的原始观测到底覆盖到哪一天"。所以这里把它钉死。

做法（全部离线、纯标准库）：
    - 快照日 = `data/processed/dashboard_data.json` 的 `span.end`；
    - 每一张观测表（逐小时海洋、逐日气象、两份海温长表、三站点对照、
      两份 NOAA 对照）里出现的最大日期都不得晚于快照日；
    - 两张主观测表（逐小时海洋、逐日气象）必须**正好**结束在快照日
      （结束得更早则链条根本产不出快照日，结束得更晚就是本次抓到的错）；
    - `data/processed/semporna_features.json` 的末日必须等于快照日；
    - `data/raw/semporna_forecast_drivers.json` 是唯一允许越过快照日的输入
      （预报天然指向未来），但它的首日必须正好是快照日的次日。

用法：
    python tools/snapshot_audit.py            # 人类可读
    python tools/snapshot_audit.py --json     # 机器可读
"""

import datetime
import io
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "raw")
EXT = os.path.join(ROOT, "data", "external")
PROC = os.path.join(ROOT, "data", "processed")

DATE = re.compile(r"\d{4}-\d{2}-\d{2}")

# (相对路径, 中文名, 是否必须正好结束在快照日)
OBSERVATIONS = (
    (os.path.join("data", "raw", "semporna_marine_hourly.csv"),
     "逐小时海洋观测（浪高 / 海温 / 水位）", True),
    (os.path.join("data", "raw", "semporna_weather_daily.csv"),
     "逐日气象观测（气温 / 降水 / 风）", True),
    (os.path.join("data", "raw", "semporna_sst_hourly_2022_2026.csv"),
     "海温逐小时长表（2022 起）", False),
    (os.path.join("data", "raw", "semporna_sst_hourly_2023_2026.csv"),
     "海温逐小时长表（2023 起）", False),
    (os.path.join("data", "external", "multisite", "semporna_daily.json"),
     "三站点对照：仙本那", False),
    (os.path.join("data", "external", "multisite", "palau_daily.json"),
     "三站点对照：帕劳", False),
    (os.path.join("data", "external", "multisite", "bunaken_daily.json"),
     "三站点对照：布纳肯", False),
    (os.path.join("data", "external", "noaa_crw", "vs_sabah_daily.csv"),
     "NOAA CRW 对照：沙巴", False),
    (os.path.join("data", "external", "noaa_crw", "vs_palau_daily.csv"),
     "NOAA CRW 对照：帕劳", False),
)

FORECAST = (os.path.join("data", "raw", "semporna_forecast_drivers.json"),
            "未来 8 天预报驱动（唯一允许越过快照日的输入）")


def _read(rel):
    """打包后 `data/` 与文档同级，故先试 ROOT/rel，再试 ROOT.parent/rel。"""
    for base in (ROOT, os.path.dirname(ROOT)):
        p = os.path.join(base, rel)
        if os.path.exists(p):
            with io.open(p, encoding="utf-8", errors="replace") as f:
                return f.read()
    return None


def _last_date(text):
    got = DATE.findall(text)
    return max(got) if got else None


def _first_date(text):
    got = DATE.findall(text)
    return min(got) if got else None


def facts():
    f = {}
    dash = _read(os.path.join("data", "processed", "dashboard_data.json"))
    if dash is None:
        return {"missing": "data/processed/dashboard_data.json"}
    D = json.loads(dash)
    span = D.get("span") or {}
    f["snap"] = span.get("end")
    f["days"] = span.get("days")
    f["span_start"] = span.get("start")

    tables = []
    obs_last = None
    for rel, name, exact in OBSERVATIONS:
        text = _read(rel)
        if text is None:
            tables.append({"path": rel, "name": name, "last": None,
                           "exact": exact, "missing": True})
            continue
        last = _last_date(text)
        tables.append({"path": rel, "name": name, "last": last,
                       "exact": exact, "missing": False})
        if last and (obs_last is None or last > obs_last):
            obs_last = last
    f["tables"] = tables
    f["n_tables"] = len(tables)
    f["obs_last"] = obs_last
    f["obs_overshoot"] = [t["name"] + "=" + t["last"] for t in tables
                          if t["last"] and f["snap"] and t["last"] > f["snap"]]

    feats = _read(os.path.join("data", "processed", "semporna_features.json"))
    f["feat_last"] = None
    if feats is not None:
        try:
            FX = json.loads(feats)
            rows = FX.get("days") or FX.get("rows") or []
            if rows:
                f["feat_last"] = rows[-1].get("date")
        except ValueError:
            f["feat_last"] = _last_date(feats)

    drv = _read(FORECAST[0])
    f["drivers_first"] = _first_date(drv) if drv else None
    f["drivers_last"] = _last_date(drv) if drv else None
    f["drivers_expected_first"] = None
    if f["snap"]:
        d = datetime.date(*[int(x) for x in f["snap"].split("-")])
        f["drivers_expected_first"] = (d + datetime.timedelta(days=1)).isoformat()
    return f


def audit():
    f = facts()
    bad = []
    if "missing" in f:
        return f, ["找不到 " + f["missing"]]
    if not f["snap"]:
        return f, ["dashboard_data.json 没有 span.end，无法定快照日"]

    for t in f["tables"]:
        if t["missing"]:
            bad.append("缺文件：%s（%s）" % (t["path"], t["name"]))
            continue
        if not t["last"]:
            bad.append("%s：文件里没有任何日期" % t["name"])
            continue
        if t["last"] > f["snap"]:
            bad.append("%s 里最大日期是 %s，晚于快照日 %s —— 包里原始观测"
                       "越过了快照日，评委离线复算会多算一天"
                       % (t["name"], t["last"], f["snap"]))
        elif t["exact"] and t["last"] != f["snap"]:
            bad.append("%s 结束在 %s，而快照日是 %s —— 主观测表必须正好"
                       "覆盖到快照日" % (t["name"], t["last"], f["snap"]))

    if f["feat_last"] != f["snap"]:
        bad.append("data/processed/semporna_features.json 的末日是 %s，"
                   "而快照日是 %s" % (f["feat_last"], f["snap"]))

    if f["drivers_first"] != f["drivers_expected_first"]:
        bad.append("%s 的首日是 %s，应为快照日的次日 %s"
                   % (FORECAST[1], f["drivers_first"],
                      f["drivers_expected_first"]))
    return f, bad


def main():
    argv = sys.argv[1:]
    f, bad = audit()
    if "--json" in argv:
        print(json.dumps({"facts": f, "failures": bad}, ensure_ascii=False,
                         indent=1))
        return 0 if not bad else 1
    print("快照审计  snapshot_audit")
    print("  数据快照日            %s（记录期 %s 起，共 %s 天）"
          % (f.get("snap"), f.get("span_start"),
             format(f.get("days"), ",") if f.get("days") else "?"))
    print("  观测表最大日期        %s（%d 张表）" % (f.get("obs_last"), f.get("n_tables", 0)))
    for t in f.get("tables", []):
        mark = "正好" if t["exact"] else "不越界"
        print("    %-26s %s  %s" % (t["name"], t["last"], mark))
    print("  特征表末日            %s" % f.get("feat_last"))
    print("  预报驱动首日          %s（应为 %s）"
          % (f.get("drivers_first"), f.get("drivers_expected_first")))
    if bad:
        print("\n=== 失败 %d 项 ===" % len(bad))
        for b in bad:
            print("  FAIL " + b)
        return 1
    print("\nRESULT ALL PASS（随包原始观测不越过快照日 %s，两张主观测表正好"
          "覆盖到那天，离线链条才能逐字节复现成品页）" % f["snap"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
