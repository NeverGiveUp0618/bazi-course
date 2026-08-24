/* 网络优先——微信 X5 内核缓存极顽固，会无视 URL 的 ?query 按路径缓存。
   其余几个 App 都因此改成网络优先，这里保持一致。 */
var C = 'bazi-course-v40-lianti';
var CORE = ['./', 'index.html', 'style.css', 'app.js',
  'data/data-meta.js', 'data/data-course.js', 'data/data-notes.js',
  'data/data-quiz.js', 'data/data-index.js'];

self.addEventListener('install', function (e) {
  self.skipWaiting();
  e.waitUntil(caches.open(C).then(function (c) { return c.addAll(CORE).catch(function () {}); }));
});
self.addEventListener('activate', function (e) {
  e.waitUntil(caches.keys().then(function (ks) {
    return Promise.all(ks.map(function (k) { return k === C ? null : caches.delete(k); }));
  }).then(function () { return self.clients.claim(); }));
});
self.addEventListener('fetch', function (e) {
  if (e.request.method !== 'GET') return;
  e.respondWith(
    fetch(e.request).then(function (r) {
      var cp = r.clone();
      caches.open(C).then(function (c) { c.put(e.request, cp); });
      return r;
    }).catch(function () {
      // ⚠️ data/*.js 现在带 ?v=<构建时间>，而 CORE 里预缓存的是不带参数的路径。
      //    离线回退必须 ignoreSearch，否则断网时这四个大文件全部 miss。
      return caches.match(e.request, { ignoreSearch: true });
    })
  );
});
