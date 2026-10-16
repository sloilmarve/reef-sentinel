# -*- coding: utf-8 -*-
"""Fetch the SAME daily drivers for three reef sites (transferability check).

The single-site criticism is fair: one location proves nothing about transferability.
This script pulls identical variables for the study site and two other Indo-Pacific
reef sites with one code path, so pipeline/multisite_check.py can rerun the whole
feature + ridge-regression stack at each site and compare skill.
Only daily aggregates are stored (the analysis does not need hourly rows).

Like pipeline/fetch_open_meteo.py it is incremental: existing rows are kept and only
the tail is refetched (60-day windows, 5/10/15 s backoff on 5xx / timeouts), then the
file is replaced atomically.  A site that cannot be reached keeps its previous file
and prints WARN instead of breaking the refresh chain; only a site with no data at
all makes the script exit non-zero.
"""
import datetime, json, os, ssl, sys, time, urllib.request
from collections import defaultdict

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(BASE, "data", "external", "multisite")
START = "2022-11-01"
SITES = [("semporna", "Semporna, Sabah, Malaysia", 4.60, 118.70),
         ("bunaken",  "Bunaken, North Sulawesi, Indonesia", 1.62, 125.20),
         ("palau",    "Palau Rock Islands", 7.30, 134.50)]

CTX = ssl.create_default_context(); CTX.check_hostname = False; CTX.verify_mode = ssl.CERT_NONE
UA = {"User-Agent": "Mozilla/5.0 (reef-sentinel research)"}
TODAY = datetime.date.today()


def get(url, tries=4):
    last = None
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120, context=CTX) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            last = e
            if i < tries - 1:
                print("  [retry %d/%d] %s -> %s" % (i + 1, tries - 1, url.split("?")[0], repr(last)[:110]))
                time.sleep(5 + 5 * i)
    raise RuntimeError("fetch failed after %d tries: %s" % (tries, repr(last)[:160]))


def num(x):
    try:
        return float(x)
    except Exception:
        return None


def windows(a, b, days=60):
    cur = a
    while cur <= b:
        stop = min(b, cur + datetime.timedelta(days=days - 1))
        yield cur, stop
        cur = stop + datetime.timedelta(days=1)


def load_raw(path):
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def write_payload(path, payload):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, path)


print("TODAY " + TODAY.isoformat())
os.makedirs(OUT, exist_ok=True)
no_data = []
for slug, name, lat, lon in SITES:
    p = os.path.join(OUT, slug + "_daily.json")
    old = load_raw(p)
    rows = {d["date"]: d for d in old.get("days", []) if d.get("date")}
    old_n = len(rows)
    old_last = max(rows) if rows else None
    old_urls = [old.get("url_marine", ""), old.get("url_archive", "")]
    start = datetime.date.fromisoformat(old_last) - datetime.timedelta(days=2) if old_last else datetime.date.fromisoformat(START)
    print("== %s ==  existing %d days, last %s" % (slug, old_n, old_last))
    urls = ["", ""]
    try:
        for a, b in windows(start, TODAY):
            MARINE = ("https://marine-api.open-meteo.com/v1/marine?latitude=%s&longitude=%s"
                      "&hourly=wave_height,sea_surface_temperature,sea_level_height_msl"
                      "&start_date=%s&end_date=%s&timezone=UTC") % (lat, lon, a.isoformat(), b.isoformat())
            WX = ("https://archive-api.open-meteo.com/v1/archive?latitude=%s&longitude=%s"
                  "&daily=precipitation_sum&start_date=%s&end_date=%s&timezone=UTC") % (lat, lon, a.isoformat(), b.isoformat())
            urls = [MARINE, WX]
            m = get(MARINE); w = get(WX)
            h = m["hourly"]
            agg = defaultdict(lambda: defaultdict(list))
            for i, t in enumerate(h["time"]):
                d = t[:10]
                for k in ("wave_height", "sea_surface_temperature", "sea_level_height_msl"):
                    v = num(h[k][i])
                    if v is not None:
                        agg[d][k].append(v)
            rain = dict(zip(w["daily"]["time"], w["daily"]["precipitation_sum"]))
            for d in sorted(agg):
                aa = agg[d]
                wave = aa.get("wave_height") or []
                sst = aa.get("sea_surface_temperature") or []
                sl = aa.get("sea_level_height_msl") or []
                r = num(rain.get(d))
                if not (wave and sst and sl and r is not None):
                    continue
                rows[d] = dict(date=d, wh_max=round(max(wave), 3),
                               sst_mean=round(sum(sst) / len(sst), 4),
                               sl_mean=round(sum(sl) / len(sl), 4),
                               precipitation_sum=round(r, 2))
            print("  %s .. %s -> %d points" % (a.isoformat(), b.isoformat(), len(h["time"])))
    except Exception as e:
        if not rows:
            print("  FATAL %s: %s" % (slug, repr(e)[:160]))
            no_data.append(slug)
            continue
        print("  WARN %s 取数失败（%s），沿用上一次的 %d 天" % (slug, repr(e)[:120], old_n))
    ds = sorted(rows)
    payload = dict(site=name, slug=slug, lat=lat, lon=lon, span=[START, ds[-1]],
                   source="Open-Meteo marine + archive API (daily aggregates of hourly values)",
                   url_marine=(urls[0] or old_urls[0]), url_archive=(urls[1] or old_urls[1]),
                   days=[rows[d] for d in ds])
    write_payload(p, payload)
    print("  WROTE %s days=%d (%d -> %d)  %s .. %s  %d bytes" % (p, len(ds), old_n, len(ds), ds[0], ds[-1], os.path.getsize(p)))

if no_data:
    print("FAILED sites with no data at all: " + ", ".join(no_data))
    sys.exit(1)
print("MULTISITE OK")
