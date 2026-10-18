#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""行尾与打包一致性审计：任何系统上生成的产物，字节都要和仓库、和提交包一致。

为什么要有这个脚本（第 39 轮）：
    项目的核心承诺之一是"第三方离线复算出同一张页面"，而"逐字节一致"这件事
    在 Windows 上有一个隐形破坏者：**文本模式写文件会把 \\n 翻成 \\r\\n**。
    实测（第 39 轮开始前）：`pipeline/` 与 `tools/` 里 23 处文本写盘没有钉
    `newline="\\n"`，于是 21 个产物在磁盘上是 CRLF、而仓库里（`.gitattributes`
    的 `* text=auto eol=lf` 归一化后）是 LF —— 提交包直接从磁盘取字节，
    所以包里那 21 个文件与克隆下来的仓库**不是同一串字节**。
    页面本身没受影响（页面 CR 0），离线复算也不受影响（`json.load` 不在乎行尾），
    但"逐字节一致"这句话在这些文件上当时并不成立。

    这类问题没有任何门禁看得见：`verify_demo.py` 只看页面与 `data/processed`
    的数值，`consistency_audit.py` 只看文档与产物说的是不是同一组数字，
    `snapshot_audit.py` 只看日期。所以这里把三件事钉死：

    1. 源码卫生：`pipeline/*.py` 与 `tools/*.py` 里**每一处**文本模式写盘
       （`open(..., "w"/"a"/"x")`、`io.open(...)`）都必须显式给出
       `newline="\\n"`；二进制模式（含 `"rb"`/`"wb"`）不受此限。
    2. 产物行尾：随包发布的文本文件（`.json`/`.jsonl`/`.txt`/`.csv`/`.md`/
       `.yml`/`.html`/`.js`/`.css`/`.py`/`.svg`）里不得出现 CR；
       只有两个 `.bat` 是**刻意** CRLF（`.gitattributes` 里单独钉的，
       Windows 双击才不出错）。
    3. 打包一致：提交包里每个 `ai4climate/...` 条目的字节，必须与磁盘上
       对应文件的字节完全相同（顶层说明文件同理）。

用法：
    python tools/portability_audit.py            # 人类可读
    python tools/portability_audit.py --json     # 机器可读
"""

import ast
import io
import json
import os
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTER = os.path.dirname(ROOT)
ZIP = os.path.join(OUTER, "提交包", "ai4climate_reef_sentinel_submission.zip")
GITATTR = os.path.join(ROOT, ".gitattributes")

SKIP_DIRS = {".git", "__pycache__", ".edge", "_backup_before_refresh",
             ".taste-skill"}
TEXT_EXT = (".json", ".jsonl", ".txt", ".csv", ".md", ".yml", ".yaml",
            ".html", ".js", ".css", ".py", ".svg")
# 刻意保持 CRLF 的文件（.gitattributes 里单独钉过；Windows 双击才不出错）
CRLF_BY_DESIGN = {"启动预览.bat", "更新数据.bat"}
# .gitattributes 必须钉住的两条规则
GITATTR_RULES = ("* text=auto eol=lf", "*.bat text eol=crlf")
# 工作文件目录：这些是我的工作区（截图 / 探针 / 浏览器缓存），不是交付内容。
# 项目目录里出现任何一个，说明"作品"与"工作文件"又混在一起了 —— 第 44 轮
# 真的抓到过：ai4climate/.taste-skill/ 里留着 3 个探针脚本、刷新前的原始数据
# 备份与 __pycache__，磁盘上打开目录分不清哪些是交付内容（打包脚本本来就跳过
# 它们，所以旧门禁全绿、提交包里也确实没有 —— 缺的是"磁盘上也要分开"这一条）。
WORK_DIRS = (".taste-skill", ".edge")
# 随包条目里绝不允许出现的**目录名**（探针 / 截图脚本 / 审计报告 / 缓存 / 备份）。
# 注意不要用 "shot-" 这种子串：项目里有一张真实照片叫
# `aerial-shot-of-a-small-island-on.jpg`，第 44 轮首跑就被它误报了。
SCRATCH_DIR_PARTS = ("taste-skill", ".edge", "__pycache__",
                     "_backup_before_refresh", "reef-scratch")
# 随包条目里绝不允许出现的**文件名前缀 / 全名**（我的探针与截图脚本叫
# probe-r4*.py、shot-r4*.mjs，审计报告叫 REPORT.md）
SCRATCH_NAME_PREFIX = ("probe-", "shot-r")
SCRATCH_NAME_EXACT = ("REPORT.md",)


def _walk_text():
    """遍历项目里的文本文件（跳过 .git 等目录），产出 (相对路径, 绝对路径)。"""
    for dp, dn, fn in os.walk(ROOT):
        dn[:] = [d for d in dn if d not in SKIP_DIRS]
        for name in sorted(fn):
            if name.lower().endswith(TEXT_EXT):
                p = os.path.join(dp, name)
                rel = os.path.relpath(p, ROOT).replace("\\", "/")
                yield rel, p


def _mode_of(call):
    """取 open(...) 的 mode：第二个位置参数，或 mode= 关键字。"""
    if len(call.args) > 1 and isinstance(call.args[1], ast.Constant) \
            and isinstance(call.args[1].value, str):
        return call.args[1].value
    for kw in call.keywords:
        if kw.arg == "mode" and isinstance(kw.value, ast.Constant) \
                and isinstance(kw.value.value, str):
            return kw.value.value
    return None


def _is_open(node):
    f = node.func
    if isinstance(f, ast.Name) and f.id == "open":
        return True
    return isinstance(f, ast.Attribute) and f.attr == "open"


def writers():
    """扫源码里的文本写盘点，返回 (全部, 未钉 newline 的)。"""
    allw, unpinned = [], []
    for base in ("pipeline", "tools"):
        d = os.path.join(ROOT, base)
        if not os.path.isdir(d):
            continue
        for name in sorted(os.listdir(d)):
            if not name.endswith(".py"):
                continue
            p = os.path.join(d, name)
            rel = base + "/" + name
            try:
                with io.open(p, encoding="utf-8") as fh:
                    tree = ast.parse(fh.read())
            except (SyntaxError, UnicodeDecodeError) as exc:
                unpinned.append("%s：无法解析（%s）" % (rel, exc))
                continue
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call) or not _is_open(node):
                    continue
                m = _mode_of(node)
                if not m or "b" in m or not any(c in m for c in "wax"):
                    continue
                where = "%s:%d" % (rel, node.lineno)
                allw.append(where)
                if not any(kw.arg == "newline" for kw in node.keywords):
                    unpinned.append(where)
    return allw, unpinned


def facts():
    f = {}
    allw, unpinned = writers()
    f["writers"] = len(allw)
    f["unpinned"] = unpinned

    text = list(_walk_text())
    f["text_files"] = len(text)
    crlf = []
    for rel, p in text:
        name = os.path.basename(rel)
        if name in CRLF_BY_DESIGN:
            continue
        with open(p, "rb") as fh:
            b = fh.read()
        if b"\r" in b:
            crlf.append("%s（%d 个 CR）" % (rel, b.count(b"\r")))
    f["crlf"] = crlf

    page = os.path.join(ROOT, "demo", "index.html")
    f["page_cr"] = None
    if os.path.exists(page):
        with open(page, "rb") as fh:
            f["page_cr"] = fh.read().count(b"\r")

    f["gitattr_rules"] = []
    if os.path.exists(GITATTR):
        with io.open(GITATTR, encoding="utf-8") as fh:
            attr = fh.read()
        f["gitattr_rules"] = [r for r in GITATTR_RULES if r in attr]

    # 项目目录里不得出现工作文件目录（作品与我的工作区必须分开）
    f["work_dirs"] = [d for d in WORK_DIRS
                      if os.path.isdir(os.path.join(ROOT, d))]

    f["zip_present"] = os.path.exists(ZIP)
    f["zip_entries"] = 0
    f["pack_missing"] = []
    f["pack_mismatch"] = []
    f["pack_crlf"] = []
    f["pack_raw_diff"] = 0
    f["pack_text"] = 0
    f["pack_binary"] = 0
    f["scratch_in_pack"] = []
    if f["zip_present"]:
        with zipfile.ZipFile(ZIP) as z:
            for entry in z.namelist():
                if entry.endswith("/"):
                    continue
                f["zip_entries"] += 1
                parts = entry.split("/")
                name = parts[-1]
                is_scratch = any(p in SCRATCH_DIR_PARTS for p in parts) \
                    or name.startswith(SCRATCH_NAME_PREFIX) \
                    or name in SCRATCH_NAME_EXACT or name.endswith(".pyc")
                if is_scratch:
                    f["scratch_in_pack"].append(entry)
                if entry.startswith("ai4climate/"):
                    disk = os.path.join(ROOT, entry[len("ai4climate/"):])
                else:
                    # 顶层条目：先看项目内（00_提交包说明.md 就在 ai4climate/ 里），
                    # 再看项目外（例如 ai4climate_reef_sentinel_submission.zip 自身）。
                    inside = os.path.join(ROOT, entry)
                    disk = inside if os.path.exists(inside) \
                        else os.path.join(OUTER, entry)
                if not os.path.exists(disk):
                    f["pack_missing"].append(entry)
                    continue
                packed = z.read(entry)
                with open(disk, "rb") as fh:
                    ondisk = fh.read()
                is_text = entry.lower().endswith(TEXT_EXT) \
                    and os.path.basename(entry) not in CRLF_BY_DESIGN
                if not is_text:
                    # 二进制条目（docx / 图片 / 视频 / 包自身）不受行尾翻译影响，
                    # 而且每次重新生成都可能与上次不同 —— 它们的新鲜度由
                    # tools/submission_selfcheck.py 管，这里只看文本条目。
                    f["pack_binary"] += 1
                    if packed != ondisk:
                        f["pack_raw_diff"] += 1
                    continue
                f["pack_text"] += 1
                # 包内的文本条目本身不能带 CR：这一条与"包是否过期"无关，
                # 只看包里装的是不是纯 LF 的字节。
                if b"\r" in packed:
                    f["pack_crlf"].append("%s（%d 个 CR）" % (entry, packed.count(b"\r")))
                if packed != ondisk:
                    f["pack_raw_diff"] += 1
                # 内容比对忽略行尾：包是否"过期"由 tools/submission_selfcheck.py
                # 管（preflight 的顺序是 先审一致性、后重打包），这里只管内容本身。
                if packed.replace(b"\r\n", b"\n") != ondisk.replace(b"\r\n", b"\n"):
                    f["pack_mismatch"].append(entry)
    return f


def audit():
    f = facts()
    bad = []
    if f["unpinned"]:
        bad.append("有 %d 处文本写盘没钉 newline=\"\\n\"，在 Windows 上会写出 "
                   "CRLF：%s" % (len(f["unpinned"]), "、".join(f["unpinned"][:6])))
    if f["crlf"]:
        bad.append("有 %d 个随包文本文件含 CR（应只有两个 .bat 是 CRLF）：%s"
                   % (len(f["crlf"]), "、".join(f["crlf"][:6])))
    if f["page_cr"]:
        bad.append("成品页含 %d 个 CR，不是纯 LF" % f["page_cr"])
    missing_rule = [r for r in GITATTR_RULES if r not in f["gitattr_rules"]]
    if missing_rule:
        bad.append(".gitattributes 缺少行尾规则：%s" % "、".join(missing_rule))
    if f["work_dirs"]:
        bad.append("项目目录里出现了工作文件目录（作品与工作文件必须分开）：%s"
                   % "、".join(f["work_dirs"]))
    if f["scratch_in_pack"]:
        bad.append("提交包里有 %d 个条目是工作文件（探针 / 截图脚本 / 审计报告 / "
                   "缓存 / 备份）：%s"
                   % (len(f["scratch_in_pack"]),
                      "、".join(f["scratch_in_pack"][:6])))
    if not f["zip_present"]:
        # 评审视角复算会把提交包解压到临时目录，那里没有包（也没有"提交包"目录），
        # 所以包相关的检查在这里按 SKIP 处理 —— 与 tools/media_audit.py 找不到
        # 视频时打印 SKIP 是同一个约定。
        pass
    else:
        if f["pack_missing"]:
            bad.append("提交包里有 %d 个条目在磁盘上找不到：%s"
                       % (len(f["pack_missing"]), "、".join(f["pack_missing"][:6])))
        if f["pack_crlf"]:
            bad.append("提交包里有 %d 个文本条目带 CR（包内字节就不是纯 LF）：%s"
                       % (len(f["pack_crlf"]), "、".join(f["pack_crlf"][:6])))
        if f["pack_mismatch"]:
            bad.append("提交包里有 %d 个条目的内容与磁盘不同（行尾之外还有差异）：%s"
                       % (len(f["pack_mismatch"]), "、".join(f["pack_mismatch"][:6])))
    return f, bad


def main():
    argv = sys.argv[1:]
    f, bad = audit()
    if "--json" in argv:
        print(json.dumps({"facts": f, "failures": bad}, ensure_ascii=False,
                         indent=1))
        return 0 if not bad else 1
    print("行尾与打包一致性审计  portability_audit")
    print("  文本写盘点            %d 处（未钉 newline 的 %d 处）"
          % (f["writers"], len(f["unpinned"])))
    print("  随包文本文件          %d 个（含 CR 的 %d 个，两个 .bat 例外）"
          % (f["text_files"], len(f["crlf"])))
    print("  成品页 CR             %s" % f["page_cr"])
    print("  .gitattributes        %d/%d 条规则在位"
          % (len(f["gitattr_rules"]), len(GITATTR_RULES)))
    print("  项目目录里的工作目录  %d 个（应为 0：%s）"
          % (len(f["work_dirs"]),
             "、".join(WORK_DIRS)))
    if f["zip_present"]:
        print("  包内工作文件条目      %d 个（应为 0）" % len(f["scratch_in_pack"]))
    if f["zip_present"]:
        print("  提交包                %d 个条目 = %d 个文本 + %d 个二进制"
              % (f["zip_entries"], f["pack_text"], f["pack_binary"]))
        print("  包内文本条目          %d 个（带 CR 的 %d 个、缺文件 %d 个、"
              "行尾之外内容不同 %d 个、与磁盘字节不同 %d 个）"
              % (f["pack_text"], len(f["pack_crlf"]), len(f["pack_missing"]),
                 len(f["pack_mismatch"]), f["pack_raw_diff"]))
    else:
        print("  提交包                SKIP（找不到 %s；评审视角复算解压到临时目录时"
              "就是这个情况）" % ZIP)
    if bad:
        print("\n=== 失败 %d 项 ===" % len(bad))
        for b in bad:
            print("  FAIL " + b)
        return 1
    pack_msg = ("提交包 %d 个文本条目与磁盘内容一致（其中 %d 个与磁盘字节不同，"
                "新鲜度由 tools/submission_selfcheck.py 管）"
                % (f["pack_text"], f["pack_raw_diff"])) if f["zip_present"] \
        else "临时副本里没有提交包，包相关检查按 SKIP 处理"
    print("\nRESULT ALL PASS（%d 处文本写盘全部钉住 LF，随包 %d 个文本文件除两个"
          "刻意 CRLF 的 .bat 外都是纯 LF，成品页 CR %s；%s）"
          % (f["writers"], f["text_files"], f["page_cr"], pack_msg))
    return 0


if __name__ == "__main__":
    sys.exit(main())
