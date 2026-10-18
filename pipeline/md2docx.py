# -*- coding: utf-8 -*-
# Convert the Chinese markdown materials in docs/ into .docx for submission upload.
import os, re, zipfile
from datetime import datetime
from docx import Document
from docx.shared import Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(ROOT, 'docs')
OUT = os.path.join(ROOT, 'docs_word')
CN = '\u5fae\u8f6f\u96c5\u9ed1'
EN = 'Segoe UI'
BQ = (0x44, 0x44, 0x44)
CODE_C = (0x1F, 0x3A, 0x5F)
HEAD_C = (0x0B, 0x3C, 0x5D)
# 生成物的时间戳一律钉死：同一份 md 转两次必须逐字节一致（评审可以自己复算）。
# 真实日期留在 git 历史与 docs/ 的修订说明里，不由 Word 的元数据来承担。
DOCX_STAMP = datetime(2026, 10, 18, 0, 0, 0)
ZIP_STAMP = (2026, 10, 18, 0, 0, 0)
AUTHOR = '\u73ca\u745a\u54e8\u5175 / Reef Sentinel'


def seal_docx(path):
    """把 .docx 里 zip 成员的时间戳钉死，让 Word 文档也逐字节可复现。

    python-docx 保存时会把**当前本地时间**写进每个 zip 成员的头里（docProps/core.xml
    里的 created/modified 反而是模板常量），所以同一份 md 两次转换出来的字节不同 ——
    一份 2 MB 的 .docx 里 17 个成员，每次重跑都全变。Word 不关心这些时间戳，但
    「同一输入同一输出」是这套材料对外承诺过的事，评审随时可以跑两次来核。
    """
    with zipfile.ZipFile(path) as z:
        items = [(i.filename, z.read(i.filename), i.compress_type, i.external_attr, i.create_system)
                 for i in z.infolist()]
    tmp = path + '.tmp'
    with zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED) as out:
        for name, data, ctype, ext, csys in items:
            zi = zipfile.ZipInfo(name, date_time=ZIP_STAMP)
            zi.compress_type = ctype
            zi.external_attr = ext
            zi.create_system = csys
            out.writestr(zi, data)
    os.replace(tmp, path)


def set_font(run, name=EN, size=None, bold=None, color=None, cn=None):
    run.font.name = name
    rPr = run._element.get_or_add_rPr()
    rF = rPr.find(qn('w:rFonts'))
    if rF is None:
        rF = OxmlElement('w:rFonts')
        rPr.append(rF)
    rF.set(qn('w:ascii'), name)
    rF.set(qn('w:hAnsi'), name)
    rF.set(qn('w:eastAsia'), cn or CN)
    if size is not None:
        run.font.size = Pt(size)
    if bold is not None:
        run.font.bold = bold
    if color is not None:
        run.font.color.rgb = RGBColor(*color)

INLINE = re.compile(r'(\*\*.+?\*\*|`[^`]+`)')

def add_inline(par, text, size=10.5, base_bold=False, color=None):
    for part in INLINE.split(text):
        if not part:
            continue
        if part.startswith('**') and part.endswith('**') and len(part) > 4:
            r = par.add_run(part[2:-2])
            set_font(r, EN, size, True, color)
        elif part.startswith('`') and part.endswith('`') and len(part) > 2:
            r = par.add_run(part[1:-1])
            set_font(r, 'Consolas', size - 0.5, base_bold, CODE_C)
        else:
            r = par.add_run(part)
            set_font(r, EN, size, base_bold, color)

def shade(cell, hexcolor):
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement('w:shd')
    shd.set(qn('w:val'), 'clear')
    shd.set(qn('w:color'), 'auto')
    shd.set(qn('w:fill'), hexcolor)
    tcPr.append(shd)

def convert(md_path, docx_path, title):
    f = open(md_path, encoding='utf-8')
    lines = f.read().split('\n')
    f.close()
    doc = Document()
    st = doc.styles['Normal']
    st.font.name = EN
    st.font.size = Pt(10.5)
    st.element.rPr.rFonts.set(qn('w:eastAsia'), CN)
    doc.add_heading(title, level=0)
    i = 0
    HEAD_SIZES = {1: 16, 2: 13.5, 3: 12, 4: 11}
    while i < len(lines):
        ln = lines[i].rstrip()
        s = ln.strip()
        if not s:
            i += 1
            continue
        if s.startswith('```'):
            i += 1
            buf = []
            while i < len(lines) and not lines[i].strip().startswith('```'):
                buf.append(lines[i])
                i += 1
            i += 1
            par = doc.add_paragraph()
            par.paragraph_format.left_indent = Pt(14)
            r = par.add_run('\n'.join(buf))
            set_font(r, 'Consolas', 9, False, (0x22, 0x22, 0x22))
            continue
        if re.match(r'^-{3,}$', s) or re.match(r'^\*{3,}$', s):
            par = doc.add_paragraph()
            r = par.add_run('_' * 46)
            set_font(r, EN, 9, False, (0xBB, 0xBB, 0xBB))
            par.alignment = WD_ALIGN_PARAGRAPH.CENTER
            i += 1
            continue
        m = re.match(r'^(#{1,6})\s+(.*)$', s)
        if m:
            lvl = min(len(m.group(1)), 4)
            txt = m.group(2)
            if lvl == 1:
                doc.add_heading(txt, level=1)
            else:
                h = doc.add_heading('', level=lvl)
                add_inline(h, txt, size=HEAD_SIZES[lvl], base_bold=True, color=HEAD_C)
            i += 1
            continue
        if s.startswith('|') and i + 1 < len(lines) and re.match(r'^\|[\s:|-]+\|$', lines[i + 1].strip()):
            header = [c.strip() for c in s.strip('|').split('|')]
            rows = []
            i += 2
            while i < len(lines) and lines[i].strip().startswith('|'):
                rows.append([c.strip() for c in lines[i].strip().strip('|').split('|')])
                i += 1
            t = doc.add_table(rows=1, cols=len(header))
            t.style = 'Light Grid Accent 1'
            for j, htxt in enumerate(header):
                cell = t.rows[0].cells[j]
                cell.text = ''
                add_inline(cell.paragraphs[0], htxt, size=9.5, base_bold=True)
                shade(cell, 'DCE6F1')
            for row in rows:
                cells = t.add_row().cells
                for j in range(len(header)):
                    val = row[j] if j < len(row) else ''
                    cells[j].text = ''
                    add_inline(cells[j].paragraphs[0], val, size=9)
            doc.add_paragraph()
            continue
        m = re.match(r'^(\s*)[-*]\s+(.*)$', ln)
        if m:
            indent = len(m.group(1)) // 2
            par = doc.add_paragraph(style='List Bullet')
            par.paragraph_format.left_indent = Pt(16 + indent * 14)
            add_inline(par, m.group(2))
            i += 1
            continue
        m = re.match(r'^(\s*)(\d+)\.\s+(.*)$', ln)
        if m:
            par = doc.add_paragraph(style='List Number')
            add_inline(par, m.group(3))
            i += 1
            continue
        if s.startswith('>'):
            par = doc.add_paragraph()
            par.paragraph_format.left_indent = Pt(20)
            add_inline(par, s.lstrip('> ').strip(), size=9.5, color=BQ)
            i += 1
            continue
        par = doc.add_paragraph()
        par.paragraph_format.space_after = Pt(4)
        add_inline(par, s)
        i += 1
    cp = doc.core_properties
    cp.title = title
    cp.author = AUTHOR
    cp.last_modified_by = AUTHOR
    cp.revision = 1
    cp.created = DOCX_STAMP
    cp.modified = DOCX_STAMP
    cp.comments = '\u7531 docs/ \u91cc\u7684 Markdown \u81ea\u52a8\u751f\u6210\uff08pipeline/md2docx.py\uff09'
    doc.save(docx_path)
    seal_docx(docx_path)
    return os.path.getsize(docx_path)

def main():
    if not os.path.isdir(OUT):
        os.makedirs(OUT)
    n = chr(48) + chr(49)
    sources = ['%s_\u9879\u76ee\u8bf4\u660e.md' % n,
               '%s_\u6570\u636e\u4e0eAI\u8bf4\u660e.md' % (chr(48) + chr(50)),
               '03_90\u5929\u9a8c\u8bc1\u8ba1\u5212.md',
               '04_\u6f14\u793a\u89c6\u9891\u9010\u5b57\u7a3f\u4e0e\u5206\u955c.md',
               '05_\u62a5\u540d\u8868\u4e0e\u63d0\u4ea4\u6e05\u5355.md',
               '06_\u4f5c\u54c1\u5e16\u4e0e\u53d1\u5e03\u8349\u7a3f.md']
    titles = {sources[0]: '\u73ca\u745a\u54e8\u5175 Reef Sentinel \u00b7 \u9879\u76ee\u8bf4\u660e',
              sources[1]: '\u73ca\u745a\u54e8\u5175 Reef Sentinel \u00b7 \u6570\u636e\u4e0e AI \u8bf4\u660e',
              sources[2]: '\u73ca\u745a\u54e8\u5175 Reef Sentinel \u00b7 90 \u5929\u9a8c\u8bc1\u8ba1\u5212',
              sources[3]: '\u73ca\u745a\u54e8\u5175 Reef Sentinel \u00b7 \u6f14\u793a\u89c6\u9891\u9010\u5b57\u7a3f\u4e0e\u5206\u955c',
              sources[4]: '\u73ca\u745a\u54e8\u5175 Reef Sentinel \u00b7 \u62a5\u540d\u8868\u4e0e\u63d0\u4ea4\u6e05\u5355',
              sources[5]: '\u73ca\u745a\u54e8\u5175 Reef Sentinel \u00b7 \u793e\u533a\u4f5c\u54c1\u5e16\u4e0e\u53d1\u5e03\u8349\u7a3f'}
    all_ok = True
    for src in sources:
        sp = os.path.join(DOCS, src)
        if not os.path.exists(sp):
            print('MISSING ' + src)
            all_ok = False
            continue
        dst = src.replace('.md', '.docx')
        size = convert(sp, os.path.join(OUT, dst), titles[src])
        print('OK  %-40s -> %-42s %d bytes' % (src, dst, size))
    print('ALL_OK' if all_ok else 'SOME_MISSING')

if __name__ == '__main__':
    main()