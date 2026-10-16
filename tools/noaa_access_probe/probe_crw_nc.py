# -*- coding: utf-8 -*-
# probe_crw_nc.py - 找 NOAA CRW 官方 NetCDF 的确切文件名与可下载性；检查 Virtual Station 是否提供 CSV 时间序列。
import re, ssl, sys, urllib.request
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE
UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36', 'Accept': '*/*'}
def get(url, n=250000, rng=None):
    h = dict(UA)
    if rng:
        h['Range'] = rng
    r = urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=30, context=CTX)
    return r.status, r.headers, r.read(n)
print('## 1 STAR DIR PAGE (look for .nc filenames)')
for u in ['https://www.star.nesdis.noaa.gov/pub/socd/mecb/crw/data/5km/v3.1_op/nc/v1.0/daily/dhw/']:
    try:
        st, hd, b = get(u, 250000)
        t = b.decode('utf-8', 'replace')
        ncs = sorted(set(re.findall('(?i)([A-Za-z0-9_.-]+\\.nc)', t)))
        hrefs = sorted(set(re.findall('(?i)href=["' + chr(39) + ']([^"' + chr(39) + '>]+)', t)))
        print('  ' + u + ' -> ' + str(st) + ' bytes=' + str(len(b)) + ' nc_files=' + str(len(ncs)) + ' hrefs=' + str(len(hrefs)))
        for x in ncs[:10]:
            print('      NC ' + x)
        for x in hrefs[:15]:
            print('      H ' + x)
        print('      snippet: ' + t[600:1400].replace(chr(10), ' ')[:700])
    except Exception as e:
        print('  FAIL ' + type(e).__name__ + ' ' + str(e)[:120])
print('## 2 GUESS NC DOWNLOAD')
CANDS = [
  'https://www.star.nesdis.noaa.gov/pub/socd/mecb/crw/data/5km/v3.1_op/nc/v1.0/daily/dhw/ct5km_dhw_v3.1_20261014.nc',
  'https://www.star.nesdis.noaa.gov/pub/socd/mecb/crw/data/5km/v3.1_op/nc/v1.0/daily/dhw/2026/ct5km_dhw_v3.1_20261014.nc',
  'https://coralreefwatch.noaa.gov/data_current/5km/v3.1_op/daily/nc/ct5km_dhw_v3.1_20261014.nc',
  'https://coralreefwatch.noaa.gov/data_current/5km/v3.1_op/daily/csv/5km-v3.1_stats-alert01_baa5_dailyupdate.csv',
]
for u in CANDS:
    try:
        st, hd, b = get(u, 200, 'bytes=0-199')
        print('  OK ' + str(st) + ' len=' + str(hd.get('Content-Length')) + ' ' + u)
    except Exception as e:
        print('  FAIL ' + type(e).__name__ + ' ' + str(e)[:90] + ' ' + u)
print('## 3 VS page: csv / data links')
try:
    st, hd, b = get('https://coralreefwatch.noaa.gov/product/vs/data.php', 300000)
    t = b.decode('utf-8', 'replace')
    for pat in ['.csv', 'ts_data', 'vs_ts', '.txt', 'nc/']:
        hits = sorted(set(re.findall('(?i)([^"' + chr(39) + ' >]*' + re.escape(pat) + '[^"' + chr(39) + ' >]*)', t)))
        print('  PAT ' + pat + ' -> ' + str(len(hits)))
        for h in hits[:8]:
            print('      ' + h)
    stations = sorted(set(re.findall('vs_ts_multiyr_([a-z_]+)\\.png', t)))
    print('  STATIONS ' + str(len(stations)) + ': ' + ', '.join(stations))
except Exception as e:
    print('  FAIL ' + str(e)[:120])