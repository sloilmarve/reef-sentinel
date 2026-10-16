# -*- coding: utf-8 -*-
# settle_forecast.py - 90 天验证计划 S1/S2 的结算器。
# 把 data/processed/archive/forecast_log.jsonl 里冻结的前向预报（每天追加一行，事后不可修改）
# 与实际观测逐日对齐，算每个时效的 RMSE、区间覆盖率，以及"上界达到高危险档时实际是否成灾"的命中率。
import datetime, json, os, sys
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LEDGER = os.path.join(ROOT, "data", "processed", "archive", "forecast_log.jsonl")
FEAT = os.path.join(ROOT, "data", "processed", "semporna_features.json")
OUT = os.path.join(ROOT, "data", "processed", "settlement_report.json")
HIGH = 2.0 / 3.0            # 与成品页一致的"高危险"档门槛（超阈值项 2/3）


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


def settle(ledger, obs):
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
            b = per.setdefault(lead, {"n": 0, "se": 0.0, "band": 0, "hi_high": 0, "hit": 0, "miss": 0})
            pred, half = float(f["risk"]), float(f.get("half") or 0.0)
            lo, hi = max(0.0, pred - half), min(1.0, pred + half)
            b["n"] += 1
            b["se"] += (pred - o["risk"]) ** 2
            if lo - 1e-9 <= o["risk"] <= hi + 1e-9:
                b["band"] += 1
            if hi >= HIGH - 1e-9:
                b["hi_high"] += 1
                if o["compound"]:
                    b["hit"] += 1
                else:
                    b["miss"] += 1
    out = {}
    for lead, b in sorted(per.items()):
        out[str(lead)] = {
            "n_settled": b["n"],
            "rmse": round((b["se"] / b["n"]) ** 0.5, 4),
            "band_coverage": round(100.0 * b["band"] / b["n"], 1),
            "hi_high_days": b["hi_high"],
            "hit": b["hit"],
            "miss": b["miss"],
            "s2_hit_rate": (round(100.0 * b["hit"] / b["hi_high"], 1) if b["hi_high"] else None),
        }
    return out


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
    got = settle(ledger, obs)
    assert got["1"]["n_settled"] == 1 and got["2"]["n_settled"] == 1 and got["3"]["n_settled"] == 1, got
    assert got["1"]["rmse"] == 0.5 and got["2"]["rmse"] == 0.5, got
    # 1 天：区间 [0, 1] 覆盖了实际 1.0；2 天：区间 [0.1, 0.9] 漏掉了实际 0.0；3 天：pred-half 为负、按页面口径夹到 0
    assert got["1"]["band_coverage"] == 100.0 and got["2"]["band_coverage"] == 0.0 and got["3"]["band_coverage"] == 100.0, got
    assert got["1"]["hi_high_days"] == 1 and got["1"]["hit"] == 1 and got["1"]["s2_hit_rate"] == 100.0, got
    assert got["2"]["hi_high_days"] == 1 and got["2"]["miss"] == 1 and got["2"]["s2_hit_rate"] == 0.0, got
    print("SELFTEST OK  手算样例一致：RMSE 0.5 / 覆盖 100%·0%·100% / S2 命中 100% 与 0% / 下界夹 0")
    return True


def main():
    if "--selftest" in sys.argv:
        selftest()
        return 0
    obs = load_observed(FEAT)
    ledger = load_ledger(LEDGER)
    last = max(obs) if obs else None
    print("台账记录         : %d 期（最早 %s，最新 %s）" % (
        len(ledger), ledger[0]["date"] if ledger else "-", ledger[-1]["date"] if ledger else "-"))
    print("实际观测最新日期 : %s" % last)
    per = settle(ledger, obs)
    n = sum(v["n_settled"] for v in per.values())
    report = {"generated_from": "data/processed/archive/forecast_log.jsonl",
              "obs_latest": last, "ledger_issues": len(ledger),
              "settled_lead_days": n, "per_lead": per}
    json.dump(report, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("已结算的(期 × 时效)对: %d" % n)
    if not n:
        print("暂无可结算记录：台账里最新一期的目标日（%s 之后）尚未被观测到；" % (
            ledger[-1]["date"] if ledger else "-"))
        print("等这些日期进入实际观测后重跑本脚本即可结算（S1 的 RMSE 与 S2 的命中率会一起算出来）。")
        print("WROTE " + OUT)
        return 0
    print("")
    print(" %-5s %-9s %-9s %-8s %-8s %-8s" % ("时效", "RMSE", "区间覆盖", "高危险日", "成灾命中", "命中率"))
    for lead, v in per.items():
        print(" %-5s %-9.4f %-8.1f%% %-8d %-8d %s" % (lead + " 天", v["rmse"], v["band_coverage"],
              v["hi_high_days"], v["hit"], ("%.1f%%" % v["s2_hit_rate"]) if v["s2_hit_rate"] is not None else "-"))
    print("")
    print("WROTE " + OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())