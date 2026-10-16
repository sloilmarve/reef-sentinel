# -*- coding: utf-8 -*-
# check_hdf5.py - 检查本机 Python 是否有 HDF5/NetCDF 读取能力，并复测 VS 文本路径。
import importlib, sys, ssl, urllib.request
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
print('## IMPORTS')
for m in ['h5py', 'netCDF4', 'xarray', 'h5netcdf', 'scipy', 'tables', 'numpy']:
    try:
        mod = importlib.import_module(m)
        print('  ' + m + ' OK ' + str(getattr(mod, '__version__', '?')))
    except Exception as e:
        print('  ' + m + ' MISS ' + type(e).__name__)
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE
UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0 Safari/537.36'}
def get(url, n=1500):
    r = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30, context=CTX)
    return r.status, r.headers, r.read(n)
print('## VS TXT')
for u in ['https://coralreefwatch.noaa.gov/product/vs/data/florida_keys.txt',
          'https://coralreefwatch.noaa.gov/product/vs/data/abrolhos_reefs.txt']:
    try:
        st, hd, b = get(u)
        print('  ' + str(st) + ' len=' + str(hd.get('Content-Length')) + ' ' + u)
        print('      ' + b.decode('utf-8', 'replace')[:500].replace(chr(10), ' | '))
    except Exception as e:
        print('  FAIL ' + str(e)[:80] + ' ' + u)
print('## NCEI FILE TEST')
for u in ['https://www.ncei.noaa.gov/data/oceans/coral-reef-watch/5km/v3.1_op/nc/v1.0/daily/dhw/2026/ct5km_dhw_v3.1_20261001.nc',
          'https://www.ncei.noaa.gov/data/oceans/coral-reef-watch/']:
    try:
        st, hd, b = get(u, 200)
        print('  ' + str(st) + ' len=' + str(hd.get('Content-Length')) + ' ' + u)
    except Exception as e:
        print('  FAIL ' + str(e)[:80] + ' ' + u)