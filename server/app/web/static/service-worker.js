const CACHE_NAME = 'ai-plantgraphy-v6';
const CORE_ASSETS = [
  '/',
  '/plants',
  '/upload',
  '/pending-local',
  '/settings',
  '/static/style.css?v=20260426-offline-drafts',
  '/static/app.js',
  '/static/offline-drafts.js',
  '/static/manifest.webmanifest',
  '/static/brand/ai-plantgraphy-icon.png',
  '/static/brand/ai-plantgraphy-header.jpg',
  '/static/icons/icon-192.png',
  '/static/icons/icon-512.png'
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(CORE_ASSETS))
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key)))
    )
  );
});

self.addEventListener('fetch', (event) => {
  if (event.request.method !== 'GET') {
    return;
  }

  event.respondWith(
    fetch(event.request).catch(async () => {
      const cached = await caches.match(event.request);
      if (cached) {
        return cached;
      }
      if (event.request.mode === 'navigate') {
        const url = new URL(event.request.url);
        if (url.pathname === '/upload') {
          return caches.match('/upload');
        }
        if (url.pathname === '/pending-local') {
          return caches.match('/pending-local');
        }
        if (url.pathname === '/settings') {
          return caches.match('/settings');
        }
      }
      throw new Error('offline');
    })
  );
});
