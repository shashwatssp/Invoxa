/*
 * Invoxa service worker: minimal, deliberately boring.
 *
 * Installs the app shell (the built SPA files are hashed and network-fetched;
 * navigation requests fall back to the cached index.html when offline) and
 * passes everything else straight to the network. API calls are never cached
 * - invoice data must always be fresh.
 */
const CACHE = 'invoxa-shell-v1';
const SHELL = ['/', '/index.html', '/manifest.webmanifest', '/icon-192.png', '/icon-512.png'];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE).then((cache) => cache.addAll(SHELL)).then(() => self.skipWaiting()),
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((key) => key !== CACHE).map((key) => caches.delete(key))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  // Never cache API traffic.
  if (url.pathname.startsWith('/api/') || url.pathname.startsWith('/health')) return;

  // Offline fallback for page navigations.
  if (event.request.mode === 'navigate') {
    event.respondWith(
      fetch(event.request).catch(() => caches.match('/index.html')),
    );
  }
});
