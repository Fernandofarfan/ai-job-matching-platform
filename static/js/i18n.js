// Textos traducidos que la plantilla deja en <script type="application/json" data-i18n>, indexados por el texto en español.
(function () {
  const messages = {};
  document.querySelectorAll('script[type="application/json"][data-i18n]').forEach((node) => {
    Object.assign(messages, JSON.parse(node.textContent));
  });
  const entities = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
  window.t = (key) => (Object.prototype.hasOwnProperty.call(messages, key) ? messages[key] : key);
  window.tHtml = (key) => String(window.t(key)).replace(/[&<>"']/g, (c) => entities[c]);
})();
