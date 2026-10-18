# -*- coding: utf-8 -*-
"""一次性把团队信息写进所有需要它的文档 —— 避免五处手工替换出现不一致。

用法（三处信息）：

    python tools\\fill_team.py "珊瑚哨兵队 / Reef Sentinel Team" \\
        "张三（某某大学，zhangsan@example.com）" "zhangsan@example.com"

    不带参数则逐项交互询问；加 --dry-run 只打印将要替换的内容，不写盘。
    python tools\\fill_team.py --dry-run

替换完成后请按顺序重跑：

    python pipeline\\md2docx.py            # 重生成 6 份 Word
    python tools\\submission_selfcheck.py  # 期望「0 处占位符」+ RESULT ALL PASS
    python tools\\pack_submission.py       # 重新打包
    python tools\\reviewer_repro.py        # 期望 RESULT ALL PASS

如果还想让演示视频的片尾出现队名，见 .taste-skill/video/build.py 里的 TEAM：
填完团队信息后重跑 `python .taste-skill\\video\\build.py` 即出新片（本脚本会顺带写好
.taste-skill/video/team.txt，build.py 优先读它）。
"""
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DOCS = os.path.join(ROOT, "docs")

FILES = [
    os.path.join(ROOT, "README.md"),
    os.path.join(ROOT, "00_提交包说明.md"),
    os.path.join(DOCS, "01_项目说明.md"),
    os.path.join(DOCS, "02_数据与AI说明.md"),
    os.path.join(DOCS, "03_90天验证计划.md"),
    os.path.join(DOCS, "04_演示视频逐字稿与分镜.md"),
    os.path.join(DOCS, "05_报名表与提交清单.md"),
    os.path.join(DOCS, "06_作品帖与发布草稿.md"),
]

# 占位符（左）-> 用哪一项信息替换（右）。逐个精确匹配，不做模糊推断。
RULES = [
    (r"〔团队名称待填〕", "team"),
    (r"团队名与成员：〔待填〕", "团队名与成员：{team}（{members}）"),
    (r"〔团队名，中英文均可；没有可以先用「珊瑚哨兵队 / Reef Sentinel Team」〕", "team"),
    (r"〔团队名〕", "team"),
    (r"〔姓名1〕、〔姓名2〕…", "members"),
    (r"〔姓名1〕〔姓名2〕", "members"),
    (r"〔姓名〕", "members"),
    (r"〔姓名、学校 / 单位、邮箱，一行一个；单人成队也可以〕", "members"),
    (r"〔你注册用的邮箱，用于识别报名记录〕", "email"),
    (r"〔机构名〕", "institution"),
]

PLACEHOLDER = re.compile("〔[^〕]*〕")


def ask(prompt, default=""):
    try:
        v = input(prompt).strip()
    except EOFError:
        v = ""
    return v or default


def main():
    args = [a for a in sys.argv[1:] if a != "--dry-run"]
    dry = "--dry-run" in sys.argv

    if len(args) >= 3:
        team, members, email = args[0], args[1], args[2]
        institution = args[3] if len(args) > 3 else team
    elif not args and not dry:
        print("请填写三项信息（直接回车使用方括号里的默认值）：")
        team = ask("  团队名 [珊瑚哨兵队 / Reef Sentinel Team]: ", "珊瑚哨兵队 / Reef Sentinel Team")
        members = ask("  成员（姓名、学校/单位、邮箱，多行用「；」分隔）: ", "〔成员待填〕")
        email = ask("  联系邮箱: ", "")
        institution = ask("  机构名（用于视频片尾，回车同团队名）: ", team)
    else:
        team = members = email = institution = None

    if team is None:
        # --dry-run 时不带参数：用占位值演示会替换成什么
        team, members, email, institution = "〈团队名〉", "〈成员〉", "〈邮箱〉", "〈机构名〉"

    for name, v in (("团队名", team), ("成员", members), ("联系邮箱", email)):
        if not v or "〔" in v or "〕" in v:
            sys.exit("「%s」为空或仍是占位符，已中止：%r" % (name, v))

    repl = {"team": team, "members": members, "email": email, "institution": institution}
    total = 0
    for path in FILES:
        if not os.path.exists(path):
            continue
        src = io.open(path, encoding="utf-8").read()
        out = src
        per_file = {}
        for pat, key in RULES:
            n = len(re.findall(pat, out))
            if n:
                tpl = repl[key] if key in repl else key.format(**repl)
                out = re.sub(pat, tpl.replace("\\", "\\\\"), out)
                per_file[pat] = per_file.get(pat, 0) + n
                total += n
        if out != src:
            rel = os.path.relpath(path, ROOT)
            print("  %-28s %d 处" % (rel, sum(per_file.values())))
            if not dry:
                io.open(path, "w", encoding="utf-8", newline="\n").write(out)

    print("共 %d 处占位符%s" % (total, "（dry-run，未写盘）" if dry else " 已替换"))

    if dry:
        print("（dry-run：上面的「剩余占位符」检查按替换前的内容显示，正式运行时会清零）")
        return
    left = []
    for path in FILES:
        if not os.path.exists(path):
            continue
        for i, line in enumerate(io.open(path, encoding="utf-8").read().splitlines(), 1):
            for m in PLACEHOLDER.finditer(line):
                left.append("%s:%d %s" % (os.path.relpath(path, ROOT), i, m.group(0)))
    if left:
        print("仍剩余 %d 处（这些不在自动替换表里，需要手工确认）：" % len(left))
        for x in left:
            print("  " + x)
    else:
        print("没有剩余占位符。")

    # 顺带把队名写给视频合成脚本（存在则写，不存在则跳过）
    vids = os.path.join(os.path.dirname(os.path.dirname(ROOT)), ".taste-skill", "video")
    if os.path.isdir(vids) and not dry:
        io.open(os.path.join(vids, "team.txt"), "w", encoding="utf-8", newline="\n").write(team + "\n")
        print("已写入 .taste-skill/video/team.txt（重跑 build.py 可让片尾出现队名）")


if __name__ == "__main__":
    main()
