# -*- coding: utf-8 -*-
# probe_crw.py - 探测 NOAA Coral Reef Watch 各数据通路在本机 Python 下是否可达。
# 背景：pwsh/.NET 层 TLS 被拦，改用 Python（已验证可访问 example.com 与 Open-Meteo）。
import concurrent.futures, ssl, urllib.request, json

UA = {'User-Agent': 'Mozilla/5.0 (reef-sentinel probe)'}
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

V = '%5B(2026-10-01):1:(2026-10-02)%5D%5B(4.6):1:(4.6)%5D%5B(118.7):1:(118.7)%5D'
URLS = [
  ('control-openmeteo', 'https://api.open-meteo.com/v1/forecast?latitude=4.6&longitude=118.7&hourly=temperature_2m&forecast_days=1'),
  ('erddap-info', 'https://coastwatch.pfeg.noaa.gov/erddap/info/index.csv'),
  ('erddap-coastwatch-dhw', 'https://coastwatch.pfeg.noaa.gov/erddap/griddap/NOAA_DHW.csv?CRW_DHW' + V),
  ('erddap-pacioos-dhw', 'https://pae-paha.pacioos.hawaii.edu/erddap/griddap/NOAA_DHW.csv?CRW_DHW' + V),
  ('erddap-oceanwatch', 'https://oceanwatch.pifsc.noaa.gov/erddap/griddap/NOAA_DHW.csv?CRW_DHW' + V),
  ('erddap-upwell', 'https://upwell.pfeg.noaa.gov/erddap/griddap/NOAA_DHW.csv?CRW_DHW' + V),
  ('ncei-erddap', 'https://www.ncei.noaa.gov/erddap/griddap/NOAA_DHW.csv?CRW_DHW' + V),
  ('ncei-crw-dir', 'https://www.ncei.noaa.gov/data/oceans/coral-reef-watch/'),
  ('crw-5km-index', 'https://coralreefwatch.noaa.gov/product/5km/index.php'),
  ('crw-vs-list', 'https://coralreefwatch.noaa.gov/vs/gauges/index.php'),
]

def one(item):
    name, url = item
    try:
        req = urllib.request.Request(url, headers=UA)
        r = urllib.request.urlopen(req, timeout=12, context=CTX)
        body = r.read(400)
        return (name, 'OK ' + str(r.status) + ' ' + str(len(body)) + 'B | ' + body[:90].decode('utf-8', 'replace').replace(chr(10), ' '))
    except Exception as e:
        return (name, 'FAIL ' + type(e).__name__ + ': ' + str(e)[:110])

with concurrent.futures.ThreadPoolExecutor(max_workers=10) as ex:
    for name, msg in ex.map(one, URLS):
        print(name.ljust(24) + msg)