/* 深链测试：八字日练的出处链接 ?go=章-#节号 要直接落到那一节（2026-10-22） */
const fs = require('fs');
const path = require('path');
const { JSDOM } = require('jsdom');

const dir = __dirname;
let pass = 0, fail = 0;
const ok = (c, m) => { c ? (pass++, console.log('  ✓', m)) : (fail++, console.log('  ✗', m)); };

const dom = new JSDOM(fs.readFileSync(path.join(dir, 'index.html'), 'utf8'), {
  runScripts: 'outside-only', pretendToBeVisual: true, url: 'https://x.test/bazi-course/?go=' + encodeURIComponent(process.argv[2] || '07-#八·F')
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
run('data/data-desk.js');
run('data/data-vke.js');
run('data/data-kt.js');    // ⚠️ 新增数据文件必须同步到这份清单，否则按需加载在 jsdom 里拿不到

// 让 app.js 的按需加载直接命中已注入的全局
window.eval(`
  window.__origCreate = document.createElement.bind(document);
  document.createElement = function(t){
    const el = window.__origCreate(t);
    if (t === 'script') {
      Object.defineProperty(el, 'src', {
        // 记下真实请求的 URL —— 按需加载有没有带版本参数，全靠它验
        set(v){ (window.__reqSrc = window.__reqSrc || []).push(v);
                setTimeout(()=> el.onload && el.onload(), 0); },
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
  await wait(); await wait(); await new Promise(r => setTimeout(r, 200));
  ok($('#s-chapter').classList.contains('active'), '带 ?go= 打开直接进教材章节');
  const hit = D.querySelector('.sr-blk');
  ok(hit && /^#*\s*八·F/.test(hit.getAttribute('data-raw') || ''), '落到「八·F」那一节标题：' + (hit && hit.getAttribute('data-raw')));
  console.log(fail ? `\n✗ 失败 ${fail} 项` : `\n✓ 深链全部通过（${pass} 项）`);
  process.exit(fail ? 1 : 0);
})();
