# -*- coding: utf-8 -*-
# 核对「答辩与追问准备」这份支持性材料：每题的出处真的能打开，且答案不引入材料里没有的新数字。
#
# 为什么需要它：平台规则写明评委会可能邀请一次不超过 10 分钟的线上问答，而五项提交材料里没有一份
# 是回答用的。这份材料本身也要能被核对 —— 一份「照读的答案」如果引用了不存在的文件、或者随手写了
# 材料里没有的数字，比没有这份材料更糟（评委当场打开就对不上）。
#
# 纯标准库、不联网、不需要浏览器。用法：
#   python tools\qa_audit.py            # 打印事实与结论
#   python tools\qa_audit.py --json     # 机器可读
import io
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTER = os.path.dirname(ROOT)
DOC07 = os.path.join(ROOT, "docs", "07_答辩与追问准备.md")
DOC01 = os.path.join(ROOT, "docs", "01_项目说明.md")
DOC02 = os.path.join(ROOT, "docs", "02_数据与AI说明.md")
DOC03 = os.path.join(ROOT, "docs", "03_90天验证计划.md")
DOC04 = os.path.join(ROOT, "docs", "04_演示视频逐字稿与分镜.md")
DOC05 = os.path.join(ROOT, "docs", "05_报名表与提交清单.md")
DOC06 = os.path.join(ROOT, "docs", "06_作品帖与发布草稿.md")
README = os.path.join(ROOT, "README.md")
DEPLOY = os.path.join(ROOT, "DEPLOY.md")
PACK00 = os.path.join(ROOT, "00_提交包说明.md")
LICENSE = os.path.join(ROOT, "LICENSE")

TOOL_ROW = "tools/qa_audit.py"
TOOL_ROW_WIN = "tools\\qa_audit.py"

BUCKETS = (
    u"真实问题与气候价值",
    u"AI 方法与技术有效性",
    u"可行性与用户体验",
    u"市场可持续性",
    u"传播与公众采纳",
    u"可扩展性与伦理与开放",
    u"高风险应用条款",
    u"复现与维护",
)
MIN_QUESTIONS = 12

Q_RE = re.compile(u"^###\\s+(Q\\d+)\\s*｜\\s*([^｜]+?)\\s*｜\\s*(.+?)\\s*$", re.M)
ANS_RE = re.compile(u"^\\*\\*答\\*\\*：(.*)$", re.M)
SRC_RE = re.compile(u"^\\*\\*出处\\*\\*：(.*)$", re.M)
TICK_RE = re.compile(r"`([^`]+)`")
SEC_RE = re.compile(u"第\\s*([0-9%s]+)\\s*节" % u"一二三四五六七八九十")
NUM_RE = re.compile(r"\d[\d,]*(?:\.\d+)?%?")
HEAD_RE = re.compile(u"^#{1,4}\\s*(.+?)\\s*$", re.M)
CN = u"一二三四五六七八九十"

# 答案里允许出现的数字，必须先在已冻结的材料里出现过（否则就是「现场编数字」）
CORPUS_FILES = (DOC01, DOC02, DOC03, DOC04, DOC05, DOC06, README, DEPLOY, PACK00, LICENSE)

# 必须写进这份材料的诚实边界（问了就这么答，不能答成别的）
MUST_SAY = (
    u"不是官方预警",
    u"不得作为",
    u"只承诺排序",
    u"书面意向",
    u"不在平台要求的五项之内",
    u"qa_audit.py",
)


def _read(path):
    """读一个材料文件。解压后的提交包里 `00_提交包说明.md` 在 `ai4climate/` 的上一层
    （外层还有一份 `先看这里.md`），所以本地找不到时再往上一层找一次——评审视角
    复算（tools/reviewer_repro.py）就是从解压目录里跑的。"""
    for cand in (path, os.path.join(os.path.dirname(ROOT), os.path.basename(path))):
        if os.path.exists(cand):
            with io.open(cand, "r", encoding="utf-8") as f:
                return f.read()
    with io.open(path, "r", encoding="utf-8") as f:
        return f.read()


def _first(*cands):
    for c in cands:
        if os.path.exists(c):
            return c
    return cands[0]


def _num_of(tok):
    """把「三」「3」都归一成阿拉伯数字字符串；不认识就返回 None。"""
    tok = tok.strip()
    if tok.isdigit():
        return tok
    if tok in CN:
        return str(CN.index(tok) + 1)
    return None


def _headings(path):
    if not os.path.exists(path):
        return None
    return [h.strip() for h in HEAD_RE.findall(_read(path))]


def _sec_ok(path, num):
    """文档里写「第 5 节」，标题里可能写「五、」；两种写法都要认。"""
    hs = _headings(path)
    if hs is None:
        return False, u"目标文件不存在"
    want = _num_of(num)
    if want is None:
        return False, u"节号无法识别：" + num
    forms = [num, want, want + "."]
    i = int(want)
    if 1 <= i <= len(CN):
        forms.append(CN[i - 1])
        forms.append(CN[i - 1] + u"、")
    for h in hs:
        for form in forms:
            if h.startswith(form):
                return True, h
    return False, u"该文件里没有以「" + num + u"」开头的标题"


def _resolve(tok):
    tok = tok.replace("\\", "/").lstrip("./")
    cands = [os.path.join(ROOT, tok), os.path.join(OUTER, tok)]
    if "/" not in tok:
        cands.append(os.path.join(ROOT, "docs", tok))
        cands.append(os.path.join(ROOT, "data", "processed", tok))
        cands.append(os.path.join(ROOT, "tools", tok))
        cands.append(os.path.join(ROOT, "pipeline", tok))
        cands.append(os.path.join(OUTER, u"提交包", tok))
    for c in cands:
        if os.path.exists(c):
            return c
    return None


def facts():
    f = {}
    f["doc_exists"] = os.path.exists(DOC07)
    if not f["doc_exists"]:
        return f
    text = _read(DOC07)
    f["doc_chars"] = len(text)
    qs = Q_RE.findall(text)
    ans = ANS_RE.findall(text)
    srcs = SRC_RE.findall(text)
    f["questions"] = len(qs)
    f["answers"] = len(ans)
    f["sources"] = len(srcs)
    f["q_eq_a"] = len(qs) == len(ans) == len(srcs)
    f["buckets_used"] = sorted(set(b.strip() for _, b, _ in qs))
    f["buckets_ok"] = [b for b in BUCKETS if b in f["buckets_used"]]
    f["buckets_missing"] = [b for b in BUCKETS if b not in f["buckets_used"]]
    f["bad_buckets"] = [b for b in f["buckets_used"] if b not in BUCKETS]

    # 出处：每个答案至少一个能打开的路径；写了「第 X 节」就必须真有那一节
    bad_src = []
    src_paths = 0
    sec_refs = 0
    for i, s in enumerate(srcs, 1):
        toks = TICK_RE.findall(s)
        if not toks:
            bad_src.append((i, u"没有给出可打开的文件路径", s.strip()[:60]))
            continue
        secs = SEC_RE.findall(s)
        for t in toks:
            p = _resolve(t)
            if p is None:
                bad_src.append((i, u"路径不存在：" + t, s.strip()[:60]))
                continue
            src_paths += 1
            if secs:
                # 「第 X 节」指的是同一行里点的那个文件（只对文档类文件校验）
                if p.endswith(".md"):
                    for num in secs:
                        ok, why = _sec_ok(p, num)
                        sec_refs += 1
                        if not ok:
                            bad_src.append((i, os.path.basename(p) + u" " + why, s.strip()[:60]))
    f["src_paths"] = src_paths
    f["sec_refs"] = sec_refs
    f["bad_src"] = bad_src

    # 答案里的数字必须先在已冻结材料里出现过
    corpus = u"".join(_read(p) for p in CORPUS_FILES if os.path.exists(p))
    new_nums = []
    nums_seen = 0
    for i, a in enumerate(ans, 1):
        for tok in NUM_RE.findall(a):
            nums_seen += 1
            if tok not in corpus:
                new_nums.append((i, tok))
    f["nums_in_answers"] = nums_seen
    f["new_nums"] = new_nums

    f["missing_must_say"] = [s for s in MUST_SAY if s not in text]
    f["doc01_landing"] = (u"07_答辩与追问准备" in _read(DOC01)) and (TOOL_ROW in _read(DOC01) or TOOL_ROW_WIN in _read(DOC01))
    f["doc02_tool"] = TOOL_ROW in _read(DOC02)
    f["pack00_landing"] = u"07_答辩与追问准备.md" in _read(PACK00)
    f["readme_landing"] = u"07_答辩与追问准备" in _read(README)
    return f


def audit(f=None):
    f = f or facts()
    bad = []
    if not f.get("doc_exists"):
        return f, [u"docs/07_答辩与追问准备.md 不存在"]
    if f["questions"] < MIN_QUESTIONS:
        bad.append(u"问题数 %d 少于 %d 题" % (f["questions"], MIN_QUESTIONS))
    if not f["q_eq_a"]:
        bad.append(u"问题 / 答 / 出处 三者的条数不一致（%d / %d / %d）" % (f["questions"], f["answers"], f["sources"]))
    if f["buckets_missing"]:
        bad.append(u"这些评审维度没有问题：" + u" / ".join(f["buckets_missing"]))
    if f["bad_buckets"]:
        bad.append(u"出现了不在六项权重（含高风险条款与复现）里的维度名：" + u" / ".join(f["bad_buckets"]))
    if f["bad_src"]:
        for i, why, s in f["bad_src"][:6]:
            bad.append(u"Q%d 的出处有问题：%s（%s）" % (i, why, s))
    if f["new_nums"]:
        for i, tok in f["new_nums"][:6]:
            bad.append(u"Q%d 的答案里出现了材料中没有的数字：%s" % (i, tok))
    if f["missing_must_say"]:
        bad.append(u"缺了必须写明的句子：" + u" / ".join(f["missing_must_say"]))
    if not f["doc01_landing"]:
        bad.append(u"docs/01 没有把这份材料与 tools\\qa_audit.py 写进去")
    if not f["doc02_tool"]:
        bad.append(u"docs/02 工具表没有 " + TOOL_ROW)
    if not f["pack00_landing"]:
        bad.append(u"00_提交包说明.md 没有列出 docs/07_答辩与追问准备.md")
    if not f["readme_landing"]:
        bad.append(u"README.md 没有提到这份材料")
    return f, bad


def main():
    as_json = "--json" in sys.argv
    f, bad = audit()
    if as_json:
        print(json.dumps({"facts": f, "bad": bad}, ensure_ascii=False, indent=2))
        return 1 if bad else 0
    if not f.get("doc_exists"):
        print(u"RESULT FAIL: docs/07_答辩与追问准备.md 不存在")
        return 1
    print(u"问题 %d 题 / 出处 %d 条（其中节号引用 %d 处）/ 答案里的数字 %d 个"
          % (f["questions"], f["src_paths"], f["sec_refs"], f["nums_in_answers"]))
    print(u"覆盖的评审维度 %d / %d：%s" % (len(f["buckets_ok"]), len(BUCKETS), u"、".join(f["buckets_ok"])))
    print(u"答案里不在材料中的新数字：%d 个" % len(f["new_nums"]))
    if bad:
        print(u"")
        for b in bad:
            print(u"  FAIL " + b)
        print(u"")
        print(u"RESULT FAIL（%d 项）：%s" % (len(bad), u"；".join(bad[:3])))
        return 1
    print(u"")
    print(u"RESULT ALL PASS（%d 题覆盖 8 个评审维度，每题出处都能打开、节号都对得上，"
          u"答案里的数字全部来自已冻结材料，诚实边界与「不属于五项必交材料」都写明了）" % f["questions"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
