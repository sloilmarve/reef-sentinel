# -*- coding: utf-8 -*-
# scan_crw_data.py - 在 CRW 5km 页面与 data_resources 页面中查找 NetCDF / GeoTIFF / CSV 数据通路。
import re, ssl, urllib.request
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE
UA = {'User-Agent': 'Mozilla/5.0 (reef-sentinel)'}
def get(url, n=500000):
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=25, context=CTX).read(n).decode('utf-8', 'replace')
for page in ['https://coralreefwatch.noaa.gov/product/5km/index.php', 'https://coralreefwatch.noaa.gov/crtr/data_resources.php']:
    print('==== ' + page)
    try:
        h = get(page)
    except Exception as e:
        print('  FAIL ' + str(e)[:120])
        continue
    print('  bytes ' + str(len(h)))
    hits = set(re.findall('(?i)["' + chr(39) + '(]([^"' + chr(39) + ')>]*?(?:\\.nc|\\.nc4|\\.tif|\\.tiff|\\.csv|netcdf|/nc/)[^"' + chr(39) + ')>]*)', h))
    for x in sorted(hits)[:60]:
        print('   HIT ' + x)
    print('  total_hits ' + str(len(hits)))