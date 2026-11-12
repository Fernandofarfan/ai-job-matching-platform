/**
 * background.js — Service worker de EmpleoIA Saver: configuración inicial, menú contextual y vinculación con la cuenta.
 */
importScripts('link.js');

const DEFAULT_SERVER = 'http://localhost:5000';

chrome.runtime.onInstalled.addListener(({ reason }) => {
  if (reason === 'install') {
    chrome.storage.sync.set({ serverUrl: DEFAULT_SERVER, autoExtract: true });
  }
  EmpleoIALink.migrateToken(chrome.storage).catch(e => console.error('EmpleoIA Saver:', e.message));
  chrome.contextMenus.create({
    id: 'save-to-empleoia',
    title: 'Guardar en EmpleoIA',
    contexts: ['page', 'link'],
  });
});

chrome.runtime.onStartup.addListener(() => {
  EmpleoIALink.migrateToken(chrome.storage).catch(e => console.error('EmpleoIA Saver:', e.message));
});

async function saveFromTab(tab) {
  await chrome.scripting.executeScript({ target: { tabId: tab.id }, files: ['content.js'] });
  const response = await chrome.tabs.sendMessage(tab.id, { action: 'extractJobData' });
  if (!response?.success || !response?.data) {
    throw new Error(response?.error || 'No se pudieron extraer los datos');
  }
  const { serverUrl } = await chrome.storage.sync.get('serverUrl');
  const extensionToken = await EmpleoIALink.getToken(chrome.storage);
  const saveResponse = await fetch(`${serverUrl || DEFAULT_SERVER}/api/tracker/save-from-extension`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-Extension-Token': extensionToken },
    body: JSON.stringify({ ...response.data, status: 'bookmarked', job_link: response.data.apply_url || response.data.page_url }),
  });
  if (!saveResponse.ok) {
    throw new Error(`No se pudo guardar (HTTP ${saveResponse.status}); revisá el servidor y que la extensión esté vinculada`);
  }
  chrome.tabs.sendMessage(tab.id, { action: 'showSavedIndicator', jobTitle: response.data.title || 'Trabajo' });
}

chrome.contextMenus.onClicked.addListener((info, tab) => {
  if (info.menuItemId === 'save-to-empleoia' && tab?.id) {
    saveFromTab(tab).catch(e => console.error('EmpleoIA Saver:', e.message));
  }
});

// La página de confirmación de la app trae el token; solo se acepta si el state es el que generó el popup
async function finishLink(tabId, url) {
  const { serverUrl } = await chrome.storage.sync.get('serverUrl');
  if (!EmpleoIALink.isLinkPage(url, serverUrl || DEFAULT_SERVER)) {
    return;
  }
  const { linkState } = await chrome.storage.session.get('linkState');
  if (!linkState) {
    return;
  }
  const [injection] = await chrome.scripting.executeScript({
    target: { tabId },
    func: () => {
      const box = document.getElementById('empleoia-extension-link');
      return box ? { state: box.dataset.state, token: box.dataset.token } : null;
    },
  });
  const token = EmpleoIALink.acceptLink(injection?.result, linkState);
  if (!token) {
    return;
  }
  await chrome.storage.local.set({ extensionToken: token });
  await chrome.storage.session.remove('linkState');
}

chrome.tabs.onUpdated.addListener((tabId, info, tab) => {
  if (info.status === 'complete' && tab.url) {
    finishLink(tabId, tab.url).catch(e => console.error('EmpleoIA Saver:', e.message));
  }
});
