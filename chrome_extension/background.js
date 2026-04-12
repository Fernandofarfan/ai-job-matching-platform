/**
 * background.js — Service Worker de EmpleoIA Saver
 * Maneja la inicialización y mensajes globales de la extensión.
 */

// ── Install ───────────────────────────────────────────────────────────────
chrome.runtime.onInstalled.addListener(({ reason }) => {
  if (reason === 'install') {
    // Configuración inicial por defecto
    chrome.storage.sync.set({
      serverUrl: 'http://localhost:5000',
      autoExtract: true,
    });

    // Abrir la plataforma al instalar (opcional)
    // chrome.tabs.create({ url: 'http://localhost:5000' });
    console.log('EmpleoIA Saver instalado correctamente ✓');
  }
});

// ── Action click (cuando no hay popup) ────────────────────────────────────
// El popup.html se encarga de todo, esto es solo por si acaso
chrome.action.onClicked.addListener((tab) => {
  console.log('EmpleoIA Saver clicked on:', tab.url);
});

// ── Context Menu (click derecho > Guardar en EmpleoIA) ──────────────────
chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({
    id: 'save-to-empleoia',
    title: '🤖 Guardar en EmpleoIA',
    contexts: ['page', 'link'],
  });
});

chrome.contextMenus.onClicked.addListener(async (info, tab) => {
  if (info.menuItemId === 'save-to-empleoia') {
    // Inyectar manualmente y extraer
    try {
      await chrome.scripting.executeScript({
        target: { tabId: tab.id },
        files: ['content.js'],
      });

      const response = await chrome.tabs.sendMessage(tab.id, { action: 'extractJobData' });
      if (response?.success && response?.data) {
        const { serverUrl } = await chrome.storage.sync.get('serverUrl');
        const url = serverUrl || 'http://localhost:5000';

        await fetch(`${url}/api/tracker/save-from-extension`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ ...response.data, status: 'bookmarked' }),
        });

        chrome.tabs.sendMessage(tab.id, {
          action: 'showSavedIndicator',
          jobTitle: response.data.title || 'Trabajo',
        });
      }
    } catch (e) {
      console.error('Context menu save error:', e);
    }
  }
});
