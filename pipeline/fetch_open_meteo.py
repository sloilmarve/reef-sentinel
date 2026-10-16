# -*- coding: utf-8 -*-
# fetch_open_meteo.py - 增量刷新 Open-Meteo 原始数据（纯标准库，直连，不依赖抓取工具）。
# 为什么需要：成品页是"生成时快照"，要让页面的"最后更新"走到今天，就必须能重新取数。
import csv, datetime, json, os, ssl, sys, time, urllib.request
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "raw")
MARINE_CSV = os.path.join(RAW, "semporna_marine_hourly.csv")
WEATHER_CSV = os.path.join(RAW, "semporna_weather_daily.csv")
LAT, LON = "4.6", "118.7"
MARINE_VARS = "sea_surface_temperature,wave_height,wave_period,wind_wave_height,sea_level_height_msl,ocean_current_velocity"
DAILY_VARS = "temperature_2m_max,temperature_2m_min,temperature_2m_mean,precipitation_sum,wind_speed_10m_max,wind_gusts_10m_max,wind_direction_10m_dominant,relative_humidity_2m_mean"
MARINE_HEADER = ["time_utc", "sea_level_height_msl", "wave_height", "wave_period", "wind_wave_height", "sea_surface_temperature", "ocean_current_velocity"]
WEATHER_HEADER = ["date", "temperature_2m_max", "temperature_2m_min", "temperature_2m_mean", "precipitation_sum", "wind_speed_10m_max", "wind_gusts_10m_max", "wind_direction_10m_dominant", "relative_humidity_2m_mean"]
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

def g(v):
    if v is None:
        return ""
    if isinstance(v, float):
        return ("%g" % v)
    return str(v)

def fetch(url, tries=4):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (reef-sentinel-refresh)"})
            with urllib.request.urlopen(req, timeout=60, context=CTX) as r:
                return json.loads(r.read().decode("utf-8", "replace"))
        except Exception as e:
            last = e
            time.sleep(2 + 3 * i)
    raise RuntimeError("fetch failed after %d tries: %s" % (tries, repr(last)[:160]))

def windows(start, end, days=60):
    cur = start
    while cur <= end:
        stop = min(end, cur + datetime.timedelta(days=days - 1))
        yield cur, stop
        cur = stop + datetime.timedelta(days=1)

def read_rows(path, key, ncol):
    rows = {}
    if not os.path.exists(path):
        return rows
    with open(path, newline="", encoding="utf-8") as fh:
        rd = csv.DictReader(fh, delimiter=";")
        for r in rd:
            if r.get(key):
                rows[r[key]] = r
    return rows

def write_rows(path, header, rows, key):
    tmp = path + ".tmp"
    with open(tmp, "w", newline="", encoding="utf-8") as fh:
        fh.write(";".join(header) + "\n")
        for k in sorted(rows.keys()):
            fh.write(";".join(g(rows[k].get(h, "")) for h in header) + "\n")
    os.replace(tmp, path)
    return len(rows)

today = datetime.date.today()
print("TODAY " + today.isoformat())

print("== 1) 海洋逐小时 ==")
marine = read_rows(MARINE_CSV, "time_utc", len(MARINE_HEADER))
old_last = max(marine.keys()) if marine else None
print("  existing rows %d, last %s" % (len(marine), old_last))
if old_last:
    start = datetime.date.fromisoformat(old_last[:10]) - datetime.timedelta(days=2)
else:
    start = datetime.date(2022, 11, 1)
added = 0
for a, b in windows(start, today):
    url = ("https://marine-api.open-meteo.com/v1/marine?latitude=" + LAT + "&longitude=" + LON
           + "&hourly=" + MARINE_VARS + "&start_date=" + a.isoformat() + "&end_date=" + b.isoformat() + "&timezone=UTC")
    d = fetch(url)
    h = d.get("hourly", {})
    times = h.get("time", [])
    for i, t in enumerate(times):
        row = {"time_utc": t}
        for v in MARINE_HEADER[1:]:
            col = h.get(v, [])
            row[v] = col[i] if i < len(col) else None
        if row.get("sea_surface_temperature") is None and row.get("wave_height") is None:
            continue
        marine[t] = row
        added += 1
    print("  %s .. %s -> %d points" % (a.isoformat(), b.isoformat(), len(times)))
n1 = write_rows(MARINE_CSV, MARINE_HEADER, marine, "time_utc")
print("  WROTE %s rows=%d" % (MARINE_CSV, n1))

print("== 2) 气象逐日 ==")
weather = read_rows(WEATHER_CSV, "date", len(WEATHER_HEADER))
old_last_d = max(weather.keys()) if weather else None
print("  existing rows %d, last %s" % (len(weather), old_last_d))
if old_last_d:
    start_d = datetime.date.fromisoformat(old_last_d) - datetime.timedelta(days=5)
else:
    start_d = datetime.date(2022, 11, 1)
for a, b in windows(start_d, today):
    url = ("https://archive-api.open-meteo.com/v1/archive?latitude=" + LAT + "&longitude=" + LON
           + "&daily=" + DAILY_VARS + "&start_date=" + a.isoformat() + "&end_date=" + b.isoformat() + "&timezone=UTC")
    d = fetch(url)
    dd = d.get("daily", {})
    times = dd.get("time", [])
    for i, t in enumerate(times):
        row = {"date": t}
        for v in WEATHER_HEADER[1:]:
            col = dd.get(v, [])
            row[v] = col[i] if i < len(col) else None
        weather[t] = row
    print("  archive %s .. %s -> %d days" % (a.isoformat(), b.isoformat(), len(times)))
print("  archive last %s" % (max(weather.keys()) if weather else "none"))
url = ("https://api.open-meteo.com/v1/forecast?latitude=" + LAT + "&longitude=" + LON
       + "&daily=" + DAILY_VARS + "&past_days=30&forecast_days=1&timezone=UTC")
d = fetch(url)
dd = d.get("daily", {})
times = dd.get("time", [])
filled = 0
for i, t in enumerate(times):
    if t in weather and all(weather[t].get(v) not in (None, "") for v in WEATHER_HEADER[1:]):
        continue
    row = weather.get(t, {"date": t})
    for v in WEATHER_HEADER[1:]:
        col = dd.get(v, [])
        if i < len(col) and col[i] is not None:
            row[v] = col[i]
    weather[t] = row
    filled += 1
print("  forecast API filled/updated %d days (last %s)" % (filled, max(weather.keys())))
n2 = write_rows(WEATHER_CSV, WEATHER_HEADER, weather, "date")
print("  WROTE %s rows=%d" % (WEATHER_CSV, n2))

print("")
print("SUMMARY marine_rows=%d last_hour=%s | weather_rows=%d last_day=%s" % (n1, max(marine.keys()), n2, max(weather.keys())))