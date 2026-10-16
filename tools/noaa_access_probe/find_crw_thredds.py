# -*- coding: utf-8 -*-
# find_crw_thredds.py - 在 STAR THREDDS 目录树中搜索 CRW/珊瑚相关数据集，并列出 image_plain / outlook 目录。
import re, ssl, sys, urllib.request
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE
UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0 Safari/537.36'}
def get(url, n=400000):
    r = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30, context=CTX)
    return r.read(n).decode('utf-8', 'replace')
TDS = 'https://www.star.nesdis.noaa.gov/thredds'
seen = set()
queue = [(TDS + '/catalog/socd/coastwatch/catalog.xml', 0), (TDS + '/catalog.xml', 0), (TDS + '/catalog/socd/catalog.xml', 0)]
hits = []
n = 0
while queue and n < 40:
    url, d = queue.pop(0)
    if url in seen or d > 3:
        continue
    seen.add(url)
    n += 1
    try:
        x = get(url)
    except Exception as e:
        continue
    for m in re.finditer('(?is)<catalogRef[^>]*href=["' + chr(39) + ']([^"' + chr(39) + ']+)["' + chr(39) + '][^>]*>(?:<datasetName>)?([^<]*)', x):
        href = m.group(1).replace('catalog.html', 'catalog.xml')
        name = m.group(2).strip()
        full = TDS + '/' + href if not href.startswith('http') else href
        low = (href + ' ' + name).lower()
        if any(k in low for k in ['crw', 'coral', 'dhw', 'baa', 'reef', 'heat']):
            hits.append((full, name))
        queue.append((full, d + 1))
    for m in re.finditer('(?is)<dataset[^>]*name=["' + chr(39) + ']([^"' + chr(39) + ']+)["' + chr(39) + ']', x):
        nm = m.group(1)
        if any(k in nm.lower() for k in ['crw', 'coral', 'dhw', 'baa', 'reef']):
            hits.append((url, nm))
print('visited ' + str(n) + ' catalogs; hits=' + str(len(hits)))
for h, nm in hits[:25]:
    print('  HIT ' + h + ' || ' + nm)
print('## IMAGE_PLAIN / OUTLOOK')
for u in ['https://www.star.nesdis.noaa.gov/pub/socd/mecb/crw/data/5km/v3.1_op/image_plain/',
          'https://www.star.nesdis.noaa.gov/pub/socd/mecb/crw/data/outlook/',
          'https://www.star.nesdis.noaa.gov/pub/socd/mecb/crw/data/marine_heatwave/']:
    try:
        t = get(u)
        hrefs = [h for h in sorted(set(re.findall('(?i)href=["' + chr(39) + ']([^"' + chr(39) + '>]+)', t))) if not any(k in h.lower() for k in ['css', 'favicon', 'mailto', 'noaa.gov/', 'doc.gov', 'usa.gov', '?c='])]
        print('  ' + u + ' links=' + str(len(hrefs)))
        for h in hrefs[:14]:
            print('      ' + h[:100])
    except Exception as e:
        print('  FAIL ' + str(e)[:70] + ' ' + u)