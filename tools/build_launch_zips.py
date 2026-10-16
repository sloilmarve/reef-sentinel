# -*- coding: utf-8 -*-
"""把当前成品页重新打包成两个「上线包」（内容完全相同，只是给两个平台各一份）。

用法： python tools/build_launch_zips.py
产物： ../提交包/上线_Cloudflare直传.zip 与 ../提交包/上线_NetlifyDrop_同一份.zip
两个 zip 里都只有 index.html（来自 demo/index.html），保证与成品页逐字节一致；
成品页每次刷新后重跑本脚本，上线包就不会落后于页面。
"""
import hashlib
import os
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "demo", "index.html")
PACK = os.path.join(os.path.dirname(ROOT), "提交包")
NAMES = ["上线_Cloudflare直传.zip", "上线_NetlifyDrop_同一份.zip"]


def main():
    with open(SRC, "rb") as f:
        page = f.read()
    digest = hashlib.sha256(page).hexdigest()[:16]
    for name in NAMES:
        dst = os.path.join(PACK, name)
        tmp = dst + ".tmp"
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
            z.writestr("index.html", page)
        os.replace(tmp, dst)
        print("WROTE %-30s %8d bytes  (index.html %d bytes, sha %s)"
              % (name, os.path.getsize(dst), len(page), digest))
    print("两个上线包与 demo/index.html 逐字节一致")
    return 0


if __name__ == "__main__":
    sys.exit(main())