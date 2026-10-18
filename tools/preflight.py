# -*- coding: utf-8 -*-
# preflight.py - 提交前一键自检：在**不联网**的前提下逐条验证这份提交包自身成立 ——
# 材料数字与数据产物一致、Word 与 md 一致、包内页面能离线逐字节复算出来。
# 任何一步非零退出、或输出里没有期望的成功标志，都会被抓出来并打印那一步的尾部输出。
#
# 为什么把联网刷新挪出判定链（2026-10-18 重排）：包里的文档是**提交时刻的冻结快照**，
# 而 pipeline/refresh.py 会把数据推进到抓取当天（这是它的职责）。旧版把刷新当第 1 步，
# 于是「跑完自检」这个动作本身就把后面的「材料与数据一致性」判成了失败 —— 越临近截止越必然失败。
# 现在判定链 6 步全部离线、不改动任何提交物；只想验联网重跑能力时另加 --with-network。
import os, subprocess, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 判定链（6 步，全部离线）。顺序有依赖：Word 必须在打包之前（否则 md 比 docx 新），
# 打包必须在一系列「看包」的步骤之前 —— 一致性审计里有一条断言「提交包与磁盘是同一串
# 字节」（tools/portability_audit.py），所以打包必须排在它前面，否则从干净状态跑自检时，
# 只要上一次改动后没手工重打包，第 2 步就会红（第 40 轮踩过：改了 00_提交包说明.md 后
# 直接跑 preflight，一致性审计报「代码与文档脱节」）。
STEPS = [
    ("重新生成 Word 版材料（必须在打包之前，否则 md 比 docx 新）", ["pipeline/md2docx.py"], "ALL_OK"),
    ("按包内当前快照重新打包提交包（必须在所有「看包」的审计之前）", ["tools/pack_submission.py"], "ENTRIES"),
    ("材料数字与数据产物一致性（含 md <-> docx 内容核对、提交包与磁盘逐条比对）", ["tools/consistency_audit.py"], "RESULT ALL CONSISTENT"),
    ("提交包自检（五份材料 / 顶层说明 / 新鲜度 / 占位符）", ["tools/submission_selfcheck.py"], "RESULT ALL PASS"),
    ("90 天验证计划结算器自检（S1/S2 与 S3–S5 的算分逻辑）", [["tools/settle_forecast.py", "--selftest"], ["tools/feedback_log.py", "--selftest"]], "SELFTEST OK"),
    ("评审视角复算：解压提交包到临时目录、离线重跑 7 步并与包内页面逐字节比对", ["tools/reviewer_repro.py"], "RESULT ALL PASS"),
]

# 可选（--with-network）：联网重跑整条流水线。它会把数据推进到抓取当天，
# 因此跑完之后包内冻结材料里的数字必然比数据旧 —— 这一步只证明「能重跑」，不参与判定。
NETWORK_STEP = ("联网重跑整条流水线（抓取 -> 特征 -> 标定 -> 模型 -> 成品页 -> 校验页）", ["pipeline/refresh.py"], "REFRESH OK")

def run(script):
    """script 是单条命令 ["路径", 参数...]；也可以是一组命令 [["a.py"], ["b.py"]]，
    按顺序跑完，任一非零就立刻返回（结算器那一步要把 S1/S2 与 S3-S5 两个自检串起来）。"""
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    cmds = script if isinstance(script[0], list) else [script]
    t0 = time.time()
    outs = []
    for c in cmds:
        p = subprocess.run([sys.executable, os.path.join(ROOT, c[0])] + c[1:],
                           cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        outs.append(p.stdout.decode("utf-8", "replace"))
        if p.returncode != 0:
            return p.returncode, "".join(outs), time.time() - t0
    return 0, "".join(outs), time.time() - t0

def tail(txt, n=12):
    lines = [x for x in txt.splitlines() if x.strip()]
    return "\n".join(lines[-n:])

def main():
    with_network = "--with-network" in sys.argv[1:]
    print("=" * 66)
    print("提交前一键自检  preflight  |  " + ROOT)
    print("判定链 %d 步，全部离线（不改动提交物、不需要网络）" % len(STEPS))
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
    if with_network:
        name, script, need = NETWORK_STEP
        code, out, dt = run(script)
        good = (code == 0) and (need in out)
        print("[+1]  %-6s %5.1fs  %s" % ("INFO" if good else "WARN", dt, name))
        if not good:
            print("      " + "\n      ".join(tail(out, 10).splitlines()))
        print("      注意：这一步已把数据推进到抓取当天，包内冻结材料里的数字此后会比数据旧；"
              "要再核对材料一致性，请重新解压一份提交包（本步不影响上面的判定结果）。")
    print("-" * 66)
    if fails:
        print("PREFLIGHT FAIL %d 步" % len(fails))
        for name, code, need, out in fails:
            print("  - " + name + "（退出码 " + str(code) + "，期望输出含 " + need + "）")
        print("  先修上面列出的步骤，再重新跑一次 python tools\\preflight.py")
        return 1
    print("PREFLIGHT ALL PASS  (%.1f s)" % (time.time() - t_all))
    print("提交材料本身已自检通过；接下来只剩需要你本人做的三件事：")
    print("  1) 推送新版上线：在 ai4climate 目录执行 git fetch origin 与 "
          "git push --force-with-lease origin editorial-layer:main"
          "（main 上有机器人的 daily refresh 提交，普通推送会被拒；理由见 DEPLOY.md 第五节）")
    print("  2) 填团队名 / 成员 / 邮箱：python tools\\fill_team.py \"团队名\" \"成员\" \"邮箱\"，再跑 python pipeline\\md2docx.py")
    print("  3) 在 https://ai4climate.deepseek.club 提交（截止 2026-10-19 24:00；演示视频 mp4 随平台单独上传）")
    return 0

if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    sys.exit(main())
