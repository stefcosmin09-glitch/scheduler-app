self.addEventListener('install', function (event) {
    self.skipWaiting();
});

self.addEventListener('activate', function (event) {
    event.waitUntil(self.clients.claim());
});

self.addEventListener('fetch', function (event) {
    var url = new URL(event.request.url);
    // Never cache or intercept the health check or the service worker itself.
    if (url.pathname === '/health' || url.pathname === '/sw.js') {
        event.respondWith(fetch(event.request));
        return;
    }
    event.respondWith(fetch(event.request).catch(function () {
        return caches.match(event.request);
    }));
});