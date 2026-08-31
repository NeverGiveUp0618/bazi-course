# -*- coding: utf-8 -*-
"""把 content/ 里的 markdown 编译成站点数据。

⭐ 内容源唯一性：markdown 是源，data/*.js 是产物。
   永远只在 content/ 里改内容，然后重跑本脚本。不要直接改 data/*.js。

用法：  python3 build.py
"""
import io
import json
import os
import re
import sys

from mdlite import md2html, strip_md

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'content')
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')


def read(p):
    with io.open(p, encoding='utf-8') as f:
        return f.read()


def write_js(name, varname, obj):
    os.makedirs(OUT, exist_ok=True)
    p = os.path.join(OUT, name)
    body = json.dumps(obj, ensure_ascii=False, separators=(',', ':'))
    with io.open(p, 'w', encoding='utf-8') as f:
        f.write(f'window.{varname}={body};\n')
    return os.path.getsize(p)


# ---------------------------------------------------------------- 题库

def split_details(s):
    """从 s 中切出第一个顶层 <details>…</details>。

    返回 (before, inner, after)；没有则 (s, None, '')。
    必须计数匹配——题库里拆解是嵌在解里面的第二层。
    """
    start = s.find('<details')
    if start < 0:
        return s, None, ''
    depth = 0
    i = start
    while i < len(s):
        if s.startswith('<details', i):
            depth += 1
            i += 8
        elif s.startswith('</details>', i):
            depth -= 1
            i += 10
            if depth == 0:
                return s[:start], s[start:i], s[i:]
        else:
            i += 1
    return s[:start], s[start:], ''


def strip_summary(block):
    """剥掉最外层 <details><summary>…</summary> 和结尾 </details>，返回 (summary, body)。"""
    m = re.match(r'\s*<details[^>]*>\s*<summary>(.*?)</summary>', block, re.S)
    summ = re.sub(r'<[^>]+>', '', m.group(1)).strip() if m else ''
    body = block[m.end():] if m else block
    body = re.sub(r'</details>\s*$', '', body)
    return summ, body


GAN = '甲乙丙丁戊己庚辛壬癸'
ZHI = '子丑寅卯辰巳午未申酉戌亥'

CHART_RE = re.compile(
    r'\|\s*\|\s*年\s*\|\s*月\s*\|\s*日\s*\|\s*时\s*\|\s*\n'
    r'\|[-\s|]+\|\s*\n'
    r'\|\s*(乾|坤)\s*\|(.+?)\|\s*\n'
    r'\|\s*\|(.+?)\|\s*\n')


def all_charts(b):
    """采集题中全部四柱盘，供页面做「吸顶盘」用（不改动正文）。

    多盘题要能分辨哪个是哪个，标签取表格前最近一行里的「命A/命B」；
    题61 的第二个盘前是 `### 🔍 对照命B：…` 标题行，所以不能只认粗体。
    """
    out = []
    clean = lambda xs: [x.strip().replace('**', '') for x in xs.split('|') if x.strip()]
    ms = list(CHART_RE.finditer(b))
    for i, m in enumerate(ms):
        gan, zhi = clean(m.group(2)), clean(m.group(3))
        if len(gan) != 4 or len(zhi) != 4:
            continue
        # 原书没给全的柱写作「？」，不能当盘（题61 第一个盘就是）
        if not all(c in GAN for c in gan) or not all(c in ZHI for c in zhi):
            continue
        label = ''
        if len(ms) > 1:
            prev = [l for l in b[:m.start()].rstrip().split('\n') if l.strip()]
            if prev:
                lm = re.search(r'(命[A-Za-z甲乙丙丁一二三])', prev[-1])
                label = lm.group(1) if lm else '盘%d' % (i + 1)
        out.append({'g': m.group(1), 'gan': gan, 'zhi': zhi, 'label': label})
    return out


def parse_chart(b):
    """抽出四柱盘做题头的大盘；抽不出就原样留在正文里。

    ⚠️ 只有【恰好一个】盘时才抽。题21/35 这类双命对照题有两个盘，
    抽走第一个会让正文里「命A」标题底下空一块，而题头那个盘又没有
    「这是命A」的标注——两头都读不通。多盘题一律整表留在正文。
    """
    ms = list(CHART_RE.finditer(b))
    if len(ms) != 1:
        return None, b
    m = ms[0]
    clean = lambda xs: [x.strip().replace('**', '') for x in xs.split('|') if x.strip()]
    gan, zhi = clean(m.group(2)), clean(m.group(3))
    if len(gan) != 4 or len(zhi) != 4:
        return None, b
    if not all(c in GAN for c in gan) or not all(c in ZHI for c in zhi):
        return None, b
    return ({'g': m.group(1), 'gan': gan, 'zhi': zhi},
            b[:m.start()] + b[m.end():])


# ── 题库分组：按资料篇目 ────────────────────────────────────────
# ⭐ 分组＝**题目来自哪一册资料**，组名和编号与手上那些 PDF 一一对应
#    （01财运篇 / 03初级班 / 04断命例题解 / 05高级班 / 06官运篇 / 07婚姻篇 …）。
#    想练哪篇就点哪组——这是用户找题时真正的心智模型。
# ⚠️ **知识点维度不放在这里**：考点标签（合/穿/墓库/象法…）已经有独立的筛选条，
#    两个维度互补，别在分组上再做一遍。
#
# 归属依据（都已核对过题目里的出处引用，不是凭标题猜）：
#   · 「三、题库正文」第一批 20 题 —— 出处全是〔例题解 pN〕→ 归 04
#   · 三·C/三·D 穿专项 —— 出处是〔实战技巧完整版 pN〕→ 归 16
#   · 三·O/三·P 标题里自带册号（19、神煞…／18、地支四墓库…）
# ⚠️ 内容源里新加 `## 三·X 某某` 分组而这里没登记，build 直接报错退出。
QUIZ_SOURCES = [
    # ⭐ 顺序＝**学习顺序**，用户 2026-08-24 定的三段（别再按资料册号重排）：
    #    ①初→中→高三个班（成体系的完整课程，先走这条主线）
    #    ②不带「篇」的技巧类（通用打法，主线之后补）
    #    ③带「篇」的主题类（按要断的事分，用到哪篇翻哪篇）
    # 括号里是资料册号——**只作溯源，不再参与排序**，别拿它当前缀写进组名。
    ('初级班',         ['三·K', '三·L', '三·M']),          # 册 03
    ('中级班',         ['三·AA']),                          # 册 15
    ('高级班',         ['三·N']),                           # 册 05
    # ⭐ 2026-08-26 新增：大老师v课实录（v 666-765，我自己的听课笔记，
    #    不是 21 册 PDF 里的任何一册）。放在三个班之后——它是面授实录，
    #    默认你已经过完初中高级班，讲的是"同一条口诀为什么会失灵"这一层。
    ('v课实录',     ['三·AB', '三·AC', '三·AD', '三·AE', '三·AF', '三·AG', '三·AH']),

    ('断命例题解',     ['三、题库正文', '三·G', '三·H', '三·I', '三·J']),  # 册 04
    ('实战技巧完整版', ['三·B', '三·C', '三·D', '三·E', '三·F']),          # 册 16
    ('四墓库专项',     ['三·P']),                           # 册 18
    ('神煞断法',       ['三·O']),                           # 册 19
    # ⭐ 2026-08-28 新增：干支互通专著（＝大任老资料里的 `六爻.pdf`，同一文件）。
    #    归"技巧类"——它是专讲【天干与地支怎么作用】的一本书（带象/自合/禄与原身），
    #    是通用打法不是主题篇。
    ('干支互通专著',   ['三·AI']),                          # 册 21

    ('财运篇',         ['三·S']),                           # 册 01
    ('官运篇',         ['三·T']),                           # 册 06
    ('婚姻篇',         ['三·Q', '三·R']),                   # 册 07
    ('六亲篇',         ['三·V']),                           # 册 10
    ('职业篇',         ['三·W']),                           # 册 14
    ('学历篇',         ['三·Z']),                           # 册 13
    ('疾病篇',         ['三·U']),                           # 册 08
    ('车祸篇',         ['三·X']),                           # 册 02
    ('牢狱篇',         ['三·W2']),                          # 册 09
    ('寿命篇',         ['三·Y']),                           # 册 12
]

# ⚠️ 资料共 21 册，题库尚未覆盖的：11《实战技巧》（与 16 完整版是否同源待查）、
#    15《中级班》、17《刑冲破害的使用方法》、20《2012 高级班彩色笔记》、
#    21《干支互通的条件和方法》——这几册一题未挖，不是漏归组。


def topic_of(group):
    """题目所在的 `## 分组标题` → 它出自哪一册资料。
    ⚠️ 「三·W」是「三·W2」的前缀——必须**长的 key 先匹配**，
       否则牢狱篇（三·W2）会被职业篇（三·W）整组吞掉。"""
    cand = sorted(((k, name) for name, keys in QUIZ_SOURCES for k in keys),
                  key=lambda x: -len(x[0]))
    for k, name in cand:
        if group.startswith(k):
            return name
    return None


def assign_topics(items):
    miss = {}
    for it in items:
        name = topic_of(it.get('group', ''))
        if not name:
            miss.setdefault(it.get('group', '(无)'), []).append(it['n'])
        it['topic'] = name or '未归类'
        it.pop('group', None)
    if miss:
        lines = ['✗ 这些分组没登记进 QUIZ_SOURCES，先确认它们出自哪一册资料：']
        for g, ns in sorted(miss.items(), key=lambda x: -len(x[1])):
            lines.append('    %-34s %d 题（如题 %s）' % (g[:34], len(ns), ns[0]))
        sys.exit('\n'.join(lines))
    # ⭐ 显示用的连续序号 seq：**按上面的组顺序**从 1 排到底，组内保持内容源原序。
    #    it['n'] 是内容源里的题号（build 分块、题间互引的锚点，**不连续也不可改**），
    #    seq 只管"从上往下数第几个"——用户要的是这个，两者别混用。
    order = {n: i for i, (n, _) in enumerate(QUIZ_SOURCES)}
    pos = {id(it): i for i, it in enumerate(items)}   # 别用 items.index（O(n²)＋按值比较）
    for seq, it in enumerate(sorted(items, key=lambda x: (order[x['topic']], pos[id(x)])), 1):
        it['seq'] = seq
    return [{'name': n, 'n': sum(1 for it in items if it['topic'] == n)}
            for n, _ in QUIZ_SOURCES]


def build_quiz():
    raw = read(os.path.join(SRC, '实用八字教材', '99-命例题库.md'))
    # ⚠️ 必须要求题号是【数字】。文件末尾「扩充方法」的模板代码块里有一行
    #    `### 【题N】一句话结论`，分块正则不认识代码块边界，会照样在那儿切一刀：
    #    代码块被劈开、前半段成了未闭合的空块，后半段因「题N」非数字被整段丢弃。
    first = re.search(r'### 【题\d', raw).start()
    intro = raw[:first]

    # ⚠️ 题目之间夹着「## 三·B 实战技巧完整版」这类分组标题，题目之后还有
    #    「## 四、按考点检索」「## 五、覆盖情况与继续扩充」。它们都会被 split
    #    并进前一道题——尾部那些尤其糟，扩充模板里的 <details> 与 ``` 示例会把
    #    题92 的解析搅乱（曾产出一个空代码块，且把整章塞进题面）。
    #    题目一律是 ### 三级标题，所以每块里遇到 ## 二级标题就不再属于这道题。
    blocks = re.split(r'\n(?=### 【题\d)', raw[first:])

    items = []
    cur_group = '三、题库正文'      # 第一批题在 `## 三、题库正文` 之下（该标题在 first 之前）
    for b in blocks:
        m = re.match(r'### 【题(\d+)】(.*?)\n', b)
        if not m:
            continue
        seg = re.split(r'\n(?=##\s)', b)
        b = seg[0]                                   # 只保留题目本体
        this_group = cur_group                       # 本题属于「它前面」那个分组
        if len(seg) > 1:
            intro += '\n\n' + '\n'.join(seg[1:])     # 分组标题/尾部章节收进说明
            # 块尾带出的 ## 标题是**下一批**题的分组（可能连着好几个）
            for x in seg[1:]:
                mm = re.match(r'##\s+(.+)', x)
                if mm:
                    cur_group = mm.group(1).strip()
        num = int(m.group(1))
        head = m.group(2)
        tags = re.findall(r'`([^`]+)`', head)
        title = re.sub(r'`[^`]+`', '', head).replace('⭐', '').strip()
        stars = head.count('⭐')
        rest = b[m.end():]

        # ⚠️ 题头吸顶盘只能取自【题面】。题61 的题面盘原书没给全（写作「？」），
        #    而拆解里有个对照命B——若从整题采集，题头会挂出命B，跟题面讲的命A对不上。
        face, det, tail = split_details(rest)
        charts = all_charts(face + tail)
        n_charts = len(charts)
        chart, face = parse_chart(face)

        jie_html = chai_html = ''
        summ = ''
        if det:
            summ, body = strip_summary(det)
            if '🔍' in summ:
                # 题37 这类：原文的解写在题面的引用块里，没有独立「解」层，
                # 唯一的 details 就是拆解本身。
                chai_html = md2html(body, heading_offset=2)
                summ = ''
            else:
                # 标准结构：解里面嵌着 🔍 拆解，摘出来单独成层
                pre, inner, post = split_details(body)
                if inner and '🔍' in inner[:200]:
                    _, cbody = strip_summary(inner)
                    chai_html = md2html(cbody, heading_offset=2)
                    body = pre + post
                jie_html = md2html(body, heading_offset=2)

        # 反推题＝原书根本没给解，练习时无答案可对（现为 19/20/53/67/77/90）。
        # ⚠️ 三条弯路都走过，别再改回去：
        #   ① 不能看 summary 叫不叫「提示」——题47/48/49 的解就写在「提示」里；
        #   ② 不能看解层有无 blockquote——题37/76/92 的解写在题面的引用块里；
        #   ③ 不能只搜「反推」二字——题11「留给你反推的"部分"」是整题有解、
        #      仅一条留白，那种仍要走对答案流程。
        # 所以只认下面这批精确短语，宁可漏判也不误判。
        # ⚠️ 必须先剥掉 ** 再匹配——短语中间常夹着粗体标记，
        #    如题19 的「属于**留给学习者反推**的题」。
        plain = b.replace('**', '')
        no_answer = any(k in plain for k in (
            '属于留给学习者反推', '留给反推', '留作大家思考',
            '留给你反推的题', '属反推题', '属可反推题', '戛然而止'))

        items.append({
            'n': num,
            'title': title,
            'tags': tags,
            'star': stars,
            'chart': chart,      # 仅单盘题有：题头大盘
            'nCharts': n_charts,  # 盘总数：多盘题>1，筛「有完整盘」看这个
            'charts': charts,     # 全部盘（含命A/命B标签），吸顶条用
            'face': md2html(face + tail, heading_offset=2),
            'jieLabel': summ or '解',
            'jie': jie_html,
            'chai': chai_html,
            'noAnswer': no_answer,
            'text': strip_md(b)[:600],
            'group': this_group,
        })

    items.sort(key=lambda x: x['n'])
    topics = assign_topics(items)
    tags = {}
    for it in items:
        for t in it['tags']:
            tags[t] = tags.get(t, 0) + 1
    return {
        'intro': md2html(intro, heading_offset=1),
        'items': items,
        'tags': sorted(tags.items(), key=lambda x: -x[1]),
        'topics': topics,
    }


# ---------------------------------------------------------------- 教材 / 笔记

def build_docs(files, kind):
    docs = []
    for path, num, title in files:
        s = read(path)
        # 去掉正文首行大标题（页面自己有标题栏）
        s = re.sub(r'^#\s+.*?\n', '', s, count=1)
        heads = []
        html = md2html(s, heading_offset=0, collect_headings=heads)
        docs.append({
            'id': f'{kind}{num}',
            'n': num,
            'title': title,
            'html': html,
            'toc': [{'lv': lv, 't': t, 'a': a} for lv, t, a in heads if lv <= 3],
            'text': strip_md(s),
            'chars': len(s),
        })
    return docs


def collect(dirpath, pattern, kind):
    out = []
    for fn in sorted(os.listdir(dirpath)):
        m = re.match(pattern, fn)
        if not m:
            continue
        out.append((os.path.join(dirpath, fn), int(m.group(1)), m.group(2)))
    return build_docs(out, kind)


def _inline(text):
    """只要行内那一层（加粗／wiki／【题N】／干支上色），不要外面的 <p>。"""
    h = md2html(text, heading_offset=0).strip()
    m = re.fullmatch(r'<p>([\s\S]*)</p>', h)
    return m.group(1) if m else h


def build_desk():
    """断命台：把 content/断命台.md 解析成逐步检查清单。

    源里的写法（刻意做得极简，方便随时增删条目）：
        ## 0 · 摆正立场      → 一步
        紧随的普通行          → 这一步的「一句话过关」
        - 条目               → 普通检查项
        !! 条目              → ⭐ 红线（漏了结论就全错），前端标红
        @ 目标               → 这一步回哪一章（wiki 名）
    """
    src = read(os.path.join(SRC, '断命台.md'))
    steps, cur = [], None
    for raw in src.split('\n'):
        line = raw.rstrip()
        m = re.match(r'^##\s+(\S+)\s*·\s*(.+)$', line)
        if m:
            cur = {'n': m.group(1), 'title': m.group(2).strip(), 'ask': '', 'items': [], 'link': ''}
            steps.append(cur)
            continue
        if cur is None or not line.strip():
            continue
        if line.startswith('@ '):
            cur['link'] = line[2:].strip()
        elif line.startswith('!! '):
            cur['items'].append({'t': _inline(line[3:].strip()), 'red': 1})
        elif line.startswith('- '):
            cur['items'].append({'t': _inline(line[2:].strip()), 'red': 0})
        elif not cur['ask']:
            cur['ask'] = _inline(line.strip())
    # 顶部说明（第一个 ## 之前的引用块）
    intro = md2html(src.split('## ')[0], heading_offset=0)
    return {'intro': intro, 'steps': steps}


def main():
    if not os.path.isdir(SRC):
        sys.exit(f'找不到内容源目录：{SRC}')

    quiz = build_quiz()
    course = collect(os.path.join(SRC, '实用八字教材'),
                     r'^(0[1-9]|1[0-6])-(.+)\.md$', 'c')
    notes = collect(SRC, r'^八字(\d\d)-(.+)\.md$', 'n')

    index_md = read(os.path.join(SRC, '00-问题清单.md'))
    desk = build_desk()
    outline = read(os.path.join(SRC, '实用八字教材', '00-教材总目录与学习路线.md'))

    meta = {
        'name': '命理精讲',
        'built': __import__('time').strftime('%Y-%m-%d %H:%M'),
        'counts': {
            'course': len(course),
            'notes': len(notes),
            'quiz': len(quiz['items']),
            'quizChart': sum(1 for i in quiz['items'] if i['nCharts']),
            'quizChai': sum(1 for i in quiz['items'] if i['chai']),
        },
        # outline 只有 6KB，留在首屏包里；index（问题清单四张表）70KB，
        # 首页根本用不到，单独出一个文件按需加载。
        'outline': md2html(outline, heading_offset=0),
    }

    sizes = [
        ('data-course.js', write_js('data-course.js', 'DATA_COURSE', course)),
        ('data-notes.js', write_js('data-notes.js', 'DATA_NOTES', notes)),
        ('data-quiz.js', write_js('data-quiz.js', 'DATA_QUIZ', quiz)),
        ('data-index.js', write_js('data-index.js', 'DATA_INDEX',
                                   md2html(index_md, heading_offset=0))),
        ('data-meta.js', write_js('data-meta.js', 'DATA_META', meta)),
        # 断命台是「实操工具」，首页用不到 ⇒ 与问题清单一样按需加载，别撑首屏包
        ('data-desk.js', write_js('data-desk.js', 'DATA_DESK', desk)),
    ]

    print('== 构建完成 ==')
    for k, v in meta['counts'].items():
        print(f'  {k:12} {v}')
    print()
    for name, size in sizes:
        print(f'  {name:18} {size/1024:8.1f} KB')
    print(f'  {"合计":18} {sum(s for _, s in sizes)/1024:8.1f} KB')

    # ===== 完整性自检 =====
    # 这套内容会持续加（用户新问一题就多一篇笔记／多一道命例），
    # 所以基线是**下限**不是等号：
    #   少了 → 报错退出（解析器吞内容了，这才是自检要防的）
    #   多了 → 只提示一句，顺手把基线抬上去，别拦着新内容进站。
    # ⚠️ 曾经写成 `!= 14`，加第15篇笔记会直接构建失败。
    BASE = {'course': 16, 'notes': 22, 'quiz': 463, 'chart': 445, 'chai': 445}

    nc = sum(1 for i in quiz['items'] if i['nCharts'])
    chai = sum(1 for i in quiz['items'] if i['chai'])
    got = {'course': len(course), 'notes': len(notes),
           'quiz': len(quiz['items']), 'chart': nc, 'chai': chai}
    NAME = {'course': '教材章数', 'notes': '笔记篇数', 'quiz': '题库题数',
            # 74 而非 75：题61 的题面盘原书没给全（两柱写作「？」），不算有完整盘
            'chart': '有完整四柱的题', 'chai': '带拆解的题'}

    bad, grew = [], []
    for k, base in BASE.items():
        if got[k] < base:
            bad.append(f'{NAME[k]}少了：基线{base}，实得{got[k]}')
        elif got[k] > base:
            grew.append(f'{NAME[k]} {base} → {got[k]}')

    # 有解＝有独立「解」层，或解写在题面的引用块里（题37/76/92 那种）
    miss = [i['n'] for i in quiz['items']
            if not i['jie'] and not i['noAnswer'] and '<blockquote>' not in i['face']]
    if miss:
        bad.append(f'这些题既无解也未标为反推题：{miss}')
    # 反推题只查"这6道必须还在"，新加的反推题不算错
    na = [i['n'] for i in quiz['items'] if i['noAnswer']]
    lost = [n for n in (19, 20, 53, 67, 77, 90) if n not in na]
    if lost:
        bad.append(f'原有反推题不见了：{lost}（实得 {na}）')

    if grew and not bad:
        print('\n📈 内容变多了：' + '，'.join(grew))
        print(f'   记得把 build.py 的 BASE 抬到 ' +
              '{' + ', '.join(f"'{k}': {got[k]}" for k in BASE) + '}')
        print('   还有 mingli-home 看板的分母（它读 bazi_course_counts，通常会自动跟上）')

    if bad:
        print('\n⚠️  自检未通过：')
        for b in bad:
            print('   -', b)
        sys.exit(1)
    print('\n✓ 自检通过')


if __name__ == '__main__':
    main()
