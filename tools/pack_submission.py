# 打包提交包：排除浏览器缓存、__pycache__ 与原始数据备份；提交包说明置于顶层
import os, sys, zipfile
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(os.path.dirname(ROOT), "提交包", "ai4climate_reef_sentinel_submission.zip")
os.makedirs(os.path.dirname(OUT), exist_ok=True)
TOP = "00_提交包说明.md"
SKIP_DIRS = {".edge", "__pycache__", ".git", "_backup_before_refresh"}
n = 0
packed = set()
TEMP_SKIPPED = []
with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in sorted(filenames):
            if fn.startswith("_") and fn.endswith(".py"):
                TEMP_SKIPPED.append(fn)
                continue
            if fn.endswith(".pyc"):
                continue
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, os.path.dirname(ROOT)).replace(os.sep, "/")
            if rel == "ai4climate/" + TOP:
                rel = TOP
            z.write(full, rel)
            packed.add(rel)
            n += 1
        # 从「已解压的提交包」里再打包时，顶层说明在 ai4climate/ 的上一层，别丢
        alt = os.path.join(os.path.dirname(ROOT), TOP)
        if TOP not in packed and os.path.exists(alt):
            z.write(alt, TOP)
            packed.add(TOP)
            n += 1
print("ZIP " + OUT)
print("ENTRIES " + str(n))
print("BYTES " + str(os.path.getsize(OUT)))
if TEMP_SKIPPED:
    print("TEMP_SKIPPED " + ", ".join(sorted(TEMP_SKIPPED)) + "（临时探针不进包）")