#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""全站体检 —— 扫 data/*.js 产物，找渲染层的破绽。

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

def scan(where, html, ctx):
    check_markdown_residue(where, html)
    check_tag_balance(where, html)
    check_empty(where, html)
    check_charts(where, html)
    check_qrefs(where, html, ctx['q'])
    check_wiki(where, html, ctx['ch'], ctx['nt'], ctx.get('anc_nt'), ctx.get('anc_ch'))
    check_inline_gz(where, html)


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

    print(f'\n{"✗ " + str(bad) + " 项检查是哑的" if bad else "✓ 全部检查项都真的会抓错"}')
    return 1 if bad else 0


if __name__ == '__main__':
    if '--selftest' in sys.argv:
        sys.exit(selftest())
    sys.exit(main())
