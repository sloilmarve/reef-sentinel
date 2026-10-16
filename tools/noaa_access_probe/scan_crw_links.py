# -*- coding: utf-8 -*-
# scan_crw_links.py - 抓取 NOAA CRW 5km 产品页，抽取所有链接，寻找可下载的 NetCDF / GeoTIFF 数据地址。
import re, ssl, urllib.request

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE
UA = {'User-Agent': 'Mozilla/5.0 (reef-sentinel)'}

def get(url, n=400000):
    req = urllib.request.Request(url, headers=UA)
    return urllib.request.urlopen(req, timeout=20, context=CTX).read(n).decode('utf-8', 'replace')

for page in ['https://coralreefwatch.noaa.gov/product/5km/index.php',
             'https://coralreefwatch.noaa.gov/product/5km/v3.1/index.php',
             'https://coralreefwatch.noaa.gov/product/vs/index.php']:
    print('==== ' + page)
    try:
        h = get(page)
    except Exception as e:
        print('  FAIL ' + type(e).__name__ + ' ' + str(e)[:120])
        continue
    print('  bytes ' + str(len(h)))
    links = re.findall('(?i)href=["' + chr(39) + ']?([^"' + chr(39) + ' >]+)', h)
    seen = []
    for l in links:
        if l not in seen:
            seen.append(l)
    keep = [l for l in seen if ('.nc' in l.lower() or 'geotiff' in l.lower() or 'netcdf' in l.lower() or 'data' in l.lower() or 'daily' in l.lower())]
    for l in keep[:40]:
        print('   LINK ' + l)
    if not keep:
        for l in seen[:25]:
            print('   any  ' + l)