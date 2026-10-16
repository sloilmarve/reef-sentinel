# -*- coding: utf-8 -*-
# probe_thredds.py - 探索 STAR THREDDS 目录，寻找可用于取单点时间序列的 CRW 数据集。
import re, ssl, sys, urllib.request
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE
UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0 Safari/537.36'}
def get(url, n=300000):
    r = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30, context=CTX)
    return r.status, r.headers, r.read(n)
def cat(url):
    st, hd, b = get(url)
    t = b.decode('utf-8', 'replace')
    items = re.findall('(?is)<a[^>]+href=["' + chr(39) + ']([^"' + chr(39) + ']+)["' + chr(39) + '][^>]*>(.*?)</a>', t)
    return st, len(b), items
for u in ['https://www.star.nesdis.noaa.gov/thredds/catalog.html',
          'https://www.star.nesdis.noaa.gov/thredds/catalog/catalog.xml']:
    print('==== ' + u)
    try:
        st, n, items = cat(u)
        print('  ' + str(st) + ' n=' + str(n) + ' items=' + str(len(items)))
        for h, txt in items[:35]:
            lab = re.sub('<[^>]+>', '', txt).strip()[:60]
            print('    ' + h[:90] + '  ||  ' + lab)
    except Exception as e:
        print('  FAIL ' + type(e).__name__ + ' ' + str(e)[:100])
print('==== CRW DATA DIRS')
for u in ['https://www.star.nesdis.noaa.gov/pub/socd/mecb/crw/data/thermal_history/',
          'https://www.star.nesdis.noaa.gov/pub/socd/mecb/crw/data/heritage_50km/',
          'https://www.star.nesdis.noaa.gov/pub/socd/mecb/crw/data/insitu/']:
    try:
        st, n, items = cat(u)
        print('  ' + u + ' -> ' + str(st) + ' links=' + str(len(items)))
        for h, txt in items[:18]:
            print('      ' + h[:80])
    except Exception as e:
        print('  FAIL ' + str(e)[:80] + ' ' + u)