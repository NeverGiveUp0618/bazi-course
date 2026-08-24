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


# ── 题库主题分组 ────────────────────────────────────────────────
# 334 题平铺一屏太长，按主题折叠。分组规则：
#   ⭐ **只看 tags[0]** —— 题库整理时第一个标签就是主考点，一题只进一组，不重复出现。
#   ⭐ **顺序＝教材的学习顺序**（虚实→十神→作用方式→墓库→做功→象法→应期→分类断法），
#      不是按题数排——这样"学完哪章练哪组"能直接对上。
# ⚠️ 这张表是**唯一**的归组口径，别在 app.js 里另抄一份。
# ⚠️ 新加的标签若没被覆盖，build 会列出来并报错退出——别让它悄悄掉进"其他"。
QUIZ_TOPICS = [
    ('虚实·藏干·替身·禄', ['虚实', '藏干', '替身', '带象', '禄']),
    ('十神', ['十神']),
    ('合·自合·暗合·拱·三合', ['合', '自合', '暗合', '拱', '三合']),
    ('冲·刑·穿·破·伏吟', ['冲', '刑', '穿', '破', '伏吟', '伏吟/反吟']),
    ('墓库·空亡', ['墓库', '空亡']),
    ('制与做功·主宾', ['制/做功', '主宾', '禁忌', '入手四步', '气势']),
    ('象法·取象', ['象法', '阴阳象', '取数']),
    ('应期', ['应期']),
    ('财官·学业', ['财', '官', '学历']),
    ('婚姻', ['婚姻']),
    ('六亲', ['六亲']),
    ('灾祸·疾病·牢狱', ['车祸', '神煞', '牢狱', '寿命', '灾祸']),
    ('方法·综合', ['反推', '综合', '方法论']),
]
_TOPIC_OF = {t: name for name, ts in QUIZ_TOPICS for t in ts}


def assign_topics(items):
    """按主考点把每题归进一个主题；有没归上的直接报错，不许悄悄漏。"""
    miss = {}
    for it in items:
        head = it['tags'][0] if it['tags'] else ''
        name = _TOPIC_OF.get(head)
        if not name:
            miss.setdefault(head or '(无标签)', []).append(it['n'])
        it['topic'] = name or '未归类'
    if miss:
        lines = ['✗ 这些主考点没写进 QUIZ_TOPICS，先决定它们归哪一组：']
        for t, ns in sorted(miss.items(), key=lambda x: -len(x[1])):
            lines.append('    %-12s %d 题（如题 %s）' % (t, len(ns), ns[0]))
        sys.exit('\n'.join(lines))
    return [{'name': n, 'n': sum(1 for it in items if it['topic'] == n)}
            for n, _ in QUIZ_TOPICS]



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
    for b in blocks:
        m = re.match(r'### 【题(\d+)】(.*?)\n', b)
        if not m:
            continue
        seg = re.split(r'\n(?=##\s)', b)
        b = seg[0]                                   # 只保留题目本体
        if len(seg) > 1:
            intro += '\n\n' + '\n'.join(seg[1:])     # 分组标题/尾部章节收进说明
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


def main():
    if not os.path.isdir(SRC):
        sys.exit(f'找不到内容源目录：{SRC}')

    quiz = build_quiz()
    course = collect(os.path.join(SRC, '实用八字教材'),
                     r'^(0[1-9]|1[0-6])-(.+)\.md$', 'c')
    notes = collect(SRC, r'^八字(\d\d)-(.+)\.md$', 'n')

    index_md = read(os.path.join(SRC, '00-问题清单.md'))
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
    BASE = {'course': 16, 'notes': 16, 'quiz': 334, 'chart': 316, 'chai': 322}

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
