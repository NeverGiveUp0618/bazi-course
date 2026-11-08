#!/usr/bin/env python3
"""build.py 之后运行：把 data/ 里的整包数据拆成「列表(meta) + 按需正文」放进 data-s/，线上走 data-s/。
data/ 保持完整（smoke.js / audit.py 仍读它）。内容零改动，只是分包。"""
import os, io, json, re

ROOT = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(ROOT, 'data')
OUT = os.path.join(ROOT, 'data-s')


def load(name, var):
    s = io.open(os.path.join(SRC, name), encoding='utf-8').read()
    return json.loads(s[len('window.%s=' % var):].rstrip().rstrip(';'))


def dump(name, text):
    with io.open(os.path.join(OUT, name), 'w', encoding='utf-8') as f:
        f.write(text)


def js(obj):
    return json.dumps(obj, ensure_ascii=False, separators=(',', ':'))


QBODY = ['face', 'jie', 'chai', 'text', 'charts', 'chart', 'jieLabel']
CHUNK = 40


def run():
    os.makedirs(OUT, exist_ok=True)
    for f in os.listdir(OUT):
        if f.endswith('.js'):
            os.remove(os.path.join(OUT, f))
    sizes = {}
    # 教材 / 笔记：meta 留 html=''、text=''，正文各一个文件
    for src, var, key in (('data-course.js', 'DATA_COURSE', 'course'), ('data-notes.js', 'DATA_NOTES', 'notes')):
        docs = load(src, var)
        meta = []
        for d in docs:
            dump('body-%s.js' % d['id'], "(window.DATA_BODY=window.DATA_BODY||{})[%s]=%s;\n" % (js(d['id']), js({'html': d['html'], 'text': d['text']})))
            m = dict(d)
            m['html'] = ''
            m['text'] = ''
            meta.append(m)
        dump(src, 'window.%s=%s;\n' % (var, js(meta)))
        sizes[key] = len(docs)
    # 题库：items 分块
    q = load('data-quiz.js', 'DATA_QUIZ')
    items = q['items']
    for i, it in enumerate(items):
        it['bk'] = i // CHUNK
        it['lz'] = 1
    chunks = {}
    for it in items:
        body = {k: it.pop(k) for k in QBODY if k in it}
        chunks.setdefault(it['bk'], {})[it['n']] = body
        it['face'] = ''
        it['jie'] = ''
        it['chai'] = ''
        it['text'] = ''
        it['charts'] = []
    for bk, d in chunks.items():
        dump('qbody-%d.js' % bk, "(window.DATA_QBODY=window.DATA_QBODY||{});Object.assign(window.DATA_QBODY,%s);\n" % js(d))
    dump('data-quiz.js', 'window.DATA_QUIZ=%s;\n' % js(q))
    tot = sum(os.path.getsize(os.path.join(OUT, f)) for f in os.listdir(OUT))
    big = max(os.path.getsize(os.path.join(OUT, f)) for f in os.listdir(OUT) if f.startswith('data-'))
    print('分包完成：data-s/ 共 %d 个文件，%.1f MB；列表类最大 %.0f KB' % (len(os.listdir(OUT)), tot / 1048576, big / 1024))


if __name__ == '__main__':
    run()
