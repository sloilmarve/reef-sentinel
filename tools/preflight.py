# -*- coding: utf-8 -*-
# preflight.py - 提交前一键自检：重跑整条流水线，再依次跑全部校验脚本，最后只给一个结论。
# 为什么需要：以前要手动记 5 条命令、还要自己判断哪一步的输出是正常的；现在一条命令跑完，
# 任何一步非零退出或输出里没有期望的成功标志都会被抓出来，并打印失败那一步的尾部输出。
import os, subprocess, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

STEPS = [
    ("重跑整条流水线（抓取 -> 特征 -> 标定 -> 模型 -> 成品页 -> 校验页）", ["pipeline/refresh.py"], "REFRESH OK"),
    ("重新生成 Word 版材料（必须在审计之前，否则 md 比 docx 新）", ["pipeline/md2docx.py"], "ALL_OK"),
    ("材料数字与数据产物一致性（含 md <-> docx 内容核对）", ["tools/consistency_audit.py"], "RESULT ALL CONSISTENT"),
    ("重新打包提交包", ["tools/pack_submission.py"], "ENTRIES"),
    ("提交包自检（五份材料 / 顶层说明 / 新鲜度 / 占位符）", ["tools/submission_selfcheck.py"], "RESULT ALL PASS"),
    ("90 天验证计划结算器自检（S1/S2 的算分逻辑）", ["tools/settle_forecast.py", "--selftest"], "SELFTEST OK"),
    ("评审视角复算：解压提交包到临时目录、离线重跑 7 步并与包内页面逐字节比对", ["tools/reviewer_repro.py"], "RESULT ALL PASS"),
]

def run(script):
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    t0 = time.time()
    p = subprocess.run([sys.executable, os.path.join(ROOT, script[0])] + script[1:],
                       cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    out = p.stdout.decode("utf-8", "replace")
    return p.returncode, out, time.time() - t0

def tail(txt, n=12):
    lines = [x for x in txt.splitlines() if x.strip()]
    return "\n".join(lines[-n:])

def main():
    print("=" * 66)
    print("提交前一键自检  preflight  |  " + ROOT)
    print("=" * 66)
    fails = []
    t_all = time.time()
    for i, (name, script, need) in enumerate(STEPS, 1):
        code, out, dt = run(script)
        good = (code == 0) and (need in out)
        flag = "PASS" if good else "FAIL"
        print("[%d/%d] %-6s %5.1fs  %s" % (i, len(STEPS), flag, dt, name))
        if not good:
            fails.append((name, code, need, out))
            print("      " + "\n      ".join(tail(out, 14).splitlines()))
    print("-" * 66)
    if fails:
        print("PREFLIGHT FAIL %d 步" % len(fails))
        for name, code, need, out in fails:
            print("  - " + name + "（退出码 " + str(code) + "，期望输出含 " + need + "）")
        print("  先修上面列出的步骤，再重新跑一次 python tools\preflight.py")
        return 1
    print("PREFLIGHT ALL PASS  (%.1f s)" % (time.time() - t_all))
    print("接下来只有三件事需要你本人做：")
    print("  1) 录 3 分钟演示视频（逐字稿 docs/04 与 演示视频提词器.html）")
    print("  2) 填团队名 / 成员 / 邮箱（docs/05 第一节）")
    print("  3) 在 https://ai4climate.deepseek.club 提交（截止 2026-10-19 24:00）")
    return 0

if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    sys.exit(main())
