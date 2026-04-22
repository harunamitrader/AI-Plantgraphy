const CACHE_NAME = 'ai-plantgraphy-v3';
const CORE_ASSETS = [
  '/',
  '/plants',
  '/upload',
  '/settings',
  '/static/style.css?v=20260422-compact2',
  '/static/app.js',
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
    fetch(event.request).catch(() => caches.match(event.request))
  );
});
