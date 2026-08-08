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
# 〔初级班 p13〕〔例题解 p16-17〕—— 出处标注，渲染成可辨识的小标签。
# ⚠️ 不能死抠「p+数字」结尾：实际还有〔…p55（红字）〕〔…p20 两例〕〔…例9〕〔存疑〕
#    等变体，抠格式会漏掉近百处。凡〔〕一律当标注渲染。
_SRC = re.compile(r'〔([^〕\n]{1,60})〕')
# 【21】【题18】—— 题号交叉引用，做成可点击
_QREF = re.compile(r'【题?\s*(\d{1,3})】')
# 【劫财】【竞争者】—— 强调短语，与 ** 加粗重复，只留高亮不留括号
_HL = re.compile(r'【([^】\n]{1,40})】')
# 「原文原话」—— 标示这句是原文。去掉括号改用颜色区分，减少视觉噪音。
# ⚠️ 不能限长：原文引用常跨好几行（段落内已被合并成 <br>），设 200 字上限会漏掉
#    最长的那批。`[^」]` 已保证匹配到最近的闭引号，非贪婪不会跨引文错配。
_QUOTE = re.compile(r'「([^」]+?)」')


def _inline(s):
    """处理行内语法。先摘出行内码，避免其中的 ** 被当粗体。"""
    stash = []

    def keep(m):
        stash.append(m.group(1))
        return f'\x00C{len(stash) - 1}\x00'

    s = _INLINE_CODE.sub(keep, s)
    s = _html.escape(s, quote=False)
    # 干支串要在 _BOLD 之前上色：串里的 ** 是标日主的，一旦被转成 <strong>
    # 就断了正则，认不出整串了。
    s = _color_gz_inline(s)
    # 括号本身是视觉噪音，一律换成样式；内部标记留给后面的 _BOLD 处理。
    s = _SRC.sub(lambda m: f'<span class="src">{m.group(1)}</span>', s)
    s = _QREF.sub(lambda m: f'<a class="qref" data-q="{m.group(1)}">题{m.group(1)}</a>', s)
    s = _HL.sub(lambda m: f'<em class="hl">{m.group(1)}</em>', s)
    s = _QUOTE.sub(lambda m: f'<q class="yw">{m.group(1)}</q>', s)
    s = _BOLD.sub(lambda m: f'<strong>{m.group(1)}</strong>', s)
    s = _LINK.sub(lambda m: f'<a href="{m.group(2)}" target="_blank" rel="noopener">{m.group(1)}</a>', s)
    # [[目标]] 或 Obsidian 的 [[目标|显示文本]]——后者只显示竖线后半段
    def _wiki(m):
        raw = m.group(1)
        target, _, label = raw.partition('|')
        return ('<a class="wiki" data-wiki="%s">%s</a>'
                % (_html.escape(target, quote=True), label or target))
    s = _WIKI.sub(_wiki, s)
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

# 干支 → 五行，用来上色。用户要求「按五行本色看」，比按干支分色好认。
_WUXING = {}
for _ch, _w in (('甲乙寅卯', 'mu'), ('丙丁巳午', 'huo'), ('戊己辰戌丑未', 'tu'),
                ('庚辛申酉', 'jin'), ('壬癸亥子', 'shui')):
    for _c in _ch:
        _WUXING[_c] = _w


def wx(c):
    """返回该字的五行 class 后缀；认不出返回空串。"""
    return _WUXING.get(c, '')


def gz_span(c, cls):
    w = wx(c)
    return '<span class="%s%s">%s</span>' % (
        cls, (' w-' + w) if w else '', _html.escape(c))


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
    return render_chart(gan, zhi, label)


def render_chart(gan, zhi, label=''):
    """四柱盘的统一 HTML。app.js 里的吸顶条用同一套结构与 class。"""
    cols = ''.join(
        '<div class="c%s"><div class="p">%s</div>%s%s</div>'
        % (' day' if k == 2 else '', p, gz_span(gan[k], 'a'), gz_span(zhi[k], 'b'))
        for k, p in enumerate(_PILLARS))
    lb = ('<span class="lb">%s造</span>' % _html.escape(label)) if label else ''
    return '<div class="ichart">%s<div class="cols">%s</div></div>' % (lb, cols)


_GAN = '甲乙丙丁戊己庚辛壬癸'
_ZHI = '子丑寅卯辰巳午未申酉戌亥'
# 简写盘：四干／四支，加粗的是日主，斜杠可能全角或半角。
# ⚠️ 括号必须是可选的——全站 190 处里只有 85 处带括号，另外 105 处是
#    「**命例·库冲成巨富**：乙己**己**庚／巳丑未午」这种裸串（教材第8章尤其多）。
_GZ_RUN = re.compile(
    r'[（(]?\s*((?:\*{0,2}[' + _GAN + r']\*{0,2}\s*){4})\s*[／/]\s*'
    r'((?:\*{0,2}[' + _ZHI + r']\*{0,2}\s*){4})\s*[）)]?')
_INLINE_CHART = _GZ_RUN


def _gz_seg(seg, cls):
    """把一串干（或支）逐字上五行色，保留原本的 ** 强调（多半是标日主）。"""
    out = []
    for m in re.finditer(r'(\*\*)?([' + _GAN + _ZHI + r'])(\*\*)?', seg):
        c = m.group(2)
        s = gz_span(c, cls)
        if m.group(1) and m.group(3):
            s = '<strong>%s</strong>' % s
        out.append(s)
    return ''.join(out)


def _color_gz_inline(s):
    """表格 / 列表 / 行内出现的干支串只上色，不提升成块级盘——那会撑破结构。"""
    return _GZ_RUN.sub(
        lambda m: '<span class="gz-run">%s<i>／</i>%s</span>'
                  % (_gz_seg(m.group(1), 'a'), _gz_seg(m.group(2), 'b')), s)


def _lift_inline_chart(para):
    """把段落里的行内简写盘提升成块级四柱盘。

    原文这类盘写成「**丙火日主**（辛丁**丙**己／亥酉**辰**亥）。**辛＝正财**…」，
    八个字连排还要自己数哪柱是哪柱，很难认。提成正规盘后前后文字自然断成两段：
    先说日主 → 看盘 → 再讲十神，读起来反而更顺。
    返回 [(kind, text)] 序列，kind 为 'p' 或 'chart'。
    """
    out = []
    last = 0
    for m in _INLINE_CHART.finditer(para):
        pick = lambda s: [c for c in s if c not in '*' and not c.isspace()]
        gan, zhi = pick(m.group(1)), pick(m.group(2))
        if len(gan) != 4 or len(zhi) != 4:
            continue
        head = para[last:m.start()].rstrip('：: 　')
        if head.strip():
            out.append(('p', head))
        out.append(('chart', render_chart(gan, zhi)))
        last = m.end()
    if not out:
        return None
    tail = para[last:].lstrip('。，、 　')
    if tail.strip():
        out.append(('p', tail))
    return out


def _cells(line):
    """拆表格行。⚠️ 必须先保护 `\\|` 转义——Obsidian 的 [[目标|显示文本]] 写在
    表格里时会转义成 `\\|`，直接按 | 切会把一个链接劈成两个单元格。"""
    line = line.strip()
    if line.startswith('|'):
        line = line[1:]
    if line.endswith('|'):
        line = line[:-1]
    line = line.replace('\\|', '\x00P\x00')
    return [c.strip().replace('\x00P\x00', '|') for c in line.split('|')]


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
        para = '<br>'.join(buf)
        parts = _lift_inline_chart(para)
        if parts:
            for kind, txt in parts:
                out.append(txt if kind == 'chart'
                           else '<p>' + _inline(txt).replace('&lt;br&gt;', '<br>') + '</p>')
        else:
            out.append('<p>' + _inline(para).replace('&lt;br&gt;', '<br>') + '</p>')

    return '\n'.join(out)


def strip_md(s):
    """取纯文本，用于搜索索引与摘要。"""
    s = re.sub(r'```.*?```', ' ', s, flags=re.S)
    s = re.sub(r'<[^>]+>', ' ', s)
    s = re.sub(r'[`*>#|\[\]]', ' ', s)
    return re.sub(r'\s+', ' ', s).strip()
