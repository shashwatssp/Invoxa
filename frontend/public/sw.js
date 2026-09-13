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

// Files shared into the app from the OS share sheet (WhatsApp, Photos,
// Files...) land here; the Upload page picks them up and clears the entry.
const SHARE_CACHE = 'invoxa-shared-file-v1';
const SHARE_KEY = 'shared-file';

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE).then((cache) => cache.addAll(SHELL)).then(() => self.skipWaiting()),
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        // Keep the shell AND a pending shared file; sweep everything else.
        Promise.all(
          keys
            .filter((key) => key !== CACHE && key !== SHARE_CACHE)
            .map((key) => caches.delete(key)),
        ),
      )
      .then(() => self.clients.claim()),
  );
});

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  // Share-target ingestion: stash the shared file, then hand the user
  // to the Upload page which reads it from the cache and queues it.
  if (event.request.method === 'POST' && url.pathname === '/share-target') {
    event.respondWith(
      (async () => {
        try {
          const form = await event.request.formData();
          const file = form.get('file');
          if (file && typeof file !== 'string') {
            const cache = await caches.open(SHARE_CACHE);
            await cache.put(
              SHARE_KEY,
              new Response(file, {
                headers: {
                  'content-type': file.type || 'application/octet-stream',
                  'x-invoxa-filename': file.name || 'shared-invoice.pdf',
                },
              }),
            );
          }
        } catch (err) {
          // Ingestion is best-effort; never block the redirect.
        }
        return Response.redirect('/app/upload?shared=1', 303);
      })(),
    );
    return;
  }

  // Never cache API traffic.
  if (url.pathname.startsWith('/api/') || url.pathname.startsWith('/health')) return;

  // Offline fallback for page navigations.
  if (event.request.mode === 'navigate') {
    event.respondWith(
      fetch(event.request).catch(() => caches.match('/index.html')),
    );
  }
});
