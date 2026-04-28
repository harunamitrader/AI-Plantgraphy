const CACHE_NAME = 'ai-plantgraphy-pages-v3';
const CORE_ASSET_PATHS = [
  '',
  'index.html',
  'plant.html',
  'plants.html',
  'observation.html',
  'observations.html',
  'upload.html',
  'pending-local.html',
  'review.html',
  'settings.html',
  'static/style.css?v=pages-v3',
  'static/app.js?v=pages-v3',
  'static/offline-drafts.js?v=pages-v3',
  'manifest.webmanifest?v=pages-v3',
  'static/brand/ai-plantgraphy-icon.png',
  'static/brand/ai-plantgraphy-header.jpg',
  'static/icons/icon-192.png',
  'static/icons/icon-512.png'
];

function rootPath() {
  return new URL(self.registration.scope).pathname;
}

function rooted(path) {
  const root = rootPath();
  if (!path) {
    return root;
  }
  return `${root}${String(path).replace(/^\/+/, '')}`;
}

function relativePagePath(pathname) {
  const root = rootPath();
  if (!pathname.startsWith(root)) {
    return '';
  }
  return pathname.slice(root.length);
}

const CORE_ASSETS = CORE_ASSET_PATHS.map(rooted);

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

self.addEventListener('fetch', (event) => {
  if (event.request.method !== 'GET') {
    return;
  }

  event.respondWith(
    (async () => {
      const fallbackUrl = fallbackUrlFor(event.request);
      if (fallbackUrl) {
        const cachedPage = await caches.match(fallbackUrl);
        if (cachedPage) {
          event.waitUntil(refreshPageCache(fallbackUrl));
          return cachedPage;
        }
      }

      try {
        const response = await fetch(event.request);
        if (response.ok || event.request.mode !== 'navigate') {
          return response;
        }
        return (await navigationFallback(event.request)) || response;
      } catch (error) {
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
  const fallbackUrl = fallbackUrlFor(request);
  return fallbackUrl ? caches.match(fallbackUrl) : null;
}

function fallbackUrlFor(request) {
  if (request.mode !== 'navigate') {
    return null;
  }
  const pathname = new URL(request.url).pathname;
  const page = relativePagePath(pathname);
  if (!page || page === 'index.html') {
    return rooted('index.html');
  }
  if (page === 'plants.html') {
    return rooted('plants.html');
  }
  if (page === 'plant.html') {
    return rooted('plant.html');
  }
  if (page === 'observations.html') {
    return rooted('observations.html');
  }
  if (page === 'observation.html') {
    return rooted('observation.html');
  }
  if (page === 'upload.html') {
    return rooted('upload.html');
  }
  if (page === 'pending-local.html') {
    return rooted('pending-local.html');
  }
  if (page === 'review.html') {
    return rooted('review.html');
  }
  if (page === 'settings.html') {
    return rooted('settings.html');
  }
  return rooted('upload.html');
}

async function refreshPageCache(url) {
  try {
    const response = await fetch(url, { cache: 'no-store' });
    if (!response.ok) {
      return;
    }
    const cache = await caches.open(CACHE_NAME);
    await cache.put(url, response.clone());
  } catch (error) {
    // keep current cache
  }
}
