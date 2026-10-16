# -*- coding: utf-8 -*-
# fetch_noaa_crw.py - 抓取 NOAA CRW 官方 5km 产品的公开汇总数据与珊瑚大三角区域图。
# 说明：CRW 的 ERDDAP 取数通道在本环境会被 302 到无法连接的主机；但 coralreefwatch.noaa.gov
# 的关键词统计 CSV 与区域 PNG 可直接下载，本脚本走这条通路，作为官方对照数据。
import os, ssl, sys, urllib.request
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'data', 'external', 'noaa_crw')
os.makedirs(OUT, exist_ok=True)
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE
UA = {'User-Agent': 'Mozilla/5.0 (reef-sentinel; research)'}
CSV_BASE = 'https://coralreefwatch.noaa.gov/data_current/5km/v3.1_op/daily/csv/'
PNG_BASE = 'https://coralreefwatch.noaa.gov/data_current/5km/v3.1_op/daily/png/'
TARGETS = [
  (CSV_BASE + '5km-v3.1_stats-alert01_baa5_dailyupdate.csv', 'stats_alert01_baa5.csv'),
  (CSV_BASE + '5km-v3.1_stats-alert02_baa5_dailyupdate.csv', 'stats_alert02_baa5.csv'),
  (CSV_BASE + '5km-v3.1_stats-alert01_baa5-max-365d_dailyupdate.csv', 'stats_alert01_baa5_max365d.csv'),
  (PNG_BASE + 'ct5km_dhw_v3.1_triangle_current.png', 'triangle_dhw.png'),
  (PNG_BASE + 'ct5km_baa5-max-7d_v3.1_triangle_current.png', 'triangle_baa5_7dmax.png'),
  (PNG_BASE + 'ct5km_hs_v3.1_triangle_current.png', 'triangle_hotspot.png'),
]
for url, name in TARGETS:
    dst = os.path.join(OUT, name)
    try:
        r = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60, context=CTX)
        b = r.read()
        with open(dst, 'wb') as fh:
            fh.write(b)
        print('OK   ' + name.ljust(34) + str(len(b)).rjust(9) + ' bytes')
    except Exception as e:
        print('FAIL ' + name.ljust(34) + type(e).__name__ + ' ' + str(e)[:70])
print('')
print('## stats_alert01_baa5.csv head/tail')
f = os.path.join(OUT, 'stats_alert01_baa5.csv')
if os.path.exists(f):
    lines = open(f, 'r', encoding='utf-8', errors='replace').read().splitlines()
    print('  lines=' + str(len(lines)))
    print('  head: ' + lines[0][:150])
    print('  first: ' + lines[1][:150])
    print('  last: ' + lines[-1][:150])
    print('## annual Pacific % (max/mean) and Global % (max)')
    yr = {}
    for ln in lines[1:]:
        parts = [x.strip() for x in ln.split(',')]
        if len(parts) < 12 or not parts[0].isdigit():
            continue
        y = int(parts[0])
        try:
            g = float(parts[8]); pa = float(parts[9]); at = float(parts[10]); ind = float(parts[11])
        except ValueError:
            continue
        yr.setdefault(y, []).append((g, pa, at, ind))
    for y in sorted(yr):
        v = yr[y]
        gmax = max(x[0] for x in v); pmax = max(x[1] for x in v); imax = max(x[3] for x in v)
        pmean = sum(x[1] for x in v) / len(v)
        print('   ' + str(y) + ' days=' + str(len(v)) + ' global_max=' + str(gmax) + '% pacific_max=' + str(round(pmax, 2)) + '% indian_max=' + str(round(imax, 2)) + '% pacific_mean=' + str(round(pmean, 2)) + '%')