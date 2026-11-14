/**
 * Eventos declarados en el HTML sin handlers inline, que la CSP bloquea.
 * - data-onclick / data-onchange / data-oninput / data-onkeydown="fn" llaman a la función global fn.
 *   data-args es un array JSON; "$el" se reemplaza por el elemento y "$event" por el evento.
 *   Con dos handlers en el mismo elemento, cada uno usa data-on<evento>-args.
 *   Si fn devuelve false, se cancela la acción por defecto.
 * - data-confirm en un form, botón o enlace pide confirmación antes de seguir.
 */
(function () {
  function resolve(value, el, event) {
    if (value === '$el') return el;
    if (value === '$event') return event;
    return value;
  }

  function dispatch(event, attr) {
    const el = event.target.closest && event.target.closest('[' + attr + ']');
    if (!el) return;
    const fn = window[el.getAttribute(attr)];
    if (typeof fn !== 'function') return;
    let args;
    try {
      args = JSON.parse(el.getAttribute(attr + '-args') || el.dataset.args || '[]');
    } catch (err) {
      console.warn('data-args inválido en', el);
      return;
    }
    args = (Array.isArray(args) ? args : [args]).map((v) => resolve(v, el, event));
    if (fn.apply(el, args) === false) event.preventDefault();
  }

  ['click', 'change', 'input', 'keydown'].forEach((type) => {
    document.addEventListener(type, (event) => dispatch(event, 'data-on' + type));
  });

  document.addEventListener('submit', (event) => {
    const form = event.target;
    if (form.dataset && form.dataset.confirm && !window.confirm(form.dataset.confirm)) {
      event.preventDefault();
      event.stopImmediatePropagation();
    }
  }, true);

  document.addEventListener('click', (event) => {
    const el = event.target.closest && event.target.closest('a[data-confirm], button[data-confirm]');
    if (el && !window.confirm(el.dataset.confirm)) {
      event.preventDefault();
      event.stopImmediatePropagation();
    }
  }, true);

  window.goBack = function () {
    window.history.back();
    return false;
  };
})();
