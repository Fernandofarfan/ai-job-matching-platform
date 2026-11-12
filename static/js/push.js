// Notificaciones push: suscribe este navegador a los avisos de la cuenta (Mi cuenta → Integraciones).
(function () {
  const box = document.getElementById('push-box');
  if (!box) return;
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

  async function init() {
    if (!('serviceWorker' in navigator) || !('PushManager' in window) || !('Notification' in window)) {
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
    let subscription = await registration.pushManager.getSubscription();

    function render() {
      if (Notification.permission === 'denied') {
        show('Bloqueaste las notificaciones de este sitio: habilitalas en la configuración del navegador.');
      } else if (subscription) {
        show('Este dispositivo recibe los avisos de alertas y recordatorios.', { active: true });
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
        subscription = await registration.pushManager.subscribe({
          userVisibleOnly: true,
          applicationServerKey: keyBytes(config.public_key),
        });
        await post('/api/push/subscribe', subscription.toJSON());
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
        status.textContent = 'Notificación de prueba enviada.';
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

  init().catch((err) => show(`No se pudieron revisar las notificaciones: ${err.message}`));
})();
