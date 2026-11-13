// Ancho de las barras de progreso que vienen del servidor: la CSP no permite style="width: ...".
document.querySelectorAll('[data-progress-width]').forEach((el) => {
  el.style.width = `${Number(el.dataset.progressWidth) || 0}%`;
});
