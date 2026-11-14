// Al llegar al login (p. ej. tras cerrar sesión) se borran las páginas privadas cacheadas por el service worker
if (window.caches) {
  caches.keys().then((names) => names.forEach((name) => caches.delete(name)));
}
