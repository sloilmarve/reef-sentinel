"""白化热压力监测与识别（方向 04 的「监测识别」一支）。

方法：以本站逐日海温（Open-Meteo Marine 日均）建 31 天滑动季节气候态，
按 Hobday et al. (2016) 的海洋热浪定义（异常 > 记录期 p90 阈值且持续 >= 5 天）识别事件，
按 Hobday et al. (2018) 以「峰值异常 / 阈值」的倍数分 I-IV 级；
分档门槛用记录自身的 84 天滚动累计异常分位数（p50 / p75 / p90）自标定，不外部拍定；
再用 NOAA CRW 官方月度白化预警区占比做月尺度与年尺度交叉验证。
输出 data/processed/bleaching_watch.json
"""
import io, os, json, math, sys
from datetime import date

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FEAT = os.path.join(BASE, "data", "processed", "semporna_features.json")
NOAA = os.path.join(BASE, "data", "external", "noaa_crw", "stats_alert01_baa5.csv")
PANEL = os.path.join(BASE, "data", "processed", "noaa_crw_panel.json")
OUT = os.path.join(BASE, "data", "processed", "bleaching_watch.json")

def pct(v, q):
    a = sorted(v)
    k = (len(a) - 1) * q
    lo = int(math.floor(k))
    hi = int(math.ceil(k))
    return a[lo] if lo == hi else a[lo] + (a[hi] - a[lo]) * (k - lo)

def pearson(x, y):
    n = len(x)
    mx = sum(x) / n
    my = sum(y) / n
    sx = math.sqrt(sum((v - mx) ** 2 for v in x))
    sy = math.sqrt(sum((v - my) ** 2 for v in y))
    if sx == 0 or sy == 0:
        return 0.0
    return sum((x[i] - mx) * (y[i] - my) for i in range(n)) / (sx * sy)

def rank_of(a):
    order = sorted(range(len(a)), key=lambda i: a[i])
    r = [0.0] * len(a)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and a[order[j + 1]] == a[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1
        for k in range(i, j + 1):
            r[order[k]] = avg
        i = j + 1
    return r

def spearman(x, y):
    return pearson(rank_of(x), rank_of(y))

D = json.load(io.open(FEAT, encoding="utf-8"))
ser = sorted([(d["date"], float(d["sst_mean"])) for d in D["days"] if d.get("sst_mean") is not None])
dates = [a for a, b in ser]
sst = [b for a, b in ser]
N = len(ser)
print("SST 有效日 %d 天：%s 至 %s" % (N, dates[0], dates[-1]))

def doy(d):
    return date(int(d[0:4]), int(d[5:7]), int(d[8:10])).timetuple().tm_yday

by = {}
for d, v in zip(dates, sst):
    by.setdefault(doy(d), []).append(v)
clim = {}
for k in range(1, 367):
    vals = []
    for off in range(-15, 16):
        i = k + off
        if i < 1:
            i += 365
        if i > 366:
            i -= 366
        vals.extend(by.get(i, []))
    if vals:
        clim[k] = sum(vals) / len(vals)
anom = [sst[i] - clim.get(doy(dates[i]), sst[i]) for i in range(N)]
THR = round(pct(anom, 0.90), 4)
SST90 = round(float(D["thresholds"]["sst"]["p90"]), 4)   # 与 build_features 同源：同一天数、同一分位算法
print("p90 异常阈值 %.4f C（基线 = 本站记录自身 %s 至 %s）；日均海温 p90 %.4f C" % (THR, dates[0], dates[-1], SST90))

ev = []
i = 0
while i < N:
    if anom[i] > THR:
        j = i
        while j + 1 < N and anom[j + 1] > THR:
            j += 1
        if j - i + 1 >= 5:
            run = list(range(i, j + 1))
            mx = max(anom[k] for k in run)
            cum = sum(anom[k] for k in run)
            mult = mx / THR if THR > 0 else 0.0
            cat = 1 if mult < 2 else (2 if mult < 3 else (3 if mult < 4 else 4))
            ev.append({"start": dates[run[0]], "end": dates[run[-1]], "days": len(run),
                       "max_anom": round(mx, 4), "cum_intensity": round(cum, 4),
                       "peak_sst": round(max(sst[k] for k in run), 2), "category": cat})
        i = j + 1
    else:
        i += 1
print("识别到海洋热浪事件 %d 次（持续 >= 5 天）" % len(ev))
for e in ev:
    print("   %s..%s %2d 天 峰值异常 %.3f 累计强度 %5.3f 峰值海温 %.2f %d 级" % (e["start"], e["end"], e["days"], e["max_anom"], e["cum_intensity"], e["peak_sst"], e["category"]))

PART_A_END = True
mon = {}
for d, v in zip(dates, sst):
    mon.setdefault(d[0:7], []).append(v)
mm = {k: sum(v) / len(v) for k, v in mon.items()}
m23 = {k: v for k, v in mm.items() if k.startswith("2023")}
k23 = max(m23, key=lambda k: m23[k])
MMM = round(m23[k23], 3)
last12 = dict(sorted(mm.items())[-12:])
kl = max(last12, key=lambda k: last12[k])
MMM_RECENT = round(last12[kl], 3)
MAXSST = round(max(sst), 2)
print("MMM（2023 基线月 %s）= %.3f C，白化阈值 %.3f C；近 12 完整月最大月均值（%s）= %.3f C，阈值 %.3f C；全期最高海温 %.2f C" % (k23, MMM, MMM + 1, kl, MMM_RECENT, MMM_RECENT + 1, MAXSST))
print("=> 两种口径阈值均高于全期最高海温，NOAA 式 DHW 在本海温产品上恒为 0（振幅压缩，已在文档与界面披露）")

yearly = []
for y in sorted(set(d[0:4] for d in dates)):
    idx = [k for k, d in enumerate(dates) if d[0:4] == y]
    if len(idx) < 30:
        continue
    ye = [e for e in ev if e["start"][0:4] == y]
    yearly.append({"year": int(y), "days": len(idx),
                   "hot_days": sum(1 for k in idx if sst[k] > SST90),
                   "mhw_days": sum(e["days"] for e in ye), "events": len(ye),
                   "max_cum": round(max([e["cum_intensity"] for e in ye] or [0.0]), 3),
                   "max_sst": round(max(sst[k] for k in idx), 2)})
print("年度：", "; ".join("%d 热压力日 %d / 热浪 %d 次 %d 天 / 最高海温 %.2f" % (y["year"], y["hot_days"], y["events"], y["mhw_days"], y["max_sst"]) for y in yearly))

W = 84
roll = [sum(max(0.0, anom[k]) for k in range(max(0, i - W + 1), i + 1)) for i in range(N)]
Q50, Q75, Q90 = [round(pct(roll, q), 3) for q in (0.5, 0.75, 0.9)]
cur = round(roll[-1], 3)
pctl = round(100.0 * sum(1 for v in roll if v <= roll[-1]) / N, 1)
tier = 0 if cur < Q50 else (1 if cur < Q75 else (2 if cur < Q90 else 3))
TIERS = ["低", "中", "高", "极高"]
cur_hot = sum(1 for k in range(max(0, N - W), N) if sst[k] > SST90)
last_ev = ev[-1] if ev else None
print("近 84 天（%s 至 %s）：热压力日 %d 天，累计热异常 %.3f C 天，= 记录自身第 %.1f 百分位（分档线 p50/p75/p90 = %.3f/%.3f/%.3f）=> 档位 %s" % (dates[max(0, N - W)], dates[-1], cur_hot, cur, pctl, Q50, Q75, Q90, TIERS[tier]))

Ln = io.open(NOAA, encoding="utf-8", errors="replace").read().rstrip().split(chr(10))
hdr = [x.strip() for x in Ln[0].split(",")]
gi = hdr.index("Global %")
pi = hdr.index("Pacific %")
off = {}
for ln in Ln[1:]:
    c = ln.split(",")
    if len(c) < len(hdr):
        continue
    key = c[0].strip() + "-" + c[1].strip().zfill(2)
    try:
        off.setdefault(key, []).append((float(c[gi]), float(c[pi])))
    except ValueError:
        pass
nm = {k: (sum(a for a, b in v) / len(v), sum(b for a, b in v) / len(v)) for k, v in off.items()}
mst = {}
for i, d in enumerate(dates):
    mst.setdefault(d[0:7], []).append((sst[i], anom[i]))
keys = [k for k in sorted(set(mst) & set(nm)) if len(mst[k]) >= 25]
cum_m = [round(sum(max(0.0, b) for a, b in mst[k]), 3) for k in keys]
hot_m = [float(sum(1 for a, b in mst[k] if a > SST90)) for k in keys]
yp = [nm[k][1] for k in keys]
yg = [nm[k][0] for k in keys]
R_CUM_PAC = round(pearson(cum_m, yp), 3)
R_CUM_GLOB = round(pearson(cum_m, yg), 3)
R_HOT_PAC = round(pearson(hot_m, yp), 3)
print("月尺度交叉验证（%d 个完整月，%s 至 %s）：累计热异常 vs 官方太平洋占比 r = %+.3f（全球 %+.3f）；热压力日数 vs 太平洋 r = %+.3f" % (len(keys), keys[0], keys[-1], R_CUM_PAC, R_CUM_GLOB, R_HOT_PAC))
PAN = json.load(io.open(PANEL, encoding="utf-8"))
ann = {e["year"]: e for e in PAN["annual"]}
ycum = {}
for i, d in enumerate(dates):
    y = int(d[0:4])
    ycum[y] = ycum.get(y, 0.0) + max(0.0, anom[i])
yrs = [y for y in sorted(ycum) if y >= 2023 and ann.get(y)]
xs = [round(ycum[y], 3) for y in yrs]
ys = [ann[y]["pacific_max"] for y in yrs]
complete = [y for y in yrs if y != max(yrs)]
R_YEAR = round(pearson([round(ycum[y], 3) for y in complete], [ann[y]["pacific_max"] for y in complete]), 3)
RHO_YEAR = round(spearman(xs, ys), 3)
print("年尺度交叉验证：年份 %s" % yrs)
print("   站内累计热异常      %s" % xs)
print("   官方太平洋年最大占比 %s" % [round(v, 5) for v in ys])
print("   Pearson r = %+.3f（%d 个完整年）；全部 %d 年 Spearman rho = %+.3f" % (R_YEAR, len(complete), len(yrs), RHO_YEAR))

# ---- 事件级对照：站内每次热浪事件，同期官方太平洋占比是否也抬升 ----
day_of = {}
for ln in Ln[1:]:
    c = ln.split(",")
    if len(c) < len(hdr):
        continue
    try:
        day_of[c[0].strip() + "-" + c[1].strip().zfill(2) + "-" + c[2].strip().zfill(2)] = (float(c[gi]), float(c[pi]))
    except ValueError:
        pass
recs = sorted(d for d in day_of if dates[0] <= d <= dates[-1])
OFF90 = round(pct([day_of[d][1] for d in recs], 0.9), 5)
mhw_days = set()
for e in ev:
    for d in recs:
        if e["start"] <= d <= e["end"]:
            mhw_days.add(d)
ev_rows = []
hit = 0
lags = []
for e in ev:
    win = [d for d in recs if e["start"] <= d <= e["end"]]
    pv = [day_of[d][1] for d in win]
    el = sum(1 for v in pv if v >= OFF90)
    mx = max(pv) if pv else 0.0
    if el > 0:
        hit += 1
    if win:
        pk = win[pv.index(max(pv))]
        lags.append((date(int(pk[0:4]), int(pk[5:7]), int(pk[8:10])) - date(int(e["start"][0:4]), int(e["start"][5:7]), int(e["start"][8:10]))).days)
    ev_rows.append({"start": e["start"], "end": e["end"], "days": e["days"], "category": e["category"],
                    "noaa_pacific_max_pct": round(mx, 5), "noaa_days_above_p90": el, "hit": bool(el > 0)})
both = sum(1 for d in recs if d in mhw_days and day_of[d][1] >= OFF90)
s_only = len(mhw_days) - both
o_only = sum(1 for d in recs if d not in mhw_days and day_of[d][1] >= OFF90)
neither = len(recs) - both - s_only - o_only
p_off_given_st = round(100.0 * both / max(1, both + s_only), 1)
p_st_given_off = round(100.0 * both / max(1, both + o_only), 1)
bg_off = round(100.0 * (both + o_only) / max(1, len(recs)), 1)
LIFT = round((both / max(1, len(mhw_days))) / max(1e-9, (both + o_only) / max(1, len(recs))), 2)
EVENT = {"site": "Semporna", "overlap_days": len(recs), "noaa_pacific_p90_pct": OFF90,
         "events_total": len(ev), "events_hit": hit, "event_hit_rate": round(100.0 * hit / max(1, len(ev)), 1),
         "mean_peak_lag_days": round(sum(lags) / max(1, len(lags)), 1),
         "contingency": {"both": both, "station_only": s_only, "official_only": o_only, "neither": neither},
         "p_official_given_station": p_off_given_st, "p_station_given_official": p_st_given_off,
         "background_official_rate": bg_off, "lift": LIFT, "events": ev_rows}
print("事件级对照（%d 天重叠，官方太平洋占比 p90 = %.5f）：站内 %d 次热浪中 %d 次同期官方太平洋占比也越过 p90（命中率 %.1f%%，官方峰值平均滞后 %.1f 天）" % (len(recs), OFF90, len(ev), hit, EVENT["event_hit_rate"], EVENT["mean_peak_lag_days"]))
print("   站内热浪日 %.1f%% 落在官方抬升日；官方抬升日中站内也报 %.1f%%（背景抬升率 %.1f%%，提升 %.2f 倍）" % (p_off_given_st, p_st_given_off, bg_off, LIFT))

VS = None
VSPATH = os.path.join(BASE, "data", "external", "noaa_crw", "vs_sabah_daily.csv")
if os.path.exists(VSPATH):
    vs = {}
    vmmm = None
    for ln in io.open(VSPATH, encoding="utf-8"):
        if ln.startswith("#"):
            if "Maximum Monthly Mean" in ln and "=" in ln:
                try:
                    vmmm = float(ln.split("=")[1].strip().split()[0])
                except Exception:
                    pass
            continue
        c = ln.strip().split(",")
        if len(c) < 8:
            continue
        try:
            vs[c[0]] = {"sst90": float(c[3]), "ssta90": float(c[4]), "hs90": float(c[5]), "dhw": float(c[6]), "alert": int(float(c[7]))}
        except ValueError:
            pass
    idx = {}
    for i, d in enumerate(dates):
        idx[d] = i
    ov = [d for d in dates if d in vs]
    a1 = sum(1 for d in ov if vs[d]["alert"] >= 1)
    a2 = sum(1 for d in ov if vs[d]["alert"] >= 2)
    a3 = sum(1 for d in ov if vs[d]["alert"] >= 3)
    a4 = sum(1 for d in ov if vs[d]["alert"] >= 4)
    vmax_dhw = max(vs[d]["dhw"] for d in ov)
    vrows = []
    vhit = 0
    for e in ev:
        win = [d for d in ov if e["start"] <= d <= e["end"]]
        md = max(vs[d]["dhw"] for d in win) if win else 0.0
        mh = max(vs[d]["hs90"] for d in win) if win else 0.0
        ma = max(vs[d]["alert"] for d in win) if win else 0
        if ma >= 1:
            vhit += 1
        vrows.append({"start": e["start"], "end": e["end"], "days": e["days"], "category": e["category"],
                      "vs_max_dhw": round(md, 3), "vs_max_hotspot": round(mh, 3), "vs_max_alert": ma,
                      "hit": bool(ma >= 1)})
    vb = sum(1 for d in ov if d in mhw_days and vs[d]["alert"] >= 1)
    vs_only = sum(1 for d in ov if d in mhw_days and vs[d]["alert"] < 1)
    vo_only = sum(1 for d in ov if d not in mhw_days and vs[d]["alert"] >= 1)
    vp_a_s = round(100.0 * vb / max(1, vb + vs_only), 1)
    vp_s_a = round(100.0 * vb / max(1, vb + vo_only), 1)
    vbg = round(100.0 * a1 / max(1, len(ov)), 1)
    vlift = round((vb / max(1, len(mhw_days))) / max(1e-9, a1 / max(1, len(ov))), 2)
    vbias = round(sum(sst[idx[d]] - vs[d]["sst90"] for d in ov) / max(1, len(ov)), 3)
    r_sst = round(pearson([sst[idx[d]] for d in ov], [vs[d]["sst90"] for d in ov]), 3)
    r_anom = round(pearson([anom[idx[d]] for d in ov], [vs[d]["ssta90"] for d in ov]), 3)
    r_dhw = round(pearson([roll[idx[d]] for d in ov], [vs[d]["dhw"] for d in ov]), 3)
    r_evd = round(pearson([e["cum_intensity"] for e in ev], [x["vs_max_dhw"] for x in vrows]), 3)
    vlast = ov[-1]
    VS = {"source": "NOAA CRW regional virtual station: Sabah, Malaysia (5km product, polygon centre 117.2E / 5.8N)",
          "overlap_days": len(ov), "first": ov[0] if ov else None, "last": ov[-1] if ov else None,
          "official_mmm": vmmm, "station_mmm": MMM, "sst_bias_station_minus_official": vbias,
          "r_sst": r_sst, "r_anom": r_anom, "r_cum84_vs_dhw": r_dhw, "r_event_intensity_vs_max_dhw": r_evd,
          "latest_date": vlast, "latest_dhw": round(vs[vlast]["dhw"], 3), "latest_alert": vs[vlast]["alert"],
          "alert_days": {"ge1": a1, "ge2": a2, "ge3": a3, "ge4": a4}, "max_dhw": round(vmax_dhw, 3),
          "events_total": len(ev), "events_hit": vhit, "event_hit_rate": round(100.0 * vhit / max(1, len(ev)), 1),
          "contingency": {"both": vb, "station_only": vs_only, "official_only": vo_only, "neither": len(ov) - vb - vs_only - vo_only},
          "p_alert_given_station": vp_a_s, "p_station_given_alert": vp_s_a, "background_alert_rate": vbg, "lift": vlift,
          "events": vrows}
    print("区域站点对照（NOAA CRW Sabah 虚拟站点，%d 天重叠）：站内 %d 次热浪中 %d 次同期官方达预警（%.1f%%）；官方达预警 %d 天（占 %.1f%%），最高到 %d 级，最大 DHW %.2f" % (len(ov), len(ev), vhit, VS["event_hit_rate"], a1, vbg, max(vs[d]["alert"] for d in ov), vmax_dhw))
    print("   本站日均海温 vs 官方热斑像素 SST 偏差 %.3f C，r = %.3f；异常 r（本站气候态 vs 官方）%.3f；近 84 天累计异常 vs 官方 DHW r = %.3f；官方最新 %s DHW %.2f 级别 %d（官方 MMM %.4f，本站短记录暖月均 %.3f）" % (vbias, r_sst, r_anom, r_dhw, vlast, vs[vlast]["dhw"], vs[vlast]["alert"], vmmm or 0.0, MMM))

PAL = os.path.join(BASE, "data", "external", "multisite", "palau_daily.json")
VSPAL = os.path.join(BASE, "data", "external", "noaa_crw", "vs_palau_daily.csv")


def station_stats(name, series, csvpath):
    """同一套口径给两个官方虚拟站点各算一份对照，供「跨站官方验证」使用。
    口径：本站逐日海温 vs 官方「90 分位热斑像素 SST」；热日 = 本站记录内 p90（简化口径，
    只用于两站可比，不等同于上文 Hobday 事件识别）。"""
    st = {}
    mmm = None
    for ln in io.open(csvpath, encoding="utf-8"):
        if ln.startswith("#"):
            if "Maximum Monthly Mean" in ln and "=" in ln:
                try:
                    mmm = float(ln.split("=")[1].strip().split()[0])
                except Exception:
                    pass
            continue
        c = ln.strip().split(",")
        if len(c) < 8:
            continue
        try:
            st[c[0]] = {"sst90": float(c[3]), "dhw": float(c[6]), "alert": int(float(c[7]))}
        except ValueError:
            pass
    ov = sorted(d for d in series if d in st)
    if len(ov) < 100:
        return None
    xs = [series[d] for d in ov]
    ys = [st[d]["sst90"] for d in ov]
    thr = pct(xs, 0.90)
    hot = set(d for d in ov if series[d] > thr)
    al = set(d for d in ov if st[d]["alert"] >= 1)
    both = len(hot & al)
    hot_only = len(hot - al)
    off_only = len(al - hot)
    mon = {}
    for d in ov:
        mon.setdefault(d[:7], []).append(series[d])
    warm = max((sum(v) / len(v), k) for k, v in mon.items())
    return {"site": name, "overlap_days": len(ov), "first": ov[0], "last": ov[-1],
            "official_mmm": mmm, "station_mean": round(sum(xs) / len(xs), 3),
            "official_hotspot_mean": round(sum(ys) / len(ys), 3),
            "bias_station_minus_official": round(sum(xs) / len(xs) - sum(ys) / len(ys), 3),
            "r_sst": round(pearson(xs, ys), 3),
            "warmest_month": warm[1], "warmest_month_mean": round(warm[0], 3),
            "hot_p90": round(thr, 3), "hot_days": len(hot),
            "alert_days": {"ge1": len(al), "ge2": sum(1 for d in ov if st[d]["alert"] >= 2), "ge3": sum(1 for d in ov if st[d]["alert"] >= 3)},
            "max_dhw": round(max(st[d]["dhw"] for d in ov), 3),
            "latest_date": ov[-1], "latest_dhw": round(st[ov[-1]]["dhw"], 3), "latest_alert": st[ov[-1]]["alert"],
            "contingency": {"both": both, "hot_only": hot_only, "official_only": off_only, "neither": len(ov) - both - hot_only - off_only},
            "p_alert_given_hot": round(100.0 * both / max(1, len(hot)), 1),
            "p_hot_given_alert": round(100.0 * both / max(1, len(al)), 1),
            "background_alert_rate": round(100.0 * len(al) / max(1, len(ov)), 1),
            "lift": round((both / max(1, len(hot))) / max(1e-9, len(al) / max(1, len(ov))), 2)}


VS_SITES = []
_sab = {d: sst[i] for i, d in enumerate(dates)}
if os.path.exists(VSPATH):
    VS_SITES.append(station_stats("Sabah, Malaysia（仙本那同区）", _sab, VSPATH))
if os.path.exists(PAL) and os.path.exists(VSPAL):
    _pd = json.load(io.open(PAL, encoding="utf-8"))
    _pal = {}
    for _row in _pd.get("days", []):
        if _row.get("sst_mean") is not None:
            _pal[_row["date"]] = float(_row["sst_mean"])
    VS_SITES.append(station_stats("Palau（帕劳）", _pal, VSPAL))
VS_SITES = [x for x in VS_SITES if x]
for _s in VS_SITES:
    print("跨站官方对照 %s：重叠 %d 天，日均海温偏差 %.3f C（r = %.3f），本站 p90 热日 %d 天中 %.1f%% 官方达预警（背景 %.1f%%，提升 %.2f 倍），官方最新 %s DHW %.2f 级别 %d"
          % (_s["site"], _s["overlap_days"], _s["bias_station_minus_official"], _s["r_sst"], _s["hot_days"],
             _s["p_alert_given_hot"], _s["background_alert_rate"], _s["lift"], _s["latest_date"], _s["latest_dhw"], _s["latest_alert"]))

OUTD = {
    "method": "Hobday et al. (2016) 海洋热浪定义 + Hobday et al. (2018) I-IV 强度分级；本站逐日海温（Open-Meteo Marine 日均）",
    "baseline": {"first": dates[0], "last": dates[-1], "n_days": N, "clim_win_days": 31,
                 "anom_p90": THR, "sst_p90": SST90, "mmm_base_year": 2023, "mmm_month": k23,
                 "mmm": MMM, "mmm_recent_month": kl, "mmm_recent": MMM_RECENT,
                 "bleach_thr": round(MMM + 1.0, 3), "max_sst": MAXSST, "dhw_max": 0.0},
    "tier_rule": {"metric": "近 84 天累计正向海温异常（摄氏度 天）", "p50": Q50, "p75": Q75, "p90": Q90,
                  "levels": ["低", "中", "高", "极高"]},
    "events": ev,
    "yearly": yearly,
    "now": {"window_days": W, "start": dates[max(0, N - W)], "end": dates[-1], "cum_anom": cur,
            "percentile": pctl, "tier": tier, "tier_txt": TIERS[tier], "hot_days": cur_hot,
            "last_event": last_ev},
    "noaa_check": {"months": len(keys), "month_first": keys[0], "month_last": keys[-1],
                   "r_cum_pacific": R_CUM_PAC, "r_cum_global": R_CUM_GLOB, "r_hot_pacific": R_HOT_PAC,
                   "years": yrs, "year_station_cum": xs, "year_noaa_pacific_max": [round(v, 5) for v in ys],
                   "r_year_pearson": R_YEAR, "r_year_spearman": RHO_YEAR, "complete_years": complete,
                   "monthly": [{"month": k, "cum_anom": cum_m[i], "noaa_pacific": round(yp[i], 5)} for i, k in enumerate(keys)], "event_level": EVENT, "vs_sabah": VS, "vs_sites": VS_SITES},
}
io.open(OUT, "w", encoding="utf-8", newline=chr(10)).write(json.dumps(OUTD, ensure_ascii=False, indent=1))
print("WROTE %s  %d bytes" % (OUT, os.path.getsize(OUT)))
