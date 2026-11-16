/* Impana Gold owner app — service worker.
   Only the look of the app (CSS, JS, icons) is kept for speed. Bills, stock and
   customers are never stored on the phone: every page comes from the server. */

const CACHE = "owner-static-v1";

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE).then((c) => c.add("/b/offline")).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k.startsWith("owner-") && k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);

  if (url.origin === location.origin && url.pathname.startsWith("/static/")) {
    event.respondWith(
      caches.match(req).then((hit) => {
        if (hit) return hit;
        return fetch(req).then((res) => {
          if (res.ok) { const copy = res.clone(); caches.open(CACHE).then((c) => c.put(req, copy)); }
          return res;
        });
      })
    );
    return;
  }

  if (req.mode === "navigate" && url.origin === location.origin && url.pathname.startsWith("/b/")) {
    event.respondWith(fetch(req).catch(() => caches.match("/b/offline")));
  }
});
