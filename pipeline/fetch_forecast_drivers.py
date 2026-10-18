# -*- coding: utf-8 -*-
"""Fetch the next 14 days of forecast DRIVERS for Semporna from Open-Meteo.

Why this exists: the early-warning model is trained on the historical record and then
has to run forward, so the forward-looking driver values come from the Open-Meteo
forecast endpoints.  These are NWP forecasts (ICON/GFS mix), not reanalysis, so they
carry their own error - the page says so.

2026-10-16: the request now mirrors the archive fetch variable-for-variable
(pipeline/fetch_open_meteo.py MARINE_VARS / DAILY_VARS) and the rows carry the same
derived columns as the history (wh_max, wh_mean, sst_mean/max, sl_mean/max/min/range,
wp_mean, ww_mean, oc_mean, the daily weather variables).  Reason: the model uses the
current-day LEVELS of those variables as features, so training and inference must see
the same columns; otherwise the forecast row would silently fall back to the training
mean for most of the feature matrix.
"""
import json, os, ssl, sys, time, urllib.request
from collections import defaultdict

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(BASE, "data", "raw")
OUT = os.path.join(RAW, "semporna_forecast_drivers.json")
LAT, LON, DAYS = 4.6, 118.7, 14
HORIZON = 8            # 固定业务时效：页面、干预窗口与所有材料都写"未来 8 天"

MARINE_VARS = "sea_surface_temperature,wave_height,wave_period,wind_wave_height,sea_level_height_msl,ocean_current_velocity"
DAILY_VARS = "temperature_2m_max,temperature_2m_min,temperature_2m_mean,precipitation_sum,wind_speed_10m_max,wind_gusts_10m_max,wind_direction_10m_dominant,relative_humidity_2m_mean"

CTX = ssl.create_default_context(); CTX.check_hostname = False; CTX.verify_mode = ssl.CERT_NONE
UA = {"User-Agent": "Mozilla/5.0 (reef-sentinel research)"}

def get_json(url, tries=5):
    """取一个 Open-Meteo JSON。对方偶尔会返回 5xx（2026-10-16 真的撞到过一次
    HTTP 503 Service Unavailable，整条刷新链因此中断），所以这里做指数退避重试：
    5 次尝试、间隔 5/10/15/20 秒；全失败才抛错，且错误信息写清是哪一个端点。"""
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=60, context=CTX) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            last = e
            if i < tries - 1:
                wait = 5 * (i + 1)
                print("  [retry %d/%d] %s -> %s，%.0f 秒后重试"
                      % (i + 1, tries - 1, url.split("?")[0], e, wait))
                time.sleep(wait)
    raise RuntimeError("Open-Meteo 连续 %d 次取数失败（%s）：%s" % (tries, url.split("?")[0], last))

MARINE = ("https://marine-api.open-meteo.com/v1/marine?latitude=%s&longitude=%s"
          "&hourly=" + MARINE_VARS + "&timezone=UTC&forecast_days=%d") % (LAT, LON, DAYS)
WEATHER = ("https://api.open-meteo.com/v1/forecast?latitude=%s&longitude=%s"
           "&daily=" + DAILY_VARS + "&timezone=UTC&forecast_days=%d") % (LAT, LON, DAYS)

mar = get_json(MARINE); wx = get_json(WEATHER)
h = mar["hourly"]; times = h["time"]
byday = defaultdict(lambda: defaultdict(list))
def num(x):
    try: return float(x)
    except: return None
for i, t in enumerate(times):
    d = t[:10]
    for k in ("wave_height", "wave_period", "wind_wave_height", "sea_surface_temperature",
              "sea_level_height_msl", "ocean_current_velocity"):
        v = num(h[k][i])
        if v is not None: byday[d][k].append(v)

wd = {k: dict(zip(wx["daily"]["time"], wx["daily"][k])) for k in wx["daily"] if k != "time"}
rows = []
for d in sorted(byday):
    w = byday[d]
    def mean(k):
        v = w.get(k) or []
        return round(sum(v)/len(v), 4) if v else None
    def mx(k):
        v = w.get(k) or []
        return round(max(v), 4) if v else None
    def mn(k):
        v = w.get(k) or []
        return round(min(v), 4) if v else None
    sl = w.get("sea_level_height_msl") or []
    row = dict(date=d,
        wh_max=round(max(w.get("wave_height") or []), 3) if w.get("wave_height") else None,
        wh_mean=mean("wave_height"),
        sst_mean=mean("sea_surface_temperature"),
        sst_max=mx("sea_surface_temperature"),
        sl_mean=mean("sea_level_height_msl"),
        sl_max=mx("sea_level_height_msl"),
        sl_min=mn("sea_level_height_msl"),
        sl_range=(round(max(sl) - min(sl), 4) if sl else None),
        wp_mean=mean("wave_period"),
        ww_mean=mean("wind_wave_height"),
        oc_mean=mean("ocean_current_velocity"),
        precipitation_sum=(round(num(wd.get("precipitation_sum", {}).get(d)), 2) if num(wd.get("precipitation_sum", {}).get(d)) is not None else None))
    for k in ("temperature_2m_max", "temperature_2m_min", "temperature_2m_mean", "wind_speed_10m_max",
              "wind_gusts_10m_max", "wind_direction_10m_dominant", "relative_humidity_2m_mean"):
        row[k] = num(wd.get(k, {}).get(d))
    rows.append(row)

# 固定业务时效。海洋预报产品当日的可覆盖天数会在 8 到 9 天之间浮动（取决于刷新时刻），
# 早期版本直接把 API 返回的全部天数交给下游，于是同一天不同时刻跑出来的页面会变成 8 天或
# 9 天，材料里的"未来 8 天"随之对不上。这里统一：只保留最后一个历史日之后的前 HORIZON 天。
try:
    _feat_p = os.path.join(BASE, "data", "processed", "semporna_features.json")
    _last_hist = json.load(open(_feat_p, encoding="utf-8"))["days"][-1]["date"]
    _kept = [r for r in rows if r["date"] > _last_hist][:HORIZON]
    if len(_kept) < len([r for r in rows if r["date"] > _last_hist]):
        print("horizon pin: kept %d of %d days after %s" % (len(_kept), len([r for r in rows if r["date"] > _last_hist]), _last_hist))
    rows = _kept
except Exception as _e:
    print("horizon pin skipped:", _e)

payload = dict(source="Open-Meteo forecast API (marine + weather)",
               url_marine=MARINE, url_weather=WEATHER,
               fetched_for="Semporna 4.6N 118.7E", days=rows)
os.makedirs(RAW, exist_ok=True)
tmp = OUT + ".tmp"
with open(tmp, "w", encoding="utf-8", newline="\n") as f:
    json.dump(payload, f, ensure_ascii=False, indent=1)
os.replace(tmp, OUT)
print("fetched forecast driver days:", len(rows), rows[0]["date"], "->", rows[-1]["date"], "->", OUT)
for r in rows[:14]:
    print("  ", r["date"], "wh_max", r["wh_max"], "rain", r["precipitation_sum"], "sst", r["sst_mean"],
          "wind", r["wind_speed_10m_max"], "wp", r["wp_mean"], "oc", r["oc_mean"], "keys", len(r))