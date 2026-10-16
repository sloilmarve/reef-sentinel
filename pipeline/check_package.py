# -*- coding: utf-8 -*-
# check_package.py - 交付前最后一道检查：提交包内容 + 本地预览服务是否真的在提供单页成品。
import os, sys, urllib.request, zipfile
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
ZIP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", "提交包", "ai4climate_reef_sentinel_submission.zip")
ZIP = os.path.abspath(ZIP)
z = zipfile.ZipFile(ZIP)
n = z.namelist()
print("ZIP " + ZIP)
print("SIZE %d bytes" % os.path.getsize(ZIP))
print("ENTRIES %d" % len(n))
demo = sorted([x for x in n if "/demo/" in x])
print("DEMO FILES")
for x in demo:
    print("  " + x.split("demo/")[-1] + "  " + str(z.getinfo(x).file_size))
print("HAS_DASHBOARD_INTERACTIVE " + str(any(x.endswith("dashboard.html") for x in n)))
print("HAS_TELEPROMPTER " + str(any("teleprompter" in x for x in n)))
noaa = [x for x in n if "noaa_crw" in x]
print("NOAA FILES %d" % len(noaa))
for x in sorted(noaa):
    print("  " + x.split("/")[-1] + "  " + str(z.getinfo(x).file_size))
print("MATERIALS " + str(sorted([x.split("/")[-1] for x in n if "/docs/" in x])))
print("WORD " + str(sorted([x.split("/")[-1] for x in n if "/docs_word/" in x])))
print("PIPELINE %d scripts" % len([x for x in n if "/pipeline/" in x and x.endswith(".py")]))
try:
    r = urllib.request.urlopen("http://127.0.0.1:8788/", timeout=25)
    b = r.read()
    h = b.decode("utf-8", "replace")
    print("HTTP %d  %d bytes" % (r.status, len(b)))
    print("HAS_OFFICIAL_PANEL " + str("官方对照" in h))
    print("HAS_PNG_DATAURI " + str("data:image/png;base64," in h))
    print("SCRIPT_TAGS %d" % h.lower().count("<script"))
    index = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "demo", "index.html")
    local = open(index, "rb").read()
    print("SERVED_BYTES_MATCH_LOCAL_FILE " + str(len(b) == len(local)))
except Exception as e:
    print("HTTP FAILED " + repr(e))