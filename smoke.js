/* 冒烟测试：在 jsdom 里真跑一遍页面，验证路由、渲染、SRS、搜索。 */
const fs = require('fs');
const path = require('path');
const { JSDOM } = require('jsdom');

const dir = __dirname;
let pass = 0, fail = 0;
const ok = (c, m) => { c ? (pass++, console.log('  ✓', m)) : (fail++, console.log('  ✗', m)); };

const dom = new JSDOM(fs.readFileSync(path.join(dir, 'index.html'), 'utf8'), {
  runScripts: 'outside-only', pretendToBeVisual: true, url: 'https://x.test/bazi-course/'
});
const { window } = dom;
// 记下滚动调用——恢复阅读位置、搜索定位都靠它，不记就没法验真假
let scrolls = [];
window.scrollTo = (x, y) => { scrolls.push(typeof x === 'object' ? x.top : y); };
window.matchMedia = window.matchMedia || (() => ({ matches: false, addListener() {}, removeListener() {} }));

// 手动喂数据（jsdom 不发网络请求）
const run = f => window.eval(fs.readFileSync(path.join(dir, f), 'utf8'));
run('data/data-meta.js');
run('data/data-course.js');
run('data/data-notes.js');
run('data/data-quiz.js');
run('data/data-index.js');

// 让 app.js 的按需加载直接命中已注入的全局
window.eval(`
  window.__origCreate = document.createElement.bind(document);
  document.createElement = function(t){
    const el = window.__origCreate(t);
    if (t === 'script') {
      Object.defineProperty(el, 'src', {
        set(v){ setTimeout(()=> el.onload && el.onload(), 0); },
        get(){ return ''; }
      });
    }
    return el;
  };
`);

run('app.js');
const D = window.document;
const $ = s => D.querySelector(s);
const wait = () => new Promise(r => setTimeout(r, 30));

(async () => {
  console.log('\n— 首页 —');
  ok($('#s-home').classList.contains('active'), '首页激活');
  // ⚠️ 别再把题数写死（build.py 的 BASE 当初就栽在 != 上）：
  //    内容一直在加，这里验的是「三处口径一致 + 不跌破基线」。
  const BASE = { course: 16, notes: 14, quiz: 269 };
  const QUIZ = Number($('#hQuiz').textContent);
  ok(QUIZ >= BASE.quiz, `统计显示 ${QUIZ} 道命例（基线 ${BASE.quiz}）`);
  ok(Number($('#hCourse').textContent) >= BASE.course, '统计显示 16 章');
  ok(Number($('#hNotes').textContent) >= BASE.notes, '统计显示 14 篇');

  console.log('\n— 教材 —');
  D.querySelector('[data-tab="course"]').click(); await wait();
  ok($('#s-course').classList.contains('active'), '切到教材列表');
  const chCards = D.querySelectorAll('#courseList [data-ch]');
  ok(chCards.length === 16, '列出 16 章，实为 ' + chCards.length);
  chCards[7].click(); await wait();
  ok($('#s-chapter').classList.contains('active'), '进入第8章');
  ok($('#ttl').textContent.includes('制与做功'), '标题正确：' + $('#ttl').textContent);
  ok($('#chapterBody').innerHTML.length > 5000, '正文已渲染');
  ok(D.querySelectorAll('#chapterBody .ichart').length > 0,
     '教材正文的命例盘转成了可吸顶的紧凑盘，共 ' + D.querySelectorAll('#chapterBody .ichart').length + ' 个');
  ok(D.querySelector('#chapterBody .ichart .c.day') !== null, '正文盘也标出日柱');
  // 五行上色：甲=木 丙=火 戊=土 庚=金 壬=水
  const wxOK = ['甲','乙','寅','卯'].every(c => /w-mu/.test(
    (D.querySelector('#chapterBody').innerHTML.match(new RegExp('<span class="[ab] w-\\w+">'+c+'</span>'))||[''])[0] || 'w-mu'));
  ok(D.querySelectorAll('#chapterBody .w-mu, #chapterBody .w-huo, #chapterBody .w-tu, #chapterBody .w-jin, #chapterBody .w-shui').length > 20,
     '干支已按五行上色，共 ' + D.querySelectorAll('#chapterBody [class*="w-"]').length + ' 字');
  ok($('#btnBack').classList.contains('show'), '返回键出现');

  console.log('\n— 内容格式（括号换成样式、干支上色）—');
  {
    const h = $('#chapterBody').innerHTML;
    const noPre = h.replace(/<pre[\s\S]*?<\/pre>/g, '');
    ok(!/[【】]/.test(noPre), '正文不再有【】括号（流程图里的保留）');
    ok(!/〔|〕/.test(noPre), '正文不再有〔〕括号');
    ok(/class="src"/.test(h), '出处渲染成金色标签');
    ok(/class="yw"/.test(h), '原文引用渲染成 <q class=yw>');
    ok(D.querySelectorAll('#chapterBody .ichart').length >= 5,
       '第8章命例全排成盘，共 ' + D.querySelectorAll('#chapterBody .ichart').length + ' 个');
    ok(!/\[\[/.test(noPre), 'wiki 链接全部渲染，无残留 [[..]]');
  }

  console.log('\n— 路由（套壳侧滑的关键）—');
  const before = $('#ttl').textContent;
  window.history.back(); await wait();
  ok($('#s-course').classList.contains('active'), 'back 回到章节列表而非退出');
  window.history.forward(); await wait();
  ok($('#ttl').textContent === before, 'forward 恢复到原章');

  console.log('\n— 题库 —');
  D.querySelector('[data-tab="qlist"]').click(); await wait();
  const rows = D.querySelectorAll('#qRows [data-q]');
  ok(rows.length === QUIZ, `题库列出 ${rows.length} 题，与首页统计 ${QUIZ} 一致`);
  ok(D.querySelectorAll('#qTags [data-t]').length > 10, '考点筛选已渲染');
  const fm = Array.from(D.querySelectorAll('#qFilters [data-m]')).map(e => e.dataset.m);
  ok(fm.join(',') === 'all,new,star,chart', '筛选只剩 全部/没看过/精读/有完整盘：' + fm.join(','));

  // 题3：单盘题 —— 题头应有四柱大盘
  const r3 = Array.from(rows).find(r => r.querySelector('.n').textContent === '3');
  r3.click(); await wait();
  ok(D.querySelectorAll('#quizBody .chart').length === 0, '单盘题：题头不再画大盘（避免同一个盘出现两次）');
  ok($('#stickyChart').querySelectorAll('.c').length === 4, '单盘题：吸顶条 4 柱');
  ok($('#stickyChart').querySelector('.c.day .a').textContent === '丙', '日柱标在第3柱(丙午)');
  ok($('#stickyChart').querySelector('.c.day .a').className === 'a w-huo', '吸顶条丙字上火色');
  ok($('#stickyChart').querySelector('.c.day .b').className === 'b w-huo', '吸顶条午字上火色');
  ok(/坤造/.test($('#stickyChart').innerHTML), '单盘题：性别标记挪进吸顶条');
  ok(D.querySelectorAll('#quizBody .ichart').length === 0,
     '单盘题：盘不在正文里重复（只在题头吸顶条）');

  // 题21：双命对照题 —— 两个盘都要留在正文，题头不放大盘
  D.querySelector('[data-tab="qlist"]').click(); await wait();
  const rows21 = D.querySelectorAll('#qRows [data-q]');
  const r21 = Array.from(rows21).find(r => r.querySelector('.n').textContent === '21');
  r21.click(); await wait();
  ok($('#s-quiz').classList.contains('active'), '进入题21');
  ok(D.querySelectorAll('#quizBody .chart').length === 0, '多盘题：题头不放大盘');
  ok(D.querySelectorAll('#quizBody .ichart').length === 2,
     '多盘题：命A命B 两个盘都留在正文（已转成紧凑盘）');
  ok(!!$('#bJie'), '「对答案」按钮存在');
  ok(!$('#L2').innerHTML, '未点开时不泄露答案');
  $('#bJie').click(); await wait();
  ok($('#L2').innerHTML.length > 100, '解已展开');
  ok(!!$('#bChai'), '「看拆解」按钮出现');
  ok(!$('#L3').innerHTML.includes('我补的推理'), '拆解仍未展开');
  $('#bChai').click(); await wait();
  ok($('#L3').innerHTML.includes('我补的推理'), '拆解展开且带免责声明');

  console.log('\n— 吸顶四柱盘 —');
  // jsdom 无 IntersectionObserver，会走 fallback 直接点亮
  const sc = $('#stickyChart');
  ok(!sc.classList.contains('hide'), '有盘的题：吸顶条常驻显示（不依赖任何滚动事件）');
  ok(sc.querySelectorAll('.grp').length === 2, '多盘题：吸顶条放两个盘，实为 ' + sc.querySelectorAll('.grp').length);
  ok(/命A/.test(sc.innerHTML) && /命B/.test(sc.innerHTML), '两盘各带命A/命B标签');
  ok(sc.querySelectorAll('.c').length === 8, '共 8 柱');
  ok(sc.querySelectorAll('.c.day').length === 2, '每盘的日柱都被标出');

  console.log('\n— 看过标记（刻意不做 SRS／自评／错题）—');
  ok(!D.querySelector('#rate'), '没有自评面板');
  ok(!window.localStorage.getItem('bazi_course_srs'), '不写 SRS');
  ok(!window.localStorage.getItem('bazi_course_tag_stats'), '不写考点正确率');
  const seen = JSON.parse(window.localStorage.getItem('bazi_course_seen') || '{}');
  ok(!!seen['21'], '看过答案后记下题号 21');
  ok(!!$('#qnav') && !!$('#bPrev') && !!$('#bNext'), '上一题/下一题导航出现');
  $('#bNext').click(); await wait();
  ok($('#ttl').textContent === '第 22 题', '下一题 → 22，实为 ' + $('#ttl').textContent);
  $('#bPrev').click(); await wait();
  ok($('#ttl').textContent === '第 21 题', '上一题 → 21');

  console.log('\n— 反推题不该有假答案 —');
  D.querySelector('[data-tab="qlist"]').click(); await wait();
  const rowsB = D.querySelectorAll('#qRows [data-q]');
  const r53 = Array.from(rowsB).find(r => r.querySelector('.n').textContent === '53');
  r53.click(); await wait();
  ok($('#bJie').textContent.includes('提示'), '反推题按钮显示「看提示方向」');
  $('#bJie').click(); await wait();
  ok($('#L2').innerHTML.includes('原书未给解'), '明确标注原书未给解');

  console.log('\n— 离开题目页要清理吸顶条 —');
  D.querySelector('[data-tab="course"]').click(); await wait();
  ok($('#stickyChart').classList.contains('hide'), '切到教材后吸顶盘隐藏');

  console.log('\n— 搜索 —');
  const search = async kw => {
    $('#btnSearch').click(); await wait();
    $('#q').value = kw;
    $('#q').dispatchEvent(new window.Event('input'));
    await new Promise(r => setTimeout(r, 400));
    return D.querySelectorAll('#hits [data-h]');
  };
  const hits = await search('巳申合');
  ok(hits.length > 0, '搜到「巳申合」' + hits.length + ' 条');

  console.log('\n— 搜索：一篇里的每一处都要列出（以前只给第一处）—');
  {
    const h = await search('做功');
    const labels = Array.from(h).map(e => e.querySelector('b').textContent);
    ok(labels.some(l => /第2处/.test(l)), '同一篇的第2处也单独成条');
    const ch13 = labels.filter(l => /^第13章/.test(l));
    ok(ch13.length > 1, '第13章「做功」27 次，列出 ' + ch13.length + ' 条（以前恒为 1 条）');
    ok(/共 \d+ 处/.test($('#hits').innerHTML), '结果头部给出总处数');
    ok(/本篇另有/.test($('#hits').innerHTML), '超出上限的标明「本篇另有 N 处」');
  }

  console.log('\n— 搜索：题库要能搜到答案与拆解（data 里的 text 被截到 600 字）—');
  {
    // 「羊刃」在题17 只出现在拆解里，旧的 q.text 截断后根本搜不到
    const h = await search('羊刃');
    const q17 = Array.from(h).find(e => /^题17/.test(e.querySelector('b').textContent));
    ok(!!q17, '搜到题17 的「羊刃」——它只写在拆解里');
    const raw = window.DATA_QUIZ.items.find(i => i.n === 17);
    ok(raw.text.indexOf('羊刃') < 0, '（对照）data 的 text 字段里确实没有它，说明走的是新的全文提取');

    q17.click(); await wait();
    ok($('#ttl').textContent === '第 17 题', '点结果跳进题17');
    ok($('#L2').innerHTML.length > 100, '命中在折叠层里 → 「解」自动展开');
    ok($('#L3').innerHTML.includes('我补的推理'), '命中在拆解里 → 拆解也自动展开');
    ok(/命中在.*已经展开/.test($('#toastTxt').textContent), '提示条说明了为什么自动展开');
    ok(D.querySelectorAll('#quizBody mark.sr-kw, #quizBody .sr-blk').length > 0, '命中处被高亮');
  }

  console.log('\n— 搜索：跳进长文要滚到命中处，不是回到顶部 —');
  {
    const h = await search('巳申合');
    const chHit = Array.from(h).find(e => /^第\d+章/.test(e.querySelector('b').textContent));
    chHit.click(); await wait();
    ok($('#s-chapter').classList.contains('active'), '跳进教材章节');
    const marks = D.querySelectorAll('#chapterBody mark.sr-kw, #chapterBody .sr-blk');
    ok(marks.length > 0, '章节正文里命中处已高亮');
    ok(/巳申合/.test(marks[0].textContent) || marks[0].classList.contains('sr-blk'),
       '高亮的正是关键词（跨标签时退化为整段）');
  }

  console.log('\n— 考点筛选：45 个全都要能筛到 —');
  {
    D.querySelector('[data-tab="qlist"]').click(); await wait();
    const total = window.DATA_QUIZ.tags.length;
    const folded = D.querySelectorAll('#qTags [data-t]').length - 1;   // 减掉「全部考点」
    ok(!!$('#tagsMore'), '有「更多」展开入口');
    $('#tagsMore').click(); await wait();
    const opened = D.querySelectorAll('#qTags [data-t]').length - 1;
    ok(opened === total, `展开后 ${total} 个考点全部列出，实为 ${opened}（收起时 ${folded}）`);
    // 挑一个以前被 slice(0,18) 埋掉的低频考点，验证它真能筛
    const rare = Array.from(D.querySelectorAll('#qTags [data-t]'))
      .find(e => e.dataset.t === '空亡');
    ok(!!rare, '低频考点「空亡」现在出现在筛选里');
    rare.click(); await wait();
    const n = D.querySelectorAll('#qRows [data-q]').length;
    ok(n > 0 && n < QUIZ, `按「空亡」筛出 ${n} 题`);
    ok(D.querySelector('#qTags .pill.sel[data-t="空亡"]') !== null, '选中态可见（即便它排在折叠区之后）');
    $('#qTags [data-t=""]').click(); await wait();
  }

  console.log('\n— 长文回来接着读 —');
  {
    window.localStorage.setItem('bazi_course_pos', JSON.stringify({ c5: 4200 }));
    window.localStorage.setItem('bazi_course_read', JSON.stringify({ c5: 40 }));
    scrolls = [];
    D.querySelector('[data-tab="course"]').click(); await wait();
    D.querySelectorAll('#courseList [data-ch]')[4].click(); await wait();
    ok(scrolls.includes(4200), '进入第5章后滚回上次的位置 4200，实际滚动序列 ' + JSON.stringify(scrolls));
    ok($('#toast').classList.contains('on'), '提示条出现');
    ok(/上次读到/.test($('#toastTxt').textContent), '提示文案：' + $('#toastTxt').textContent);
    $('#toastAct').click(); await wait();
    ok(scrolls[scrolls.length - 1] === 0, '点「从头读」回到顶部');

    // 快读完的不该再跳回去
    window.localStorage.setItem('bazi_course_read', JSON.stringify({ c5: 97 }));
    scrolls = [];
    D.querySelector('[data-tab="course"]').click(); await wait();
    D.querySelectorAll('#courseList [data-ch]')[4].click(); await wait();
    ok(!scrolls.includes(4200), '已读 97% 的章节不再跳回，从头看更顺');
    window.localStorage.removeItem('bazi_course_pos');
    window.localStorage.removeItem('bazi_course_read');
  }

  console.log('\n— 笔记上/下篇 —');
  {
    D.querySelector('[data-tab="notes"]').click(); await wait();
    D.querySelectorAll('#noteList [data-nt]')[3].click(); await wait();
    ok($('#s-note').classList.contains('active'), '进入第4篇笔记');
    const t0 = $('#ttl').textContent;
    ok(!$('#nextNt').disabled, '「下一篇」可用');
    ok($('#nextNt').textContent !== '下一篇 ›', '按钮上直接写出下一篇标题：' + $('#nextNt').textContent);
    $('#nextNt').click(); await wait();
    ok($('#ttl').textContent !== t0, '切到下一篇：' + $('#ttl').textContent);
    $('#prevNt').click(); await wait();
    ok($('#ttl').textContent === t0, '「上一篇」回到 ' + t0);
    // 首尾要禁用
    D.querySelector('[data-tab="notes"]').click(); await wait();
    D.querySelectorAll('#noteList [data-nt]')[0].click(); await wait();
    ok($('#prevNt').disabled, '第1篇的「上一篇」禁用');
  }

  console.log('\n— 首屏包 & 进度口径 —');
  {
    ok(!window.DATA_META.index, '问题清单已移出首屏包 data-meta.js');
    ok(typeof window.DATA_INDEX === 'string' && window.DATA_INDEX.length > 10000,
       '问题清单改为按需加载的 data-index.js');
    const metaKB = fs.statSync(path.join(dir, 'data/data-meta.js')).size / 1024;
    ok(metaKB < 20, `首屏 data-meta.js 降到 ${metaKB.toFixed(1)}KB（原 124KB）`);
    D.querySelector('[data-tab="notes"]').click(); await wait();
    $('[data-go2="index"]').click(); await wait();
    ok($('#indexBody').innerHTML.length > 10000, '问题清单仍能正常打开');

    window.localStorage.setItem('bazi_course_read',
      JSON.stringify({ c1: 100, c2: 100, n1: 100, n2: 100, n3: 100 }));
    D.querySelector('[data-tab="home"]').click(); await wait();
    const chips = $('#progChips').textContent;
    ok(/教材 2\/16/.test(chips), '首页显示 教材 2/16');
    ok(/笔记 3\/14/.test(chips), '首页也显示 笔记 3/14（以前笔记根本不计）：' + chips);
    ok(/命例/.test(chips), '首页显示 命例 N/92');
    window.localStorage.removeItem('bazi_course_read');
  }

  console.log('\n— 多词搜索（空格分隔）—');
  {
    const one = await search('墓库');
    ok(one.length > 0, '单词「墓库」' + one.length + ' 条（行为不变）');

    const two = await search('墓库 冲开');
    ok(two.length > 0, '「墓库 冲开」搜到 ' + two.length + ' 条（以前恒为 0）');
    ok(/同时含/.test($('#hits').innerHTML), '结果头部说明是「同时含…」');
    // 每条命中所在的文档必须两个词都有
    const html = $('#hits').innerHTML;
    ok((html.match(/<em>/g) || []).length > two.length,
       '片段里两个词都被点出来（<em> 数多于结果条数）');

    // 跳转要用第一个词定位——整串含空格，在正文里根本不存在
    two[0].click(); await wait();
    const scr = $('#s-chapter').classList.contains('active') ? '#chapterBody'
              : $('#s-note').classList.contains('active') ? '#noteBody' : '#quizBody';
    ok(D.querySelectorAll(scr + ' mark.sr-kw, ' + scr + ' .sr-blk').length > 0,
       '多词搜索跳过去照样定位到「墓库」');

    const none = await search('墓库 绝不可能出现的词');
    ok(none.length === 0, '缺一个词就不该命中');
    ok(/没找到同时含/.test($('#hits').innerHTML), '无结果时说明是多词条件');
  }

  console.log('\n— 内容会一直加：分母不能写死 —');
  {
    const c = JSON.parse(window.localStorage.getItem('bazi_course_counts') || '{}');
    ok(c.course === Number($('#hCourse').textContent)
       && c.notes === Number($('#hNotes').textContent)
       && c.quiz === QUIZ,
       '启动时把真实总量写给导航看板：' + JSON.stringify(c));

    // 看板在另一个仓库(mingli-home)，这里直接把它那段口径搬过来跑一遍，
    // 免得哪天它悄悄退回写死的 16/14/92
    const home = fs.readFileSync(
      path.join(dir, '..', 'mingli-home', 'index.html'), 'utf8');
    const seg = (home.match(/jingjiang:function\(\)\{[\s\S]*?\n    \}/) || [''])[0];
    ok(seg.length > 100, '找到看板的 jingjiang 统计段');
    ok(/bazi_course_counts/.test(seg), '看板改为读 bazi_course_counts 当分母');
    ok(!/\/16 章|\/14 篇|\/92 题/.test(seg), '看板里不再有写死的 /16 /14 /92');

    // build.py 的自检必须是下限而非等号，否则加第15篇笔记会直接构建失败
    const bp = fs.readFileSync(path.join(dir, 'build.py'), 'utf8');
    ok(!/len\(notes\) != 14|len\(course\) != 16/.test(bp),
       'build.py 不再用 != 钉死数量');
    ok(/got\[k\] < base/.test(bp), 'build.py 改成「跌破基线才报错」');
  }

  console.log('\n— 我的笔记 —');
  {
    window.localStorage.removeItem('bazi_course_mynotes');
    // 进第 8 章，选中正文里的一句
    D.querySelector('[data-tab="course"]').click(); await wait();
    D.querySelectorAll('#courseList [data-ch]')[7].click(); await wait();

    const body = $('#chapterBody');
    // 找一个够长的文本节点当作"用户选中的一句"
    const walker = D.createTreeWalker(body, 4, null);
    let node = null;
    while ((node = walker.nextNode())) if (node.nodeValue.trim().length > 12) break;
    const picked = node.nodeValue.trim().slice(0, 20);

    const range = D.createRange();
    range.setStart(node, node.nodeValue.indexOf(picked));
    range.setEnd(node, node.nodeValue.indexOf(picked) + picked.length);
    const sel = window.getSelection();
    sel.removeAllRanges(); sel.addRange(range);
    // jsdom 没有布局，getBoundingClientRect 恒为 0 → 浮标逻辑会短路，
    // 这里补一个几何，否则测的是 fallback 分支（这站栽过一次的坑）
    range.getBoundingClientRect = () => ({ top: 300, bottom: 320, left: 40, width: 120, height: 20 });
    const origGet = D.createRange;
    D.dispatchEvent(new window.Event('selectionchange'));
    await new Promise(r => setTimeout(r, 200));

    ok($('#selBtn').classList.contains('on'), '选中正文后浮出「存进笔记」');
    $('#selBtn').click(); await wait();
    const saved = JSON.parse(window.localStorage.getItem('bazi_course_mynotes') || '[]');
    ok(saved.length === 1, '存下 1 条笔记，实为 ' + saved.length);
    ok(saved[0].text === picked, '存的是选中的原句');
    ok(saved[0].scr === 'chapter' && saved[0].id === 8, '记下出处：' + saved[0].from);
    ok(typeof saved[0].occ === 'number', '记下在文中第几处（跳回定位用）');

    $('#btnMyNotes').click(); await wait();
    ok($('#s-mynotes').classList.contains('active'), '顶栏 📌 进我的笔记');
    ok(D.querySelectorAll('#mnList .mncard').length === 1, '列表显示 1 条');

    console.log('\n  — 跳回原文（复用搜索定位那套）—');
    D.querySelector('[data-mn-go]').click(); await wait();
    ok($('#s-chapter').classList.contains('active'), '跳回第 8 章');
    ok(D.querySelectorAll('#chapterBody mark.sr-kw, #chapterBody .sr-blk').length > 0,
       '原句被高亮（不是只回到章首）');

    console.log('\n  — 批注与删除 —');
    $('#btnMyNotes').click(); await wait();
    window.prompt = () => '这句是本章的题眼';
    D.querySelector('[data-mn-memo]').click(); await wait();
    ok(JSON.parse(window.localStorage.getItem('bazi_course_mynotes'))[0].memo === '这句是本章的题眼', '批注已存');
    ok(/这句是本章的题眼/.test($('#mnList').innerHTML), '批注显示在卡片上');
    window.confirm = () => true;
    D.querySelector('[data-mn-del]').click(); await wait();
    ok(JSON.parse(window.localStorage.getItem('bazi_course_mynotes')).length === 0, '删除生效');
    ok(/还没有笔记/.test($('#mnList').innerHTML), '空态给出用法说明');

    console.log('\n  — 边界 —');
    ok(!$('#selBtn').classList.contains('on'), '切屏后浮标收起');
    window.localStorage.removeItem('bazi_course_mynotes');
  }

  console.log('\n— 表格排版 —');
  {
    D.querySelector('[data-tab="course"]').click(); await wait();
    D.querySelectorAll('#courseList [data-ch]')[7].click(); await wait();
    const h = $('#chapterBody').innerHTML;
    ok(/<div class="tw">/.test(h), '表格外包了横向滚动容器');
    const nw = (h.match(/<td class="nw">/g) || []).length;
    ok(nw > 0, `短标签单元格标了 .nw 防断行，本章 ${nw} 个`);
    // 长文本单元格不该被 nowrap，否则表格会撑到没法读
    const longNw = [...$('#chapterBody').querySelectorAll('td.nw')]
      .filter(td => td.textContent.trim().length > 6);
    ok(longNw.length === 0, '长文本单元格没有被误标 nowrap');
  }

  console.log('\n— 全站去图标：顶栏／底栏／首页入口都是纯文字 —');
  // ⚠️ 用码点判断，别拿正则数 emoji：✍️ 是「字符+变体选择符」两个码点，
  //    \u4e00-\u9fff 这类范围也框不住 ⌂ 这种符号区的字。
  var isPlain = function (txt) {
    return Array.from(txt).every(function (ch) {
      var c = ch.codePointAt(0);
      return c < 0x2000 || (c >= 0x3000 && c <= 0x9fff);  // ASCII/标点 + CJK
    });
  };
  var tabs = Array.from(D.querySelectorAll('.tabbar button'));
  ok(tabs.length === 4, '底栏 4 个 tab');
  ok(tabs.every(function (b) { return isPlain(b.textContent.trim()); }),
     '底栏没有图标，只有文字：' + tabs.map(function (b) { return b.textContent.trim(); }).join(' '));
  ok(D.querySelectorAll('.tabbar .ic').length === 0, '底栏 .ic 图标位已删干净');
  var modes = Array.from(D.querySelectorAll('.mode'));
  ok(modes.length === 3 && modes.every(function (m) { return isPlain(m.textContent); }),
     '首页三入口也去了 emoji');
  ok(D.querySelectorAll('.mode .ic').length === 0, '首页入口 .ic 图标位已删干净');
  var acts = Array.from(D.querySelectorAll('.topbar .act'));
  ok(acts.length === 3 && acts.every(function (b) { return isPlain(b.textContent.trim()); }),
     '顶栏也去了 emoji：' + acts.map(function (b) { return b.textContent.trim(); }).join(' '));
  // 主题键三态：随（跟随系统）→ 阴 → 阳 → 随，字要跟着换
  var bt = D.querySelector('#btnTheme'), marks = [];
  // ⚠️ 三态一圈只点 3 下：点 4 下会多转一格，把主题停在 dark，
  //    下面「— 主题 —」那两项就跟着一起挂。
  var readMark = function () { return bt.textContent.trim() + bt.getAttribute('data-set'); };
  marks.push(readMark());
  for (var ti = 0; ti < 3; ti++) { bt.click(); marks.push(readMark()); }
  ok(marks.join(' ') === '随0 阴1 阳1 随0', '主题键三态字随状态换：' + marks.join(' → '));

  console.log('\n— 主题 —');
  $('#btnTheme').click();
  ok(D.documentElement.getAttribute('data-theme') === 'dark', '切到深色');
  $('#btnTheme').click();
  ok(D.documentElement.getAttribute('data-theme') === 'light', '切到浅色');

  console.log(`\n${fail ? '✗' : '✓'} 通过 ${pass} 项，失败 ${fail} 项`);
  process.exit(fail ? 1 : 0);
})().catch(e => { console.error('测试崩溃:', e); process.exit(1); });
