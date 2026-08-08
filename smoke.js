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
window.scrollTo = () => {};
window.matchMedia = window.matchMedia || (() => ({ matches: false, addListener() {}, removeListener() {} }));

// 手动喂数据（jsdom 不发网络请求）
const run = f => window.eval(fs.readFileSync(path.join(dir, f), 'utf8'));
run('data/data-meta.js');
run('data/data-course.js');
run('data/data-notes.js');
run('data/data-quiz.js');

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
  ok($('#btnBack').classList.contains('show'), '返回键出现');

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
  ok(D.querySelectorAll('.chart .col').length === 4, '单盘题：题头渲染 4 柱大盘');
  ok(D.querySelector('#quizBody .doc').innerHTML.indexOf('<table>') < 0,
     '单盘题：盘已从正文抽走，不重复出现');

  // 题21：双命对照题 —— 两个盘都要留在正文，题头不放大盘
  D.querySelector('[data-tab="qlist"]').click(); await wait();
  const rows21 = D.querySelectorAll('#qRows [data-q]');
  const r21 = Array.from(rows21).find(r => r.querySelector('.n').textContent === '21');
  r21.click(); await wait();
  ok($('#s-quiz').classList.contains('active'), '进入题21');
  ok(D.querySelectorAll('.chart .col').length === 0, '多盘题：题头不放大盘');
  ok((D.querySelector('#quizBody .doc').innerHTML.match(/<table>/g) || []).length === 2,
     '多盘题：命A命B 两个盘都留在正文');
  ok(!!$('#bJie'), '「对答案」按钮存在');
  ok(!$('#L2').innerHTML, '未点开时不泄露答案');
  $('#bJie').click(); await wait();
  ok($('#L2').innerHTML.length > 100, '解已展开');
  ok(!!$('#bChai'), '「看拆解」按钮出现');
  ok(!$('#L3').innerHTML.includes('我补的推理'), '拆解仍未展开');
  $('#bChai').click(); await wait();
  ok($('#L3').innerHTML.includes('我补的推理'), '拆解展开且带免责声明');

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

  console.log('\n— 搜索 —');
  $('#btnSearch').click(); await wait();
  $('#q').value = '巳申合';
  $('#q').dispatchEvent(new window.Event('input'));
  await new Promise(r => setTimeout(r, 400));
  const hits = D.querySelectorAll('#hits [data-h]');
  ok(hits.length > 0, '搜到「巳申合」' + hits.length + ' 条');

  console.log('\n— 主题 —');
  $('#btnTheme').click();
  ok(D.documentElement.getAttribute('data-theme') === 'dark', '切到深色');
  $('#btnTheme').click();
  ok(D.documentElement.getAttribute('data-theme') === 'light', '切到浅色');

  console.log(`\n${fail ? '✗' : '✓'} 通过 ${pass} 项，失败 ${fail} 项`);
  process.exit(fail ? 1 : 0);
})().catch(e => { console.error('测试崩溃:', e); process.exit(1); });
