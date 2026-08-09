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
  ok($('#hQuiz').textContent === '92', '统计显示 92 道命例，实为 ' + $('#hQuiz').textContent);
  ok($('#hCourse').textContent === '16', '统计显示 16 章');
  ok($('#hNotes').textContent === '14', '统计显示 14 篇');

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
  ok(rows.length === 92, '列出 92 题，实为 ' + rows.length);
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
    ok(n > 0 && n < 92, `按「空亡」筛出 ${n} 题`);
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

  console.log('\n— 内容会一直加：分母不能写死 —');
  {
    const c = JSON.parse(window.localStorage.getItem('bazi_course_counts') || '{}');
    ok(c.course === 16 && c.notes === 14 && c.quiz === 92,
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

  console.log('\n— 主题 —');
  $('#btnTheme').click();
  ok(D.documentElement.getAttribute('data-theme') === 'dark', '切到深色');
  $('#btnTheme').click();
  ok(D.documentElement.getAttribute('data-theme') === 'light', '切到浅色');

  console.log(`\n${fail ? '✗' : '✓'} 通过 ${pass} 项，失败 ${fail} 项`);
  process.exit(fail ? 1 : 0);
})().catch(e => { console.error('测试崩溃:', e); process.exit(1); });
