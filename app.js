/* 命理精讲 — app.js
 *
 * 内容全部由 build.py 从 Obsidian markdown 编译而来（data/*.js）。
 * 改内容请改 markdown 后重跑 build.py，不要动 data/*.js。
 */
(function () {
'use strict';

var $ = function (s, r) { return (r || document).querySelector(s); };
var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };
var META = window.DATA_META || {};

/* ============================ 存储 ============================
 * ⚠️ 这些键会被五术堂导航首页的学习看板读取，改名要同步改看板。
 *   bazi_course_read  {文档id: 阅读百分比 0-100}   c1..c16 教材 / n1..n14 笔记
 *   bazi_course_seen  {题号: 时间戳}               看过答案的题
 *   bazi_course_last  {scr, id}
 *   bazi_course_pos   {文档id: scrollTop}         上次读到哪（长文回来接着读用）
 *
 * ⚠️ 刻意不做 SRS／错题本／自评打分（用户 2026-08-08 要求「练就简单点」）。
 *    命例是主观题，本来也没法客观判分；这里只留一个「看过」标记，
 *    好让列表能看出做到哪了，不制造复习压力。
 */
var K = {
  read: 'bazi_course_read',
  seen: 'bazi_course_seen',
  last: 'bazi_course_last',
  pos:  'bazi_course_pos',
  // 内容总量，写给五术堂导航看板当分母用——内容会一直加，
  // 看板那边不该再把 16/14/92 写死在字符串里
  counts: 'bazi_course_counts',
  // 我的笔记：用户自己划的句子。⚠️ 与内容里那 14 篇「笔记」是两回事，
  // UI 上一律叫「我的笔记」，别混。
  notes: 'bazi_course_mynotes',
  theme: 'bazi_course_theme'
};
function ls(k, d) {
  try { var v = localStorage.getItem(k); return v ? JSON.parse(v) : d; }
  catch (e) { return d; }
}
function save(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) {} }

/* ============================ 按需加载 ============================ */
var loaded = {};
function need(file, globalName) {
  if (loaded[file]) return Promise.resolve(window[globalName]);
  return new Promise(function (res, rej) {
    var s = document.createElement('script');
    s.src = 'data/' + file;
    s.onload = function () { loaded[file] = 1; res(window[globalName]); };
    s.onerror = function () { rej(new Error('加载失败 ' + file)); };
    document.head.appendChild(s);
  });
}
var needCourse = function () { return need('data-course.js', 'DATA_COURSE'); };
var needNotes  = function () { return need('data-notes.js', 'DATA_NOTES'); };
var needQuiz   = function () { return need('data-quiz.js', 'DATA_QUIZ'); };
// 问题清单 70KB，只有点进「四张索引表」才要，不进首屏包
var needIndex  = function () { return need('data-index.js', 'DATA_INDEX'); };

/* ============================ 路由 ============================
 * 套壳(view.html)里 iframe 与顶层共享同一条 session history。
 * 若本站不碰 history，做题深处一次侧滑会直接退出整个 App 回导航首页。
 * 所以照其余几个 App 的统一包装：前进 pushState，回到栈上已有的屏则
 * history.go(-n) 折叠，popstate 幂等重放。
 */
var stack = [];   // 历史条目，与 history 的 state.i 一一对应
var pos = 0;      // 当前所在下标
var cur = { scr: 'home', id: null };

var TITLES = {
  home: '命理精讲', course: '教材 · 16章', chapter: '', notes: '笔记与索引',
  note: '', index: '问题清单', outline: '学习路线', qlist: '命例题库',
  quiz: '', search: '搜索', mynotes: '我的笔记'
};
var ROOTS = { home: 1, course: 1, notes: 1, qlist: 1 };

function _apply(scr, id) {
  cur = { scr: scr, id: id };
  $$('.screen').forEach(function (el) { el.classList.remove('active'); });
  var el = $('#s-' + scr);
  if (el) el.classList.add('active');

  $('#btnBack').classList.toggle('show', !ROOTS[scr]);
  $('#ttl').textContent = TITLES[scr] || '命理精讲';
  $$('.tabbar button').forEach(function (b) {
    b.classList.toggle('on', b.dataset.tab === scr);
  });
  $('#fabToc').style.display = (scr === 'chapter' || scr === 'note') ? 'block' : 'none';
  if (scr !== 'quiz') $('#stickyChart').classList.add('hide');
  hideToast();
  var sb = $('#selBtn'); if (sb) sb.classList.remove('on');

  RENDER[scr] && RENDER[scr](id);
  if (scr !== 'search') save(K.last, { scr: scr, id: id });
  window.scrollTo(0, 0);
}

function show(scr, id, find) {
  // find＝{kw,occ}：从搜索结果跳过来时，渲染完要滚到那一处并高亮
  pendingFind = find || null;
  if (scr === cur.scr && id === cur.id) {
    if (find) _apply(scr, id);   // 已经在这一屏，也要重新定位
    return;
  }
  // 目标已在当前位置之前 → 折叠回去，不要堆重复条目
  for (var k = 0; k <= pos && k < stack.length; k++) {
    if (stack[k].scr === scr && stack[k].id === id) {
      if (k < pos) { history.go(k - pos); return; }
      break;
    }
  }
  // 新导航：丢弃 forward 侧的条目（与浏览器行为一致）
  stack = stack.slice(0, pos + 1);
  stack.push({ scr: scr, id: id });
  pos = stack.length - 1;
  history.pushState({ i: pos }, '', '');
  _apply(scr, id);
}

window.addEventListener('popstate', function (e) {
  var i = (e.state && typeof e.state.i === 'number') ? e.state.i : 0;
  if (i >= stack.length) i = stack.length - 1;
  if (i < 0) i = 0;
  // ⚠️ 只移动指针，绝不截断 stack——截断会让 forward 找不到原来那屏
  pos = i;
  var t = stack[i] || { scr: 'home', id: null };
  _apply(t.scr, t.id);
});

/* ============================ 视图 ============================ */
var RENDER = {};

function esc(s) {
  return String(s).replace(/[&<>"]/g, function (c) {
    return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c];
  });
}

/* 干支按五行上色。⚠️ 这份映射必须与 mdlite.py 的 _WUXING 保持一致，
   否则同一个字在吸顶条和正文里会是两种颜色。 */
var WX = {};
[['甲乙寅卯', 'mu'], ['丙丁巳午', 'huo'], ['戊己辰戌丑未', 'tu'],
 ['庚辛申酉', 'jin'], ['壬癸亥子', 'shui']].forEach(function (p) {
  p[0].split('').forEach(function (c) { WX[c] = p[1]; });
});
function gz(c, cls) {
  return '<span class="' + cls + (WX[c] ? ' w-' + WX[c] : '') + '">' + esc(c) + '</span>';
}

/* ============================ 提示条 ============================ */
var toastTimer = null;
function toast(msg, actLabel, actFn) {
  var t = $('#toast');
  if (!t) return;
  $('#toastTxt').textContent = msg;
  var b = $('#toastAct');
  if (actLabel) {
    b.textContent = actLabel;
    b.style.display = '';
    b.onclick = function () { hideToast(); actFn(); };
  } else b.style.display = 'none';
  t.classList.add('on');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(hideToast, 5000);
}
function hideToast() {
  var t = $('#toast');
  if (t) t.classList.remove('on');
  clearTimeout(toastTimer);
}

/* ==================== 搜索定位：滚到命中处并高亮 ====================
 * 搜索结果点进来，以前是回到文档顶部——一章六千字，等于让人再找一遍。
 *
 * ⚠️ 关键词常被行内标签劈成多个文本节点（「巳<strong>申</strong>合」），
 *    所以先把全部文本节点拼成一条串、在串上定位，再用 Range 映射回 DOM。
 *    同节点内的命中精确套 <mark>；跨节点的 surroundContents 会抛错，
 *    退化成整段闪一下——照样看得见，不会因为一个高亮把页面搞崩。
 */
var pendingFind = null;
function takeFind() { var f = pendingFind; pendingFind = null; return f; }

var BLOCKISH = { P: 1, LI: 1, TD: 1, TH: 1, DIV: 1, BLOCKQUOTE: 1, PRE: 1,
                 H1: 1, H2: 1, H3: 1, H4: 1, TABLE: 1 };

function findInDoc(roots, kw, occ) {
  if (!kw) return false;
  roots = [].concat(roots).filter(Boolean);
  if (!roots.length) return false;

  var nodes = [], text = '';
  roots.forEach(function (root) {
    var w = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, null, false), n;
    while ((n = w.nextNode())) { nodes.push({ node: n, at: text.length }); text += n.nodeValue; }
  });

  var idx = -1, from = 0;
  for (var k = 0; k <= (occ || 0); k++) {
    idx = text.indexOf(kw, from);
    if (idx < 0) break;
    from = idx + 1;
  }
  // 序号对不上（纯文本与 DOM 之间总有细微出入）就退回第一处，别放弃定位
  if (idx < 0) idx = text.indexOf(kw);
  if (idx < 0) return false;

  function locate(p) {
    for (var i = nodes.length - 1; i >= 0; i--) {
      if (nodes[i].at <= p) return { node: nodes[i].node, off: p - nodes[i].at };
    }
    return null;
  }
  var a = locate(idx), b = locate(idx + kw.length - 1);
  if (!a || !b) return false;

  var target = null;
  try {
    var r = document.createRange();
    r.setStart(a.node, a.off);
    r.setEnd(b.node, Math.min(b.off + 1, b.node.nodeValue.length));
    var m = document.createElement('mark');
    m.className = 'sr-kw';
    r.surroundContents(m);        // 跨标签时抛错 → 走下面的整段高亮
    target = m;
  } catch (e) {
    var blk = a.node.parentNode;
    while (blk && !BLOCKISH[blk.tagName] && blk.parentNode) blk = blk.parentNode;
    if (blk && blk.classList) { blk.classList.add('sr-blk'); target = blk; }
  }
  if (!target) return false;

  // jsdom 没实现 scrollIntoView，别让它把整条渲染带崩
  try { target.scrollIntoView({ block: 'center' }); } catch (e2) {
    try { window.scrollTo(0, target.offsetTop - 120); } catch (e3) {}
  }
  return true;
}

/* ==================== 长文回来接着读 ====================
 * 教材一章平均六千字、最长九千字，读到一半退出，回来不该从头开始。
 * read[id] 只记百分比（给列表看），这里另存实际 scrollTop。
 */
function savePos(id) {
  var y = document.documentElement.scrollTop || document.body.scrollTop || 0;
  var p = ls(K.pos, {});
  if (Math.abs((p[id] || 0) - y) < 40) return;
  p[id] = y;
  save(K.pos, p);
}
function restorePos(id) {
  var y = (ls(K.pos, {}))[id] || 0;
  var read = ls(K.read, {});
  // 快读完的（≥95%）不必再跳回去，从头重看更顺
  if (y < 300 || (read[id] || 0) >= 95) return false;
  try { window.scrollTo(0, y); } catch (e) {}
  toast('已回到上次读到的地方', '从头读', function () { window.scrollTo(0, 0); });
  return true;
}

/* 文档渲染完的统一收尾：优先搜索定位，其次恢复上次位置 */
function afterDoc(root, id) {
  var f = takeFind();
  if (f) {
    if (findInDoc(root, f.kw, f.occ)) return;
  }
  restorePos(id);
}

/* ---------- 首页 ---------- */
RENDER.home = function () {
  var c = META.counts || {};
  $('#hCourse').textContent = c.course || 0;
  $('#hNotes').textContent = c.notes || 0;
  $('#hQuiz').textContent = c.quiz || 0;
  $('#buildInfo').textContent = '内容更新于 ' + (META.built || '—');

  var read = ls(K.read, {});
  // ⚠️ read 里教材(c*)与笔记(n*)混存，数"章"只能取 c 开头
  function done(pre) {
    return Object.keys(read).filter(function (k) {
      return k.charAt(0) === pre && read[k] >= 90;
    }).length;
  }
  var chDone = done('c'), ntDone = done('n');
  var qDone = Object.keys(ls(K.seen, {})).length;
  // 口径与五术堂导航看板一致：教材16 + 笔记14 + 命例92
  var total = (c.course || 16) + (c.notes || 14) + (c.quiz || 92);
  var pct = Math.round((chDone + ntDone + qDone) / total * 100);
  $('#progPct').textContent = pct + '%';
  $('#progBar').style.width = pct + '%';

  $('#progChips').innerHTML =
    '<span class="pill g">教材 ' + chDone + '/' + (c.course || 16) + '</span>' +
    '<span class="pill g">笔记 ' + ntDone + '/' + (c.notes || 14) + '</span>' +
    '<span class="pill g">命例 ' + qDone + '/' + (c.quiz || 92) + '</span>';

  var mn = myNotes().length;
  var hint = $('#myNoteHint');
  if (hint) hint.textContent = mn ? ('已存 ' + mn + ' 条') : '选中正文任意一句，即可存进来';

  var last = ls(K.last, null);
  var box = $('#resume');
  if (last && last.scr && last.scr !== 'home' && !ROOTS[last.scr]) {
    box.innerHTML = '<div class="card tap" id="resumeCard"><div class="row spread">' +
      '<div><b style="font-size:15px">继续上次</b><div class="muted" style="margin-top:2px">' +
      esc(lastLabel(last)) + '</div></div><span style="color:var(--ink3)">›</span></div></div>';
    $('#resumeCard').onclick = function () { show(last.scr, last.id); };
  } else box.innerHTML = '';
};

function lastLabel(l) {
  if (l.scr === 'chapter') return '第 ' + l.id + ' 章';
  if (l.scr === 'note') return '笔记 ' + l.id;
  if (l.scr === 'quiz') return '第 ' + l.id + ' 题';
  return TITLES[l.scr] || '';
}

/* ---------- 教材 ---------- */
RENDER.course = function () {
  var box = $('#courseList');
  box.innerHTML = '<div class="empty">载入中…</div>';
  needCourse().then(function (list) {
    var read = ls(K.read, {});
    box.innerHTML = list.map(function (c) {
      var p = read[c.id] || 0;
      return '<div class="card tap" data-ch="' + c.n + '">' +
        '<div class="row spread"><div style="flex:1">' +
        '<b style="font-size:15.5px">第' + c.n + '章 · ' + esc(c.title) + '</b>' +
        '<div class="muted" style="margin-top:3px">' + Math.round(c.chars / 100) / 10 + ' 千字 · ' +
        c.toc.length + ' 节</div></div>' +
        (p >= 90 ? '<span class="pill">已读</span>' : p > 0 ?
          '<span class="pill g">' + p + '%</span>' : '<span style="color:var(--ink3)">›</span>') +
        '</div>' + (p > 0 && p < 90 ? '<div class="bar"><i style="width:' + p + '%"></i></div>' : '') +
        '</div>';
    }).join('');
    $$('[data-ch]', box).forEach(function (el) {
      el.onclick = function () { show('chapter', +el.dataset.ch); };
    });
  });
};

var curDoc = null;
RENDER.chapter = function (n) {
  needCourse().then(function (list) {
    var c = list.filter(function (x) { return x.n === n; })[0];
    if (!c) return;
    curDoc = c;
    $('#ttl').textContent = '第' + c.n + '章 · ' + c.title;
    $('#chapterBody').innerHTML = '<h1>' + esc(c.title) + '</h1>' + c.html;
    bindDoc($('#chapterBody'));
    $('#prevCh').disabled = n <= 1;
    $('#nextCh').disabled = n >= list.length;
    $('#prevCh').onclick = function () { show('chapter', n - 1); };
    $('#nextCh').onclick = function () { show('chapter', n + 1); };
    trackRead(c.id);
    afterDoc($('#chapterBody'), c.id);
  });
};

/* ---------- 笔记 ---------- */
RENDER.notes = function () {
  var box = $('#noteList');
  box.innerHTML = '<div class="empty">载入中…</div>';
  needNotes().then(function (list) {
    var read = ls(K.read, {});
    box.innerHTML =
      '<div class="card tap" data-go2="index"><div class="row spread">' +
      '<div><b style="font-size:15px">📇 问题清单 · 四张索引表</b>' +
      '<div class="muted" style="margin-top:2px">问题／知识点／命例反查</div></div>' +
      '<span style="color:var(--ink3)">›</span></div></div>' +
      list.map(function (c) {
        return '<div class="card tap" data-nt="' + c.n + '">' +
          '<div class="row spread"><div style="flex:1">' +
          '<b style="font-size:15px">八字' + String(c.n).padStart(2, '0') + ' · ' + esc(c.title) + '</b>' +
          '<div class="muted" style="margin-top:3px">' + Math.round(c.chars / 100) / 10 + ' 千字</div>' +
          '</div>' + (read[c.id] >= 90 ? '<span class="pill">已读</span>' :
            '<span style="color:var(--ink3)">›</span>') + '</div></div>';
      }).join('');
    $$('[data-nt]', box).forEach(function (el) {
      el.onclick = function () { show('note', +el.dataset.nt); };
    });
    $$('[data-go2]', box).forEach(function (el) {
      el.onclick = function () { show(el.dataset.go2, null); };
    });
  });
};

RENDER.note = function (n) {
  needNotes().then(function (list) {
    var c = list.filter(function (x) { return x.n === n; })[0];
    if (!c) return;
    curDoc = c;
    $('#ttl').textContent = c.title;
    $('#noteBody').innerHTML = '<h1>' + esc(c.title) + '</h1>' + c.html;
    bindDoc($('#noteBody'));

    // 上/下篇：笔记按 n 排序，前后各取一篇（教材早就有，笔记之前只能退回列表）
    var i = -1;
    for (var k = 0; k < list.length; k++) if (list[k].n === n) { i = k; break; }
    var prev = i > 0 ? list[i - 1] : null;
    var next = i >= 0 && i < list.length - 1 ? list[i + 1] : null;
    $('#prevNt').disabled = !prev;
    $('#nextNt').disabled = !next;
    $('#prevNt').textContent = prev ? '‹ ' + prev.title : '‹ 上一篇';
    $('#nextNt').textContent = next ? next.title + ' ›' : '下一篇 ›';
    $('#prevNt').onclick = prev ? function () { show('note', prev.n); } : null;
    $('#nextNt').onclick = next ? function () { show('note', next.n); } : null;

    trackRead(c.id);
    afterDoc($('#noteBody'), c.id);
  });
};

RENDER.index = function () {
  var box = $('#indexBody');
  box.innerHTML = '<div class="empty">载入中…</div>';
  needIndex().then(function (html) {
    box.innerHTML = html || '';
    bindDoc(box);
    afterDoc(box, 'index');
  });
};
RENDER.outline = function () {
  $('#outlineBody').innerHTML = META.outline || '';
  bindDoc($('#outlineBody'));
};

/* 文内跳转：[[wiki]] 与题号引用（原文里写作【21】） */
function bindDoc(root) {
  $$('a.wiki', root).forEach(function (a) {
    a.onclick = function (e) {
      e.preventDefault();
      gotoWiki(a.dataset.wiki);
    };
  });
  $$('a.qref', root).forEach(function (a) {
    a.onclick = function (e) {
      e.preventDefault();
      show('quiz', +a.dataset.q);
    };
  });
}
function gotoWiki(name) {
  /* 链接写作「八字06-未入辰库是什么意思#八、⭐ 追问：…」——# 后面是【标题原文】。
     ⚠️ 以前整串拿去匹配篇号，锚点被直接丢掉，点进去永远落在文章顶部；
        笔记动辄几百行，等于"能跳到、但找不着"。
     这里把锚点拆出来，交给搜索那套 findInDoc 按纯文本定位并高亮——
     ⭐ 故意不在前端复刻 build.py 的 slug 规则：那要求两边永远同步，太脆。
        按标题文本找，改了 slug 规则也不会坏。找不到就退化成落顶部，不会更糟。*/
  var find = null, h = name.indexOf('#');
  if (h >= 0) {
    var anchor = name.slice(h + 1).trim();
    name = name.slice(0, h);
    if (anchor) find = { kw: anchor, occ: 0 };
  }
  // 先认几个整页目标，否则「99-命例题库」会被下面的章号规则误当成第99章
  if (/问题清单/.test(name)) { show('index', null, find); return; }
  if (/总目录|学习路线/.test(name)) { show('outline', null, find); return; }
  if (/命例题库/.test(name)) { show('qlist', null, find); return; }
  var m = /八字(\d+)/.exec(name);
  if (m) { show('note', +m[1], find); return; }
  m = /题\s*(\d+)/.exec(name);
  if (m) { show('quiz', +m[1], find); return; }
  m = /第?\s*(\d+)\s*[章篇]/.exec(name);
  if (m) { show('chapter', +m[1], find); return; }
  show('search', null);
  setTimeout(function () { $('#q').value = name; doSearch(); }, 60);
}

/* 阅读进度：滚动到底算读完 */
var readTimer = null;
function trackRead(id) {
  clearInterval(readTimer);
  readTimer = setInterval(function () {
    if (cur.scr !== 'chapter' && cur.scr !== 'note') { clearInterval(readTimer); return; }
    var h = document.documentElement;
    var max = h.scrollHeight - h.clientHeight;
    var p = max <= 0 ? 100 : Math.min(100, Math.round((h.scrollTop / max) * 100));
    var read = ls(K.read, {});
    if (p > (read[id] || 0)) { read[id] = p; save(K.read, read); }
    savePos(id);   // 百分比只够列表显示，回来接着读要的是实际位置
  }, 1500);
}

/* ---------- 题库 ---------- */
var qFilter = { mode: 'all', tag: null };
var tagsOpen = false;

RENDER.qlist = function () {
  var box = $('#qRows');
  box.innerHTML = '<div class="empty">载入中…</div>';
  needQuiz().then(function (Q) {
    var seen = ls(K.seen, {});

    var modes = [
      ['all', '全部 ' + Q.items.length],
      ['new', '没看过'],
      ['star', '精读'],
      ['chart', '有完整盘']
    ];
    $('#qFilters').innerHTML = modes.map(function (m) {
      return '<span class="pill' + (qFilter.mode === m[0] ? ' sel' : '') +
        '" data-m="' + m[0] + '">' + m[1] + '</span>';
    }).join('');
    $$('[data-m]').forEach(function (el) {
      el.onclick = function () { qFilter.mode = el.dataset.m; RENDER.qlist(); };
    });

    /* 考点标签：45 个全都要能筛到。
       以前写死 slice(0,18)，「刑」「破」「空亡」「暗合」「羊刃」这些
       低频但正经的考点全被埋了，筛不出来。现在默认收起，一键展开全部；
       当前选中的那个即便排在后面也始终可见。 */
    var FOLD = 14;
    var shown = tagsOpen ? Q.tags : Q.tags.slice(0, FOLD);
    if (qFilter.tag && !shown.some(function (t) { return t[0] === qFilter.tag; })) {
      var sel = Q.tags.filter(function (t) { return t[0] === qFilter.tag; });
      shown = sel.concat(shown);
    }
    $('#qTags').innerHTML = '<span class="pill' + (qFilter.tag ? ' g' : ' sel') +
      '" data-t="">全部考点</span>' +
      shown.map(function (t) {
        return '<span class="pill' + (qFilter.tag === t[0] ? ' sel' : ' g') +
          '" data-t="' + esc(t[0]) + '">' + esc(t[0]) + ' ' + t[1] + '</span>';
      }).join('') +
      (Q.tags.length > FOLD
        ? '<span class="pill g" id="tagsMore">' +
          (tagsOpen ? '收起 ‹' : '更多 ' + (Q.tags.length - FOLD) + ' 个 ›') + '</span>'
        : '');
    $$('[data-t]').forEach(function (el) {
      el.onclick = function () { qFilter.tag = el.dataset.t || null; RENDER.qlist(); };
    });
    if ($('#tagsMore')) {
      $('#tagsMore').onclick = function () { tagsOpen = !tagsOpen; RENDER.qlist(); };
    }

    var list = Q.items.filter(function (it) {
      if (qFilter.tag && it.tags.indexOf(qFilter.tag) < 0) return false;
      switch (qFilter.mode) {
        case 'new': return !seen[it.n];
        case 'star': return it.star > 0;
        case 'chart': return it.nCharts > 0;
      }
      return true;
    });

    if (!list.length) { box.innerHTML = '<div class="empty">这个筛选下没有题</div>'; return; }
    box.innerHTML = list.map(function (it) {
      return '<div class="qrow" data-q="' + it.n + '">' +
        '<span class="n">' + it.n + '</span>' +
        '<span class="t">' + (it.star ? '⭐' : '') + esc(it.title) +
        (it.noAnswer ? ' <span class="pill g" style="font-size:10px">反推</span>' : '') + '</span>' +
        '<span class="s"><i class="dot ' + (seen[it.n] ? 'ok' : 'new') + '"></i></span></div>';
    }).join('');
    $$('[data-q]', box).forEach(function (el) {
      el.onclick = function () { show('quiz', +el.dataset.q); };
    });
  });
};

RENDER.quiz = function (n) {
  needQuiz().then(function (Q) {
    var it = Q.items.filter(function (x) { return x.n === n; })[0];
    if (!it) return;
    $('#ttl').textContent = '第 ' + it.n + ' 题';

    var h = '<div class="card">';
    h += '<div class="qhead"><span class="no">' + it.n + '</span>' +
         '<span class="tt">' + esc(it.title) + '</span></div>';
    if (it.tags.length) {
      h += '<div class="row wrap" style="gap:5px;margin:6px 0 2px">' +
        it.tags.map(function (t) { return '<span class="pill g">' + esc(t) + '</span>'; }).join('') +
        '</div>';
    }
    h += '<div class="doc">' + it.face + '</div>';
    h += '</div>';

    // 三层递进：先自己推，再看解，还不懂再看拆解
    h += '<div class="layer" id="L1"><button class="btn pri" id="bJie">' +
      (it.noAnswer ? '看提示方向' : '对答案 · ' + esc(it.jieLabel)) + '</button></div>';
    h += '<div class="layer" id="L2"></div>';
    h += '<div class="layer" id="L3"></div>';
    h += '<div id="L4"></div>';

    $('#quizBody').innerHTML = h;
    bindDoc($('#quizBody'));
    navBar(it);
    setupSticky(it);

    function openChai() {
      $('#L3').innerHTML = '<div class="reveal chai doc">' +
        '<div class="muted" style="margin-bottom:8px">我补的推理，非原文，可推翻。</div>' +
        it.chai + '</div>';
      bindDoc($('#L3'));
    }
    function openJie() {
      $('#L1').innerHTML = '';
      var body = it.noAnswer
        ? '<div class="muted" style="margin-bottom:6px">⚠️ 原书未给解，这是反推题——下面只有方向，没有答案。</div>' + it.jie
        : it.jie;
      $('#L2').innerHTML = '<div class="reveal doc">' + body + '</div>';
      bindDoc($('#L2'));
      if (it.chai) {
        $('#L3').innerHTML = '<button class="btn" id="bChai" style="width:100%;margin-top:10px">' +
          '🔍 还是不懂 · 看拆解</button>';
        $('#bChai').onclick = openChai;
      }
      markSeen(it.n);
    }
    $('#bJie').onclick = openJie;

    /* 从搜索跳进来：命中可能落在「解」或「拆解」里，那两层默认是收着的，
       不展开的话点进来只看见题面，等于没搜到。按命中位置自动拆到那一层。 */
    var f = takeFind();
    if (f) {
      var inFace = plain(it.face).indexOf(f.kw) >= 0;
      var inJie  = plain(it.jie).indexOf(f.kw) >= 0;
      if (!inFace) {
        openJie();
        if (!inJie && it.chai) openChai();
        toast('命中在' + (inJie ? '答案' : '拆解') + '里，已经展开');
      }
      findInDoc($('#quizBody'), f.kw, f.occ);
    }
  });
};

/* HTML → 纯文本。搜索与「命中在哪一层」都靠它。 */
var _pd = null;
function plain(html) {
  if (!html) return '';
  if (!_pd) _pd = document.createElement('div');
  _pd.innerHTML = html;
  return _pd.textContent || '';
}

/* ---------- 吸顶四柱盘 ----------
 * 讲解与拆解里满是「卯戌合」「日支巳」这种指代盘上具体字的话，
 * 盘滚出视野就得来回翻。滚过题头后把盘缩成一条钉在顶栏下方。
 * 多盘对照题（题21/35 等 9 道）把两个盘都放上去，横向可滑。
 */
function setupSticky(it) {
  var bar = $('#stickyChart');
  var cs = it.charts || [];
  bar.classList.toggle('hide', !cs.length);
  if (!cs.length) { bar.querySelector('.inner').innerHTML = ''; return; }

  var pos = ['年', '月', '日', '时'];
  bar.querySelector('.inner').innerHTML = cs.map(function (c) {
    return '<div class="grp">' +
      '<span class="lb">' + esc(c.label || (c.g + '造')) + '</span>' +
      '<div class="cols">' + pos.map(function (p, i) {
        return '<div class="c' + (i === 2 ? ' day' : '') + '">' +
          '<div class="p">' + p + '</div>' +
          gz(c.gan[i], 'a') + gz(c.zhi[i], 'b') + '</div>';
      }).join('') + '</div></div>';
  }).join('');

}

/* 看过就记一笔，仅用于列表上的圆点与「没看过」筛选。不打分、不排复习。 */
function markSeen(n) {
  var s = ls(K.seen, {});
  if (s[n]) return;
  s[n] = Date.now();
  save(K.seen, s);
}

function navBar(it) {
  needQuiz().then(function (Q) {
    var i = -1;
    for (var k = 0; k < Q.items.length; k++) if (Q.items[k].n === it.n) { i = k; break; }
    var prev = i > 0 ? Q.items[i - 1] : null;
    var next = i >= 0 && i < Q.items.length - 1 ? Q.items[i + 1] : null;
    $('#L4').innerHTML =
      '<div class="row spread" id="qnav" style="gap:10px;margin:20px 0 6px">' +
      '<button class="btn" id="bPrev" style="flex:1"' + (prev ? '' : ' disabled') + '>‹ 上一题</button>' +
      '<button class="btn" id="bList" style="flex:0 0 auto">题库</button>' +
      '<button class="btn pri" id="bNext" style="flex:1"' + (next ? '' : ' disabled') + '>下一题 ›</button>' +
      '</div>';
    $('#bList').onclick = function () { show('qlist', null); };
    if (prev) $('#bPrev').onclick = function () { show('quiz', prev.n); };
    if (next) $('#bNext').onclick = function () { show('quiz', next.n); };
  });
}

/* ==================== 我的笔记 ====================
 * 选中正文任意一句 → 浮出「存进笔记」→ 存下原文＋出处＋在文中的第几处。
 * ⚠️ 与内容里那 14 篇「笔记」是两回事，UI 一律称「我的笔记」。
 *
 * 跳回原文直接复用搜索定位那套（pendingFind + findInDoc）：
 * 存 occ（该句在本文档中第几次出现），点笔记就能滚回原句并高亮。
 */
function myNotes() { return ls(K.notes, []); }
function saveMyNotes(v) { save(K.notes, v); }

/* 当前屏对应的正文容器与出处信息 */
function noteCtx() {
  if (cur.scr === 'chapter') return { root: $('#chapterBody'), from: '第' + cur.id + '章' };
  if (cur.scr === 'note')    return { root: $('#noteBody'),    from: '笔记 ' + cur.id };
  if (cur.scr === 'quiz')    return { root: $('#quizBody'),    from: '题 ' + cur.id };
  if (cur.scr === 'index')   return { root: $('#indexBody'),   from: '问题清单' };
  if (cur.scr === 'outline') return { root: $('#outlineBody'), from: '学习路线' };
  return null;
}

/* 选中文本在该文档纯文本里是第几次出现——跳回时用它精确定位 */
function occOf(root, text) {
  var all = root.textContent || '';
  var sel = window.getSelection();
  if (!sel || !sel.rangeCount) return 0;
  var r = sel.getRangeAt(0).cloneRange();
  try {
    r.setStart(root, 0);
    var before = r.toString();
    return before.split(text).length - 1;
  } catch (e) { return 0; }
}

var selTimer = null;
function onSelChange() {
  clearTimeout(selTimer);
  selTimer = setTimeout(function () {
    var btn = $('#selBtn');
    if (!btn) return;
    var sel = window.getSelection();
    var text = sel ? String(sel).trim() : '';
    var ctx = noteCtx();
    // 选太短没意义、太长存不下重点；必须落在正文容器内
    if (!ctx || text.length < 4 || text.length > 400 ||
        !sel.rangeCount || !ctx.root.contains(sel.getRangeAt(0).commonAncestorContainer)) {
      btn.classList.remove('on');
      return;
    }
    var rect;
    try { rect = sel.getRangeAt(0).getBoundingClientRect(); } catch (e) { return; }
    if (!rect || !rect.width) { btn.classList.remove('on'); return; }
    var top = rect.top - 46;
    if (top < 56) top = rect.bottom + 8;          // 顶部放不下就挪到选区下方
    btn.style.top = top + 'px';
    btn.style.left = Math.max(10, Math.min(rect.left, window.innerWidth - 130)) + 'px';
    btn.classList.add('on');
    btn._pending = { text: text, ctx: ctx, occ: occOf(ctx.root, text) };
  }, 120);
}

function addMyNote() {
  var btn = $('#selBtn');
  var p = btn && btn._pending;
  if (!p) return;
  var list = myNotes();
  // 同一处重复划不重复存
  if (list.some(function (x) { return x.text === p.text && x.scr === cur.scr && x.id === cur.id; })) {
    toast('这句已经在笔记里了');
  } else {
    list.unshift({
      t: Date.now(), text: p.text, from: p.ctx.from,
      scr: cur.scr, id: cur.id, occ: p.occ, memo: ''
    });
    saveMyNotes(list);
    toast('已存进笔记（共 ' + list.length + ' 条）', '去看看', function () { show('mynotes', null); });
  }
  btn.classList.remove('on');
  var sel = window.getSelection();
  if (sel && sel.removeAllRanges) sel.removeAllRanges();
}

var mnFilter = 'all';
RENDER.mynotes = function () {
  var list = myNotes();
  var box = $('#mnList');
  var kinds = [['all', '全部 ' + list.length]];
  var byFrom = {};
  list.forEach(function (n) { byFrom[n.scr] = (byFrom[n.scr] || 0) + 1; });
  [['chapter', '教材'], ['note', '笔记'], ['quiz', '命例']].forEach(function (k) {
    if (byFrom[k[0]]) kinds.push([k[0], k[1] + ' ' + byFrom[k[0]]]);
  });
  $('#mnFilters').innerHTML = list.length ? kinds.map(function (k) {
    return '<span class="pill' + (mnFilter === k[0] ? ' sel' : ' g') + '" data-mn="' + k[0] + '">' + k[1] + '</span>';
  }).join('') : '';
  $$('[data-mn]').forEach(function (el) {
    el.onclick = function () { mnFilter = el.dataset.mn; RENDER.mynotes(); };
  });

  var show_ = list.filter(function (n) { return mnFilter === 'all' || n.scr === mnFilter; });
  if (!show_.length) {
    box.innerHTML = '<div class="empty">' + (list.length
      ? '这个来源下还没有笔记'
      : '还没有笔记。<br><br>读教材、笔记或命例时，<b>用手指长按选中一句话</b>，<br>会浮出「📌 存进笔记」。') + '</div>';
    return;
  }
  box.innerHTML = show_.map(function (n, i) {
    var idx = list.indexOf(n);
    return '<div class="mncard">' +
      '<div class="mnfrom">' + esc(n.from) + '<span>' + fmtDay(n.t) + '</span></div>' +
      '<div class="mntext" data-mn-go="' + idx + '">' + esc(n.text) + '</div>' +
      (n.memo ? '<div class="mnmemo" data-mn-memo="' + idx + '">' + esc(n.memo) + '</div>' : '') +
      '<div class="mnact">' +
        '<button data-mn-go="' + idx + '">跳到原文 ›</button>' +
        '<button data-mn-memo="' + idx + '">' + (n.memo ? '改批注' : '加批注') + '</button>' +
        '<button data-mn-del="' + idx + '" class="del">删除</button>' +
      '</div></div>';
  }).join('');
  $$('[data-mn-go]', box).forEach(function (el) {
    el.onclick = function () {
      var n = list[+el.dataset.mnGo];
      if (!n) return;
      show(n.scr, n.id, { kw: n.text.slice(0, 30), occ: n.occ || 0 });
    };
  });
  $$('[data-mn-memo]', box).forEach(function (el) {
    el.onclick = function () {
      var i = +el.dataset.mnMemo, n = list[i];
      var v = prompt('给这句话加一条自己的批注：', n.memo || '');
      if (v === null) return;
      n.memo = v.trim(); saveMyNotes(list); RENDER.mynotes();
    };
  });
  $$('[data-mn-del]', box).forEach(function (el) {
    el.onclick = function () {
      var i = +el.dataset.mnDel;
      if (!confirm('删掉这条笔记？')) return;
      list.splice(i, 1); saveMyNotes(list); RENDER.mynotes();
    };
  });
};

function fmtDay(t) {
  var d = new Date(t), n = new Date();
  var same = d.toDateString() === n.toDateString();
  return same ? '今天' : (d.getMonth() + 1) + '-' + d.getDate();
}

/* ---------- 搜索 ---------- */
RENDER.search = function () { setTimeout(function () { $('#q').focus(); }, 80); };

/* 题库的可搜索全文。
 * ⚠️ data 里的 q.text 是 strip_md(b)[:600]——截断的，92 题里 80 题被砍，
 *    平均只覆盖每题六成，答案和拆解基本搜不到。
 *    这里改从渲染用的 html 现提纯文本：覆盖 100%，且不给 data 多加一个字节。
 *    顺序 标题→考点→题面→解→拆解 与题目页展开后的 DOM 顺序一致，
 *    所以「第几次出现」的序号可以直接拿去定位。
 */
var qTextCache = null;
function quizTexts(Q) {
  if (qTextCache) return qTextCache;
  qTextCache = Q.items.map(function (it) {
    return it.title + ' ' + (it.tags || []).join(' ') + ' ' +
           plain(it.face) + plain(it.jie) + plain(it.chai);
  });
  return qTextCache;
}

var PER_DOC = 4;      // 同一篇最多列几条，免得一章刷满整屏
var MAX_HITS = 260;

function doSearch() {
  var kw = $('#q').value.trim();
  var box = $('#hits');
  if (kw.length < 1) { box.innerHTML = '<div class="empty">输入关键词开始搜索</div>'; return; }
  box.innerHTML = '<div class="empty">搜索中…</div>';
  // 空格分词：「墓库 冲开」＝两个词都要出现的地方。
  // 以前整串 indexOf，这么搜恒定 0 条。
  var terms = kw.split(/\s+/).filter(Boolean);
  var main = terms[0];
  var rest = terms.slice(1);

  Promise.all([needCourse(), needNotes(), needQuiz()]).then(function (r) {
    var hits = [], total = 0, capped = false;

    // 一篇文档里的每一处命中都列出来（上限 PER_DOC），并记下是第几处，
    // 点进去就能直接滚到那一处——以前只给第一处、还回到文档顶部。
    function scan(text, label, scr, id) {
      // 多词：所有词都得在这篇里，缺一个就跳过
      for (var t = 0; t < rest.length; t++) if (text.indexOf(rest[t]) < 0) return;

      // 先收齐 main 的全部出现位置
      var spots = [], at = -1, occ = 0;
      while ((at = text.indexOf(main, at + 1)) >= 0) { spots.push({ at: at, occ: occ }); occ++; }
      total += spots.length;

      // 多词时优先列「其他词也在附近」的那几处，否则片段里只看得见第一个词，
      // 看不出两者的关联。occ 保持原序号不变，定位才不会错位。
      if (rest.length) {
        spots.forEach(function (s) {
          s.near = rest.reduce(function (acc, w) {
            var d = Infinity, p = -1;
            while ((p = text.indexOf(w, p + 1)) >= 0) d = Math.min(d, Math.abs(p - s.at));
            return acc + d;
          }, 0);
        });
        spots.sort(function (a, b) { return a.near - b.near; });
      }

      var listed = 0, more = 0;
      spots.forEach(function (sp) {
        if (listed < PER_DOC && hits.length < MAX_HITS) {
          var s = Math.max(0, sp.at - 28);
          var tail = text.slice(sp.at + main.length, sp.at + main.length + 56);
          hits.push({
            label: label + (sp.occ ? ' · 第' + (sp.occ + 1) + '处' : ''),
            scr: scr, id: id, occ: sp.occ,
            snip: (s > 0 ? '…' : '') + esc(text.slice(s, sp.at)) +
                  '<em>' + esc(main) + '</em>' + hi(tail) + '…'
          });
          listed++;
        } else more++;
      });
      if (more > 0 && hits.length) hits[hits.length - 1].more = more;
      if (hits.length >= MAX_HITS) capped = true;
    }

    // 片段里把其余关键词也点出来
    function hi(s) {
      var out = esc(s);
      rest.forEach(function (w) {
        out = out.split(esc(w)).join('<em>' + esc(w) + '</em>');
      });
      return out;
    }

    r[0].forEach(function (c) { scan(c.text, '第' + c.n + '章 · ' + c.title, 'chapter', c.n); });
    r[1].forEach(function (c) { scan(c.text, '笔记 · ' + c.title, 'note', c.n); });
    var qt = quizTexts(r[2]);
    r[2].items.forEach(function (q, i) {
      scan(qt[i], '题' + q.n + ' · ' + q.title, 'quiz', q.n);
    });

    if (!hits.length) {
      box.innerHTML = '<div class="empty">没找到' +
        (rest.length ? '同时含「' + terms.map(esc).join('」「') + '」的地方'
                     : '「' + esc(kw) + '」') + '</div>';
      return;
    }
    box.innerHTML =
      '<div class="muted" style="margin-bottom:8px">' +
        (rest.length ? '同时含「' + terms.map(esc).join('」「') + '」：' : '') +
        '共 ' + total + ' 处' +
        (hits.length < total ? '，列出 ' + hits.length + ' 条' : '') +
        (capped ? '（已达上限，缩小关键词看更全）' : '') + '</div>' +
      hits.map(function (h, i) {
        return '<div class="hit" data-h="' + i + '"><b>' + esc(h.label) + '</b>' +
          (h.more ? '<span class="pill g" style="margin-left:6px;font-size:10px">本篇另有 ' +
                    h.more + ' 处</span>' : '') +
          '<p>' + h.snip + '</p></div>';
      }).join('');
    $$('[data-h]', box).forEach(function (el) {
      el.onclick = function () {
        var h = hits[+el.dataset.h];
        // 定位用第一个词——整串（含空格）在正文里不存在，传过去必然找不到
        show(h.scr, h.id, { kw: main, occ: h.occ });
      };
    });
  });
}

/* ---------- 目录抽屉 ---------- */
$('#fabToc').onclick = function () {
  if (!curDoc || !curDoc.toc || !curDoc.toc.length) return;
  $('#sheetInner').innerHTML = '<b style="font-size:15px">' + esc(curDoc.title) + '</b>' +
    '<div class="toc" style="margin-top:10px">' +
    curDoc.toc.map(function (t) {
      return '<a data-a="' + t.a + '" class="' + (t.lv >= 3 ? 'l3' : '') + '">' + esc(t.t) + '</a>';
    }).join('') + '</div>';
  $('#sheet').classList.add('on');
  $$('#sheetInner [data-a]').forEach(function (a) {
    a.onclick = function () {
      $('#sheet').classList.remove('on');
      var el = document.getElementById(a.dataset.a);
      if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
    };
  });
};
$('#sheet').onclick = function (e) { if (e.target === $('#sheet')) $('#sheet').classList.remove('on'); };

/* ---------- 交互绑定 ---------- */
$('#btnBack').onclick = function () { history.back(); };
$('#btnSearch').onclick = function () { show('search', null); };
$('#btnMyNotes').onclick = function () { show('mynotes', null); };
$('#selBtn').onclick = addMyNote;
document.addEventListener('selectionchange', onSelChange);
// 点别处就收起浮标
document.addEventListener('scroll', function () { $('#selBtn').classList.remove('on'); }, true);
$$('.tabbar button').forEach(function (b) {
  b.onclick = function () {
    var t = b.dataset.tab;
    if (t === cur.scr) { window.scrollTo({ top: 0, behavior: 'smooth' }); return; }
    // tab 是根屏：重置为栈底，避免来回切 tab 堆出一长串历史
    stack = [{ scr: t, id: null }];
    pos = 0;
    history.replaceState({ i: 0 }, '', '');
    _apply(t, null);
  };
});
$$('[data-go]').forEach(function (el) {
  el.onclick = function () { show(el.dataset.go, null); };
});
$('#q').addEventListener('input', function () {
  clearTimeout(window._st);
  window._st = setTimeout(doSearch, 220);
});

/* 主题 */
var THEME_MARK = { dark: ['阴', '配色：深色'], light: ['阳', '配色：浅色'] };
function applyTheme(t) {
  if (t) document.documentElement.setAttribute('data-theme', t);
  else document.documentElement.removeAttribute('data-theme');
  // 按钮显示的是「当前是哪一态」，不是「点了会变成什么」
  var m = THEME_MARK[t] || ['随', '配色：跟随系统'], b = $('#btnTheme');
  b.textContent = m[0];
  b.setAttribute('aria-label', m[1]);
  b.setAttribute('data-set', t ? '1' : '0');
}
applyTheme(ls(K.theme, null));
$('#btnTheme').onclick = function () {
  var now = ls(K.theme, null);
  var next = now === 'dark' ? 'light' : now === 'light' ? null : 'dark';
  save(K.theme, next); applyTheme(next);
};

/* 套壳适配：在 iframe 里时隐藏自带返回入口，交给 view.html 的顶栏 */
try {
  if (window.self !== window.top) document.documentElement.classList.add('wst-frame-guard');
} catch (e) {
  document.documentElement.classList.add('wst-frame-guard');
}

/* 启动 */
save(K.counts, META.counts || {});   // 把分母同步给导航看板
history.replaceState({ i: 0 }, '', '');
stack = [{ scr: 'home', id: null }];
pos = 0;
_apply('home', null);

if ('serviceWorker' in navigator) {
  window.addEventListener('load', function () {
    navigator.serviceWorker.register('sw.js').catch(function () {});
  });
}

})();
