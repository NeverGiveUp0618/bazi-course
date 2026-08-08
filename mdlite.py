# -*- coding: utf-8 -*-
"""零依赖 Markdown → HTML 转换器。

只覆盖本项目 markdown 实际用到的语法，不求通用：
标题 / 粗体 / 行内码 / 围栏代码块 / 表格 / 引用 / 列表 / 分隔线 /
原生 details-summary / [[wiki链接]] / 〔出处 pN〕

之所以不用 python-markdown：系统 Python 是 externally-managed，
装库要么 --break-system-packages 要么建 venv，两者都会让 build.py
在别的机器/别的时间跑不起来。内容是自己写的、语法可控，自己转最稳。
"""
import re
import html as _html

# ---------- 行内 ----------

_INLINE_CODE = re.compile(r'`([^`\n]+)`')
_BOLD = re.compile(r'\*\*(.+?)\*\*', re.S)
_WIKI = re.compile(r'\[\[([^\]]+)\]\]')
_LINK = re.compile(r'\[([^\]]+)\]\(([^)]+)\)')
# 〔初级班 p13〕〔例题解 p16-17〕—— 出处标注，渲染成可辨识的小标签
_SRC = re.compile(r'〔([^〕]*?p\d[\d\-,\s]*)〕')


def _inline(s):
    """处理行内语法。先摘出行内码，避免其中的 ** 被当粗体。"""
    stash = []

    def keep(m):
        stash.append(m.group(1))
        return f'\x00C{len(stash) - 1}\x00'

    s = _INLINE_CODE.sub(keep, s)
    s = _html.escape(s, quote=False)
    s = _SRC.sub(lambda m: f'<span class="src">〔{m.group(1)}〕</span>', s)
    s = _BOLD.sub(lambda m: f'<strong>{m.group(1)}</strong>', s)
    s = _LINK.sub(lambda m: f'<a href="{m.group(2)}" target="_blank" rel="noopener">{m.group(1)}</a>', s)
    s = _WIKI.sub(
        lambda m: f'<a class="wiki" data-wiki="{_html.escape(m.group(1), quote=True)}">{m.group(1)}</a>', s)
    for i, c in enumerate(stash):
        s = s.replace(f'\x00C{i}\x00', f'<code>{_html.escape(c, quote=False)}</code>')
    return s


# ---------- 块级 ----------

_H = re.compile(r'^(#{1,6})\s+(.*)$')
_HR = re.compile(r'^\s*---+\s*$')
_UL = re.compile(r'^(\s*)[-*]\s+(.*)$')
_OL = re.compile(r'^(\s*)(\d+)\.\s+(.*)$')
_RAW = re.compile(r'^\s*</?(details|summary|div|br|hr|p|span|img)\b', re.I)
_TABLE_SEP = re.compile(r'^\s*\|[\s:|-]+\|\s*$')


_PILLARS = ['年', '月', '日', '时']


def _four_pillar(head, body):
    """把「空|年|月|日|时」这种四柱表渲染成紧凑盘，好让它在正文里吸顶。

    教材与笔记里散着 111 个命例盘，读到讲解时盘早滚没了。渲染成紧凑盘 +
    CSS sticky，滚动时当前命例的盘会一直钉在顶栏下，直到下一个盘接替它。
    认不出的（缺干支、只有一行的占位表）退回普通表格，不硬套。
    """
    if len(head) != 5 or head[0].strip():
        return None
    if [h.strip() for h in head[1:]] != _PILLARS:
        return None
    if len(body) < 2 or len(body[0]) < 5 or len(body[1]) < 5:
        return None
    clean = lambda xs: [c.replace('**', '').strip() for c in xs[1:5]]
    gan, zhi = clean(body[0]), clean(body[1])
    if not all(gan) or not all(zhi):
        return None
    label = body[0][0].replace('**', '').strip('（）() ') or ''
    cols = ''.join(
        '<div class="c%s"><div class="p">%s</div><div class="a">%s</div>'
        '<div class="b">%s</div></div>'
        % (' day' if k == 2 else '', p, _html.escape(gan[k]), _html.escape(zhi[k]))
        for k, p in enumerate(_PILLARS))
    lb = ('<span class="lb">%s造</span>' % _html.escape(label)) if label else ''
    return '<div class="ichart">%s<div class="cols">%s</div></div>' % (lb, cols)


def _cells(line):
    line = line.strip()
    if line.startswith('|'):
        line = line[1:]
    if line.endswith('|'):
        line = line[:-1]
    return [c.strip() for c in line.split('|')]


def md2html(text, heading_offset=0, collect_headings=None):
    """转换 markdown。

    heading_offset: 标题降级层数（章节内容嵌进页面时用）。
    collect_headings: 传入 list 则回填 (level, text, anchor)，用于生成目录。
    """
    lines = text.replace('\r\n', '\n').split('\n')
    out = []
    i = 0
    n = len(lines)
    anchors = {}

    def anchor_for(t):
        base = re.sub(r'[^\w一-鿿]+', '-', re.sub(r'<[^>]+>', '', t)).strip('-') or 'h'
        k = anchors.get(base, 0)
        anchors[base] = k + 1
        return base if k == 0 else f'{base}-{k}'

    while i < n:
        line = lines[i]

        # 围栏代码块：原样保留（拆解里的流程图全靠它）
        if line.lstrip().startswith('```'):
            lang = line.lstrip()[3:].strip()
            i += 1
            buf = []
            while i < n and not lines[i].lstrip().startswith('```'):
                buf.append(lines[i])
                i += 1
            i += 1
            cls = f' class="lang-{_html.escape(lang, quote=True)}"' if lang else ''
            out.append(f'<pre{cls}><code>{_html.escape(chr(10).join(buf), quote=False)}</code></pre>')
            continue

        # 原生 HTML 行（details/summary 等）原样透传
        if _RAW.match(line):
            out.append(line.strip())
            i += 1
            continue

        if not line.strip():
            i += 1
            continue

        if _HR.match(line):
            out.append('<hr>')
            i += 1
            continue

        m = _H.match(line)
        if m:
            lv = min(6, len(m.group(1)) + heading_offset)
            txt = _inline(m.group(2))
            a = anchor_for(m.group(2))
            if collect_headings is not None:
                collect_headings.append((len(m.group(1)), re.sub(r'<[^>]+>', '', txt), a))
            out.append(f'<h{lv} id="{a}">{txt}</h{lv}>')
            i += 1
            continue

        # 表格：当前行含 | 且下一行是分隔行
        if '|' in line and i + 1 < n and _TABLE_SEP.match(lines[i + 1]):
            head = _cells(line)
            i += 2
            body = []
            while i < n and lines[i].strip().startswith('|'):
                body.append(_cells(lines[i]))
                i += 1
            ic = _four_pillar(head, body)
            if ic:
                out.append(ic)
                continue
            t = ['<div class="tw"><table>', '<thead><tr>']
            t += [f'<th>{_inline(c)}</th>' for c in head]
            t.append('</tr></thead><tbody>')
            for r in body:
                t.append('<tr>' + ''.join(f'<td>{_inline(c)}</td>' for c in r) + '</tr>')
            t.append('</tbody></table></div>')
            out.append(''.join(t))
            continue

        # 引用块：原文引文，本项目里语义很重（必须与我的重建区分开）
        if line.lstrip().startswith('>'):
            buf = []
            while i < n and (lines[i].lstrip().startswith('>') or
                             (lines[i].strip() and buf and not _RAW.match(lines[i]))):
                if not lines[i].lstrip().startswith('>'):
                    break
                buf.append(re.sub(r'^\s*>\s?', '', lines[i]))
                i += 1
            inner = md2html('\n'.join(buf), heading_offset)
            out.append(f'<blockquote>{inner}</blockquote>')
            continue

        # 列表
        if _UL.match(line) or _OL.match(line):
            ordered = bool(_OL.match(line))
            tag = 'ol' if ordered else 'ul'
            items = []
            while i < n:
                mu, mo = _UL.match(lines[i]), _OL.match(lines[i])
                if not (mu or mo):
                    break
                items.append(_inline((mo.group(3) if mo else mu.group(2))))
                i += 1
            out.append(f'<{tag}>' + ''.join(f'<li>{x}</li>' for x in items) + f'</{tag}>')
            continue

        # 段落：连续非空、非块起始的行合成一段
        buf = [line]
        i += 1
        while i < n and lines[i].strip() and not (
                _RAW.match(lines[i]) or _H.match(lines[i]) or _HR.match(lines[i]) or
                lines[i].lstrip().startswith(('```', '>', '|')) or
                _UL.match(lines[i]) or _OL.match(lines[i])):
            buf.append(lines[i])
            i += 1
        out.append('<p>' + _inline('<br>'.join(buf)).replace('&lt;br&gt;', '<br>') + '</p>')

    return '\n'.join(out)


def strip_md(s):
    """取纯文本，用于搜索索引与摘要。"""
    s = re.sub(r'```.*?```', ' ', s, flags=re.S)
    s = re.sub(r'<[^>]+>', ' ', s)
    s = re.sub(r'[`*>#|\[\]]', ' ', s)
    return re.sub(r'\s+', ' ', s).strip()
