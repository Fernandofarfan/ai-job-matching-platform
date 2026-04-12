/**
 * EmpleoIA – Service Worker v1.0
 * Estrategia: Cache-First para assets estáticos, Network-First para APIs
 */

const CACHE_NAME = 'empleoia-v1';
const OFFLINE_URL = '/offline';

// Assets que siempre queremos en caché
const STATIC_ASSETS = [
  '/',
  '/tracker',
  '/analytics',
  '/results',
  '/static/css/main.css',
  '/static/css/analytics_premium.css',
  '/static/css/tracker_premium.css',
  '/static/css/navbar_premium.css',
  '/static/js/main.js',
  '/static/js/offline-cache.js',
];

// ── Install: Pre-cache assets estáticos ──────────────────────
self.addEventListener('install', (event) => {
  console.log('[SW] Install');
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      // Ignoramos errores individuales para no bloquear la instalación
      return Promise.allSettled(
        STATIC_ASSETS.map((url) =>
          cache.add(url).catch((err) => console.warn(`[SW] Could not cache ${url}:`, err))
        )
      );
    }).then(() => self.skipWaiting())
  );
});

// ── Activate: Eliminar caches viejos ─────────────────────────
self.addEventListener('activate', (event) => {
  console.log('[SW] Activate');
  event.waitUntil(
    caches.keys().then((cacheNames) =>
      Promise.all(
        cacheNames
          .filter((name) => name !== CACHE_NAME)
          .map((name) => {
            console.log(`[SW] Deleting old cache: ${name}`);
            return caches.delete(name);
          })
      )
    ).then(() => self.clients.claim())
  );
});

// ── Fetch: Estrategia híbrida ─────────────────────────────────
self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // Solo manejar requests del mismo origen
  if (url.origin !== location.origin) return;

  // Para APIs → Network-First con fallback a cache
  if (url.pathname.startsWith('/api/')) {
    event.respondWith(networkFirstStrategy(request));
    return;
  }

  // Para exportaciones → siempre Network (no cachear archivos binarios)
  if (url.pathname.startsWith('/export/')) {
    return;
  }

  // Para assets estáticos → Cache-First
  if (url.pathname.startsWith('/static/')) {
    event.respondWith(cacheFirstStrategy(request));
    return;
  }

  // Para páginas HTML → Network-First con fallback offline
  event.respondWith(networkFirstWithOfflineFallback(request));
});

// ── Estrategias ───────────────────────────────────────────────

async function cacheFirstStrategy(request) {
  const cached = await caches.match(request);
  if (cached) return cached;

  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(CACHE_NAME);
      cache.put(request, response.clone());
    }
    return response;
  } catch {
    return new Response('Asset no disponible offline', { status: 503 });
  }
}

async function networkFirstStrategy(request) {
  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(CACHE_NAME);
      cache.put(request, response.clone());
    }
    return response;
  } catch {
    const cached = await caches.match(request);
    if (cached) return cached;
    return new Response(
      JSON.stringify({ success: false, error: 'Sin conexión. Mostrando datos en caché.', offline: true }),
      { status: 503, headers: { 'Content-Type': 'application/json' } }
    );
  }
}

async function networkFirstWithOfflineFallback(request) {
  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(CACHE_NAME);
      cache.put(request, response.clone());
    }
    return response;
  } catch {
    const cached = await caches.match(request);
    if (cached) return cached;
    // Retornar la página raíz cacheada como fallback
    const fallback = await caches.match('/');
    return fallback || new Response('Offline – Sin conexión', { status: 503 });
  }
}

// ── Background Sync: guardar datos pendientes ────────────────
self.addEventListener('sync', (event) => {
  if (event.tag === 'sync-tracker-updates') {
    event.waitUntil(syncTrackerUpdates());
  }
});

async function syncTrackerUpdates() {
  console.log('[SW] Syncing pending tracker updates...');
  // Implementación básica – los clientes manejan la cola via IndexedDB
}

// ── Push Notifications (base) ────────────────────────────────
self.addEventListener('push', (event) => {
  if (!event.data) return;
  const data = event.data.json();
  event.waitUntil(
    self.registration.showNotification(data.title || 'EmpleoIA', {
      body: data.body || 'Tienes novedades en tu búsqueda laboral.',
      icon: '/static/icons/icon-192.png',
      badge: '/static/icons/badge-72.png',
      tag: 'empleoia-notification',
    })
  );
});
