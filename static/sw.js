self.addEventListener("install", event => {
  event.waitUntil(
    caches.open("metarearn-cache").then(cache => {
      return cache.addAll([
        "/",
        "/static/css/style.css",
        "/static/images/metarearnlogo.png"
      ]);
    })
  );
});

self.addEventListener("fetch", event => {
  event.respondWith(
    caches.match(event.request).then(response => response || fetch(event.request))
  );
});
