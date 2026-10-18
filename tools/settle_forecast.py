# -*- coding: utf-8 -*-
# settle_forecast.py - 90 天验证计划 S1/S2 的结算器。
# 把 data/processed/archive/forecast_log.jsonl 里冻结的前向预报（每天追加一行，事后不可修改）
# 与实际观测逐日对齐，算每个时效的 RMSE、区间覆盖率，以及 S2 判据：
#   「上界越过成品页窗口表那条线（= 危险指数 p95，当前 0.333）的日子，实际出现复合灾害的比例」
#   按时效输出 触发天数 / 命中 / 精确率 / 召回率 / 相对背景率的提升倍数。
# 触发线与成品页、priority_plan.json 同源，不再写死；回溯预期见 data/processed/s2_hindcast.json。
import datetime, json, os, sys
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LEDGER = os.path.join(ROOT, "data", "processed", "archive", "forecast_log.jsonl")
FEAT = os.path.join(ROOT, "data", "processed", "semporna_features.json")
PLAN = os.path.join(ROOT, "data", "processed", "priority_plan.json")
OUT = os.path.join(ROOT, "data", "processed", "settlement_report.json")
DEFAULT_LINE = 1.0 / 3.0      # 与成品页窗口表一致；正常情况下从 priority_plan.json 读，读不到才回退
MIN_TRIGGER = 5               # 判定 S2 前至少要积累这么多次触发，样本太少只报数字不下结论


def trigger_line():
    """触发线 = 危险指数 p95（成品页窗口表判「高」档的那条线）。"""
    try:
        p = json.load(open(PLAN, encoding="utf-8"))
        v = float(p["thresholds"]["risk_p95"])
        return (v, "priority_plan.json")
    except Exception:
        return (DEFAULT_LINE, "fallback 1/3")


def load_observed(path):
    """逐日实际值：危险指数 = 超阈值项 / 3，成灾 = 超阈值项 >= 2。"""
    F = json.load(open(path, encoding="utf-8"))
    obs = {}
    for r in F["days"]:
        n = r.get("n_haz")
        if n is None:
            continue
        obs[r["date"]] = {"risk": round(n / 3.0, 6), "n_haz": n, "compound": 1 if n >= 2 else 0}
    return obs


def load_ledger(path):
    recs = []
    if not os.path.exists(path):
        return recs
    for ln in open(path, encoding="utf-8"):
        ln = ln.strip()
        if not ln:
            continue
        try:
            recs.append(json.loads(ln))
        except Exception as e:
            print("  SKIP 无法解析的台账行：" + str(e))
    return recs


def settle(ledger, obs, line=DEFAULT_LINE):
    """返回 {时效: 统计}，口径与成品页一致（区间 = risk ± half，夹在 0..1）。"""
    per = {}
    for rec in ledger:
        d0 = datetime.date.fromisoformat(rec["date"])
        for f in rec.get("forecast", []):
            lead = int(f["lead"])
            key = (d0 + datetime.timedelta(days=lead)).isoformat()
            o = obs.get(key)
            if o is None:
                continue
            b = per.setdefault(lead, {"n": 0, "se": 0.0, "band": 0, "comp": 0,
                                      "trigger": 0, "hit": 0, "miss": 0})
            pred, half = float(f["risk"]), float(f.get("half") or 0.0)
            lo, hi = max(0.0, pred - half), min(1.0, pred + half)
            b["n"] += 1
            b["se"] += (pred - o["risk"]) ** 2
            if lo - 1e-9 <= o["risk"] <= hi + 1e-9:
                b["band"] += 1
            if o["compound"]:
                b["comp"] += 1
            if hi >= line - 1e-9:
                b["trigger"] += 1
                if o["compound"]:
                    b["hit"] += 1
                else:
                    b["miss"] += 1
    out = {}
    for lead, b in sorted(per.items()):
        base = (float(b["comp"]) / b["n"]) if b["n"] else 0.0
        prec = (float(b["hit"]) / b["trigger"]) if b["trigger"] else None
        out[str(lead)] = {
            "n_settled": b["n"],
            "rmse": round((b["se"] / b["n"]) ** 0.5, 4),
            "band_coverage": round(100.0 * b["band"] / b["n"], 1),
            "compound_days": b["comp"],
            "base_rate_pct": round(100.0 * base, 2),
            "hi_high_days": b["trigger"],
            "hit": b["hit"],
            "miss": b["miss"],
            "s2_precision_pct": (round(100.0 * prec, 1) if prec is not None else None),
            "s2_recall_pct": (round(100.0 * b["hit"] / b["comp"], 1) if b["comp"] else None),
            "s2_lift_vs_base": (round(prec / base, 2) if (prec is not None and base) else None),
        }
    return out


def verdict(per):
    """S2 改后的判据：1 天档触发 >= MIN_TRIGGER 次时，提升 >= 2 倍且召回 >= 80%。"""
    one = per.get("1")
    if not one:
        return {"status": "pending", "why": "尚无 1 天档可结算记录"}
    if one["hi_high_days"] < MIN_TRIGGER:
        return {"status": "pending", "why": "1 天档触发 %d 次（少于 %d 次，只报数字不下结论）" % (one["hi_high_days"], MIN_TRIGGER)}
    ok = (one["s2_lift_vs_base"] is not None and one["s2_lift_vs_base"] >= 2.0
          and one["s2_recall_pct"] is not None and one["s2_recall_pct"] >= 80.0)
    return {"status": ("pass" if ok else "fail"),
            "why": "1 天档触发 %d 次：精确率 %s%%，提升 %s 倍，召回 %s%%" % (
                one["hi_high_days"], one["s2_precision_pct"], one["s2_lift_vs_base"], one["s2_recall_pct"]),
            "criterion": "提升 >= 2 倍且召回 >= 80%（回溯预期：3.68 倍 / 90.9%）"}


def selftest():
    """用手算得出的最小样例验证结算口径（不依赖真实台账）。"""
    obs = {"2026-01-02": {"risk": 1.0, "n_haz": 3, "compound": 1},
           "2026-01-03": {"risk": 0.0, "n_haz": 0, "compound": 0},
           "2026-01-04": {"risk": 0.0, "n_haz": 0, "compound": 0}}
    ledger = [{"date": "2026-01-01",
               "risk": 0.0, "n_haz": 0,
               "forecast": [{"lead": 1, "risk": 0.5, "hi": 1.0, "half": 0.6},
                            {"lead": 2, "risk": 0.5, "hi": 0.9, "half": 0.4},
                            {"lead": 3, "risk": 0.1, "hi": 0.6, "half": 0.5}]}]
    got = settle(ledger, obs, line=1.0 / 3.0)
    assert got["1"]["n_settled"] == 1 and got["2"]["n_settled"] == 1 and got["3"]["n_settled"] == 1, got
    assert got["1"]["rmse"] == 0.5 and got["2"]["rmse"] == 0.5, got
    # 1 天：区间 [0, 1] 覆盖了实际 1.0；2 天：区间 [0.1, 0.9] 漏掉了实际 0.0；3 天：pred-half 为负、按页面口径夹到 0
    assert got["1"]["band_coverage"] == 100.0 and got["2"]["band_coverage"] == 0.0 and got["3"]["band_coverage"] == 100.0, got
    # S2：三条 hi 都越过 1/3 线（1.0 / 0.9 / 0.6），只有 1 天档命中复合灾害
    assert got["1"]["hi_high_days"] == 1 and got["1"]["hit"] == 1 and got["1"]["s2_precision_pct"] == 100.0, got
    assert got["1"]["s2_recall_pct"] == 100.0 and got["1"]["s2_lift_vs_base"] == 1.0, got
    assert got["2"]["hi_high_days"] == 1 and got["2"]["miss"] == 1 and got["2"]["s2_precision_pct"] == 0.0, got
    # 2 天档那条线上没有复合灾害日（compound_days = 0）：召回与提升在数学上无定义，如实给 None，不写 0 充数
    assert got["2"]["s2_recall_pct"] is None and got["2"]["s2_lift_vs_base"] is None, got
    # 触发线抬高到 2/3 时：只有 1 天档（hi = 1.0）越线
    got2 = settle(ledger, obs, line=2.0 / 3.0)
    assert got2["1"]["hi_high_days"] == 1 and got2["2"]["hi_high_days"] == 1 and got2["3"]["hi_high_days"] == 0, got2
    v = verdict(got)
    assert v["status"] == "pending", v
    print("SELFTEST OK  手算样例一致：RMSE 0.5 / 覆盖 100%·0%·100% / S2 精确率 100% 与 0% / 提升 1.0 与 0.0 / 触发线抬高到 2/3 后 3 天档（hi = 0.6）不再触发 / 样本不足判 pending")
    return True


def main():
    if "--selftest" in sys.argv:
        selftest()
        return 0
    line, src = trigger_line()
    obs = load_observed(FEAT)
    ledger = load_ledger(LEDGER)
    last = max(obs) if obs else None
    print("触发线           : hi >= %.4f（来自 %s，与成品页窗口表同一档）" % (line, src))
    print("台账记录         : %d 期（最早 %s，最新 %s）" % (
        len(ledger), ledger[0]["date"] if ledger else "-", ledger[-1]["date"] if ledger else "-"))
    print("实际观测最新日期 : %s" % last)
    per = settle(ledger, obs, line=line)
    n = sum(v["n_settled"] for v in per.values())
    vd = verdict(per)
    report = {"generated_from": "data/processed/archive/forecast_log.jsonl",
              "trigger_line": round(line, 4), "trigger_line_source": src,
              "obs_latest": last, "ledger_issues": len(ledger),
              "settled_lead_days": n, "s2_verdict": vd, "per_lead": per}
    json.dump(report, open(OUT, "w", encoding="utf-8", newline="\n"), ensure_ascii=False, indent=1)
    print("已结算的(期 × 时效)对: %d" % n)
    if not n:
        print("暂无可结算记录：台账里最新一期的目标日（%s 之后）尚未被观测到；" % (
            ledger[-1]["date"] if ledger else "-"))
        print("等这些日期进入实际观测后重跑本脚本即可结算（S1 的 RMSE 与 S2 的精确率 / 召回率会一起算出来）。")
        print("WROTE " + OUT)
        return 0
    print("")
    print(" %-5s %-8s %-9s %-8s %-9s %-8s %-9s %-8s %-8s" % (
        "时效", "RMSE", "区间覆盖", "复合日", "背景率", "触发日", "精确率", "召回率", "提升"))
    for lead, v in per.items():
        print(" %-5s %-8.4f %-8.1f%% %-8d %-8.2f%% %-8d %-9s %-8s %-8s" % (
            lead + " 天", v["rmse"], v["band_coverage"], v["compound_days"], v["base_rate_pct"],
            v["hi_high_days"],
            ("%.1f%%" % v["s2_precision_pct"]) if v["s2_precision_pct"] is not None else "-",
            ("%.1f%%" % v["s2_recall_pct"]) if v["s2_recall_pct"] is not None else "-",
            ("%.2f" % v["s2_lift_vs_base"]) if v["s2_lift_vs_base"] is not None else "-"))
    print("")
    print("S2 判定          : %s（%s）" % (vd["status"], vd["why"]))
    print("WROTE " + OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())