# -*- coding: utf-8 -*-
# probe_crw_year.py - 列出 CRW 5km NetCDF 年份目录内容，实测文件大小与格式（CDF vs HDF5）。
import re, ssl, sys, urllib.request
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE
UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36'}
def get(url, n=250000, rng=None):
    h = dict(UA)
    if rng:
        h['Range'] = rng
    r = urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=40, context=CTX)
    return r.status, r.headers, r.read(n)
BASE = 'https://www.star.nesdis.noaa.gov/pub/socd/mecb/crw/data/5km/v3.1_op/nc/v1.0/daily/'
print('## LISTINGS')
for u in [BASE, BASE + 'dhw/2026/', BASE + 'baa5/2026/', BASE + 'sst/2026/']:
    try:
        st, hd, b = get(u)
        t = b.decode('utf-8', 'replace')
        hrefs = [x for x in sorted(set(re.findall('(?i)href=["' + chr(39) + ']([^"' + chr(39) + '>]+)', t))) if 'css' not in x and 'js' not in x]
        print('  ' + u + ' -> ' + str(st) + ' n=' + str(len(b)) + ' links=' + str(len(hrefs)))
        for x in hrefs[-14:]:
            print('      ' + x)
    except Exception as e:
        print('  ' + u + ' FAIL ' + type(e).__name__ + ' ' + str(e)[:90])
print('## FILE HEAD')
F = BASE + 'dhw/2026/ct5km_dhw_v3.1_20261014.nc'
for cand in [F, BASE + 'dhw/2026/ct5km_dhw_v3.1_20261001.nc']:
    try:
        st, hd, b = get(cand, 64, 'bytes=0-63')
        print('  ' + str(st) + ' total=' + str(hd.get('Content-Range')) + ' magic=' + repr(b[:16]))
        print('      url ' + cand)
        break
    except Exception as e:
        print('  FAIL ' + str(e)[:90] + ' ' + cand)
print('## VS TXT SAMPLE')
for u in ['https://coralreefwatch.noaa.gov/data/vs/data/florida_keys.txt', 'https://coralreefwatch.noaa.gov/data/vs/data/abrolhos_reefs.txt']:
    try:
        st, hd, b = get(u, 1200)
        print('  ' + str(st) + ' len=' + str(hd.get('Content-Length')) + ' ' + u)
        print('      ' + b.decode('utf-8', 'replace')[:600].replace(chr(10), ' | '))
    except Exception as e:
        print('  FAIL ' + str(e)[:90] + ' ' + u)