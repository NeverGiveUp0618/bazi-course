#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""全站体检 —— 扫 data/*.js 产物，找渲染层的破绽 + 领域断言的硬错。

⭐ 2026-08-26 起不只查"渲染"了，还常驻校验**能由基准表推导的断言**：
   禄位（含丁未/癸丑半禄）· 长生位（分阴阳/不分阴阳两套）
   · 破的组别（只认子卯·卯午·午酉）· 穿/冲/暗合的组别
   · 十神（以日主为基准的格式化标注，548 处）
   ⚠️ 旬空没做：全站只有 1 处带盘的断言，样本太少，不值当；
      且「看空亡用年干推」这条口径本身还在待查（见问题清单）。
   起因：手工机检抓到「壬禄在子」「丙禄在寅」「辛长生在酉」「子酉破」等硬错，
   其中一处还是当天刚写的新内容 —— 这类错不该靠人工每次核。
⚠️ 这类检查必须配**豁免机制**（标了 存疑/订正/照录/传统 的放行）与**负向自测用例**，
   否则假红比漏报更难受（第一版上线时假红 9 处）。

    python3 audit.py          # 体检
    npm run audit

⭐ 为什么要有这个文件
2026-08-09 那次体检是临时写的脚本，跑完就丢了，靠它查出 5 个缺陷却没沉淀下来。
这套内容会一直加（用户新问一题就多一篇笔记），每加一次都该重扫一遍，
否则解析器在新格式上悄悄吞内容，没人会发现——`build.py` 的数量自检只看
"有几篇"，看不见"某篇里少了半段"。

体检和 smoke.js 分工不同：
    smoke.js  —— 交互对不对（路由、展开、搜索、筛选）
    audit.py  —— 内容渲染得对不对（残留、配平、盘、链接、上色）

⚠️ 检查项分两级：
    ERROR 一定是 bug，非零退出
    WARN  已知的合理例外（见各项注释里的说明），只提示不拦

⚠️ `<pre>` 里的东西一律不算——那是 ASCII 流程图，2162 个【】、776 个「」
   都是排版的一部分，去掉会乱。所有正文检查都先剥 <pre>。
"""
import io
import json
import os
import re
from html import unescape as _unescape
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, 'data')

GAN = '甲乙丙丁戊己庚辛壬癸'
ZHI = '子丑寅卯辰巳午未申酉戌亥'
# 与 mdlite.py 的 _WUXING、app.js 的 WX 是同一份映射的第三处副本，
# 这里只用来判断"该上色的字有没有上色"，不参与渲染。
WUXING = {}
for chars, name in [('甲乙寅卯', 'mu'), ('丙丁巳午', 'huo'),
                    ('戊己辰戌丑未', 'tu'), ('庚辛申酉', 'jin'), ('壬癸亥子', 'shui')]:
    for c in chars:
        WUXING[c] = name

errors, warns = [], []


def err(where, msg):
    errors.append(f'{where}｜{msg}')


def warn(where, msg):
    warns.append(f'{where}｜{msg}')


def load(name, var):
    p = os.path.join(DATA, name)
    if not os.path.exists(p):
        err('data', f'缺文件 {name}——先跑 build.py')
        return None
    s = io.open(p, encoding='utf-8').read()
    m = re.match(r'window\.' + var + r'=(.*);\s*$', s, re.S)
    if not m:
        err('data', f'{name} 不是预期的 window.{var}=… 格式')
        return None
    return json.loads(m.group(1))


def strip_pre(h):
    return re.sub(r'<pre[\s\S]*?</pre>', '', h)


# ---------------------------------------------------------------- 检查项

def check_markdown_residue(where, html):
    """未渲染的 markdown 残留＝解析器漏了某种写法。"""
    h = strip_pre(html)
    # 成对的 ** 没转成 <strong>
    n = len(re.findall(r'\*\*', h))
    if n:
        err(where, f'残留 {n} 个 ** 未渲染成粗体（附近：{_near(h, "**")}）')
    if '[[' in h or ']]' in h:
        err(where, f'残留 wiki 链接 [[…]]（附近：{_near(h, "[[")}）')
    # 行首 # 标题没转（放在 <p> 里的）
    m = re.search(r'<p>#{1,6}\s', h)
    if m:
        err(where, f'残留未渲染的标题：{h[m.start():m.start() + 40]}')
    # 表格竖线漏在正文里（转义过的 \| 是 Obsidian 的 [[a|b]]，另算）
    m = re.search(r'<p>[^<]*\|[^<]*\|', h)
    if m:
        warn(where, f'正文段落里有多个竖线，可能是没认出的表格：{h[m.start():m.start() + 50]}')
    if re.search(r'\\\|', h):
        err(where, '残留转义竖线 \\|——表格里的 [[目标|显示]] 被劈成两格了')


def _near(h, tok):
    i = h.find(tok)
    return h[max(0, i - 25):i + 25].replace('\n', ' ') if i >= 0 else ''


PAIRED = ['details', 'summary', 'blockquote', 'table', 'thead', 'tbody',
          'tr', 'td', 'th', 'ul', 'ol', 'li', 'p', 'strong', 'em', 'q',
          'div', 'span', 'mark', 'pre', 'code', 'h1', 'h2', 'h3', 'h4']


def check_tag_balance(where, html):
    """标签配平。浏览器容错会掩盖问题——题37 曾 1 开 2 闭，一直没暴露。"""
    for tag in PAIRED:
        opens = len(re.findall(r'<' + tag + r'(?:\s[^>]*)?>', html))
        closes = len(re.findall(r'</' + tag + r'>', html))
        if opens != closes:
            err(where, f'<{tag}> 开{opens} 闭{closes} 不配平')


def check_empty(where, html):
    if re.search(r'<pre><code[^>]*>\s*</code></pre>', html):
        err(where, '有空代码块——多半是分块正则劈开了 ``` 围栏')
    if re.search(r'<table>\s*</table>', html):
        err(where, '有空表格')
    if re.search(r'<blockquote>\s*</blockquote>', html):
        err(where, '有空引用块')


def check_charts(where, html):
    """四柱盘：柱数必须是 4，干支必须合法，且每个字都该有五行色。

    ⚠️ 题61 原书两柱写作「？」，那种认不出的会退回普通表格、不进这里，
       所以进到 .ichart 的就必须是完整合法的盘。
    """
    # ⚠️ .c 里嵌着 .p（年月日时），别用 <div class="c">(.*?)</div> 去切，
    #    非贪婪会停在 .p 的闭合标签上。直接按整柱的固定形状匹配。
    COL = re.compile(
        r'<div class="c( day)?"><div class="p">.</div>'
        r'<span class="a( w-\w+)?">(.)</span>'
        r'<span class="b( w-\w+)?">(.)</span></div>')
    for chart in re.findall(r'<div class="ichart[^"]*">[\s\S]*?</div></div>', html):
        cols = COL.findall(chart)
        raw = len(re.findall(r'<div class="c(?: day)?">', chart))
        if not raw:
            continue
        if len(cols) != raw:
            err(where, f'{raw} 柱里有 {raw - len(cols)} 柱形状不对（干支不是各一个字？）')
            continue
        if raw != 4:
            err(where, f'盘只有 {raw} 柱（应为4）')
            continue
        for _day, wg, g, wz, z in cols:
            for ch, wx, pool, name in ((g, wg, GAN, '天干'), (z, wz, ZHI, '地支')):
                if ch not in pool:
                    err(where, f'{name}位置出现「{ch}」')
                    continue
                want = WUXING.get(ch)
                got = (wx or '').replace(' w-', '')
                if got != want:
                    err(where, f'「{ch}」的五行色是 {got or "无"}，应为 {want}')
        if ' day"' not in chart and 'c day' not in chart:
            warn(where, '盘里没有标出日柱')


def check_qrefs(where, html, valid_q):
    for n in re.findall(r'class="qref"[^>]*data-q="(\d+)"', html):
        if int(n) not in valid_q:
            err(where, f'题号链接指向不存在的第 {n} 题')
    for n in re.findall(r'data-q="(\d+)"[^>]*class="qref"', html):
        if int(n) not in valid_q:
            err(where, f'题号链接指向不存在的第 {n} 题')


def _titles(html):
    """一篇文档里所有小标题的文本（h1–h6），供锚点校验做基准。
    ⚠️ 不能用 build 出来的 toc——它只收 lv<=3，h4 标题会被误判成"不存在"。
    ⚠️ 必须 unescape：html 里引号是 &quot;，而 md 原文是真引号，不还原就全对不上。"""
    out = set()
    for m in re.finditer(r'<h[1-6][^>]*>([\s\S]*?)</h[1-6]>', html):
        t = re.sub(r'<[^>]+>', '', m.group(1))
        out.add(_unescape(t).strip())
    return out


def check_wiki(where, html, chapters, notes, anc_nt=None, anc_ch=None):
    """wiki 链接的落点。app.js 的 gotoWiki 认不出的会退回搜索——不算错，
    但指向明确不存在的章号/篇号就是错。
    ⭐ 还要验 `[[某篇#某节]]` 里的**锚点**：改了节标题却忘了改引用，页面会跳到篇首，
       表面看不出错（2026-08-25 笔记17 重写后，问题清单 18 处锚点全失效就是这么漏过去的）。"""
    def _anchor(name, table, num, what):
        if '#' not in name or table is None:
            return
        base, anc = _unescape(name).split('#', 1)
        titles = table.get(num)
        if titles is None:
            return                     # 该篇没存 toc，跳过
        anc = anc.strip()
        if anc and anc not in titles:
            err(where, f'wiki 锚点在《{base}》里不存在：#{anc[:24]}（{what}改过标题？）')

    for name in re.findall(r'class="wiki"[^>]*data-wiki="([^"]*)"', html):
        m = re.match(r'^八字(\d+)', name)
        if m and int(m.group(1)) not in notes:
            err(where, f'wiki 指向不存在的笔记 八字{m.group(1)}')
            continue
        if m:
            _anchor(name, anc_nt, int(m.group(1)), '笔记')
            continue
        m2 = re.match(r'^(\d+)-', name)
        if m2:
            _anchor(name, anc_ch, int(m2.group(1)), '教材')
        if re.search(r'问题清单|总目录|学习路线|命例题库', name):
            continue
        m = re.match(r'^第?\s*(\d+)\s*[章篇]', name)
        if m and int(m.group(1)) not in chapters:
            err(where, f'wiki 指向不存在的第 {m.group(1)} 章')


INLINE_GZ = re.compile(r'<span class="gz-run">([\s\S]*?)</span>')


def check_inline_gz(where, html):
    """行内干支串里的字也要上色（表格/列表里的盘不提升，但仍要上色）。"""
    for run in INLINE_GZ.findall(html):
        for ch in re.findall(r'>([^<])<', run):
            if ch in WUXING and 'w-' not in run:
                err(where, f'行内干支串未上五行色：{run[:50]}')
                break


# ---------------------------------------------------------------- 主流程

# ── 可推导的干支断言：禄位／长生位 ─────────────────────────
# ⭐ 2026-08-26 加。起因：手工机检抓到 3 处硬错——
#   「壬禄在子」（壬禄在亥，子是壬的羊刃）、「丙禄在寅」（丙禄在巳，寅是丙的长生）、
#   「辛长生在酉」（酉是辛的禄）。这类断言【可由基准表推导】，就该让脚本盯着。
# ⚠️ 标了「存疑/订正/照录」的行是**故意保留的原文口径异常**，必须放行，否则天天假红。
LU = {'甲': '寅', '乙': '卯', '丙': '巳', '丁': '午', '戊': '巳',
      '己': '午', '庚': '申', '辛': '酉', '壬': '亥', '癸': '子'}
HALF_LU = {'丁': '未', '癸': '丑'}          # 半禄〔中级班 p25〕
CS = {'甲': '亥', '丙': '寅', '戊': '寅', '庚': '巳', '壬': '申',
      '乙': '午', '丁': '酉', '己': '酉', '辛': '子', '癸': '卯'}
CS_WX = {'木': '亥', '火': '寅', '土': '寅', '金': '巳', '水': '申'}  # 不分阴阳的统一长生
GAN_WX = {'甲': '木', '乙': '木', '丙': '火', '丁': '火', '戊': '土',
          '己': '土', '庚': '金', '辛': '金', '壬': '水', '癸': '水'}
_EXEMPT = ('存疑', '订正', '照录', '疑为', '应为', '不是禄', '假长生', '⚠️')


def _line_of(text, pos):
    """断言所在的那一行（用来判断有没有被标注豁免）。"""
    a = text.rfind('\n', 0, pos) + 1
    b = text.find('\n', pos)
    return text[a: b if b > 0 else len(text)]


def check_ganzhi_claims(where, html):
    """禄位／长生位这类**可由基准表推导**的断言。"""
    plain = re.sub(r'<[^>]+>', '', html)
    for m in re.finditer(r'([甲乙丙丁戊己庚辛壬癸])\s*(?:的)?禄\s*(?:在|位?在)\s*([子丑寅卯辰巳午未申酉戌亥])', plain):
        g, z = m.group(1), m.group(2)
        if LU[g] == z or HALF_LU.get(g) == z:
            continue
        if any(k in _line_of(plain, m.start()) for k in _EXEMPT):
            continue
        err(where, f'禄位错：「{g}禄在{z}」应为 {g}禄在{LU[g]}')
    for m in re.finditer(r'([甲乙丙丁戊己庚辛壬癸])\s*(?:的)?长生\s*(?:在|位?在)\s*([子丑寅卯辰巳午未申酉戌亥])', plain):
        g, z = m.group(1), m.group(2)
        if CS[g] == z or CS_WX[GAN_WX[g]] == z:
            continue
        if any(k in _line_of(plain, m.start()) for k in _EXEMPT):
            continue
        err(where, f'长生位错：「{g}长生在{z}」应为 {CS[g]}（或统一长生 {CS_WX[GAN_WX[g]]}）')


# ── 十神标注 ──────────────────────────────────────────
# ⭐ 2026-08-26 加。既有质检（2026-08-15）人工验过 320 处、抓到 1 处真错，
#    但一直没固化。现在常驻：拆解开头「X火日主（盘）。A＝正官｜B＝食神」这种
#    **格式化、以日主为基准**的标注，全部验算。
# ⚠️ 地支按【藏干本气】定阴阳五行——这正是视频课第 676 讲那三套阴阳里的第③套
#    （「天地阴阳诀，定十神」，原理是与藏干本气一致）。
_BEN = {'子': '癸', '丑': '己', '寅': '甲', '卯': '乙', '辰': '戊', '巳': '丙',
        '午': '丁', '未': '己', '申': '庚', '酉': '辛', '戌': '戊', '亥': '壬'}
_GWX = {'甲': '木', '乙': '木', '丙': '火', '丁': '火', '戊': '土',
        '己': '土', '庚': '金', '辛': '金', '壬': '水', '癸': '水'}
_GYANG = set('甲丙戊庚壬')
_SHENG = {'木': '火', '火': '土', '土': '金', '金': '水', '水': '木'}
_KE = {'木': '土', '土': '水', '水': '火', '火': '金', '金': '木'}
# 一个真名可以被哪些写法接受（合称、简写都算对）
_ALIAS = {
    '比肩': {'比肩', '比劫', '比'}, '劫财': {'劫财', '比劫', '劫', '羊刃'},
    '食神': {'食神', '食伤', '食'}, '伤官': {'伤官', '食伤', '伤'},
    '偏财': {'偏财', '财', '财才'}, '正财': {'正财', '财'},
    '七杀': {'七杀', '官杀', '杀'}, '正官': {'正官', '官', '官杀'},
    '偏印': {'偏印', '印', '枭', '枭印', '枭神'}, '正印': {'正印', '印', '枭印'},
}
_SS_NAMES = '比肩|劫财|食神|伤官|偏财|正财|七杀|正官|偏印|正印|比劫|食伤|官杀|枭印|财|官|印|杀|枭'


def _shishen(day, other):
    o = _BEN[other] if other in _BEN else other
    dw, ow = _GWX[day], _GWX[o]
    same = (day in _GYANG) == (o in _GYANG)
    if dw == ow:
        return '比肩' if same else '劫财'
    if _SHENG[dw] == ow:
        return '食神' if same else '伤官'
    if _KE[dw] == ow:
        return '偏财' if same else '正财'
    if _KE[ow] == dw:
        return '七杀' if same else '正官'
    return '偏印' if same else '正印'


def check_shishen(where, html):
    """拆解里以日主为基准的十神标注。"""
    plain = re.sub(r'<[^>]+>', '', html)
    # ⚠️ 换了太极点，同一个字的十神就变——整段豁免
    if re.search(r'太极点|换个角度看|站在.{1,4}角度|以.{1,3}为太极', plain):
        return
    for m in re.finditer(r'([甲乙丙丁戊己庚辛壬癸])[木火土金水]日主（([^）]*)）。([^\n]*)', plain):
        day, pan, rest = m.group(1), m.group(2), m.group(3)
        gans = re.findall(r'[甲乙丙丁戊己庚辛壬癸]', pan)
        if len(gans) == 4 and gans[2] != day:
            err(where, f'日主与盘不符：标作「{day}日主」，但盘的日干是「{gans[2]}」')
        for mm in re.finditer(r'([甲乙丙丁戊己庚辛壬癸子丑寅卯辰巳午未申酉戌亥、\s]{1,9})[＝=]\s*((?:%s)(?:\s*[/／]\s*(?:%s))*)'
                              % (_SS_NAMES, _SS_NAMES), rest):
            chars = re.findall(r'[甲乙丙丁戊己庚辛壬癸子丑寅卯辰巳午未申酉戌亥]', mm.group(1))
            claims = [c.strip() for c in re.split(r'[/／]', mm.group(2))]
            # ⭐「寅午＝食伤/财」是**一一对应**的合写，不是"两个字都是食伤又都是财"
            pairs = (list(zip(chars, claims)) if len(claims) == len(chars) and len(claims) > 1
                     else [(c, cl) for c in chars for cl in claims])
            for ch, claim in pairs:
                real = _shishen(day, ch)
                if claim not in _ALIAS[real]:
                    err(where, f'十神错：{day}日主，「{ch}＝{claim}」应为【{real}】')


# ⭐ 2026-08-26 续：穿／冲／暗合的组别（与 check_po 同类，247 处断言实测真错 0）
_PAIRS = {
    '穿': {frozenset(x) for x in ('子未', '丑午', '寅巳', '卯辰', '申亥', '酉戌')},
    '冲': {frozenset(x) for x in ('子午', '丑未', '寅申', '卯酉', '辰戌', '巳亥')},
    '暗合': {frozenset(x) for x in ('寅丑', '午亥', '卯申', '子巳')},
}
_ZHI = '子丑寅卯辰巳午未申酉戌亥'


def check_pairs(where, html):
    """地支两两关系的组别。
    ⚠️ 三个必须避开的断句坑（第一版全踩了）：
      ① 不跨行——「子：被午冲、被未穿\n亥：…」会被接成「未穿亥」
      ② 排除并列——「不喜寅穿亥冲」是"寅穿"＋"亥冲"，不是"寅穿亥"
      ③ 豁免看窗口不看单行——存疑说明常写在引用块外面
    """
    plain = re.sub(r'<[^>]+>', '', html)
    for name, ok in _PAIRS.items():
        # (?![冲穿破合刑]) 挡掉「寅穿亥冲」这类并列；[^\n]* 保证不跨行
        for m in re.finditer(r'([%s])\s*相?%s\s*([%s])(?![冲穿破合刑])' % (_ZHI, name, _ZHI), plain):
            a, b = m.group(1), m.group(2)
            if a == b or frozenset(a + b) in ok:
                continue
            if '\n' in plain[m.start():m.end()]:
                continue
            win = plain[max(0, m.start() - 150): m.end() + 150]
            if any(k in win for k in _EXEMPT + ('传统', '另一套', '口径', '笔误')):
                continue
            err(where, f'{name}的组别可疑：「{a}{name}{b}」不在本体系{name}的组里')


def check_po(where, html):
    """⚠️ 本体系「破」只有三组：子卯·卯午·午酉。
    2026-08-26 订正过一处全站性混用——把传统六破的「子酉」写进了本体系口径。"""
    plain = re.sub(r'<[^>]+>', '', html)
    # ⚠️ 排除「…丑午 | 破坏力…」这类表格边界消失造成的误接
    for m in re.finditer(r'([子丑寅卯辰巳午未申酉戌亥])\s*([子丑寅卯辰巳午未申酉戌亥])\s*相?破(?!坏)', plain):
        pair = frozenset(m.group(1) + m.group(2))
        if pair in ({frozenset('子卯'), frozenset('卯午'), frozenset('午酉')}):
            continue
        win = plain[max(0, m.start() - 120): m.end() + 120]
        if any(k in win for k in _EXEMPT + ('传统', '六破', '另一套', '刑冲破害')):
            continue
        err(where, f'破的组别可疑：「{m.group(1)}{m.group(2)}破」——本体系破只有 子卯·卯午·午酉')


# ── 考点标签的一致性（⭐ 2026-08-26 加）─────────────────────
# App 的筛选条全靠 tags。同义标签会把筛选切碎：
# 实测——既有用 `学历`、新题用 `学业`；既有 `入手四步`、新题 `入手`。
# 读者点「学业」只筛到一半，另一半藏在「学历」里，且没人会想到去点。
_SYNONYM = [           # 每组只许留一个；留的是第一个
    ('学业', '学历', '文凭'),
    ('入手', '入手四步', '入手三步'),
    ('制/做功', '做功', '制'),
    ('墓库', '库', '入墓'),
    ('六亲', '亲属'),
]


def check_tags(quiz):
    used = {}
    for it in quiz.get('items') or []:
        for t in it.get('tags') or []:
            used.setdefault(t, []).append(it['n'])
    for group in _SYNONYM:
        hit = [t for t in group if t in used]
        if len(hit) > 1:
            others = '、'.join(f'`{t}`(题{used[t][0]}等{len(used[t])}题)' for t in hit[1:])
            err('考点标签', f'同义标签并存，筛选会被切碎：应统一为 `{hit[0]}`，但还有 {others}')
    # ⚠️ 标签体系表在【题库自己的 intro】里（build 把首尾章节都收进 intro），
    #    别去问题清单/教材总目录里找——第一版就找错了地方，假红 25 条。
    intro = quiz.get('intro') or ''
    for t, ns in sorted(used.items(), key=lambda x: -len(x[1])):
        if len(ns) >= 5 and f'<code>{t}</code>' not in intro and f'`{t}`' not in intro:
            warn('考点标签', f'`{t}` 用了 {len(ns)} 题，但「考点标签体系」表里没登记')


# ── 反向链接：新内容别成孤岛（⭐ 2026-08-26 加）──────────────
# 只有出链没有入链 = 读者从既有内容那边永远发现不了它。
# 实测抓到：笔记18 除"问题清单"外无人引用（天地门三部曲里 17→19 有链、却没人链 18）；
#          讲口诀/歌诀的 4 处都没指向新写的笔记21。
# ⚠️ 不把「问题清单」算作入链——它链到所有笔记，算上就永远不会报。
def check_backlinks(course, notes, quiz):
    have_nt = {c['n'] for c in notes}
    have_ch = {c['n'] for c in course}
    in_nt = {n: set() for n in have_nt}
    in_ch = {n: set() for n in have_ch}
    srcs = ([(f'笔记{c["n"]}', c['html'], ('nt', c['n'])) for c in notes] +
            [(f'第{c["n"]}章', c['html'], ('ch', c['n'])) for c in course] +
            [('题库', (quiz.get('intro') or '') +
              ''.join((it.get(k) or '') for it in quiz.get('items') or []
                      for k in ('face', 'jie', 'chai')), (None, None))])
    for name, html, self_id in srcs:
        for m in re.finditer(r'data-wiki="([^"]+)"', html):
            tgt = m.group(1).split('#')[0].split('|')[0].strip()
            mn = re.match(r'八字(\d+)-', tgt)
            mc = re.match(r'(\d+)-', tgt)
            if mn and int(mn.group(1)) in have_nt:
                if self_id != ('nt', int(mn.group(1))):
                    in_nt[int(mn.group(1))].add(name)
            elif mc and int(mc.group(1)) in have_ch:
                if self_id != ('ch', int(mc.group(1))):
                    in_ch[int(mc.group(1))].add(name)
    for n, srcs_ in sorted(in_nt.items()):
        if not srcs_:
            warn('反向链接', f'笔记{n} 除问题清单外**没有任何入链**——'
                             f'读者从别处发现不了它，该在相关章节加个指引')
    for n, srcs_ in sorted(in_ch.items()):
        if not srcs_:
            warn('反向链接', f'第{n}章 没有任何入链')


def scan(where, html, ctx):
    check_markdown_residue(where, html)
    check_tag_balance(where, html)
    check_empty(where, html)
    check_charts(where, html)
    check_qrefs(where, html, ctx['q'])
    check_wiki(where, html, ctx['ch'], ctx['nt'], ctx.get('anc_nt'), ctx.get('anc_ch'))
    check_inline_gz(where, html)
    check_ganzhi_claims(where, html)
    check_po(where, html)
    check_shishen(where, html)
    check_pairs(where, html)


def main():
    course = load('data-course.js', 'DATA_COURSE')
    notes = load('data-notes.js', 'DATA_NOTES')
    quiz = load('data-quiz.js', 'DATA_QUIZ')
    meta = load('data-meta.js', 'DATA_META')
    index = load('data-index.js', 'DATA_INDEX')
    if errors:
        _report()
        return 1

    ctx = {
        'q': {i['n'] for i in quiz['items']},
        'ch': {c['n'] for c in course},
        'nt': {c['n'] for c in notes},
        # ⭐ 每篇的标题集合，供 check_wiki 验「[[某篇#某节]]」里的锚点是否真存在。
        #    2026-08-25 重写笔记17 时改了全部节标题，问题清单里 18 处锚点当场失效，
        #    而当时 build/smoke/audit 全绿——就是因为没人验锚点。加上这层。
        'anc_nt': {c['n']: _titles(c['html']) for c in notes},
        'anc_ch': {c['n']: _titles(c['html']) for c in course},
    }

    for c in course:
        scan(f'第{c["n"]}章', c['html'], ctx)
    for c in notes:
        scan(f'笔记{c["n"]}', c['html'], ctx)
    for it in quiz['items']:
        for part, label in (('face', '题面'), ('jie', '解'), ('chai', '拆解')):
            if it.get(part):
                scan(f'题{it["n"]}·{label}', it[part], ctx)
    scan('学习路线', meta.get('outline', ''), ctx)
    scan('问题清单', index or '', ctx)

    check_tags(quiz)
    check_backlinks(course, notes, quiz)

    # 首屏包不该再长胖——问题清单曾把它撑到 124KB
    meta_kb = os.path.getsize(os.path.join(DATA, 'data-meta.js')) / 1024
    if meta_kb > 20:
        err('首屏包', f'data-meta.js 涨到 {meta_kb:.1f}KB——大块内容该拆出去按需加载')

    # 吸顶盘的数据字段：charts 里的每个盘都要有 4 干 4 支
    for it in quiz['items']:
        for c in it.get('charts') or []:
            if len(c.get('gan', '')) != 4 or len(c.get('zhi', '')) != 4:
                err(f'题{it["n"]}', f'吸顶盘数据不是四柱：{c.get("gan")}/{c.get("zhi")}')
            for ch in c.get('gan', ''):
                if ch not in GAN:
                    err(f'题{it["n"]}', f'吸顶盘天干位出现「{ch}」')
            for ch in c.get('zhi', ''):
                if ch not in ZHI:
                    err(f'题{it["n"]}', f'吸顶盘地支位出现「{ch}」')

    n_docs = len(course) + len(notes) + len(quiz['items'])
    print(f'== 全站体检 == 扫了 {n_docs} 个文档'
          f'（{len(course)}章 / {len(notes)}篇 / {len(quiz["items"])}题）')
    return _report()


def _report():
    if warns:
        print(f'\n⚠️  {len(warns)} 条提示（已知例外，不拦）：')
        for w in warns[:30]:
            print('   -', w)
        if len(warns) > 30:
            print(f'   …另有 {len(warns) - 30} 条')
    if errors:
        print(f'\n✗ {len(errors)} 处缺陷：')
        for e in errors[:60]:
            print('   -', e)
        if len(errors) > 60:
            print(f'   …另有 {len(errors) - 60} 处')
        return 1
    print('\n✓ 体检通过，没有渲染缺陷')
    return 0


def selftest():
    """⚠️ 体检脚本自己也要被体检。

    一个只会打印「通过」的脚本毫无价值——正则写错、结构变了，它照样全绿。
    （这站踩过一模一样的坑：吸顶盘第一版在 jsdom 里走 fallback 分支，
      4 条断言全过，功能其实一次都没执行。）

    所以这里给每个检查项喂一段**故意坏掉**的 HTML，要求它必须报错。
    改了任何检查逻辑，先跑 `python3 audit.py --selftest`。
    """
    global errors, warns
    ctx = {'q': {1, 2}, 'ch': {1, 2}, 'nt': {1, 2},
           'anc_nt': {1: {'一、真有这一节'}}, 'anc_ch': {}}
    ok_chart = ('<div class="ichart"><div class="cols">' +
                ''.join(f'<div class="c{" day" if p == "日" else ""}">'
                        f'<div class="p">{p}</div>'
                        f'<span class="a w-mu">乙</span>'
                        f'<span class="b w-mu">卯</span></div>'
                        for p in '年月日时') +
                '</div></div>')

    cases = [
        ('未渲染的粗体', '<p>这里有 **强调** 没转</p>'),
        ('残留 wiki 链接', '<p>见 [[八字01-某题]]</p>'),
        ('残留标题', '<p>## 这是标题</p>'),
        ('转义竖线', '<table><tr><td>a\\|b</td></tr></table>'),
        ('标签不配平', '<div><p>少一个闭合</div>'),
        ('空代码块', '<pre><code></code></pre>'),
        ('空表格', '<table></table>'),
        # ⭐ 2026-08-26 加：禄位／长生位／破的组别（都是可由基准表推导的断言）
        ('禄位错', '<p>壬禄在子，故为通根</p>'),
        ('长生位错', '<p>辛长生在酉</p>'),
        ('破的组别错', '<p>子酉破，故不生</p>'),
        ('十神错', '<p>甲木日主（甲甲甲甲／子子子子）。子＝正财｜甲＝比肩</p>'),
        ('日主与盘不符', '<p>丙火日主（壬甲乙甲／子辰子午）。子＝正官</p>'),
        ('穿的组别错', '<p>寅穿午，故不吉</p>'),
        ('冲的组别错', '<p>子冲寅，主动</p>'),

        ('盘少一柱', ok_chart.replace(
            '<div class="c"><div class="p">时</div>'
            '<span class="a w-mu">乙</span><span class="b w-mu">卯</span></div>', '')),
        ('天干位出现地支', ok_chart.replace('<span class="a w-mu">乙</span>',
                                            '<span class="a w-mu">卯</span>', 1)),
        ('五行色标错', ok_chart.replace('<span class="a w-mu">乙</span>',
                                        '<span class="a w-huo">乙</span>', 1)),
        ('干支没上色', ok_chart.replace('<span class="a w-mu">乙</span>',
                                        '<span class="a">乙</span>', 1)),
        ('题号链接指向不存在的题',
         '<a class="qref" data-q="999">【999】</a>'),
        ('wiki 指向不存在的笔记',
         '<a class="wiki" data-wiki="八字99-无此篇">x</a>'),
        ('wiki 锚点在该篇里不存在',
         '<a class="wiki" data-wiki="八字1-某篇#根本没有这一节">x</a>'),
        ('wiki 指向不存在的章',
         '<a class="wiki" data-wiki="第99章">x</a>'),
    ]

    print('== 体检脚本自检 == 每项喂一段坏 HTML，必须能报出来\n')
    bad = 0
    for name, html in cases:
        errors, warns = [], []
        scan('自检', html, ctx)
        if errors:
            print(f'  ✓ {name} → {errors[0].split("｜", 1)[1][:52]}')
        else:
            print(f'  ✗ {name} → 没报错！这项检查是哑的')
            bad += 1

    # 反过来：好的内容不能被误报
    errors, warns = [], []
    scan('自检', '<p>正常段落</p>' + ok_chart, ctx)
    if errors:
        print(f'  ✗ 正常内容被误报：{errors[0]}')
        bad += 1
    else:
        print('  ✓ 正常内容不误报')

    # ── 考点标签：同义并存必须报错 ──
    errors, warns = [], []
    check_tags({'items': [{'n': 1, 'tags': ['学业']}, {'n': 2, 'tags': ['学历']}], 'intro': ''})
    if errors:
        print(f"  ✓ 标签·同义并存 → {errors[0].split(chr(65372), 1)[1][:56]}")
    else:
        bad += 1
        print('  ✗ 标签·同义并存 → 没报错！这项检查是哑的')
    errors, warns = [], []
    check_tags({'items': [{'n': i, 'tags': ['学业']} for i in range(9)], 'intro': ''})
    if warns:
        print(f"  ✓ 标签·未登记 → {warns[0].split(chr(65372), 1)[1][:56]}")
    else:
        bad += 1
        print('  ✗ 标签·未登记 → 没报！这项检查是哑的')

    # ── 反向链接：孤岛必须报 ──
    errors, warns = [], []
    check_backlinks(
        course=[{'n': 1, 'html': '<a data-wiki="八字01-甲">x</a>'}],
        notes=[{'n': 1, 'html': ''}, {'n': 18, 'html': '<a data-wiki="八字01-甲">x</a>'}],
        quiz={'intro': '', 'items': []})
    if any('笔记18' in w for w in warns):
        print('  ✓ 反向链接·孤岛 → 笔记18 无入链被抓到')
    else:
        bad += 1
        print('  ✗ 反向链接·孤岛 → 没报！这项检查是哑的')
    errors, warns = [], []
    check_backlinks(
        course=[{'n': 1, 'html': '<a data-wiki="八字18-乙">x</a>'}],
        notes=[{'n': 18, 'html': ''}],
        quiz={'intro': '', 'items': []})
    if any('笔记18' in w for w in warns):
        bad += 1
        print('  ✗ 反向链接·有入链却报了 → 误报')
    else:
        print('  ✓ 反向链接·有入链正确放行')

    # ⭐ 负向用例：这些【必须不报错】。
    #   假红比漏报更难受——2026-08-26 加禄位/破的检查时，一上来就把
    #   「传统六破引文」和表格里「丑午 | 破坏力」误接成错，全站假红 9 处。
    negatives = [
        ('标了存疑的原文口径异常', '<p>原文作「子酉破」，本站无此破，照录标存疑</p>'),
        ('传统六破的引文', '<p>传统六破：子酉相破，丑辰相破，寅亥相破，未戌相破</p>'),
        ('表格边界消失的「破坏力」', '<p>子未 · 卯辰 · 酉戌 · 丑午 破坏力最厉害</p>'),
        ('半禄（丁见未·癸见丑）', '<p>丁禄在未为半禄，癸禄在丑亦然</p>'),
        ('不分阴阳的统一长生', '<p>金统一长生在巳，故庚长生在巳</p>'),
        # ⭐ 十神：一一对应的合写、合称、换太极点，都必须放行
        ('十神·一一对应的合写', '<p>壬水日主（甲庚壬辛／寅午辰亥）。寅午＝食伤/财</p>'),
        ('十神·合称（官杀/食伤/比劫）', '<p>乙木日主（己丙乙丁／酉子酉亥）。酉＝七杀｜丙、丁＝伤官/食神｜子、亥＝印</p>'),
        ('十神·换太极点整段豁免', '<p>以酉为太极点：癸酉＝劫财＋伤官。壬水日主（癸甲壬壬／寅酉申寅）。酉＝劫财</p>'),
        # ⭐ 组别检查的三个断句坑
        ('组别·并列不是一组', '<p>妻星得位，不喜寅穿亥冲，宫不稳定</p>'),
        ('组别·不跨行', '<p>子：被午冲、被未穿\n亥：被巳冲</p>'),
        ('组别·存疑说明在附近', '<p>⚠️ 笔记内部自相矛盾，判为笔误。原文：大运己巳，巳冲申，大运就定性了</p>'),
    ]
    for name, html in negatives:
        errors, warns = [], []
        check_ganzhi_claims('负向', html)
        check_po('负向', html)
        check_shishen('负向', html)
        check_pairs('负向', html)
        if errors:
            bad += 1
            print(f'  ✗ {name} → ⚠️ 误报了：{errors[0][1]}')
        else:
            print(f'  ✓ {name} → 正确放行')

    print(f'\n{"✗ " + str(bad) + " 项有问题" if bad else "✓ 全部检查项都真的会抓错，且不误报"}')
    return 1 if bad else 0


if __name__ == '__main__':
    if '--selftest' in sys.argv:
        sys.exit(selftest())
    sys.exit(main())
