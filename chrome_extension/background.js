/**
 * background.js — Service worker de EmpleoIA Saver: configuración inicial y menú contextual.
 */
const DEFAULT_SERVER = 'http://localhost:5000';

chrome.runtime.onInstalled.addListener(({ reason }) => {
  if (reason === 'install') {
    chrome.storage.sync.set({ serverUrl: DEFAULT_SERVER, autoExtract: true });
  }
  chrome.contextMenus.create({
    id: 'save-to-empleoia',
    title: 'Guardar en EmpleoIA',
    contexts: ['page', 'link'],
  });
});

async function saveFromTab(tab) {
  await chrome.scripting.executeScript({ target: { tabId: tab.id }, files: ['content.js'] });
  const response = await chrome.tabs.sendMessage(tab.id, { action: 'extractJobData' });
  if (!response?.success || !response?.data) {
    throw new Error(response?.error || 'No se pudieron extraer los datos');
  }
  const { serverUrl, extensionToken } = await chrome.storage.sync.get(['serverUrl', 'extensionToken']);
  const saveResponse = await fetch(`${serverUrl || DEFAULT_SERVER}/api/tracker/save-from-extension`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-Extension-Token': extensionToken || '' },
    body: JSON.stringify({ ...response.data, status: 'bookmarked', job_link: response.data.apply_url || response.data.page_url }),
  });
  if (!saveResponse.ok) {
    throw new Error(`No se pudo guardar (HTTP ${saveResponse.status}); revisá el servidor y el token de la extensión`);
  }
  chrome.tabs.sendMessage(tab.id, { action: 'showSavedIndicator', jobTitle: response.data.title || 'Trabajo' });
}

chrome.contextMenus.onClicked.addListener((info, tab) => {
  if (info.menuItemId === 'save-to-empleoia' && tab?.id) {
    saveFromTab(tab).catch(e => console.error('EmpleoIA Saver:', e.message));
  }
});
