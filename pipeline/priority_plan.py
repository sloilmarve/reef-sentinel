"""保护与恢复优先级判断（方向 04 的「保护与恢复优先级」一支）。

两块输出：
(1) 未来逐日干预窗口排序：用成品页 1-9 天预报的风险上界（点预报 + 80% 经验半宽）排序，
    上界最低的日子优先做可逆性低的保护施工/移栽，上界越过本站 p95 的日子列为暂停；
(2) 三站点保护优先级排序：对仙本那 / 布纳肯 / 帕劳各站用同一口径算
    近 84 天累计热异常（占本站记录自身的百分位）与近 90 天多压力日数，
    得分 = 0.6 x 热暴露百分位 + 0.4 x 多压力日相对值，据此给出「先去哪个站做保护评估」；
(3) 白化后恢复窗口：以最近一次海洋热浪事件的结束日推 4 至 8 周复测窗口。
输出 data/processed/priority_plan.json
"""
import io, os, json, math, sys
from datetime import date, timedelta

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
P = lambda *a: os.path.join(BASE, *a)
DASH = P("data", "processed", "dashboard_data.json")
BLEA = P("data", "processed", "bleaching_watch.json")
MULTI = P("data", "external", "multisite")
OUT = P("data", "processed", "priority_plan.json")

def pct(v, q):
    a = sorted(v)
    k = (len(a) - 1) * q
    lo = int(math.floor(k))
    hi = int(math.ceil(k))
    return a[lo] if lo == hi else a[lo] + (a[hi] - a[lo]) * (k - lo)

def doy(d):
    return date(int(d[0:4]), int(d[5:7]), int(d[8:10])).timetuple().tm_yday

def anom_series(dates, vals):
    """31 天滑动季节气候态 -> 逐日异常。"""
    by = {}
    for d, v in zip(dates, vals):
        by.setdefault(doy(d), []).append(v)
    clim = {}
    for k in range(1, 367):
        buf = []
        for off in range(-15, 16):
            i = k + off
            if i < 1:
                i += 365
            if i > 366:
                i -= 366
            buf.extend(by.get(i, []))
        if buf:
            clim[k] = sum(buf) / len(buf)
    return [vals[i] - clim.get(doy(dates[i]), vals[i]) for i in range(len(vals))]

def site_metrics(path):
    M = json.load(io.open(path, encoding="utf-8"))
    ds = [d for d in M["days"] if d.get("sst_mean") is not None]
    dates = [d["date"] for d in ds]
    sst = [float(d["sst_mean"]) for d in ds]
    an = anom_series(dates, sst)
    N = len(ds)
    W = 84
    roll = [sum(max(0.0, an[k]) for k in range(max(0, i - W + 1), i + 1)) for i in range(N)]
    cur = round(roll[-1], 3)
    pctl = round(100.0 * sum(1 for v in roll if v <= roll[-1]) / N, 1)
    # 该站自己的热浪事件（>= 5 天）
    thr = pct(an, 0.90)
    evs = []
    i = 0
    while i < N:
        if an[i] > thr:
            j = i
            while j + 1 < N and an[j + 1] > thr:
                j += 1
            if j - i + 1 >= 5:
                run = list(range(i, j + 1))
                mx = max(an[k] for k in run)
                mult = (mx / thr) if thr > 0 else 0.0
                evs.append({"start": dates[run[0]], "end": dates[run[-1]], "days": len(run),
                            "max_anom": round(mx, 4), "cum_intensity": round(sum(an[k] for k in run), 4),
                            "peak_sst": round(max(sst[k] for k in run), 2),
                            "category": 1 if mult < 2 else (2 if mult < 3 else 3)})
            i = j + 1
        else:
            i += 1
    strongest = max(evs, key=lambda e: e["cum_intensity"]) if evs else None
    # 近 90 天多压力日：浪 / 雨 / 水位 各自越过该站 p90 中，至少两项同日
    wh = [float(d.get("wh_max") or 0.0) for d in ds]
    pr = [float(d.get("precipitation_sum") or 0.0) for d in ds]
    sl = [float(d.get("sl_mean") or 0.0) for d in ds]
    tw, tp, tl = pct(wh, 0.9), pct(pr, 0.9), pct(sl, 0.9)
    multi = 0
    for k in range(max(0, N - 90), N):
        if (1 if wh[k] > tw else 0) + (1 if pr[k] > tp else 0) + (1 if sl[k] > tl else 0) >= 2:
            multi += 1
    return {"site": M.get("site", os.path.basename(path)), "slug": M.get("slug", ""),
            "lat": M.get("lat"), "lon": M.get("lon"), "n_days": N, "last": dates[-1],
            "sst_p90": round(pct(sst, 0.9), 3), "anom_p90": round(thr, 4),
            "heat_cum_84d": cur, "heat_pctl": pctl, "mhw_events": len(evs),
            "mhw_days": sum(e["days"] for e in evs), "strongest": strongest, "multi_days_90d": multi,
            "window": [dates[max(0, N - W)], dates[-1]]}

D = json.load(io.open(DASH, encoding="utf-8"))
B = json.load(io.open(BLEA, encoding="utf-8"))
S = D["series"]
if isinstance(S, dict):
    sdates = list(S.get("date") or S.get("dates") or [])
    srisk = [float(v) for v in (S.get("risk") or [])]
else:
    sdates = [r["date"] for r in S]
    srisk = [float(r["risk"]) for r in S]
print("成品页序列：%d 天 %s 至 %s；风险 p90 = %.4f p95 = %.4f 最大 = %.4f" % (len(srisk), sdates[0], sdates[-1], pct(srisk, 0.9), pct(srisk, 0.95), max(srisk)))
RP90, RP95 = round(pct(srisk, 0.9), 4), round(pct(srisk, 0.95), 4)

fc = D["forecast"]
days = []
for r in fc:
    v = float(r.get("risk", r.get("value", r.get("v", 0.0))))
    h = float(r.get("half", 0.0))
    # 第 62 轮：上界一律取成品页那一个（dashboard 的 hi，三位小数、且夹在 0..1），
    # 不再自己重算 v + h。原来两边各算一次，同一张卡上「上界 0.301」与图里的 0.302
    # 会并排出现（差在第四位小数的取整）。verify_demo.py 现在逐日断言两者相等。
    up = round(float(r.get("hi", v + h)), 4)
    if up >= RP95 and RP95 > 0:
        tier, act = "高", "暂停不可逆施工与移栽，只做巡护记录"
    elif up >= RP90 and RP90 > 0:
        tier, act = "中", "可做低强度巡护，移栽前先复核当日海况"
    else:
        tier, act = "低", "优先安排保护施工与珊瑚移栽（可逆性最好的窗口）"
    days.append({"lead": r.get("lead"), "date": r["date"], "value": round(v, 4), "half": round(h, 4), "upper": up,
                 "tier": tier, "action": act})
for x in days:
    x["pctl"] = round(100.0 * sum(1 for v in srisk if v <= x["upper"]) / len(srisk), 1)
days_sorted = sorted(days, key=lambda x: x["upper"])
for i, x in enumerate(days_sorted):
    x["rank"] = i + 1
print("未来 %d 天干预窗口排序（按风险上界升序）：" % len(days))
for x in days_sorted:
    print("   第 %d 位 %s 上界 %.3f（点预报 %.3f + %.3f）%s" % (x["rank"], x["date"], x["upper"], x["value"], x["half"], x["tier"]))

sites = [site_metrics(os.path.join(MULTI, f)) for f in ["semporna_daily.json", "bunaken_daily.json", "palau_daily.json"]]
maxm = max([s["multi_days_90d"] for s in sites] + [1])
for s in sites:
    s["score"] = round(0.6 * s["heat_pctl"] / 100.0 + 0.4 * s["multi_days_90d"] / float(maxm), 4)
sites_sorted = sorted(sites, key=lambda s: -s["score"])
for i, s in enumerate(sites_sorted):
    s["rank"] = i + 1
print("三站点保护优先级（得分 = 0.6 x 近 84 天热暴露百分位 + 0.4 x 近 90 天多压力日相对值）：")
for s in sites_sorted:
    st = s["strongest"] or {}
    print("   第 %d 位 %s  热暴露 %.3f C 天（第 %.1f 百分位）多压力日 %d  热浪 %d 次 / %d 天  最强 %s 起 %s 天 %d 级  得分 %.4f" % (s["rank"], s["site"], s["heat_cum_84d"], s["heat_pctl"], s["multi_days_90d"], s["mhw_events"], s["mhw_days"], st.get("start", "-"), st.get("days", 0), st.get("category", 0), s["score"]))

le = B["now"]["last_event"]
if le:
    e0 = date(int(le["end"][0:4]), int(le["end"][5:7]), int(le["end"][8:10]))
    today = date(int(B["now"]["end"][0:4]), int(B["now"]["end"][5:7]), int(B["now"]["end"][8:10]))
    w4 = (e0 + timedelta(days=28)).isoformat()
    w8 = (e0 + timedelta(days=56)).isoformat()
    rec = {"event_end": le["end"], "event_days": le["days"], "category": le["category"],
           "cum_intensity": le["cum_intensity"], "peak_sst": le["peak_sst"],
           "today": today.isoformat(), "days_since": (today - e0).days,
           "w4": w4, "w8": w8, "inside": today <= (e0 + timedelta(days=56)),
           "action": "白化后 4 至 8 周是关键复测窗口：这段时间不做不可逆移栽，安排一次固定样线复测（覆盖率、颜色、藻类），把结果写入下一次判断"}
else:
    rec = {}
print("恢复窗口：最近一次热浪 %s（%d 天，%d 级）结束；今天距结束 %d 天；4 周 %s / 8 周 %s，窗口内 = %s" % (rec.get("event_end"), rec.get("event_days", 0), rec.get("category", 0), rec.get("days_since", 0), rec.get("w4"), rec.get("w8"), rec.get("inside")))

# 恢复期内不得安排不可逆移栽：施工窗口的动作必须与之相容，不能在同一天给出互斥指令
_no_transplant = bool(rec.get("inside")) and int(rec.get("days_since", 9999) or 9999) <= 28
if _no_transplant:
    for _x in days:
        if _x["tier"] == "低":
            _x["action"] = "优先安排可逆性作业（清污 / 巡护 / 固定样线复测）；不可逆移栽需等恢复期结束（%s 之后）" % rec.get("w4", "-")
        elif _x["tier"] == "中":
            _x["action"] = "只做低强度巡护与当日海况复核；不可逆移栽需等恢复期结束（%s 之后）" % rec.get("w4", "-")
bt = B["tier_rule"]
sop = [
 {"stage": "日常（低 / 中）", "trigger": "近 84 天累计热异常 < p75 = %.3f C 天" % bt["p75"], "action": "每周刷新一次数据；不额外投入现场人力", "timing": "每周"},
 {"stage": "关注（高）", "trigger": "p75 %.3f ≤ 累计热异常 < p90 %.3f" % (bt["p75"], bt["p90"]), "action": "加密到每周两次看数；做可逆措施的物料与人员准备", "timing": "每周两次"},
 {"stage": "触发（极高）", "trigger": "累计热异常 >= p90 = %.3f C 天" % bt["p90"], "action": "启动固定样线复测（覆盖率 / 颜色 / 藻类）；暂停不可逆移栽；通知保护区管理方", "timing": "48 小时内"},
 {"stage": "严重（2 级及以上热浪）", "trigger": "新出现 >= 2 级热浪事件，或风险上界越过 p95 = %.3f" % RP95, "action": "立即复测并上报；冻结移栽计划", "timing": "24 小时内"},
 {"stage": "恢复期 0–4 周", "trigger": "最近一次热浪结束后 0 至 28 天（复测起点 %s）" % rec.get("w4", "-"), "action": "禁止不可逆移栽；完成一次固定样线基线复测", "timing": str(rec.get("w4", "-"))},
 {"stage": "恢复期 4–8 周", "trigger": "热浪结束后 28 至 56 天（复测起点 %s）" % rec.get("w8", "-"), "action": "复测并评估恢复情况，决定是否重开保护工程", "timing": str(rec.get("w8", "-"))},
 {"stage": "施工窗口选择", "trigger": "未来 %d 天预报（风险上界最低的一天是 %s = %.3f）" % (len(days_sorted), days_sorted[0]["date"], days_sorted[0]["upper"]), "action": "把可逆性低的施工排在风险上界最低的日子；上界越过 p95 的日子暂停", "timing": days_sorted[0]["date"]},
]
# 「今天适用哪一档」由数据算出来，不写死：同一时刻可能有多档同时成立
# （例如热压力已到「极高」、同时未来窗口上界又越过 p95），此时按最严的一档执行。
cum_now = float(B["now"]["cum_anom"])
maxup = max(x["upper"] for x in days)
ev_cat = int(rec.get("category", 0) or 0)
ev_since = int(rec.get("days_since", 9999) or 9999)
recent_strong = (ev_cat >= 2) and (ev_since <= 28)
cond = [
    cum_now < bt["p75"],
    bt["p75"] <= cum_now < bt["p90"],
    cum_now >= bt["p90"],
    recent_strong or (RP95 > 0 and maxup > RP95),
    bool(rec.get("inside")) and ev_since <= 28,
    bool(rec.get("inside")) and 28 < ev_since <= 56,
    True,
]
# 理由句按实际比较结果生成（不写死），未触发的档位也要读得通
why = [
    "今天近 84 天累计热异常 %.3f C 天 %s p75 %.3f" % (cum_now, "低于" if cond[0] else "不低于", bt["p75"]),
    "今天累计热异常 %.3f C 天%s p75 %.3f 与 p90 %.3f" % (cum_now, "落在" if cond[1] else "不在", bt["p75"], bt["p90"]),
    "今天累计热异常 %.3f C 天 %s p90 %.3f" % (cum_now, "不低于" if cond[2] else "低于", bt["p90"]),
    ("最近一次热浪 %d 级、结束 %d 天（<= 28 天）" % (ev_cat, ev_since)) if recent_strong else
    ("未来 %d 天上界最高 %.3f %s p95 %.3f" % (len(days), maxup, "越过" if (RP95 > 0 and maxup > RP95) else "未越过", RP95)),
    "最近一次热浪结束 %d 天，%s 0–28 天复测窗口" % (ev_since, "落在" if cond[4] else "不在"),
    "最近一次热浪结束 %d 天，%s 28–56 天复测窗口" % (ev_since, "落在" if cond[5] else "不在"),
    "任何时候都适用（参考行，不单独触发动作）",
]
SEV = {"日常（低 / 中）": 0, "关注（高）": 1, "触发（极高）": 2, "严重（2 级及以上热浪）": 3}
for _i, _s in enumerate(sop):
    _s["active"] = bool(cond[_i])
    _s["active_reason"] = why[_i]
act = [s for s in sop if s["active"]]
_press = [s for s in act if s["stage"] in SEV]
today_stage = max(_press, key=lambda s: SEV[s["stage"]])["stage"] if _press else ""
print("触发—响应 SOP 共 %d 条；最早可施工日 %s（上界 %.3f）" % (len(sop), days_sorted[0]["date"], days_sorted[0]["upper"]))
print("今天适用 %d 条：%s；热压力最严的一档 = %s" % (len(act), "、".join(s["stage"] for s in act), today_stage))

OUTD = {"method": "见 formula 字段；风险上界 = 点预报 + 80% 经验半宽（interval_audit 标定）",
        "thresholds": {"risk_p90": RP90, "risk_p95": RP95},
        "windows": days_sorted,
        "sites": sites_sorted,
        "recovery": rec,
        "sop": sop,
        "today": {"stage": today_stage, "active": [s["stage"] for s in act],
                  "cum_anom": cum_now, "risk_now": float(D["now"].get("risk", 0.0)),
                  "max_upper": round(maxup, 4), "p75": bt["p75"], "p90": bt["p90"], "p95": RP95,
                  "note": "两条轴：危险指数（浪/雨/水位）与热压力（海温）分开；SOP 第一条判断看热压力轴"},
        "formula": {"window_score": "按风险上界升序排序；上界 = 点预报 + 该时效 80% 经验半宽",
                    "site_score": "0.6 x 近 84 天热暴露百分位 + 0.4 x 近 90 天多压力日 / 三站最大多压力日",
                    "note": "多压力日 = 浪 / 雨 / 水位 中至少两项同日越过该站自身 p90；跨站点为同一口径的简化代理指标，用于排序，不等同于仙本那成品页指数"}}
io.open(OUT, "w", encoding="utf-8", newline=chr(10)).write(json.dumps(OUTD, ensure_ascii=False, indent=1))
print("WROTE %s  %d bytes" % (OUT, os.path.getsize(OUT)))
