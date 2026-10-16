# -*- coding: utf-8 -*-
"""评审视角复算：把提交包解压到临时目录，只用包内材料离线重跑一遍，验证结论可复现。

这一步回答的是评审最可能问的问题：「把你们交的压缩包解压出来，不连外网、不看你们的开发目录，
能不能自己把页面和数字重新算出来？」

做三件事：
  1) 先从压缩包里读出 demo/index.html 的字节与 sha —— 这是「交出去的那一份」；
  2) 解压到系统临时目录，在解压出来的副本里按顺序跑离线步骤（不需要网络）：
     pipeline/build_features.py -> skill_regression.py -> leakage_audit.py -> build_dashboard.py
     -> build_static.py -> verify_demo.py，外加 tools/consistency_audit.py；
  3) 比对「副本里重建出来的页面」与「包里的页面」是否逐字节一致。

一致就说明：包内材料自足（数据 + 代码 + 文档），任意第三方能在自己的机器上复算出同一张页面。
临时目录跑完即删，不污染本目录。

用法： python tools/reviewer_repro.py
"""
import hashlib, io, os, shutil, subprocess, sys, tempfile, zipfile

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACK = os.path.join(os.path.dirname(ROOT), "提交包", "ai4climate_reef_sentinel_submission.zip")

STEPS = [
    ("pipeline/build_features.py", "从原始数据重算阈值与 66 个模型特征"),
    ("pipeline/skill_regression.py", "重算 4 折技巧回归表"),
    ("pipeline/leakage_audit.py", "重跑前视泄漏审计（截断不变性）"),
    ("pipeline/build_dashboard.py", "重算界面载荷与 8 天预报"),
    ("pipeline/build_static.py", "重新生成单页成品"),
    ("pipeline/verify_demo.py", "核验成品页与数据产物一致"),
    ("tools/consistency_audit.py", "核验文档数字与数据产物一致"),
]


def sha(b):
    return hashlib.sha256(b).hexdigest()


def main():
    print("评审视角复算  reviewer_repro  |  " + ROOT)
    print("=" * 66)
    if not os.path.exists(PACK):
        print("SKIP 提交包不在同级目录（解压后的布局属正常，跳过复算；要复算请先跑 tools/pack_submission.py）")
        return 0

    z = zipfile.ZipFile(PACK)
    names = z.namelist()
    member = None
    for n in names:
        if n.replace("\\", "/").endswith("demo/index.html"):
            member = n
            break
    if member is None:
        print("FAIL 压缩包里找不到 demo/index.html")
        return 1
    packed = z.read(member)
    packed_sha = sha(packed)
    print("包里页面      : %s（%s 字节）" % (packed_sha[:16], format(len(packed), ",")))
    print("包内条目      : %d 个" % len(names))

    tmp = tempfile.mkdtemp(prefix="reef_repro_")
    try:
        z.extractall(tmp)
        z.close()
        proj = None
        for base, dirs, _files in os.walk(tmp):
            if "pipeline" in dirs and "demo" in dirs:
                proj = base
                break
        if proj is None:
            print("FAIL 解压后找不到项目目录（应含 pipeline/ 与 demo/）")
            return 1
        print("解压到        : %s" % proj)
        print("-" * 66)
        fails = []
        for rel, why in STEPS:
            p = os.path.join(proj, rel.replace("/", os.sep))
            if not os.path.exists(p):
                print("  FAIL %-32s 包内缺少该脚本" % rel)
                fails.append(rel)
                continue
            r = subprocess.run([sys.executable, p], cwd=proj, capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=900)
            tail = [x for x in (r.stdout or "").strip().splitlines() if x.strip()]
            tail = tail[-1][:58] if tail else ""
            if r.returncode == 0:
                print("  OK   %-32s %s" % (rel, tail))
            else:
                print("  FAIL %-32s exit=%s  %s" % (rel, r.returncode, tail))
                fails.append(rel)

        rebuilt = os.path.join(proj, "demo", "index.html")
        if not os.path.exists(rebuilt):
            print("  FAIL 复算后没有生成 demo/index.html")
            fails.append("demo/index.html")
            return 1
        with open(rebuilt, "rb") as f:
            got = f.read()
        got_sha = sha(got)
        print("-" * 66)
        print("复算页面      : %s（%s 字节）" % (got_sha[:16], format(len(got), ",")))
        same = got_sha == packed_sha
        if same:
            print("  逐字节一致：包内材料自足，第三方可离线复算出同一张页面")
        else:
            print("  FAIL 复算页面与包内页面不一致（包内 %s / 复算 %s）" % (packed_sha[:16], got_sha[:16]))
            fails.append("页面逐字节比对")
        print("-" * 66)
        if fails:
            print("RESULT FAIL（%d 项）: %s" % (len(fails), "、".join(fails)))
            return 1
        print("RESULT ALL PASS（%d 步离线复算 + 页面逐字节比对）" % len(STEPS))
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
