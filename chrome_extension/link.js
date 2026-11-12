/**
 * link.js — Vincular la extensión con la cuenta de EmpleoIA sin copiar tokens.
 *
 * El popup genera un `state` al azar, lo guarda en chrome.storage.session y abre
 * /account/extension/link?state=… . Al confirmar, la app responde una página con
 * <div id="empleoia-extension-link" data-state data-token>; el service worker la lee,
 * comprueba el state y guarda el token solo en este dispositivo (chrome.storage.local).
 */
const EmpleoIALink = (() => {
  const LINK_PATH = '/account/extension/link';
  const TOKEN_RE = /^[A-Za-z0-9_-]{20,128}$/;

  function newState(cryptoObj = globalThis.crypto) {
    const bytes = cryptoObj.getRandomValues(new Uint8Array(24));
    return btoa(String.fromCharCode(...bytes)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
  }

  function linkUrl(serverUrl, state) {
    return `${serverUrl.replace(/\/+$/, '')}${LINK_PATH}?state=${encodeURIComponent(state)}`;
  }

  function isLinkPage(url, serverUrl) {
    try {
      const page = new URL(url);
      return page.origin === new URL(serverUrl).origin && page.pathname === LINK_PATH;
    } catch (e) {
      return false;
    }
  }

  function acceptLink(found, pendingState) {
    if (!found || !pendingState || found.state !== pendingState) {
      return null;
    }
    return TOKEN_RE.test(found.token || '') ? found.token : null;
  }

  // Versiones anteriores guardaban el token en storage.sync (se copiaba a todos los Chrome de la cuenta de Google)
  async function migrateToken(storage) {
    const { extensionToken } = await storage.sync.get('extensionToken');
    if (!extensionToken) {
      return;
    }
    const local = await storage.local.get('extensionToken');
    if (!local.extensionToken) {
      await storage.local.set({ extensionToken });
    }
    await storage.sync.remove('extensionToken');
  }

  async function getToken(storage) {
    return (await storage.local.get('extensionToken')).extensionToken || '';
  }

  return { LINK_PATH, newState, linkUrl, isLinkPage, acceptLink, migrateToken, getToken };
})();

if (typeof module !== 'undefined') {
  module.exports = EmpleoIALink;
}
