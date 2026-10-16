# NOAA CRW 官方数据的取数命令（在任意能上外网的机器上跑，结果放到 data/external/）
# 1) ERDDAP 单点时间序列（小、快、最好用）：Semporna 4.6N 118.7E
curl -sL "https://coastwatch.pfeg.noaa.gov/erddap/griddap/NOAA_DHW.csv?CRW_SST,CRW_SSTANOMALY,CRW_HOTSPOT,CRW_DHW,CRW_BAA%5B(1985-01-01):1:(2026-10-14)%5D%5B(4.6):1:(4.6)%5D%5B(118.7):1:(118.7)%5D" -o crw_point_semporna.csv

# 2) 珊瑚大三角区域逐日网格（NetCDF, 约 100MB）——做风险地图用
curl -sL "https://coralreefwatch.noaa.gov/product/5km/v3.1/nc/v1.0/daily/baa/2026/CT5KM-20261001_v3.1_baa.nc" -o CT5KM-20261001_v3.1_baa.nc

# 3) 如果上面 404，用 NOAA ERDDAP 的切片（只取珊瑚大三角 108-128E, 0-12N）
curl -sL "https://coastwatch.pfeg.noaa.gov/erddap/griddap/NOAA_DHW.nc?CRW_BAA%5B(2026-09-01):1:(2026-10-14)%5D%5B(0.0):1:(12.0)%5D%5B(108.0):1:(128.0)%5D" -o crw_baa_triangle.nc
