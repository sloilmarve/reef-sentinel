import json, ssl, urllib.request
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
def get(u):
    req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0 (reef-sentinel-probe)"})
    with urllib.request.urlopen(req, timeout=25, context=ctx) as r:
        return r.status, r.read().decode("utf-8", "replace")
u1 = "https://marine-api.open-meteo.com/v1/marine?latitude=4.6&longitude=118.7&hourly=sea_surface_temperature,wave_height&start_date=2026-10-13&end_date=2026-10-15&timezone=UTC"
u2 = "https://archive-api.open-meteo.com/v1/archive?latitude=4.6&longitude=118.7&daily=precipitation_sum,temperature_2m_mean&start_date=2026-10-10&end_date=2026-10-15&timezone=UTC"
u3 = "https://api.open-meteo.com/v1/forecast?latitude=4.6&longitude=118.7&daily=precipitation_sum,temperature_2m_mean&forecast_days=3&timezone=UTC"
for name, u in [("marine", u1), ("archive", u2), ("forecast", u3)]:
    try:
        s, b = get(u)
        d = json.loads(b)
        keys = sorted(d.keys())
        print(name, "OK", s, "bytes", len(b), "keys", ",".join(keys))
        if "daily" in d:
            print("   daily", json.dumps(d["daily"])[:300])
        if "hourly" in d:
            t = d["hourly"]["time"]
            print("   hourly points", len(t), "first", t[0], "last", t[-1])
    except Exception as e:
        print(name, "FAIL", repr(e)[:200])