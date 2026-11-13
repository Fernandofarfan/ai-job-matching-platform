/**
 * EmpleoIA – Service Worker v1.0
 * Estrategia: Network-First con fallback a caché (assets, APIs y páginas)
 */

const CACHE_NAME = 'empleoia-v3';
const OFFLINE_URL = '/offline';

// Assets que siempre queremos en caché
const STATIC_ASSETS = [
  '/',
  '/tracker',
  '/analytics',
  '/results',
  '/static/css/analytics_premium.css',
  '/static/css/tracker_premium.css',
  '/static/css/navbar_premium.css',
  // los scripts de base.html y de las páginas de arriba: sin ellos, esas páginas abren offline pero vacías
  '/static/js/csrf.js',
  '/static/js/actions.js',
  '/static/js/offline-cache.js',
  '/static/js/push.js',
  '/static/js/copilot.js',
  '/static/js/i18n.js',
  '/static/js/pages/job_tracker.js',
  '/static/js/pages/dashboard.js',
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

  // Para assets estáticos → Network-First: un deploy nuevo se ve sin esperar a que cambie CACHE_NAME
  if (url.pathname.startsWith('/static/')) {
    event.respondWith(networkFirstStrategy(request));
    return;
  }

  // Para páginas HTML → Network-First con fallback offline
  event.respondWith(networkFirstWithOfflineFallback(request));
});

// ── Estrategias ───────────────────────────────────────────────

// Las redirecciones (p. ej. al login cuando venció la sesión) no se guardan bajo la URL pedida.
function cacheable(response) {
  return response.ok && !response.redirected;
}

async function networkFirstStrategy(request) {
  try {
    const response = await fetch(request);
    if (cacheable(response)) {
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
    if (cacheable(response)) {
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

// ── Push Notifications ──────────────────────────────────────
self.addEventListener('push', (event) => {
  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch {
    data = { body: event.data ? event.data.text() : '' };
  }
  event.waitUntil(
    self.registration.showNotification(data.title || 'EmpleoIA', {
      body: data.body || 'Tenés novedades en tu búsqueda laboral.',
      icon: '/static/icons/icon-192.png',
      badge: '/static/icons/badge-72.png',
      data: { url: typeof data.url === 'string' && data.url.startsWith('/') ? data.url : '/' },
    })
  );
});

// Al tocar la notificación: enfoca una pestaña abierta de la app o abre la URL del aviso.
self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const target = new URL((event.notification.data && event.notification.data.url) || '/', self.location.origin).href;
  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((windows) => {
      const open = windows.find((w) => w.url === target);
      if (open) return open.focus();
      return self.clients.openWindow(target);
    })
  );
});
