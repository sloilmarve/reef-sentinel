"""下载 NOAA CRW「区域虚拟站点」Sabah, Malaysia 的逐日海温/白化预警序列，裁剪到本站记录期写成 CSV。

上游（纯文本，不需要 NetCDF / HDF5）：https://coralreefwatch.noaa.gov/product/vs/data/sabah.txt
站点：Sabah, Malaysia（多边形中心 117.2E / 5.8N，覆盖沙巴；本站仙本那在沙巴东南岸，同属一个官方区域站点）
上游表头自带 Averaged Maximum Monthly Mean = 29.4999 C。
官方 10 个字段：YYYY MM DD SST_MIN SST_MAX SST@90th_HS SSTA@90th_HS 90th_HS DHW ALERT。
注意语义：SST@90th_HS 是「区域热点（90 分位热斑像素）」的 SST，不是区域平均；SSTA@90th_HS 是它的异常；
90th_HS 是那个像素的热斑值；DHW 是 90th_HS 在 12 周内的累积（官方用 90 分位像素而非平均，避免少数暖像素夸大等级）。
白化预警级别：0 无压力 / 1 Watch 观察 / 2 Warning 警告 / 3 Alert Level 1 / 4 Alert Level 2

输出 data/external/noaa_crw/vs_sabah_daily.csv（date,sst_min,sst_max,sst90hs,ssta90hs,hs90,dhw,alert）
只保留 2022-10-01 起，避免把 1.2 MB 全史（1985 至今）塞进提交包；需要时可重跑本脚本延伸。
用法：python tools/noaa_access_probe/fetch_vs_sabah.py [本地 sabah.txt 路径（离线时用）]
"""
import io, os, sys, urllib.request

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(ROOT, "data", "external", "noaa_crw", "vs_sabah_daily.csv")
URL = "https://coralreefwatch.noaa.gov/product/vs/data/sabah.txt"
KEEP_FROM = "2022-10-01"

def fetch():
    req = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
    with urllib.request.urlopen(req, timeout=90) as f:
        return f.read().decode("utf-8", "replace")

def main():
    if len(sys.argv) > 1:
        txt = io.open(sys.argv[1], encoding="utf-8", errors="replace").read()
        print("READ", sys.argv[1])
    else:
        txt = fetch()
        print("FETCHED", URL)
    mmm = ""
    for i, ln in enumerate(txt.splitlines()):
        if "Maximum Monthly Mean" in ln and i + 1 < len(txt.splitlines()):
            mmm = txt.splitlines()[i + 1].strip()
    rows = []
    for ln in txt.splitlines():
        a = ln.split()
        if len(a) >= 10 and len(a[0]) == 4 and a[0].isdigit() and a[1].isdigit() and a[2].isdigit():
            d = "%s-%s-%s" % (a[0], a[1].zfill(2), a[2].zfill(2))
            if d >= KEEP_FROM:
                rows.append([d] + a[3:10])
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with io.open(OUT, "w", encoding="utf-8", newline=chr(10)) as f:
        f.write("# NOAA CRW regional virtual station: Sabah, Malaysia (%s)" % URL + chr(10))
        f.write("# polygon centre 117.2E / 5.8N; Averaged Maximum Monthly Mean = %s C" % mmm + chr(10))
        f.write("# date,sst_min,sst_max,sst90hs,ssta90hs,hs90,dhw,alert  (alert 0 none / 1 watch / 2 warning / 3 alert1 / 4 alert2)" + chr(10))
        for r in rows:
            f.write(",".join(r) + chr(10))
    print("WROTE", OUT, len(rows), "rows", rows[0][0], "->", rows[-1][0], "| MMM", mmm)

if __name__ == "__main__":
    main()