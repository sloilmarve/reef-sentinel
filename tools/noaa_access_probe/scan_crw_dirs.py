# -*- coding: utf-8 -*-
# scan_crw_dirs.py - 探测 CRW 目录是否可枚举文件，并抓取 Virtual Station 数据入口。
import io, os, re, ssl, sys, urllib.request
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE
UA = {'User-Agent': 'Mozilla/5.0 (reef-sentinel)'}
def get(url, n=300000):
    r = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=25, context=CTX)
    return r.status, r.read(n)
DIRS = [
  'https://coralreefwatch.noaa.gov/data_current/5km/v3.1_op/daily/',
  'https://coralreefwatch.noaa.gov/data_current/5km/v3.1_op/daily/nc/',
  'https://coralreefwatch.noaa.gov/data_current/5km/v3.1_op/daily/geotiff/',
  'https://coralreefwatch.noaa.gov/data_current/5km/v3.1_op/daily/csv/',
  'https://coralreefwatch.noaa.gov/data_current/5km/v3.1_op/daily/png/',
  'https://coralreefwatch.noaa.gov/product/vs/',
]
print('## DIR SCAN')
for d in DIRS:
    try:
        st, b = get(d)
        t = b.decode('utf-8', 'replace')
        files = sorted(set(re.findall('(?i)href=["' + chr(39) + ']([^"' + chr(39) + '>]+)', t)))
        dat = [f for f in files if (f.lower().endswith('.nc') or f.lower().endswith('.csv') or f.lower().endswith('.png') or f.lower().endswith('.tif') or f.lower().endswith('.tiff'))]
        auto = 'Index of' in t or len(dat) > 2
        print('  ' + d + ' -> ' + str(st) + ' bytes=' + str(len(b)) + ' autoindex=' + str(auto) + ' files=' + str(len(dat)))
        for f in dat[:12]:
            print('      F ' + f)
        if not dat:
            print('      head: ' + t[:200].replace(chr(10), ' '))
    except Exception as e:
        print('  ' + d + ' -> FAIL ' + type(e).__name__ + ' ' + str(e)[:100])
print('## VS PAGE')
for u in ['https://coralreefwatch.noaa.gov/product/vs/data.php', 'https://coralreefwatch.noaa.gov/product/vs/index.php']:
    try:
        st, b = get(u)
        t = b.decode('utf-8', 'replace')
        hrefs = sorted(set(re.findall('(?i)href=["' + chr(39) + ']?([^"' + chr(39) + ' >]+)', t)))
        print('  ' + u + ' -> ' + str(st) + ' bytes=' + str(len(b)) + ' links=' + str(len(hrefs)))
        for h in hrefs[:35]:
            print('      L ' + h)
    except Exception as e:
        print('  ' + u + ' -> FAIL ' + str(e)[:100])