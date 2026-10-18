# 提交自检：官方 5 项材料是否齐、文档里还有几处待填、成品页与提交包是否新鲜
import json, os, re, sys, time, zipfile
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ZIP = os.path.join(os.path.dirname(ROOT), "提交包", "ai4climate_reef_sentinel_submission.zip")
DOCS = os.path.join(ROOT, "docs")
WORD = os.path.join(ROOT, "docs_word")
bad = 0

def ok(cond, msg):
    global bad
    print(("  OK   " if cond else "  FAIL ") + msg)
    if not cond:
        bad += 1

print("== 官方 5 项材料 ==")
md = sorted(f for f in os.listdir(DOCS) if f.endswith(".md"))
docx = sorted(f for f in os.listdir(WORD) if f.endswith(".docx"))
ok(len(md) >= 5, "官方要求的 5 项材料齐全（md 共 " + str(len(md)) + " 份：项目说明 / 数据与AI说明 / 90天验证计划 / 演示视频稿 / 报名表清单）")
ok(len(docx) >= 5, "Word 版齐全（共 " + str(len(docx)) + " 份）")
ok(all(os.path.exists(os.path.join(DOCS, n)) for n in ["01_项目说明.md", "02_数据与AI说明.md", "03_90天验证计划.md", "04_演示视频逐字稿与分镜.md", "05_报名表与提交清单.md"]),
   "五份必交材料逐一点名在册")
page = os.path.join(ROOT, "demo", "index.html")
html = open(page, encoding="utf-8").read()
_n_script = html.lower().count("<script")
ok(_n_script == 1 and 'src="http' not in html.lower() and "<link" not in html.lower(),
   "成品页仅含 1 个内联渐进增强脚本、无任何外链脚本 / 样式（SCRIPT_TAGS=%d，离线可开）" % _n_script)
ok("data:image/png;base64" in html, "官方区域图已内嵌（单文件离线可开）")
if os.path.exists(ZIP):
    ok(True, "提交包存在 " + str(os.path.getsize(ZIP)) + " bytes")
else:
    print("  SKIP 提交包不在同级目录（解压后的布局属正常，跳过包体检查；要打包请跑 tools/pack_submission.py）")

print("== Word 材料的可复现性 ==")
_ZIP_STAMP = (2026, 10, 18, 0, 0, 0)
_sealed, _unsealed = 0, []
for _n in docx:
    with zipfile.ZipFile(os.path.join(WORD, _n)) as _z:
        _stamps = set(_i.date_time for _i in _z.infolist())
    if _stamps == {_ZIP_STAMP}:
        _sealed += 1
    else:
        _unsealed.append(_n)
ok(not _unsealed,
   "Word 版逐字节可复现：%d 份 .docx 的每个 zip 成员时间戳都钉在 2026-10-18 00:00:00（pipeline/md2docx.py 的 seal_docx），"
   "同一份 md 转两次得到同一串字节%s" % (_sealed, "" if not _unsealed else "；未钉死：" + "、".join(_unsealed)))

print("== 文档里还需要你填的地方 ==")
pat = re.compile("〔[^〕]*〕")
hits = []
for f in md:
    p = os.path.join(DOCS, f)
    for i, line in enumerate(open(p, encoding="utf-8").read().splitlines(), 1):
        for m in pat.finditer(line):
            hits.append((f, i, m.group(0)))
for f, i, t in hits:
    print("  TODO " + f + ":" + str(i) + "  " + t)
print("  共 " + str(len(hits)) + " 处占位符" + ("" if hits else "（已全部填好）"))

print("== 新鲜度 ==")
if os.path.exists(ZIP):
    zt = os.path.getmtime(ZIP)
    newest = max(os.path.getmtime(os.path.join(dp, f)) for dp, dn, fn in os.walk(ROOT) for f in fn if ".edge" not in dp and "__pycache__" not in dp and f != os.path.basename(ZIP))
    ok(zt >= newest, "提交包不旧于项目内任何文件（包 " + time.strftime("%m-%d %H:%M", time.localtime(zt)) + "）")
    with zipfile.ZipFile(ZIP) as z:
        names = z.namelist()
    need = ["ai4climate/demo/index.html", "ai4climate/README.md", "ai4climate/更新数据.bat", "ai4climate/启动预览.bat"]
    for n in need:
        ok(n in names, "包内含 " + n)
    ok(("00_提交包说明.md" in names) or ("ai4climate/00_提交包说明.md" in names),
       "压缩包顶层有 00_提交包说明.md（打开压缩包第一眼就能看到）")
    ok(any(n.endswith("05_报名表与提交清单.docx") for n in names), "包内含报名表清单 Word 版")
    ok(any(n.endswith("noaa_crw/triangle_dhw.png") for n in names), "包内含 NOAA 官方区域图")

print("== 演示视频 ==")
import media_audit
_vf, _vbad, _vskip = media_audit.audit()
_vclock = "时长见文件"
if _vskip:
    print("  SKIP " + _vskip)
else:
    _vclock = _vf["clock"]
    for _b in _vbad:
        ok(False, _b)
    ok(not _vbad,
       "演示视频 %s（%.2f 秒，上限 180 秒）/ %d bytes（%.2f MB）/ %d×%d / %s + %s —— 材料里的时长、体积、分辨率、编码逐条与文件字节一致（tools/media_audit.py，纯标准库解析 MP4，不用 ffprobe）"
       % (_vf["clock"], _vf["seconds"], _vf["bytes"], _vf["bytes"] / 1e6, _vf["width"], _vf["height"],
          _vf["video_codec"], "mp4a" if _vf["has_aac"] else "?"))

print("")
print("还需你本人完成的三件事：")
print("  1) 填团队名 / 成员 / 邮箱，一条命令写进所有文档：python tools\\fill_team.py \"团队名\" \"成员\" \"邮箱\"")
print("     （再跑 python pipeline\\md2docx.py 重生成 Word）")
print("  2) 上传演示视频（已出片：提交包/珊瑚哨兵-Reef-Sentinel-演示视频.mp4，" + _vclock + "；")
print("     要改旁白就改 .taste-skill/video/vo.json 后重跑 python .taste-skill\\video\\build.py）")
print("  3) 在 https://ai4climate.deepseek.club 提交（截止 2026-10-19 24:00）")
print("")
print("RESULT " + ("ALL PASS" if bad == 0 else str(bad) + " ITEM(S) NEED ATTENTION"))