# -*- coding: utf-8 -*-
# probe_crw_files.py - 探测 NOAA STAR/NESDIS 官方 NetCDF 与 CRW 站点 PNG/CSV 是否可下载及大小。
import concurrent.futures, ssl, urllib.request
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE
UA = {'User-Agent': 'Mozilla/5.0 (reef-sentinel)'}
URLS = [
  ('star-dhw-dir', 'https://www.star.nesdis.noaa.gov/pub/socd/mecb/crw/data/5km/v3.1_op/nc/v1.0/daily/dhw/'),
  ('star-baa-dir', 'http://www.star.nesdis.noaa.gov/pub/socd/mecb/crw/data/5km/v3.1_op/nc/v1.0/daily/baa5-max-7d/'),
  ('star-clim-dir', 'https://www.star.nesdis.noaa.gov/pub/sod/mecb/crw/data/5km/v3.1_op/climatology/nc/'),
  ('crw-csv-baa', 'https://coralreefwatch.noaa.gov/data_current/5km/v3.1_op/daily/csv/5km-v3.1_stats-alert01_baa5_dailyupdate.csv'),
  ('crw-png-dhw-tri', 'https://coralreefwatch.noaa.gov/data_current/5km/v3.1_op/daily/png/ct5km_dhw_v3.1_triangle_current.png'),
  ('crw-png-baa-tri', 'https://coralreefwatch.noaa.gov/data_current/5km/v3.1_op/daily/png/ct5km_baa5-max-7d_v3.1_triangle_current.png'),
  ('crw-png-sst-tri', 'https://coralreefwatch.noaa.gov/data_current/5km/v3.1_op/daily/png/coraltemp_v3.1_triangle_current.png'),
]
def one(item):
    name, url = item
    try:
        r = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=20, context=CTX)
        b = r.read(600)
        size = r.headers.get('Content-Length')
        txt = b[:160].decode('utf-8', 'replace').replace(chr(10), ' ')
        return (name, 'OK ' + str(r.status) + ' len=' + str(size) + ' | ' + txt[:150])
    except Exception as e:
        return (name, 'FAIL ' + type(e).__name__ + ' ' + str(e)[:110])
with concurrent.futures.ThreadPoolExecutor(max_workers=7) as ex:
    for n, m in ex.map(one, URLS):
        print(n.ljust(16) + m)