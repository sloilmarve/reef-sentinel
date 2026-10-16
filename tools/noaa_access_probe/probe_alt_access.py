# -*- coding: utf-8 -*-
# probe_alt_access.py - 找 NOAA CRW 的 GeoTIFF / THREDDS / OPeNDAP 通路，并检查 VS 页面是否有按经纬度取数的接口。
import re, ssl, sys, urllib.request
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE
UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0 Safari/537.36'}
def get(url, n=120000):
    r = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30, context=CTX)
    return r.status, r.headers, r.read(n)
print('## GEOTIFF / ALT DIRS')
for u in ['https://www.star.nesdis.noaa.gov/pub/socd/mecb/crw/data/5km/v3.1_op/',
          'https://www.star.nesdis.noaa.gov/pub/socd/mecb/crw/data/50km/',
          'https://www.star.nesdis.noaa.gov/pub/socd/mecb/crw/data/']:
    try:
        st, hd, b = get(u)
        t = b.decode('utf-8', 'replace')
        hrefs = [x for x in sorted(set(re.findall('(?i)href=["' + chr(39) + ']([^"' + chr(39) + '>]+)', t))) if not any(k in x.lower() for k in ['css', 'js', 'noaa.gov/', 'mailto', 'favicon', 'usa.gov'])]
        print('  ' + u + ' -> ' + str(st) + ' n=' + str(len(b)) + ' links=' + str(len(hrefs)))
        for x in hrefs[:22]:
            print('      ' + x)
    except Exception as e:
        pass
print('## THREDDS / OPENDAP')
for u in ['https://coastwatch.pfeg.noaa.gov/thredds/catalog/crw/catalog.html',
          'https://www.star.nesdis.noaa.gov/thredds/catalog.html',
          'https://pae-paha.pacioos.hawaii.edu/thredds/catalog.html',
          'https://upwell.pfeg.noaa.gov/thredds/catalog.html']:
    try:
        st, hd, b = get(u)
        print('  OK ' + str(st) + ' n=' + str(len(b)) + ' ' + u)
    except Exception as e:
        print('  FAIL ' + type(e).__name__ + ' ' + str(e)[:70] + ' ' + u)