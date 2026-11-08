/* 分包测试：站点只拿到 data-s/ 的 meta，点进去才按需加载正文（用真文件喂 jsdom，不预注入全量数据） */
const fs = require('fs');
const path = require('path');
const { JSDOM } = require('jsdom');
const dir = __dirname;
let pass = 0, fail = 0;
const ok = (c, m) => { c ? (pass++, console.log('  ✓', m)) : (fail++, console.log('  ✗', m)); };
const html = fs.readFileSync(path.join(dir, 'index.html'), 'utf8').replace(/<link rel="stylesheet"[^>]*>/g, '').replace(/<script async[^>]*><\/script>/, '');
const dom = new JSDOM(html, { runScripts: 'outside-only', pretendToBeVisual: true, url: 'https://x.test/bazi-course/' });
const { window } = dom;
window.scrollTo = () => {};
window.matchMedia = window.matchMedia || (() => ({ matches: false, addListener() {}, removeListener() {} }));
window.eval(fs.readFileSync(path.join(dir, 'data/data-meta.js'), 'utf8'));
const requested = [];
window.__loadFile = (u) => {
  const rel = u.split('?')[0];
  requested.push(rel);
  window.eval(fs.readFileSync(path.join(dir, rel), 'utf8'));
};
window.eval(`
  const _oc = document.createElement.bind(document);
  document.createElement = function (t) {
    const el = _oc(t);
    if (t === 'script') Object.defineProperty(el, 'src', {
      set(v) { setTimeout(() => { try { window.__loadFile(v); el.onload && el.onload(); } catch (e) { el.onerror && el.onerror(e); } }, 0); },
      get() { return ''; } });
    return el;
  };`);
const errs = [];
window.addEventListener('error', e => errs.push(e.message));
window.eval(fs.readFileSync(path.join(dir, 'app.js'), 'utf8'));
const D = window.document;
const $ = s => D.querySelector(s), $$ = s => [...D.querySelectorAll(s)];
const wait = ms => new Promise(r => setTimeout(r, ms));
const click = el => el.dispatchEvent(new window.MouseEvent('click', { bubbles: true }));

(async () => {
  console.log('分包');
  await wait(100);
  click($('[data-tab="course"]')); await wait(200);
  ok($$('[data-ch]').length >= 16, '课程列表只靠 meta 就能画出 ' + $$('[data-ch]').length + ' 章');
  ok(!requested.some(f => /body-c\d+\.js/.test(f)), '打开列表时没有拉任何章节正文');
  ok(fs.statSync(path.join(dir, 'data-s/data-course.js')).size < 250 * 1024, '课程列表包 < 250KB');
  click($('[data-ch="1"]')); await wait(300);
  ok($('#chapterBody').textContent.length > 1500, '点第 1 章后才加载正文，长度 ' + $('#chapterBody').textContent.length);
  ok(requested.filter(f => /body-c\d+\.js/.test(f)).length === 1, '只拉了 1 个章节文件');
  await wait(1900);
  ok(Object.keys(JSON.parse(window.localStorage.getItem('bazi_course_read') || '{}')).length === 0, '读章节不会自动记已读');
  click($('#readToggle')); await wait(30);
  ok(Object.values(JSON.parse(window.localStorage.getItem('bazi_course_read') || '{}'))[0] >= 90, '点「标记为已读」才记录');
  click($('[data-tab="notes"]')); await wait(200);
  click($('[data-nt]')); await wait(300);
  ok($('#noteBody').textContent.length > 1000, '笔记正文按需加载');
  click($('[data-tab="qlist"]')); await wait(300);
  click($('.qgh')); await wait(30);
  click($('.qrow')); await wait(300);
  ok($('#quizBody').textContent.length > 20 && /断|反馈|解|答案/.test($('#quizBody').textContent), '命例页内容按需加载');
  console.log('   all requests:', requested.join(' ')); console.log('   quiz text:', $('#quizBody').textContent.slice(0,80)); console.log('   qbody requests:', requested.filter(f => /qbody/.test(f)).join(','));
  ok(requested.filter(f => /qbody-\d+\.js/.test(f)).length === 1, '只拉了 1 个命例块');
  click($('#btnSearch')); await wait(80);
  $('#q').value = '墓库'; $('#q').dispatchEvent(new window.Event('input', { bubbles: true })); await wait(1500);
  ok($$('#hits > *').length > 5, '搜索会补齐全部正文后返回结果：' + $$('#hits > *').length);
  ok(errs.length === 0, '无脚本错误' + (errs.length ? '：' + errs.join(' | ') : ''));
  console.log(`\n${pass} 通过，${fail} 失败`);
  process.exit(fail ? 1 : 0);
})();
