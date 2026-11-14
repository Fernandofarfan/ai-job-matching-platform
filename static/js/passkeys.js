// Passkeys (WebAuthn): registrar una en Mi cuenta (#passkeyForm) y entrar con una en el login (#passkeyLogin).
(function () {
  const supported = window.PublicKeyCredential && navigator.credentials;
  const csrf = () => (document.querySelector('input[name=csrf_token]') || {}).value || '';

  function toBytes(b64url) {
    const b64 = b64url.replace(/-/g, '+').replace(/_/g, '/') + '==='.slice((b64url.length + 3) % 4);
    return Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
  }
  function toB64(buffer) {
    let text = '';
    new Uint8Array(buffer).forEach((b) => { text += String.fromCharCode(b); });
    return btoa(text).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
  }
  async function post(url, body) {
    const resp = await fetch(url, {
      method: 'POST', credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf() },
      body: JSON.stringify(body || {}),
    });
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) throw new Error(data.error || resp.statusText);
    return data;
  }
  function show(el, text) {
    if (!el) return;
    el.textContent = text;
    el.classList.toggle('d-none', !text);
  }

  const form = document.getElementById('passkeyForm');
  if (form) {
    const status = document.getElementById('passkeyStatus');
    if (!supported) {
      form.classList.add('d-none');
      show(status, form.dataset.unsupported);
    }
    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      show(status, '');
      try {
        const options = await post(form.dataset.optionsUrl, { password: form.elements.password.value });
        options.challenge = toBytes(options.challenge);
        options.user.id = toBytes(options.user.id);
        (options.excludeCredentials || []).forEach((c) => { c.id = toBytes(c.id); });
        const cred = await navigator.credentials.create({ publicKey: options });
        await post(form.action, {
          name: form.elements.name.value,
          credential: {
            id: cred.id, rawId: toB64(cred.rawId), type: cred.type,
            authenticatorAttachment: cred.authenticatorAttachment,
            clientExtensionResults: cred.getClientExtensionResults(),
            response: {
              clientDataJSON: toB64(cred.response.clientDataJSON),
              attestationObject: toB64(cred.response.attestationObject),
              transports: cred.response.getTransports ? cred.response.getTransports() : [],
            },
          },
        });
        window.location.reload();
      } catch (err) {
        show(status, err.name === 'NotAllowedError' ? form.dataset.cancelled : (err.message || form.dataset.failed));
      }
    });
  }

  const login = document.getElementById('passkeyLogin');
  if (login) {
    const status = document.getElementById('passkeyLoginStatus');
    if (!supported) login.classList.add('d-none');
    login.addEventListener('click', async () => {
      show(status, '');
      try {
        const options = await post(login.dataset.optionsUrl);
        options.challenge = toBytes(options.challenge);
        (options.allowCredentials || []).forEach((c) => { c.id = toBytes(c.id); });
        const cred = await navigator.credentials.get({ publicKey: options });
        const result = await post(login.dataset.loginUrl, {
          next: login.dataset.next || '',
          credential: {
            id: cred.id, rawId: toB64(cred.rawId), type: cred.type,
            authenticatorAttachment: cred.authenticatorAttachment,
            clientExtensionResults: cred.getClientExtensionResults(),
            response: {
              clientDataJSON: toB64(cred.response.clientDataJSON),
              authenticatorData: toB64(cred.response.authenticatorData),
              signature: toB64(cred.response.signature),
              userHandle: cred.response.userHandle ? toB64(cred.response.userHandle) : null,
            },
          },
        });
        window.location.assign(result.redirect || '/');
      } catch (err) {
        show(status, err.name === 'NotAllowedError' ? login.dataset.cancelled : (err.message || login.dataset.failed));
      }
    });
  }
})();
