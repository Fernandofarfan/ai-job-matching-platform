/**
 * EmpleoIA – Offline Cache Manager (IndexedDB)
 * Cachea los datos del tracker y searches para modo offline.
 */

const DB_NAME = 'EmpleoIA_Offline';
const DB_VERSION = 1;
const STORES = {
  tracker: 'tracker_jobs',
  results: 'search_results',
  profiles: 'user_profiles',
};

// ── Abrir / Inicializar la base de datos ────────────────────
function openDB() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION);

    req.onupgradeneeded = (event) => {
      const db = event.target.result;
      if (!db.objectStoreNames.contains(STORES.tracker)) {
        db.createObjectStore(STORES.tracker, { keyPath: 'id' });
      }
      if (!db.objectStoreNames.contains(STORES.results)) {
        db.createObjectStore(STORES.results, { autoIncrement: true });
      }
      if (!db.objectStoreNames.contains(STORES.profiles)) {
        db.createObjectStore(STORES.profiles, { keyPath: 'role_type' });
      }
    };

    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

// ── Guardar datos en IndexedDB ───────────────────────────────
// replace=true borra antes lo guardado, así no quedan registros que el servidor ya no devuelve.
async function saveToStore(storeName, data, replace = false) {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(storeName, 'readwrite');
    const store = tx.objectStore(storeName);
    if (replace) store.clear();
    if (Array.isArray(data)) {
      data.forEach((item) => store.put(item));
    } else {
      store.put(data);
    }
    tx.oncomplete = () => resolve(true);
    tx.onerror = () => reject(tx.error);
  });
}

// ── Leer todos los datos de un store ────────────────────────
async function getAllFromStore(storeName) {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(storeName, 'readonly');
    const req = tx.objectStore(storeName).getAll();
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

// ── Sincronizar tracker con la base de datos del servidor ────
async function syncTrackerData() {
  try {
    const response = await fetch('/api/tracker/jobs');
    if (!response.ok) throw new Error('Network error');
    const data = await response.json();
    if (data.success && data.jobs) {
      await saveToStore(STORES.tracker, data.jobs, true);
      console.log(`[OfflineCache] Cached ${data.jobs.length} tracker jobs`);
      return data.jobs;
    }
  } catch (err) {
    console.warn('[OfflineCache] Using offline data:', err.message);
    return getAllFromStore(STORES.tracker);
  }
}

// ── Cargar datos del tracker (online → offline fallback) ─────
async function loadTrackerData() {
  if (navigator.onLine) {
    return syncTrackerData();
  }
  const cached = await getAllFromStore(STORES.tracker);
  showOfflineBanner(cached.length);
  return cached;
}

// ── Mostrar banner offline ───────────────────────────────────
function showOfflineBanner(cachedCount = 0) {
  const existing = document.getElementById('offline-banner');
  if (existing) return;

  const banner = document.createElement('div');
  banner.id = 'offline-banner';
  banner.innerHTML = `
    <div class="offline-banner">
      <span>
        <i class="bi bi-wifi-off offline-banner-icon"></i>
        Modo Offline – Mostrando ${cachedCount} registros en caché
      </span>
      <button type="button" data-close-offline-banner class="offline-banner-close">
        Cerrar
      </button>
    </div>
  `;
  document.body.prepend(banner);
  // sin onclick inline: la CSP bloquea los handlers en el HTML
  banner.querySelector('[data-close-offline-banner]').addEventListener('click', () => banner.remove());
  // Ajustar el body para que no tape contenido
  document.body.style.paddingTop = '46px';
}

// ── Actualizar banner de estado de conexión ──────────────────
function updateOnlineStatus() {
  const isOnline = navigator.onLine;
  const indicator = document.getElementById('network-indicator');

  if (indicator) {
    indicator.innerHTML = isOnline
      ? '<span class="badge network-badge network-badge-online">● Online</span>'
      : '<span class="badge network-badge network-badge-offline">● Offline</span>';
  }

  if (!isOnline) {
    showOfflineBanner();
  } else {
    const banner = document.getElementById('offline-banner');
    if (banner) {
      banner.remove();
      document.body.style.paddingTop = '';
    }
    // Sincronizar datos cuando vuelve la conexión
    syncTrackerData().catch(console.warn);
  }
}

// ── Guardar búsqueda offline ─────────────────────────────────
async function saveSearchOffline(searchData) {
  await saveToStore(STORES.results, {
    ...searchData,
    saved_at: new Date().toISOString(),
  });
  console.log('[OfflineCache] Search saved for offline viewing');
}

// ── Registro del Service Worker ──────────────────────────────
async function registerServiceWorker() {
  if (!('serviceWorker' in navigator)) {
    console.warn('[SW] Service Workers not supported');
    return;
  }

  try {
    const reg = await navigator.serviceWorker.register('/sw.js', { scope: '/' });
    console.log('[SW] Registered:', reg.scope);

    reg.addEventListener('updatefound', () => {
      const newWorker = reg.installing;
      newWorker.addEventListener('statechange', () => {
        if (newWorker.state === 'installed' && navigator.serviceWorker.controller) {
          showUpdateToast();
        }
      });
    });
  } catch (err) {
    console.error('[SW] Registration failed:', err);
  }
}

// ── Toast de actualización disponible ───────────────────────
function showUpdateToast() {
  const toast = document.createElement('div');
  toast.innerHTML = `
    <div class="update-toast">
      <span class="update-toast-text">🔄 Nueva versión disponible</span>
      <button type="button" data-reload class="update-toast-button">Actualizar</button>
    </div>
  `;
  document.body.appendChild(toast);
  toast.querySelector('[data-reload]').addEventListener('click', () => location.reload());
  setTimeout(() => toast.remove(), 8000);
}

// ── Inicialización automática ────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  registerServiceWorker();
  updateOnlineStatus();

  window.addEventListener('online',  updateOnlineStatus);
  window.addEventListener('offline', updateOnlineStatus);
});

// Exportar funciones útiles al scope global para usarlas en otros scripts
window.OfflineCache = {
  syncTrackerData,
  loadTrackerData,
  saveSearchOffline,
  getAllFromStore,
  STORES,
};
