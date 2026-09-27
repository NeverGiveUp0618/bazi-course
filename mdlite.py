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
        # ⚠️ 表格里的 wiki 链接写作 [[目标#锚点\|显示文本]]——竖线被转义过，
        #    直接 partition('|') 会把 \ 留在 target 末尾，锚点因此匹配不上。
        raw = raw.replace('\\|', '|')
        target, _, label = raw.partition('|')
        # ⚠️ data-wiki 要给运行时按【标题纯文本】定位锚点（见 app.js gotoWiki），
        #    但这一步跑在 _INLINE_CODE/_QUOTE/_BOLD 之后，target 里已经混进了
        #    \x00C0\x00 代码占位与 <q>/<strong>/<span> 标记。
        #    不还原成纯文本，锚点就永远匹配不上目标标题（曾有 73 条锚点因此失效）。
        plain = target
        for _i, _c in enumerate(stash):
            plain = plain.replace(f'\x00C{_i}\x00', _c)
        plain = re.sub(r'<[^>]+>', '', plain)
        return ('<a class="wiki" data-wiki="%s">%s</a>'
                % (_html.escape(plain, quote=True), label or target))
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


# ---------- 讲解手册模式：标题清洗 ----------
# ⚠️ 源文件的标题里混着三种给"施工"看的东西，学习时全是噪音：
#      重要度 ⭐⭐ ／ 警示 ⚠️ ／ 补丁编号「一·B、」「3.2·C」／ 日期「（2026-08-28 补）」
#    手册模式把它们从标题文字里摘出来，各自变成一个小标记，标题只剩"这一节讲什么"。
# ⚠️⚠️ 锚点仍用**原始标题**生成 —— 站内几百处交叉指引靠它，绝不能跟着变。

_HM_MARK = re.compile(r'^((?:⭐|⚠️|📌|💡|❗|✅|❌|※|\s)+)')
# 补丁编号：中文序号带·B、阿拉伯多级带·C、圆圈数字、以及裸"判据"式小节
_HM_NUM = re.compile(
    r'^(?:'
    r'[一二三四五六七八九十]+(?:·[A-Z])?[、.．]'          # 一、 / 一·B、
    r'|\d+(?:\.\d+)*(?:·[A-Z])?[、.．]?(?=\s|\S)'      # 3.2 / 3.2·B
    r'|[①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮]'                          # ①
    r')\s*')
_HM_TAIL = re.compile(r'（([^（）]{1,60})）\s*$')
_HM_DATE = re.compile(r'\d{4}-\d{2}-\d{2}\s*')
# 尾注里剩下这些就是纯施工痕迹，整条丢掉
_HM_JUNK = re.compile(r'^(?:补|补齐|补充|补上|新增|已?订正|重写|改写|待补)?$')


def _hm_head(raw):
    """拆一行标题 → (正文, 星级, 警示级, 小字注, 是否次要)。"""
    t = raw.strip()
    minor = False

    # ① 前导标记
    m = _HM_MARK.match(t)
    stars = warn = 0
    if m:
        stars = m.group(1).count('⭐')
        warn = m.group(1).count('⚠️')
        t = t[m.end():].lstrip()

    # ② 补丁编号（丢掉，渲染时重新连续编号）
    t = _HM_NUM.sub('', t, count=1).lstrip()

    # ③ 标记可能夹在编号后面（「一·B、⭐⭐ 被漏掉的…」）
    m = _HM_MARK.match(t)
    if m:
        stars = max(stars, m.group(1).count('⭐'))
        warn = max(warn, m.group(1).count('⚠️'))
        t = t[m.end():].lstrip()

    # ④ 〔存疑〕/待查 → 次要
    if '存疑' in t or '待查' in t:
        minor = True
    t = re.sub(r'^〔(?:存疑|待查)〕\s*', '', t)

    # ⑤ 尾巴上的括号注：日期是施工痕迹，出处/提示留成小字
    note = ''
    m = _HM_TAIL.search(t)
    if m:
        orig = m.group(1)
        # ⚠️ 只有尾注里**真带日期**才算施工痕迹。不设这个前提，
        #    「（与 1.3 互补）」会被削成「与 1.3 互」——"互补"的补挨了刀。
        if _HM_DATE.search(orig):
            inner = _HM_DATE.sub('', orig).strip(' ，,、')
            inner = re.sub(r'\s*(?:补齐|补上|补充|补|新增|重写)$', '', inner).strip(' ，,、')
            t = t[:m.start()].rstrip()
            # 留下来的小字注只有一个用处：能回查原书。所以必须带页码或讲次，
            # 「核」「v课补入」「从面授」这类只说明我当时干了什么，对学习没用。
            inner = re.sub(r'^(?:补|补充|新增|补入)[，,、]\s*', '', inner)
            note = inner if re.search(r'p\s*\d|\d\s*讲', inner) else ''
        elif _HM_JUNK.match(orig.strip()):
            t = t[:m.start()].rstrip()          # 「（补）」这种纯痕迹
    return t.strip() or raw.strip(), stars, warn, note, minor


def _hm_render(lv, txt, anchor, seq):
    """手册模式的标题 HTML：序号色块 + 标题 + 重点/注意标 + 小字注。"""
    body, stars, warn, note, minor = _hm_head(txt)
    num = ''
    if lv == 2:
        seq[2] += 1
        seq[3] = 0
        num = str(seq[2])
    elif lv == 3:
        seq[3] += 1
        num = '%d.%d' % (seq[2], seq[3]) if seq[2] else str(seq[3])
    cls = ['mh', 'mh%d' % lv]
    if warn:
        cls.append('mhw')
    if minor:
        cls.append('mhm')
    bits = []
    if num:
        bits.append('<span class="mhn">%s</span>' % num)
    bits.append('<span class="mht">%s</span>' % _inline(body))
    if stars >= 2:
        bits.append('<span class="mhb mhb2">必背</span>')
    elif stars == 1:
        bits.append('<span class="mhb">重点</span>')
    if warn:
        bits.append('<span class="mhb mhbw">注意</span>')
    if minor:
        bits.append('<span class="mhb mhbm">存疑</span>')
    # ⚠️ data-raw 留着**清洗前**的整行标题：站内几百处 [[某章#某节]] 是按
    #    标题原文去页面里找的，标题一洗它们就全落空。跳转和 audit 都认这个属性。
    h = '<h%d id="%s" class="%s" data-raw="%s">%s</h%d>' % (
        lv, anchor, ' '.join(cls), _html.escape(txt.strip(), quote=True), ''.join(bits), lv)
    if note:
        h += '<div class="mhnote">%s</div>' % _inline(note)
    return h, body, minor


_HM_TIP = re.compile(r'^(?:\*\*)?((?:⚠️|⭐|📌|💡)+)')


def _hm_tip(para):
    """段首标记 → 提示框的类名。没有标记就返回 None。"""
    m = _HM_TIP.match(para.strip())
    if not m:
        return None
    mk = m.group(1)
    if '⚠️⚠️' in mk:
        return 'tipw2'
    if '⚠️' in mk:
        return 'tipw'
    if '⭐⭐' in mk:
        return 'tips2'
    if '⭐' in mk:
        return 'tips'
    return 'tipi'


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
    # ⚠️ 原书没给全的柱写作「？」或「—」（如题61 第一个盘）。这种不能硬排成盘，
    #    退回普通表格，让读者一眼看出这里原书就是缺的。
    if not all(c in _GAN for c in gan) or not all(c in _ZHI for c in zhi):
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
# ⚠️ `**` 必须成对包住单字（标日主用），不能写成 `\*{0,2}字\*{0,2}`——那样
#    「**【巨富那例】乙己己庚／巳丑未午**（己土日主）」里粗体的闭合标记会被
#    末字吃进盘中，剩下的 ** 就落单了。
_G1 = r'(?:\*\*[' + _GAN + r']\*\*|[' + _GAN + r'])'
_Z1 = r'(?:\*\*[' + _ZHI + r']\*\*|[' + _ZHI + r'])'
_GZ_RUN = re.compile(
    r'[（(]?\s*((?:' + _G1 + r'\s*){4})\s*[／/]\s*((?:' + _Z1 + r'\s*){4})\s*[）)]?')
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
    in_bold = False   # 盘常写在粗体中间（**命A（乙壬甲甲／未午子戌）—— 29岁亡**），
                      # 拆段会让 ** 落单，得把断开的粗体在两侧各自补齐
    for m in _INLINE_CHART.finditer(para):
        pick = lambda s: [c for c in s if c not in '*' and not c.isspace()]
        gan, zhi = pick(m.group(1)), pick(m.group(2))
        if len(gan) != 4 or len(zhi) != 4:
            continue
        head = para[last:m.start()].rstrip('：: 　')
        if in_bold:
            # 上一段把粗体补闭合了，这一段若原本就带着闭合标记，去掉免得凑成 ****
            head = head[2:] if head.startswith('**') else '**' + head
        if head.count('**') % 2:
            head += '**'
            in_bold = True
        else:
            in_bold = False
        if head.strip().strip('*'):
            out.append(('p', head))
        out.append(('chart', render_chart(gan, zhi)))
        last = m.end()
    if not out:
        return None
    tail = para[last:].lstrip('。，、 　')
    if in_bold:
        # 同上：「**【巨富那例】乙己己庚／巳丑未午**（己土日主）」这种，
        # 粗体的闭合标记就紧跟在盘后面，head 已补过，这里要吃掉它。
        tail = tail[2:] if tail.startswith('**') else '**' + tail
    if tail.strip().strip('*'):
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


def md2html(text, heading_offset=0, collect_headings=None, manual=False):
    """转换 markdown。

    heading_offset: 标题降级层数（章节内容嵌进页面时用）。
    collect_headings: 传入 list 则回填 (level, text, anchor, stars, minor)，用于生成目录。
    manual: 讲解手册模式 —— 标题去掉施工痕迹、重新连续编号、
            存疑/待查那一节连正文一起降成小字（见 _hm_head）。
    """
    lines = text.replace('\r\n', '\n').split('\n')
    out = []
    i = 0
    n = len(lines)
    anchors = {}
    seq = {2: 0, 3: 0}          # 手册模式的连续编号
    minor_open = [None]         # 正在收小字的那一节的层级

    def close_minor(lv=0):
        if minor_open[0] is not None and lv <= minor_open[0]:
            out.append('</div>')
            minor_open[0] = None

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
            a = anchor_for(m.group(2))
            if manual and 2 <= lv <= 4:
                close_minor(lv)
                h, clean, minor = _hm_render(lv, m.group(2), a, seq)
                out.append(h)
                _, stars, _w, _nt, _mn = _hm_head(m.group(2))
                if collect_headings is not None:
                    collect_headings.append((len(m.group(1)), clean, a, stars, minor))
                if minor:
                    out.append('<div class="minorbody">')
                    minor_open[0] = lv
                i += 1
                continue
            txt = _inline(m.group(2))
            if manual:
                close_minor(lv)
            if collect_headings is not None:
                ct = re.sub(r'<[^>]+>', '', txt)
                collect_headings.append((len(m.group(1)), ct, a, 0, False)
                                        if manual else (len(m.group(1)), ct, a))
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
            # ⚠️ 短标签单元格(序号/干支/是否)要禁止换行——否则窄屏下
            #    「（一）」会被拆成两行，第8章「制局十类」整张表都这样。
            #    只标短的：长文本仍要正常换行，否则会把表格撑到没法读。
            #    表格外层有 .tw(overflow-x:auto)，撑宽了是横向滚动，不挤压。
            for r in body:
                cells = []
                for c in r:
                    plain = re.sub(r'<[^>]+>', '', _inline(c))
                    cls = ' class="nw"' if len(plain.strip()) <= 6 else ''
                    cells.append(f'<td{cls}>{_inline(c)}</td>')
                t.append('<tr>' + ''.join(cells) + '</tr>')
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
        # 手册模式：段首的 ⚠️／⭐ 是作者标的"这段要紧"，正文里却和别的段一个样。
        # 给它们各自一个框，一屏扫下去就能分出"提醒"和"要点"。
        tip = _hm_tip(para) if manual else None
        if tip:
            out.append('<div class="tip %s">' % tip)
        parts = _lift_inline_chart(para)
        if parts:
            for kind, txt in parts:
                out.append(txt if kind == 'chart'
                           else '<p>' + _inline(txt).replace('&lt;br&gt;', '<br>') + '</p>')
        else:
            out.append('<p>' + _inline(para).replace('&lt;br&gt;', '<br>') + '</p>')
        if tip:
            out.append('</div>')

    if manual:
        close_minor(0)
    return '\n'.join(out)


def strip_md(s):
    """取纯文本，用于搜索索引与摘要。"""
    s = re.sub(r'```.*?```', ' ', s, flags=re.S)
    s = re.sub(r'<[^>]+>', ' ', s)
    s = re.sub(r'[`*>#|\[\]]', ' ', s)
    return re.sub(r'\s+', ' ', s).strip()
