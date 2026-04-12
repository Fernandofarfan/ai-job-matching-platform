/**
 * popup.js — Lógica del popup de la extensión EmpleoIA Saver
 */

let extractedJobData = null;
let selectedStatus = 'applying';

// ── Init ───────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', async () => {
  await loadSettings();
  await checkCurrentPage();
  setupStatusSelector();
  setupSettingsToggle();
});

async function loadSettings() {
  const data = await chrome.storage.sync.get(['serverUrl']);
  const input = document.getElementById('server-url');
  if (data.serverUrl) {
    input.value = data.serverUrl;
  }
  input.addEventListener('change', async () => {
    await chrome.storage.sync.set({ serverUrl: input.value });
  });
}

function getServerUrl() {
  return document.getElementById('server-url').value || 'http://localhost:5000';
}

// ── Page Check ────────────────────────────────────────────────────────────
async function checkCurrentPage() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  const url = tab.url || '';

  const supportedDomains = [
    'linkedin.com/jobs', 'indeed.com/viewjob', 'ar.indeed.com',
    'bumeran.com.ar', 'computrabajo.com'
  ];

  const isSupported = supportedDomains.some(d => url.includes(d));

  if (!isSupported) {
    document.getElementById('not-supported').style.display = 'block';
    document.getElementById('main-interface').style.display = 'none';
  } else {
    // Auto-extract on open
    autoExtract(tab);
  }
}

async function autoExtract(tab) {
  try {
    const response = await chrome.tabs.sendMessage(tab.id, { action: 'extractJobData' });
    if (response && response.success && response.data) {
      handleExtractedData(response.data);
    }
  } catch (e) {
    // Content script might not be injected yet
    console.log('Auto-extract failed, manual extraction needed:', e.message);
  }
}

// ── Extract ───────────────────────────────────────────────────────────────
async function extractJob() {
  const btn = document.getElementById('extract-btn');
  btn.innerHTML = '<span class="spinner"></span> Extrayendo...';
  btn.disabled = true;

  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    const response = await chrome.tabs.sendMessage(tab.id, { action: 'extractJobData' });

    if (response && response.success) {
      handleExtractedData(response.data);
      showMessage('✅ Datos extraídos correctamente', 'success');
    } else {
      showMessage('❌ No se pudieron extraer los datos: ' + (response?.error || 'error desconocido'), 'error');
    }
  } catch (error) {
    showMessage('❌ Error: ' + error.message + '. Recargá la página e intentá de nuevo.', 'error');
  } finally {
    btn.innerHTML = '🔍 Extraer datos de esta página';
    btn.disabled = false;
  }
}

function handleExtractedData(data) {
  extractedJobData = data;

  const preview = document.getElementById('job-preview');
  preview.style.display = 'block';

  document.getElementById('platform-name').textContent = capitalize(data.platform || 'web');
  document.getElementById('preview-title').textContent = data.title || 'Sin título detectado';
  document.getElementById('preview-meta').textContent = [data.company, data.location].filter(Boolean).join(' · ');
  document.getElementById('save-btn').disabled = false;
}

// ── Save ──────────────────────────────────────────────────────────────────
async function saveJob() {
  if (!extractedJobData) {
    showMessage('⚠️ Primero extraé los datos de la página', 'error');
    return;
  }

  const saveBtn = document.getElementById('save-btn');
  saveBtn.innerHTML = '<span class="spinner"></span> Guardando...';
  saveBtn.disabled = true;

  const serverUrl = getServerUrl();
  const payload = {
    ...extractedJobData,
    status: selectedStatus,
    job_link: extractedJobData.apply_url || extractedJobData.page_url,
  };

  try {
    const response = await fetch(`${serverUrl}/api/tracker/save-from-extension`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Extension-Source': 'empleoia-chrome-extension'
      },
      body: JSON.stringify(payload)
    });

    const result = await response.json();

    if (response.ok && result.success) {
      showMessage(`✅ ¡Guardado! "${(extractedJobData.title || '').slice(0, 40)}"`, 'success');
      saveBtn.textContent = '✅ Guardado';
      saveBtn.style.background = 'linear-gradient(135deg, #22c55e, #16a34a)';

      // Notify content script to show toast on page
      const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
      chrome.tabs.sendMessage(tab.id, {
        action: 'showSavedIndicator',
        jobTitle: extractedJobData.title || ''
      });

    } else if (result.exists) {
      showMessage('ℹ️ Este trabajo ya está en tu tracker', 'success');
    } else {
      showMessage('❌ Error al guardar: ' + (result.message || 'Error desconocido'), 'error');
      saveBtn.disabled = false;
      saveBtn.textContent = '💾 Guardar en Job Tracker';
    }

  } catch (error) {
    const isConnectionError = error.message.includes('fetch') || error.message.includes('Failed');
    if (isConnectionError) {
      showMessage(`❌ No se pudo conectar a ${serverUrl}. ¿EmpleoIA está corriendo?`, 'error');
    } else {
      showMessage('❌ Error: ' + error.message, 'error');
    }
    saveBtn.disabled = false;
    saveBtn.textContent = '💾 Guardar en Job Tracker';
  }
}

// ── Status Selector ───────────────────────────────────────────────────────
function setupStatusSelector() {
  document.querySelectorAll('.status-option').forEach(option => {
    option.addEventListener('click', () => {
      document.querySelectorAll('.status-option').forEach(o => o.classList.remove('active'));
      option.classList.add('active');
      selectedStatus = option.dataset.status;
    });
  });
}

// ── Settings Toggle ───────────────────────────────────────────────────────
function setupSettingsToggle() {
  const btn = document.getElementById('settings-toggle');
  const panel = document.getElementById('settings-panel');
  btn.addEventListener('click', () => {
    panel.style.display = panel.style.display === 'none' ? 'block' : 'none';
  });
}

// ── Utilities ─────────────────────────────────────────────────────────────
function showMessage(text, type) {
  const area = document.getElementById('message-area');
  area.textContent = text;
  area.className = `message ${type}`;
  area.style.display = 'block';
  if (type === 'success') {
    setTimeout(() => { area.style.display = 'none'; }, 4000);
  }
}

function capitalize(str) {
  return str ? str.charAt(0).toUpperCase() + str.slice(1) : '';
}
