// Notificaciones push. Una suscripción es de la cuenta que la activó en este navegador: al salir o
// al entrar con otra cuenta se da de baja (no llegan avisos de una cuenta a quien use el navegador después),
// y la cuenta nueva tiene que activarla explícitamente en Mi cuenta.
(function () {
  const OWNER_KEY = 'empleoia-push-account';
  const account = (document.querySelector('meta[name="push-account"]') || {}).content || '';
  const supported = 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window;

  function keyBytes(base64url) {
    const padded = (base64url + '='.repeat((4 - (base64url.length % 4)) % 4)).replace(/-/g, '+').replace(/_/g, '/');
    return Uint8Array.from(atob(padded), (c) => c.charCodeAt(0));
  }

  async function post(url, body) {
    const response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body || {}),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || `Error ${response.status}`);
    return data;
  }

  async function currentSubscription() {
    if (!supported) return null;
    const registration = await navigator.serviceWorker.getRegistration('/');
    return registration ? registration.pushManager.getSubscription() : null;
  }

  // Suscripción de otra cuenta: se da de baja en el servicio de push (el servidor la borra al recibir 410).
  async function dropIfOtherAccount(subscription) {
    if (!subscription || !account || localStorage.getItem(OWNER_KEY) === account) return subscription;
    try {
      await subscription.unsubscribe();
    } catch {
      return subscription;
    }
    localStorage.removeItem(OWNER_KEY);
    return null;
  }

  async function dropOnLogout() {
    const subscription = await currentSubscription();
    if (!subscription) return;
    await post('/api/push/unsubscribe', { endpoint: subscription.endpoint }).catch(() => {});
    await subscription.unsubscribe().catch(() => {});
    localStorage.removeItem(OWNER_KEY);
  }

  document.querySelectorAll('form[action$="/logout"]').forEach((form) => {
    form.addEventListener('submit', (event) => {
      if (!supported || form.dataset.pushDropped) return;
      event.preventDefault();
      form.dataset.pushDropped = '1';
      const timeout = new Promise((resolve) => setTimeout(resolve, 1500));
      Promise.race([dropOnLogout(), timeout]).finally(() => form.submit());
    });
  });

  async function settings(box) {
    const status = document.getElementById('push-status');
    const enableBtn = document.getElementById('push-enable');
    const testBtn = document.getElementById('push-test');
    const disableBtn = document.getElementById('push-disable');

    function show(text, { enable = false, active = false } = {}) {
      status.textContent = text;
      enableBtn.hidden = !enable;
      testBtn.hidden = !active;
      disableBtn.hidden = !active;
    }

    if (!supported) {
      show('Este navegador no admite notificaciones push. En iPhone, primero agregá la app a la pantalla de inicio.');
      return;
    }
    const config = await fetch('/api/push/config').then((r) => r.json()).catch(() => ({}));
    if (!config.enabled) {
      show('El administrador no configuró las notificaciones push (VAPID_PUBLIC_KEY y VAPID_PRIVATE_KEY).');
      return;
    }
    const registration = await navigator.serviceWorker.register('/sw.js', { scope: '/' });
    await navigator.serviceWorker.ready;
    let subscription = await dropIfOtherAccount(await registration.pushManager.getSubscription());

    function render() {
      if (Notification.permission === 'denied') {
        show('Bloqueaste las notificaciones de este sitio: habilitalas en la configuración del navegador.');
      } else if (subscription && Notification.permission === 'granted') {
        show('Este dispositivo recibe los avisos de alertas y recordatorios de tu cuenta.', { active: true });
      } else {
        show('Recibí en este dispositivo los avisos de alertas y recordatorios.', { enable: true });
      }
    }

    enableBtn.addEventListener('click', async () => {
      enableBtn.disabled = true;
      try {
        if ((await Notification.requestPermission()) !== 'granted') {
          render();
          return;
        }
        subscription = subscription || await registration.pushManager.subscribe({
          userVisibleOnly: true,
          applicationServerKey: keyBytes(config.public_key),
        });
        await post('/api/push/subscribe', subscription.toJSON());
        localStorage.setItem(OWNER_KEY, account);
        render();
      } catch (err) {
        show(`No se pudo activar: ${err.message}`, { enable: true });
      } finally {
        enableBtn.disabled = false;
      }
    });

    testBtn.addEventListener('click', async () => {
      testBtn.disabled = true;
      try {
        await post('/api/push/test', { endpoint: subscription.endpoint });
        status.textContent = 'Notificación de prueba enviada a este dispositivo.';
      } catch (err) {
        status.textContent = `No se pudo mandar: ${err.message}`;
      } finally {
        testBtn.disabled = false;
      }
    });

    disableBtn.addEventListener('click', async () => {
      disableBtn.disabled = true;
      try {
        if (subscription) {
          await post('/api/push/unsubscribe', { endpoint: subscription.endpoint });
          await subscription.unsubscribe();
          subscription = null;
          localStorage.removeItem(OWNER_KEY);
        }
        render();
      } catch (err) {
        status.textContent = `No se pudo desactivar: ${err.message}`;
      } finally {
        disableBtn.disabled = false;
      }
    });

    render();
  }

  const box = document.getElementById('push-box');
  if (box) {
    settings(box).catch((err) => {
      document.getElementById('push-status').textContent = `No se pudieron revisar las notificaciones: ${err.message}`;
    });
  } else if (account) {
    currentSubscription().then(dropIfOtherAccount).catch(() => {});
  }
})();
