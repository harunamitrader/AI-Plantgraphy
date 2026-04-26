const CACHE_NAME = 'ai-plantgraphy-v8';
const CORE_ASSETS = [
  '/',
  '/connect',
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
    caches.open(CACHE_NAME).then((cache) => cache.addAll(CORE_ASSETS)).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener('message', (event) => {
  const data = event.data || {};
  if (data.type !== 'AI_PLANTGRAPHY_SW_STATUS') {
    return;
  }
  event.source?.postMessage({
    type: 'AI_PLANTGRAPHY_SW_STATUS',
    version: CACHE_NAME,
    coreAssets: CORE_ASSETS,
  });
});

self.addEventListener('fetch', (event) => {
  if (event.request.method !== 'GET') {
    return;
  }

  event.respondWith(
    (async () => {
      const fallbackPath = fallbackPathFor(event.request);
      if (fallbackPath) {
        const cachedPage = await caches.match(fallbackPath);
        if (cachedPage) {
          event.waitUntil(refreshPageCache(fallbackPath));
          return cachedPage;
        }
      }

      try {
        const response = await fetch(event.request);
        if (response.ok || event.request.mode !== 'navigate') {
          return response;
        }
        return (await navigationFallback(event.request)) || response;
      } catch (err) {
        const cached = await caches.match(event.request);
        if (cached) {
          return cached;
        }
        return (await navigationFallback(event.request)) || Response.error();
      }
    })()
  );
});

async function navigationFallback(request) {
  const fallbackPath = fallbackPathFor(request);
  return fallbackPath ? caches.match(fallbackPath) : null;
}

function fallbackPathFor(request) {
  if (request.mode !== 'navigate') {
    return null;
  }
  const url = new URL(request.url);
  if (url.pathname === '/' || url.pathname === '') {
    return '/';
  }
  if (url.pathname === '/connect') {
    return '/upload';
  }
  if (url.pathname === '/upload') {
    return '/upload';
  }
  if (url.pathname === '/pending-local') {
    return '/pending-local';
  }
  if (url.pathname === '/settings') {
    return '/settings';
  }
  return null;
}

async function refreshPageCache(path) {
  try {
    const response = await fetch(path, { cache: 'no-store' });
    if (!response.ok) {
      return;
    }
    const cache = await caches.open(CACHE_NAME);
    await cache.put(path, response.clone());
  } catch (err) {
    // offline or upstream unavailable; keep current cache
  }
}
