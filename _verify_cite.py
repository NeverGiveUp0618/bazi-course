# -*- coding: utf-8 -*-
"""_verify_cite.py —— 引文出处核对（2026-08-30 全量核查时写的，此前八字项目没有这层）

做什么：扫全站 `〔大任 · 03初级班 p13〕` 这类出处标记，把**紧贴它的引用块**里的原文
拿去该 PDF 的该页（±1 页）找，找不到就报出来。

⚠️ 三个必须注意的（都是踩出来的）：
  1. **PDF 文本与站内引文要用同一套归一化**——第一版 PDF 侧只去空白、站内侧去标点，
     结果 34% 假红。
  2. **只认紧贴的引用块**（出处行本身或它上面连续的 `>` 行）。隔着段落去猜配对，必错。
  3. 站内引文常用「……」把原文几段接起来 ⇒ 按省略号切开，任一段命中即算命中。

跑法：`python3 _verify_cite.py`（需要本机有 民八字/大任老资料，缺了就跳过）
⭐ **页码口径（用户 2026-08-30 裁定）：一律按 PDF 文件页序**——原书页脚印的页码与 PDF 页序
   偏移不固定（+1~+5 都出现过），所以只认文件页序。

2026-08-30 基线：**可核 464 处，页码偏移 0、检索不到 0**（全清）。
再跑若报出东西，就是**真的新问题**——不是已知项。
"""

import io, os, re, glob, sys, collections
import fitz
CONTENT="/Users/xiaojin/Documents/文稿同步文件夹/03_学习 (Learning)/Seafile/学习资料/自创项目/bazi-course/content"
ROOT="/Users/xiaojin/Documents/文稿同步文件夹/03_学习 (Learning)/Seafile/seafile实时备份/桌面重要文件/民八字"
DAREN=os.path.join(ROOT,"大任老资料/大任老资料")
MAP={
 "初级班":"03、初级班.pdf", "03初级班":"03、初级班.pdf",
 "中级班":"15、中级班.pdf", "15中级班":"15、中级班.pdf",
 "十八道法门":"十八道法门.pdf",
 "18地支四墓库":"18、地支四墓库的使用方法.pdf", "地支四墓库":"18、地支四墓库的使用方法.pdf",
 "例题解":"04、断命例题解.pdf", "04断命例题解":"04、断命例题解.pdf", "断命例题解":"04、断命例题解.pdf",
 "实战技巧完整版":"16、实战技巧完整版.pdf", "16实战技巧完整版":"16、实战技巧完整版.pdf",
 "实战技巧":"11、实战技巧.pdf",
 "2012高级面授":"2012高级面授班录音彩色笔记 .pdf", "2012面授":"2012高级面授班录音彩色笔记 .pdf",
 "面授":"2012高级面授班录音彩色笔记 .pdf",
 "17刑冲破害":"17、刑冲破害的使用方法.pdf", "刑冲破害":"17、刑冲破害的使用方法.pdf",
 "19神煞":"19、神煞在实战断命时的使用方法.pdf", "神煞":"19、神煞在实战断命时的使用方法.pdf",
 "21干支互通":"六爻.pdf", "干支互通":"六爻.pdf",
 "高级班":"05、高级班.pdf", "财运篇":"01、财运篇.pdf", "婚姻篇":"07、婚姻篇.pdf",
 "六亲篇":"10、六亲篇.pdf", "职业篇":"14、职业篇.pdf", "学历篇":"13、学历篇.pdf",
 "疾病篇":"08、疾病篇.pdf", "寿命篇":"12、寿命篇.pdf", "官运篇":"06、官运篇.pdf",
 "牢狱篇":"09、牢狱篇.pdf", "车祸篇":"02、车祸篇.pdf",
}
_cache={}
def pagetext_wide(pdf, n):
    """页码口径不一时用的宽窗口：PDF 序号 n ± 6 页"""
    path=os.path.join(DAREN,pdf)
    if not os.path.exists(path): return None
    d=_cache.get(("doc",pdf))
    if d is None:
        try: d=fitz.open(path)
        except Exception: return None
        _cache[("doc",pdf)]=d
    return norm("".join(d[i].get_text() for i in range(max(0,n-7), min(d.page_count,n+6))))
def norm(t):
    # ⭐ 只留汉字/数字/字母：站内引文里会混进 →、⭐、加粗号、破折号，
    #    早先的黑名单式清洗漏掉「→」，害得一条本来对得上的引文报成找不到。
    return re.sub(r'[^\u4e00-\u9fff0-9A-Za-z]', '', t)
def pagetext(pdf, n):
    key=(pdf,n)
    if key in _cache: return _cache[key]
    path=os.path.join(DAREN,pdf)
    if not os.path.exists(path): return None
    d=_cache.get(("doc",pdf))
    if d is None:
        try: d=fitz.open(path)
        except Exception: return None
        _cache[("doc",pdf)]=d
    txts=[]
    for i in (n-2,n-1,n):          # 该页 ± 1（页码可能整体偏一页）
        if 0<=i<d.page_count: txts.append(d[i].get_text())
    t=norm("".join(txts))
    _cache[key]=t
    return t

SRC=re.compile(r'〔([^〕]{2,80}?)\s*p\s*(\d+)')
tot=miss=skip=0
bad=[]; off=[]
for f in sorted(glob.glob(os.path.join(CONTENT,"**","*.md"), recursive=True)):
    s=io.open(f,encoding="utf-8").read(); name=os.path.basename(f)
    lines=s.split("\n")
    for i,ln in enumerate(lines):
        m=SRC.search(ln)
        if not m: continue
        who=m.group(1); page=int(m.group(2))
        # 〔… p11-12〕〔… p17 大运歌、p41、p53〕——整段里出现的页码都算数
        seg_all=ln[m.start():]
        seg_all=seg_all[:seg_all.find('〕')+1] if '〕' in seg_all else seg_all
        pages=[int(x) for x in re.findall(r'p\s*(\d+)', seg_all)] or [page]
        # 〔… p7–9〕这种区间要展开，否则中间几页取不到
        for a,b in re.findall(r'p\s*(\d+)\s*[-–~]\s*(\d+)', seg_all):
            pages += list(range(int(a), int(b)+1))
        pages=sorted(set(pages))
        # ⚠️ 只核大任那 22 册（本机有 PDF）；小任的资料另有出处体系，别硬套到大任的书上
        if '小任' in who: continue
        pdf=None
        for k,v in MAP.items():
            if k in who: pdf=v; break
        if not pdf: continue
        # ⚠️ 只认「紧贴」的引用块：出处行本身，或它上面**连续**的 > 块。
        #    隔着别的段落去猜，必然配错（第一版 34% 未命中，多半是配对错）。
        quote=None
        blk=[]
        if ln.lstrip().startswith('>'): blk.append(ln)
        j=i-1
        while j>=0 and lines[j].lstrip().startswith('>'):
            blk.append(lines[j]); j-=1
        if not blk: continue
        # ⭐ 就近配对：一行里常有「引文A」〔出处A〕「引文B」〔出处B〕，
        #    取块内最长的那条必然张冠李戴（实测 10 条假红里 5 条是这么来的）。
        #    先在出处标记【之前】的同行文字里找，找不到再往上一行找最后一条。
        cand=re.findall(r'[「『]([^」』\n]{10,})[」』]', ln[:m.start()])
        if not cand:
            for b in blk[1:] if blk and blk[0] is ln else blk:
                c2=re.findall(r'[「『]([^」』\n]{10,})[」』]', b)
                if c2: cand=[c2[-1]]; break
        if not cand: continue
        quote=cand[-1]
        # 站里有少量「」包的是**我方设问/归纳**，不是原文——标了就放行
        if re.search(r'我的提问|非原文|我的归纳|我的重建|我的凑法', "".join(blk)): continue
        tot+=1
        pt="".join(filter(None,(pagetext(pdf,x) for x in pages)))
        if not pt or len(pt)<50: skip+=1; continue
        # ⚠️ 站内引文常用「……」把原文的几段接起来，整串当指纹必然失配。
        #    按省略号切开，任一段命中即算命中。
        segs=[norm(x) for x in re.split(r'…+|\.{3,}|\s*\(略\)\s*', quote)]
        segs=[x for x in segs if len(x)>=8]
        ok=False
        for seg in segs or [norm(quote)]:
            # ⚠️ 短引文（「卯申互绝路途伤」才 7 字）在只试 16/12/9 时永远判不出命中
            for L in (16,12,9,len(seg)):
                if len(seg)>=max(5,L) and seg[:L] in pt: ok=True; break
            if ok: break
        # 页码口径不一：少数按原书印刷页（比 PDF 序号小 2–5），再放宽一次窗口
        if not ok:
            wide=pagetext_wide(pdf, page)
            for seg in segs or [norm(quote)]:
                for L in (16,12,9):
                    if len(seg)>=L and wide and seg[:L] in wide: ok='offset'; break
                if ok: break
        if ok=='offset':
            off.append((name,i+1,who,page,quote[:30]))
            continue
        if not ok:
            miss+=1
            bad.append((name,i+1,who,page,quote[:34]))
print("核了 %d 处引文（跳过无文本/扫描件 %d 处）：页码偏移 %d 处、完全找不到 %d 处\n"%(tot,skip,len(off),miss))
print("== 页码偏移（附近几页能找到，多半是按原书印刷页标的）==")
for x in off: print("  %s:%d  〔%s p%d〕「%s…」"%x)
print()
for x in bad[:45]: print("  %s:%d  〔%s p%d〕「%s…」"%x)
if len(bad)>45: print("  … 另 %d"%(len(bad)-45))
