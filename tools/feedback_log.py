# -*- coding: utf-8 -*-
# feedback_log.py - 90 天验证计划里 S3 / S4 / S5 的记录与结算工具。
# 为什么需要：S1（准确性）与 S2（校准度）能用四年历史数据回溯检验，S3（真实使用）/
# S4（决策影响）/ S5（误报耐受）只能等真实使用期发生 —— 但"记录"必须先有固定格式与
# 固定算分口径，否则 90 天后只能靠回忆写总结，无法证伪。本工具把这三条变成可追加、
# 可复算的台账：追加一行 -> 立刻算出判定，判定写进 data/processed/engagement_report.json。
#
# 用法：
#   python tools/feedback_log.py --add-s3 2026-11-02 "Sipadan Scuba" "WhatsApp 群" "店长说这周看了 3 次"
#   python tools/feedback_log.py --add-s4 2026-11-05 "Sipadan Scuba" "把浮潜团改期到 11-07" "1 天档上界 0.42 越线" "如期改期，当天浪高 1.1 m"
#   python tools/feedback_log.py --add-s5 2026-11-05 "Sipadan Scuba" 2 3 "两次误报都出现在 3 天档"
#   python tools/feedback_log.py --report      # 打印判定，并写 data/processed/engagement_report.json
#   python tools/feedback_log.py --selftest    # 手算样例校验算分逻辑（preflight 第 6 步会跑）
#
# 算分口径（与 docs/03_90天验证计划.md 第一节的 S3 / S4 / S5 逐字对应）：
#   S3 真实使用：同一家机构在连续 4 个 ISO 周里每周至少记录 1 次查看 -> 达标（≥ 1 家）
#   S4 决策影响：记录了 ≥ 3 次"因预报而改变计划"的具体事件（含原计划 / 依据 / 结果）-> 达标
#   S5 信任与误报耐受：记录对方的容忍门槛与实际误报次数，判定"实际 <= 门槛"；
#      这一条不设通过线，只要求"有明确门槛 + 有误报计数"，因为误报耐受本身是主观量。
import argparse, json, os, sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG = os.path.join(ROOT, "data", "processed", "engagement_log.json")
REPORT = os.path.join(ROOT, "data", "processed", "engagement_report.json")
S3_WEEKS = 4
S4_MIN = 3


def load_log():
    if not os.path.exists(LOG):
        return {"site": "Semporna, Sabah", "s3": [], "s4": [], "s5": []}
    d = json.load(open(LOG, encoding="utf-8"))
    for k in ("s3", "s4", "s5"):
        d.setdefault(k, [])
    return d


def save_log(d):
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    with open(LOG, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(d, fh, ensure_ascii=False, indent=1, sort_keys=False)
        fh.write("\n")


def _monday(s):
    """把 YYYY-MM-DD 转成该 ISO 周的周一（连续周的判定因此与月界无关）。"""
    import datetime
    y, m, dd = [int(x) for x in str(s).strip().split("-")]
    d = datetime.date(y, m, dd)
    return d - datetime.timedelta(days=d.isoweekday() - 1)


def s3_verdict(recs):
    """按机构算：最长连续周数（每周去重）。达标 = 任一机构连续 >= S3_WEEKS 周。"""
    per = {}
    for r in recs:
        org = str(r.get("org", "")).strip()
        if not org:
            continue
        per.setdefault(org, set()).add(_monday(r.get("date")))
    out = {}
    for org, days in per.items():
        ws = sorted(days)
        best = run = 1 if ws else 0
        for a, b in zip(ws, ws[1:]):
            run = run + 1 if (b - a).days == 7 else 1
            best = max(best, run)
        out[org] = {"weeks": len(ws), "best_run": best}
    best_any = max([v["best_run"] for v in out.values()] or [0])
    return {"orgs": out, "n_orgs": len(out), "best_run": best_any,
            "need_weeks": S3_WEEKS, "verdict": "pass" if best_any >= S3_WEEKS else "pending"}


def s4_verdict(recs):
    """每条都要有原计划（change）、依据（basis）、结果（outcome）才算一条完整事件。"""
    complete = [r for r in recs
                if str(r.get("change", "")).strip() and str(r.get("basis", "")).strip()
                and str(r.get("outcome", "")).strip()]
    n = len(complete)
    return {"n": n, "n_incomplete": len(recs) - n, "need": S4_MIN,
            "verdict": "pass" if n >= S4_MIN else "pending"}


def s5_verdict(recs):
    """不设通过线：只要求有明确门槛与误报计数，并如实判 observed <= tolerance。"""
    tol = [r.get("tolerance") for r in recs if isinstance(r.get("tolerance"), int)]
    obs = [r.get("false_alarms") for r in recs if isinstance(r.get("false_alarms"), int)]
    if not tol or not obs:
        return {"n": len(recs), "tolerance_max": None, "false_alarms_max": None,
                "within_tolerance": None, "verdict": "pending"}
    t, o = max(tol), max(obs)
    return {"n": len(recs), "tolerance_max": t, "false_alarms_max": o,
            "within_tolerance": bool(o <= t),
            "verdict": "recorded"}


def report(d):
    s3, s4, s5 = s3_verdict(d["s3"]), s4_verdict(d["s4"]), s5_verdict(d["s5"])
    r = {
        "task": "90 天验证计划 S3 / S4 / S5 的记录结算（真实使用 / 决策影响 / 误报耐受）",
        "site": d.get("site", ""),
        "n_s3": len(d["s3"]), "n_s4": len(d["s4"]), "n_s5": len(d["s5"]),
        "s3": s3, "s4": s4, "s5": s5,
        "verdict": "pass" if (s3["verdict"] == "pass" and s4["verdict"] == "pass") else "pending",
        "note": ("这三条只能等真实使用期发生，没有外部记录时如实报 pending，"
                 "不用 0 充数、也不把空台账写成达标"),
    }
    return r


def _print(r):
    print("S3 真实使用：" + str(r["s3"]["n_orgs"]) + " 家机构、最长连续 "
          + str(r["s3"]["best_run"]) + " 周（需 " + str(r["s3"]["need_weeks"]) + " 周）-> "
          + r["s3"]["verdict"])
    for org, v in sorted(r["s3"]["orgs"].items()):
        print("    " + org + "：记录 " + str(v["weeks"]) + " 周，最长连续 " + str(v["best_run"]) + " 周")
    print("S4 决策影响：" + str(r["s4"]["n"]) + " 条完整事件（需 " + str(r["s4"]["need"]) + " 条）-> "
          + r["s4"]["verdict"])
    if r["s5"]["verdict"] == "pending":
        print("S5 误报耐受：尚无记录 -> pending")
    else:
        print("S5 误报耐受：容忍门槛最高 " + str(r["s5"]["tolerance_max"]) + " 次，实际误报最多 "
              + str(r["s5"]["false_alarms_max"]) + " 次，实际未超门槛 = "
              + str(r["s5"]["within_tolerance"]))
    print("总判定：" + r["verdict"] + "（" + r["note"] + "）")


def selftest():
    # 连续 4 周（2026-01-05 / 12 / 19 / 26 都是周一）-> 达标；跨月的 2 周断档 -> 只算 2 周。
    ok3 = [{"date": "2026-01-05", "org": "A"}, {"date": "2026-01-12", "org": "A"},
           {"date": "2026-01-19", "org": "A"}, {"date": "2026-01-26", "org": "A"},
           {"date": "2026-01-05", "org": "B"}, {"date": "2026-02-02", "org": "B"}]
    v3 = s3_verdict(ok3)
    assert v3["verdict"] == "pass" and v3["best_run"] == 4 and v3["n_orgs"] == 2, v3
    gap3 = [{"date": "2026-01-05", "org": "A"}, {"date": "2026-01-12", "org": "A"},
            {"date": "2026-01-26", "org": "A"}, {"date": "2026-02-02", "org": "A"}]
    v3b = s3_verdict(gap3)
    assert v3b["verdict"] == "pending" and v3b["best_run"] == 2, v3b
    # 同一周记两次只算 1 周（去重）。
    dup3 = [{"date": "2026-01-05", "org": "A"}, {"date": "2026-01-07", "org": "A"}]
    assert s3_verdict(dup3)["best_run"] == 1, s3_verdict(dup3)
    # 跨月但连续：01-26 与 02-02 相差 7 天，仍算连续。
    cross3 = [{"date": "2026-01-19", "org": "A"}, {"date": "2026-01-26", "org": "A"},
              {"date": "2026-02-02", "org": "A"}, {"date": "2026-02-09", "org": "A"}]
    assert s3_verdict(cross3)["best_run"] == 4, s3_verdict(cross3)
    ev = [{"change": "改期", "basis": "上界越线", "outcome": "如期"}, {}]
    v4 = s4_verdict(ev * 3)
    assert v4["n"] == 3 and v4["n_incomplete"] == 3 and v4["verdict"] == "pass", v4
    assert s4_verdict(ev)["verdict"] == "pending", s4_verdict(ev)
    v5 = s5_verdict([{"false_alarms": 2, "tolerance": 3}])
    assert v5["within_tolerance"] is True and v5["verdict"] == "recorded", v5
    v5b = s5_verdict([{"false_alarms": 4, "tolerance": 3}])
    assert v5b["within_tolerance"] is False, v5b
    assert s5_verdict([])["verdict"] == "pending", s5_verdict([])
    # 空台账不得写成达标。
    empty = report({"site": "x", "s3": [], "s4": [], "s5": []})
    assert empty["verdict"] == "pending" and empty["s3"]["best_run"] == 0, empty
    print("SELFTEST OK  手算样例一致：连续 4 周达标 / 断档只算 2 周 / 同周去重 / 跨月仍连续 / "
          "3 条完整事件达标（不完整不计） / 误报超门槛如实判 False / 空台账判 pending")


def main():
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("--add-s3", nargs=3, metavar=("DATE", "ORG", "CHANNEL"))
    ap.add_argument("--add-s4", nargs=4, metavar=("DATE", "ORG", "CHANGE", "BASIS"))
    ap.add_argument("--add-s5", nargs=4, metavar=("DATE", "ORG", "FALSE_ALARMS", "TOLERANCE"))
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        selftest()
        return 0
    d = load_log()
    changed = False
    if a.add_s3:
        d["s3"].append({"date": a.add_s3[0], "org": a.add_s3[1], "channel": a.add_s3[2]})
        changed = True
    if a.add_s4:
        d["s4"].append({"date": a.add_s4[0], "org": a.add_s4[1], "change": a.add_s4[2],
                        "basis": a.add_s4[3], "outcome": ""})
        changed = True
    if a.add_s5:
        d["s5"].append({"date": a.add_s5[0], "org": a.add_s5[1],
                        "false_alarms": int(a.add_s5[2]), "tolerance": int(a.add_s5[3])})
        changed = True
    if changed:
        save_log(d)
        print("已追加到 " + os.path.relpath(LOG, ROOT))
    if not os.path.exists(LOG):
        save_log(d)   # 台账不存在时先落一份空台账：产物必须在，空也要是"明确的空"
        print("已建立空台账 " + os.path.relpath(LOG, ROOT))
    r = report(d)
    _print(r)
    os.makedirs(os.path.dirname(REPORT), exist_ok=True)
    with open(REPORT, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(r, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    print("REPORT WROTE " + os.path.relpath(REPORT, ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
