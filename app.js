/* 八字精讲 — app.js
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
 *
 * ⚠️ 刻意不做 SRS／错题本／自评打分（用户 2026-08-08 要求「练就简单点」）。
 *    命例是主观题，本来也没法客观判分；这里只留一个「看过」标记，
 *    好让列表能看出做到哪了，不制造复习压力。
 */
var K = {
  read: 'bazi_course_read',
  seen: 'bazi_course_seen',
  last: 'bazi_course_last',
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

/* ============================ 路由 ============================
 * 套壳(view.html)里 iframe 与顶层共享同一条 session history。
 * 若本站不碰 history，做题深处一次侧滑会直接退出整个 App 回导航首页。
 * 所以照其余几个 App 的统一包装：前进 pushState，回到栈上已有的屏则
 * history.go(-n) 折叠，popstate 幂等重放。
 */
var stickyIO = null;  // 吸顶盘的 IntersectionObserver（切屏要断开）
var stack = [];   // 历史条目，与 history 的 state.i 一一对应
var pos = 0;      // 当前所在下标
var cur = { scr: 'home', id: null };

var TITLES = {
  home: '八字精讲', course: '教材 · 16章', chapter: '', notes: '笔记与索引',
  note: '', index: '问题清单', outline: '学习路线', qlist: '命例题库',
  quiz: '', search: '搜索'
};
var ROOTS = { home: 1, course: 1, notes: 1, qlist: 1 };

function _apply(scr, id) {
  cur = { scr: scr, id: id };
  $$('.screen').forEach(function (el) { el.classList.remove('active'); });
  var el = $('#s-' + scr);
  if (el) el.classList.add('active');

  $('#btnBack').classList.toggle('show', !ROOTS[scr]);
  $('#ttl').textContent = TITLES[scr] || '八字精讲';
  $$('.tabbar button').forEach(function (b) {
    b.classList.toggle('on', b.dataset.tab === scr);
  });
  $('#fabToc').style.display = (scr === 'chapter' || scr === 'note') ? 'block' : 'none';
  if (scr !== 'quiz') {
    $('#stickyChart').classList.remove('on');
    if (stickyIO) { stickyIO.disconnect(); stickyIO = null; }
  }

  RENDER[scr] && RENDER[scr](id);
  if (scr !== 'search') save(K.last, { scr: scr, id: id });
  window.scrollTo(0, 0);
}

function show(scr, id) {
  if (scr === cur.scr && id === cur.id) return;
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

/* ---------- 首页 ---------- */
RENDER.home = function () {
  var c = META.counts || {};
  $('#hCourse').textContent = c.course || 0;
  $('#hNotes').textContent = c.notes || 0;
  $('#hQuiz').textContent = c.quiz || 0;
  $('#buildInfo').textContent = '内容更新于 ' + (META.built || '—');

  var read = ls(K.read, {});
  // read 里教材(c*)与笔记(n*)混存，进度只算教材
  var chDone = Object.keys(read).filter(function (k) {
    return k.charAt(0) === 'c' && read[k] >= 90;
  }).length;
  var qDone = Object.keys(ls(K.seen, {})).length;
  var total = (c.course || 16) + (c.quiz || 92);
  var pct = Math.round((chDone + qDone) / total * 100);
  $('#progPct').textContent = pct + '%';
  $('#progBar').style.width = pct + '%';

  $('#progChips').innerHTML =
    '<span class="pill g">教材 ' + chDone + '/' + (c.course || 16) + '</span>' +
    '<span class="pill g">命例 ' + qDone + '/' + (c.quiz || 92) + '</span>';

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
    trackRead(c.id);
  });
};

RENDER.index = function () {
  $('#indexBody').innerHTML = META.index || '';
  bindDoc($('#indexBody'));
};
RENDER.outline = function () {
  $('#outlineBody').innerHTML = META.outline || '';
  bindDoc($('#outlineBody'));
};

/* 文内 [[wiki]] 跳转 */
function bindDoc(root) {
  $$('a.wiki', root).forEach(function (a) {
    a.onclick = function (e) {
      e.preventDefault();
      gotoWiki(a.dataset.wiki);
    };
  });
}
function gotoWiki(name) {
  var m = /八字(\d+)/.exec(name);
  if (m) { show('note', +m[1]); return; }
  m = /题\s*(\d+)/.exec(name);
  if (m) { show('quiz', +m[1]); return; }
  m = /第?\s*(\d+)\s*[章篇]/.exec(name);
  if (m) { show('chapter', +m[1]); return; }
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
  }, 1500);
}

/* ---------- 题库 ---------- */
var qFilter = { mode: 'all', tag: null };

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

    $('#qTags').innerHTML = '<span class="pill' + (qFilter.tag ? ' g' : ' sel') +
      '" data-t="">全部考点</span>' +
      Q.tags.slice(0, 18).map(function (t) {
        return '<span class="pill' + (qFilter.tag === t[0] ? ' sel' : ' g') +
          '" data-t="' + esc(t[0]) + '">' + esc(t[0]) + ' ' + t[1] + '</span>';
      }).join('');
    $$('[data-t]').forEach(function (el) {
      el.onclick = function () { qFilter.tag = el.dataset.t || null; RENDER.qlist(); };
    });

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
    if (it.chart) {
      var pos = ['年', '月', '日', '时'];
      h += '<div style="margin-top:8px"><span class="gender">' + it.chart.g + '造</span></div>';
      h += '<div class="chart">' + pos.map(function (p, i) {
        return '<div class="col"><div class="pos">' + p + '</div>' +
          '<div class="g">' + esc(it.chart.gan[i]) + '</div>' +
          '<div class="z">' + esc(it.chart.zhi[i]) + '</div></div>';
      }).join('') + '</div>';
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

    $('#bJie').onclick = function () {
      $('#L1').innerHTML = '';
      var body = it.noAnswer
        ? '<div class="muted" style="margin-bottom:6px">⚠️ 原书未给解，这是反推题——下面只有方向，没有答案。</div>' + it.jie
        : it.jie;
      $('#L2').innerHTML = '<div class="reveal doc">' + body + '</div>';
      bindDoc($('#L2'));
      if (it.chai) {
        $('#L3').innerHTML = '<button class="btn" id="bChai" style="width:100%;margin-top:10px">' +
          '🔍 还是不懂 · 看拆解</button>';
        $('#bChai').onclick = function () {
          $('#L3').innerHTML = '<div class="reveal chai doc">' +
            '<div class="muted" style="margin-bottom:8px">我补的推理，非原文，可推翻。</div>' +
            it.chai + '</div>';
          bindDoc($('#L3'));
        };
      }
      markSeen(it.n);
    };
  });
};

/* ---------- 吸顶四柱盘 ----------
 * 讲解与拆解里满是「卯戌合」「日支巳」这种指代盘上具体字的话，
 * 盘滚出视野就得来回翻。滚过题头后把盘缩成一条钉在顶栏下方。
 * 多盘对照题（题21/35 等 9 道）把两个盘都放上去，横向可滑。
 */
function setupSticky(it) {
  var bar = $('#stickyChart');
  if (stickyIO) { stickyIO.disconnect(); stickyIO = null; }
  bar.classList.remove('on');

  var cs = it.charts || [];
  if (!cs.length) { bar.querySelector('.inner').innerHTML = ''; return; }

  var pos = ['年', '月', '日', '时'];
  bar.querySelector('.inner').innerHTML = cs.map(function (c) {
    return '<div class="grp">' +
      (c.label ? '<span class="lb">' + esc(c.label) + '</span>' : '') +
      '<div class="cols">' + pos.map(function (p, i) {
        return '<div class="c' + (i === 2 ? ' day' : '') + '">' +
          '<div class="p">' + p + '</div>' +
          '<div class="a">' + esc(c.gan[i]) + '</div>' +
          '<div class="b">' + esc(c.zhi[i]) + '</div></div>';
      }).join('') + '</div></div>';
  }).join('');

  // 题头盘（或题面首个表格）滚出视野时才亮出来，别一进来就占两层
  var anchor = $('#quizBody .chart') || $('#quizBody table') || $('#quizBody .card');
  if (!anchor || typeof IntersectionObserver === 'undefined') { bar.classList.add('on'); return; }
  stickyIO = new IntersectionObserver(function (es) {
    bar.classList.toggle('on', !es[0].isIntersecting);
  }, { rootMargin: '-96px 0px 0px 0px', threshold: 0 });
  stickyIO.observe(anchor);
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

/* ---------- 搜索 ---------- */
RENDER.search = function () { setTimeout(function () { $('#q').focus(); }, 80); };

function doSearch() {
  var kw = $('#q').value.trim();
  var box = $('#hits');
  if (kw.length < 1) { box.innerHTML = '<div class="empty">输入关键词开始搜索</div>'; return; }
  box.innerHTML = '<div class="empty">搜索中…</div>';
  Promise.all([needCourse(), needNotes(), needQuiz()]).then(function (r) {
    var hits = [];
    function scan(text, label, scr, id) {
      var i = text.indexOf(kw);
      if (i < 0) return;
      var s = Math.max(0, i - 30);
      hits.push({
        label: label, scr: scr, id: id,
        snip: (s > 0 ? '…' : '') + text.slice(s, i) +
              '<em>' + esc(kw) + '</em>' + text.slice(i + kw.length, i + kw.length + 60) + '…'
      });
    }
    r[0].forEach(function (c) { scan(c.text, '第' + c.n + '章 · ' + c.title, 'chapter', c.n); });
    r[1].forEach(function (c) { scan(c.text, '笔记 · ' + c.title, 'note', c.n); });
    r[2].items.forEach(function (q) { scan(q.text, '题' + q.n + ' · ' + q.title, 'quiz', q.n); });

    if (!hits.length) { box.innerHTML = '<div class="empty">没找到「' + esc(kw) + '」</div>'; return; }
    box.innerHTML = '<div class="muted" style="margin-bottom:8px">' + hits.length + ' 条结果</div>' +
      hits.map(function (h, i) {
        return '<div class="hit" data-h="' + i + '"><b>' + esc(h.label) + '</b><p>' + h.snip + '</p></div>';
      }).join('');
    $$('[data-h]', box).forEach(function (el) {
      el.onclick = function () { var h = hits[+el.dataset.h]; show(h.scr, h.id); };
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
function applyTheme(t) {
  if (t) document.documentElement.setAttribute('data-theme', t);
  else document.documentElement.removeAttribute('data-theme');
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
