/* ============================================================
   EmpleoIA – main.js
   Utilidades globales compartidas por todas las páginas
   ============================================================ */

/**
 * Resalta el enlace de navegación activo según la URL actual.
 */
function highlightActiveNav() {
  const path = window.location.pathname;
  document.querySelectorAll('.navbar-nav .nav-link').forEach((link) => {
    const href = link.getAttribute('href');
    if (!href || href === '#') return;
    if (path === href || (href !== '/' && path.startsWith(href))) {
      link.classList.add('active');
      link.setAttribute('aria-current', 'page');
    }
  });
}

/**
 * Escapa HTML para inserción segura vía innerHTML (anti-XSS).
 */
function escHtml(value) {
  if (value === null || value === undefined) return '';
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

/**
 * Resuelve una URL solo si es http(s) válida (bloquea javascript:, data:).
 */
function safeUrl(value) {
  if (!value) return '';
  try {
    const u = new URL(String(value));
    return (u.protocol === 'http:' || u.protocol === 'https:') ? u.href : '';
  } catch {
    return '';
  }
}

document.addEventListener('DOMContentLoaded', highlightActiveNav);
