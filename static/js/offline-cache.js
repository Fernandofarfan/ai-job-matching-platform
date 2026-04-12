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
async function saveToStore(storeName, data) {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(storeName, 'readwrite');
    const store = tx.objectStore(storeName);
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
      await saveToStore(STORES.tracker, data.jobs);
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
    <div style="
      position: fixed; top: 0; left: 0; right: 0; z-index: 9999;
      background: linear-gradient(90deg, #f59e0b, #d97706);
      color: white; padding: 10px 20px;
      display: flex; align-items: center; justify-content: space-between;
      font-family: Inter, sans-serif; font-size: 0.875rem; font-weight: 600;
      box-shadow: 0 2px 8px rgba(0,0,0,0.2);
    ">
      <span>
        <i class="bi bi-wifi-off" style="margin-right:8px;"></i>
        Modo Offline – Mostrando ${cachedCount} registros en caché
      </span>
      <button onclick="document.getElementById('offline-banner').remove()"
              style="background:rgba(255,255,255,0.2); border:none; color:white;
                     padding:4px 12px; border-radius:20px; cursor:pointer; font-weight:600;">
        Cerrar
      </button>
    </div>
  `;
  document.body.prepend(banner);
  // Ajustar el body para que no tape contenido
  document.body.style.paddingTop = '46px';
}

// ── Actualizar banner de estado de conexión ──────────────────
function updateOnlineStatus() {
  const isOnline = navigator.onLine;
  const indicator = document.getElementById('network-indicator');

  if (indicator) {
    indicator.innerHTML = isOnline
      ? '<span class="badge" style="background:#22c55e; font-size:0.7rem;">● Online</span>'
      : '<span class="badge" style="background:#ef4444; font-size:0.7rem;">● Offline</span>';
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
    const reg = await navigator.serviceWorker.register('/static/sw.js', { scope: '/' });
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
    <div style="
      position: fixed; bottom: 20px; left: 50%; transform: translateX(-50%);
      background: #1a1a2e; color: white; padding: 14px 24px;
      border-radius: 12px; box-shadow: 0 8px 30px rgba(0,0,0,0.3);
      display: flex; align-items: center; gap: 14px;
      font-family: Inter, sans-serif; z-index: 10000;
    ">
      <span style="font-size:0.9rem;">🔄 Nueva versión disponible</span>
      <button onclick="location.reload()" style="
        background: #667eea; border: none; color: white;
        padding: 6px 14px; border-radius: 8px; cursor: pointer;
        font-weight: 600; font-size: 0.82rem;
      ">Actualizar</button>
    </div>
  `;
  document.body.appendChild(toast);
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
