/* Minimal SW: cache shell assets, avoid broken registration */
const CACHE = 'kaskad-v2';
const ASSETS = [
  '/static/style_v6.css',
  '/static/icon-192.png',
  '/static/icon-512.png',
];

self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(ASSETS)).catch(() => {}));
  self.skipWaiting();
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', (e) => {
  if (e.request.method !== 'GET') return;
  const url = new URL(e.request.url);
  // manifest — всегда из сети (иначе залипает старый start_url)
  if (url.pathname === '/static/manifest.json') {
    e.respondWith(fetch(e.request));
    return;
  }
  // network-first for API/html, cache-first for static
  if (url.pathname.startsWith('/static/') || url.pathname.startsWith('/works-photos/')) {
    e.respondWith(
      caches.match(e.request).then((hit) => hit || fetch(e.request).then((res) => {
        const clone = res.clone();
        caches.open(CACHE).then((c) => c.put(e.request, clone)).catch(() => {});
        return res;
      }).catch(() => hit))
    );
    return;
  }
  e.respondWith(
    fetch(e.request).catch(() => caches.match(e.request))
  );
});
