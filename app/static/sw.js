var CACHE_VERSION = 'ts-v3';

self.addEventListener('install', function (event) {
    self.skipWaiting();
});

self.addEventListener('activate', function (event) {
    event.waitUntil(
        caches.keys().then(function (keys) {
            return Promise.all(keys.filter(function (k) {
                return k !== CACHE_VERSION;
            }).map(function (k) { return caches.delete(k); }));
        }).then(function () { return self.clients.claim(); })
    );
});

self.addEventListener('fetch', function (event) {
    var url = new URL(event.request.url);
    // Never intercept the health check, the service worker or API calls.
    if (url.pathname === '/health' || url.pathname === '/sw.js') {
        event.respondWith(fetch(event.request));
        return;
    }
    // HTML navigations are always network-first.
    if (event.request.mode === 'navigate') {
        event.respondWith(
            fetch(event.request).catch(function () {
                return caches.match(event.request);
            })
        );
        return;
    }
    event.respondWith(fetch(event.request).catch(function () {
        return caches.match(event.request);
    }));
});