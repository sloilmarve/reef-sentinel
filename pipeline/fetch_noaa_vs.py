# -*- coding: utf-8 -*-
"""抓 NOAA CRW 区域虚拟站点的逐日序列，裁剪后写入本地 CSV（当前两个站点：Sabah / Palau）。

上游是纯文本、不需要 NetCDF / HDF5：https://coralreefwatch.noaa.gov/product/vs/data/<slug>.txt
  * sabah.txt 站点多边形中心 117.2E / 5.8N（覆盖沙巴；本站仙本那在沙巴东南岸，同属一个官方区域站点）
  * palau.txt 站点对应帕劳（本项目的第二个对照站，用来验证「换一个官方站点、结论是否还成立」）
  * 布纳肯（Bunaken）在官方虚拟站点列表里没有对应文件（404），故跨站官方对照只有两个站
上游表头自带 Averaged Maximum Monthly Mean（C），会原样抄进文件头供下游读取。
官方 10 个字段：YYYY MM DD SST_MIN SST_MAX SST@90th_HS SSTA@90th_HS 90th_HS DHW ALERT。
语义提醒：SST@90th_HS 是「90 分位热斑像素」的 SST（不是区域平均），DHW 是那个像素 12 周的累积。
预警级别：0 无压力 / 1 Watch / 2 Warning / 3 Alert Level 1 / 4 Alert Level 2。

本模块在每日刷新链里跑（refresh.py 的 STEPS），让官方逐日对照跟着项目数据窗口一起前进：
  * 抓取失败（连续 4 次）时**不报错退出**，保留上一次的文件并打印 WARN，避免外部站点抖动打断整条链；
  * 抓到的行数异常少（< 1000）时同样保留旧文件，防止上游改版把对照写坏；
  * 只保留 2022-10-01 起到本项目数据窗口末日的部分（1.2 MB 全史不进提交包）；
  * 先写 .tmp 再 os.replace，避免半截文件被下游读到。

用法： python pipeline/fetch_noaa_vs.py
"""
import io, json, os, ssl, sys, time, urllib.request

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DASH = os.path.join(ROOT, "data", "processed", "dashboard_data.json")
KEEP_FROM = "2022-10-01"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
STATIONS = [("sabah", "Sabah, Malaysia"), ("palau", "Palau")]


def out_path(slug):
    return os.path.join(ROOT, "data", "external", "noaa_crw", "vs_%s_daily.csv" % slug)


def url_of(slug):
    return "https://coralreefwatch.noaa.gov/product/vs/data/%s.txt" % slug


def fetch(url, tries=4):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=90, context=ssl.create_default_context()) as f:
                return f.read().decode("utf-8", "replace")
        except Exception as e:
            last = e
            if i < tries - 1:
                wait = 5 * (i + 1)
                print("  [retry %d/%d] %s -> %s，%d 秒后重试" % (i + 1, tries - 1, url.split("/")[-1], e, wait))
                time.sleep(wait)
    raise RuntimeError("NOAA 虚拟站点连续 %d 次取数失败（%s）：%s" % (tries, url, last))


def parse(txt):
    lines = txt.splitlines()
    mmm = ""
    for i, ln in enumerate(lines):
        if "Maximum Monthly Mean" in ln and i + 1 < len(lines):
            mmm = lines[i + 1].strip()
    rows = []
    for ln in lines:
        a = ln.split()
        if len(a) >= 10 and len(a[0]) == 4 and a[0].isdigit() and a[1].isdigit() and a[2].isdigit():
            rows.append(["%s-%s-%s" % (a[0], a[1].zfill(2), a[2].zfill(2))] + a[3:10])
    return mmm, rows


def read_existing(path):
    if not os.path.exists(path):
        return []
    out = []
    for ln in io.open(path, encoding="utf-8"):
        if ln.startswith("#") or not ln.strip():
            continue
        c = ln.strip().split(",")
        if len(c) >= 8:
            out.append(c)
    return out


def window_end():
    try:
        with io.open(DASH, encoding="utf-8") as fh:
            return json.load(fh)["span"]["end"]
    except Exception:
        return None


def write(path, url, title, mmm, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with io.open(tmp, "w", encoding="utf-8", newline=chr(10)) as f:
        f.write("# NOAA CRW regional virtual station: %s (%s)" % (title, url) + chr(10))
        f.write("# Averaged Maximum Monthly Mean = %s C" % mmm + chr(10))
        f.write("# date,sst_min,sst_max,sst90hs,ssta90hs,hs90,dhw,alert  (alert 0 none / 1 watch / 2 warning / 3 alert1 / 4 alert2)" + chr(10))
        for r in rows:
            f.write(",".join(r) + chr(10))
    os.replace(tmp, path)


def run(slug, title, end):
    path = out_path(slug)
    url = url_of(slug)
    try:
        txt = fetch(url)
    except Exception as e:
        print("  WARN 官方虚拟站点 %s 取数失败（%s），保留上一次的 %s" % (title, e, os.path.relpath(path, ROOT)))
        print("  OK   NOAA virtual station %s kept as-is（外部站点抖动不打断刷新链）" % slug)
        return 0
    mmm, all_rows = parse(txt)
    if len(all_rows) < 1000:
        print("  WARN 站点 %s 解析到的行数异常（%d 行），保留上一次的文件" % (title, len(all_rows)))
        print("  OK   NOAA virtual station %s kept as-is" % slug)
        return 0
    rows = [r for r in all_rows if r[0] >= KEEP_FROM and (end is None or r[0] <= end)]
    old = read_existing(path)
    old_d = set(r[0] for r in old)
    new_d = set(r[0] for r in rows)
    added = sorted(new_d - old_d)
    dropped = sorted(old_d - new_d)
    write(path, url, title, mmm, rows)
    print("  OK   NOAA CRW 区域虚拟站点 %s：上游 %d 行（%s → %s），保留 %d 行（%s → %s）"
          % (title, len(all_rows), all_rows[0][0], all_rows[-1][0], len(rows), rows[0][0], rows[-1][0]))
    print("  官方 MMM = %s C；项目数据窗口末日 = %s" % (mmm, end or "(未知，未裁剪上界)"))
    if added:
        print("  新增 %d 天：%s" % (len(added), ", ".join(added)))
    if dropped:
        print("  移除 %d 天：%s" % (len(dropped), ", ".join(dropped)))
    if not added and not dropped:
        print("  与上一次逐日一致（上游还没有更新到更近的日期）")
    return 0


def main():
    end = window_end()
    rc = 0
    for slug, title in STATIONS:
        rc = max(rc, run(slug, title, end))
    return rc


if __name__ == "__main__":
    sys.exit(main())