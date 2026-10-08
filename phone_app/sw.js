// App shell is cached so the app opens with no signal. Queue and config are network-first with a cached fallback.
// Video clips are NOT handled here: the app stores them itself in IndexedDB and plays them from blobs (iOS Safari does not play range-requested video from the Cache API reliably).
const V = "gonogo-shell-v2";
const SHELL = ["./", "index.html", "manifest.webmanifest", "icon-192.png", "icon-512.png", "apple-touch-icon.png", "fonts.css",
  "fonts/jbmono-normal-400.woff2", "fonts/jbmono-normal-500.woff2", "fonts/jbmono-normal-700.woff2", "fonts/jbmono-italic-700.woff2", "fonts/jbmono-italic-800.woff2"];
self.addEventListener("install", e => { e.waitUntil(caches.open(V).then(c => c.addAll(SHELL))); self.skipWaiting(); });
self.addEventListener("activate", e => { e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== V).map(k => caches.delete(k)))).then(() => self.clients.claim())); });
self.addEventListener("fetch", e => {
  const u = new URL(e.request.url);
  if (e.request.method !== "GET" || u.origin !== location.origin || u.pathname.endsWith(".mp4") || u.pathname.startsWith("/api/")) return;
  if (/queue_[LR]\.json$|config\.json$/.test(u.pathname)) {
    e.respondWith(fetch(e.request).then(r => { const c = r.clone(); caches.open(V).then(x => x.put(e.request, c)); return r; }).catch(async () => {
      const c = await caches.match(e.request);       // network failed: answer from cache and say so, so the app can show "offline"
      if (!c) return Response.error();
      const h = new Headers(c.headers); h.set("X-From-Cache", "1");
      return new Response(await c.blob(), { status: c.status, headers: h });
    }));
    return;
  }
  e.respondWith(caches.match(e.request, { ignoreSearch: true }).then(r => r || fetch(e.request)));
});
