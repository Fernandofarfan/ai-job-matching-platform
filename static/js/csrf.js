// CSRF: agrega el token a fetch same-origin y a todos los formularios POST
(function () {
    const token = document.querySelector('meta[name="csrf-token"]').content;
    const originalFetch = window.fetch;
    window.fetch = function (input, init) {
        init = init || {};
        const method = (init.method || 'GET').toUpperCase();
        const url = new URL(typeof input === 'string' ? input : input.url, window.location.href);
        if (!['GET', 'HEAD', 'OPTIONS'].includes(method) && url.origin === window.location.origin) {
            const headers = new Headers(init.headers || {});
            headers.set('X-CSRFToken', token);
            init.headers = headers;
        }
        return originalFetch.call(this, input, init);
    };
    document.addEventListener('submit', function (event) {
        const form = event.target;
        if (form.method.toLowerCase() === 'post' && !form.querySelector('input[name="csrf_token"]')) {
            const input = document.createElement('input');
            input.type = 'hidden';
            input.name = 'csrf_token';
            input.value = token;
            form.appendChild(input);
        }
    }, true);
})();
