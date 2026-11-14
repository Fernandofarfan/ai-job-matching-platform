"""Tests de notificaciones push (Web Push con VAPID)."""
import base64
import json
from types import SimpleNamespace
from unittest import mock

import pytest

import accounts
import push

FCM = 'https://fcm.googleapis.com/fcm/send/abc'


@pytest.fixture
def vapid(monkeypatch):
    """Claves VAPID de prueba generadas con el script."""
    from scripts.generate_vapid_keys import generate
    pub, priv = generate()
    monkeypatch.setenv('VAPID_PUBLIC_KEY', pub)
    monkeypatch.setenv('VAPID_PRIVATE_KEY', priv)
    return pub, priv


def test_generated_keys_are_valid_vapid(vapid):
    """La pública es un punto P-256 sin comprimir (65 bytes) y pywebpush acepta la privada."""
    from py_vapid import Vapid
    pub, priv = vapid
    assert len(base64.urlsafe_b64decode(pub + '==')) == 65
    assert Vapid.from_string(priv).sign({'aud': 'https://fcm.googleapis.com', 'sub': 'mailto:a@b.c'})


@pytest.mark.parametrize('endpoint', [
    'http://fcm.googleapis.com/x', 'https://169.254.169.254/latest', 'https://localhost/x',
    'https://fcm.googleapis.com.evil.com/x', 'https://fcm.googleapis.com:8443/x', 'https://evilfcm.googleapis.com.io/x',
])
def test_subscribe_rejects_non_push_endpoints(endpoint):
    """El servidor hace POST al endpoint: solo servicios de push conocidos por HTTPS (sin SSRF)."""
    with pytest.raises(push.PushError):
        push.subscribe(1, endpoint, 'k', 'a')


def test_subscribe_extra_hosts(monkeypatch):
    """PUSH_ALLOWED_HOSTS agrega servicios de push."""
    monkeypatch.setenv('PUSH_ALLOWED_HOSTS', 'push.example.com')
    push.subscribe(1, 'https://eu.push.example.com/x', 'k', 'a')
    assert push.device_count(1) == 1


def test_subscriptions_are_per_account():
    """Cada cuenta ve y borra solo sus dispositivos; un dispositivo re-suscripto pasa a la otra cuenta."""
    push.subscribe(1, FCM, 'k', 'a')
    push.subscribe(1, FCM, 'k2', 'a2')
    push.subscribe(2, 'https://updates.push.services.mozilla.com/wpush/v2/x', 'k', 'a')
    assert push.device_count(1) == 1 and push.device_count(2) == 1
    assert not push.unsubscribe(2, FCM)
    push.subscribe(2, FCM, 'k', 'a')
    assert push.device_count(1) == 0 and push.device_count(2) == 2
    assert push.unsubscribe(2, FCM) and push.device_count(2) == 1


def test_send_delivers_and_drops_expired(vapid):
    """Manda a cada dispositivo de la cuenta y borra los que el servicio dio de baja (410)."""
    push.subscribe(1, FCM, 'k', 'a')
    push.subscribe(1, 'https://web.push.apple.com/x', 'k', 'a')
    push.subscribe(2, 'https://fcm.googleapis.com/fcm/send/otra', 'k', 'a')
    calls = []

    def fake(**kwargs):
        calls.append(kwargs)
        if 'apple' in kwargs['subscription_info']['endpoint']:
            raise _gone()
    with mock.patch.object(push, '_webpush', side_effect=fake):
        assert push.send(1, 'Hola', 'Cuerpo', 'https://evil.com') == 1
    assert len(calls) == 2 and push.device_count(1) == 1 and push.device_count(2) == 1
    payload = json.loads(calls[0]['data'])
    assert payload == {'title': 'Hola', 'body': 'Cuerpo', 'url': '/'}
    assert calls[0]['vapid_private_key'] == vapid[1] and calls[0]['vapid_claims']['sub'].startswith('mailto:')


def _gone():
    """Error de pywebpush con respuesta 410."""
    err = Exception('410 Gone')
    err.response = SimpleNamespace(status_code=410)
    return err


def test_send_without_vapid_does_nothing(monkeypatch):
    """Sin claves VAPID no se intenta mandar."""
    monkeypatch.delenv('VAPID_PRIVATE_KEY', raising=False)
    push.subscribe(1, FCM, 'k', 'a')
    with mock.patch.object(push, '_webpush') as webpush:
        assert push.send(1, 't', 'b') == 0
    webpush.assert_not_called()


def test_push_api(api, vapid):
    """La API devuelve la clave pública, suscribe, prueba y da de baja este navegador."""
    config = api.get('/api/push/config').json()
    assert config['enabled'] and config['public_key'] == vapid[0] and config['devices'] == 0
    body = {'endpoint': FCM, 'keys': {'p256dh': 'k', 'auth': 'a'}}
    assert api.post('/api/push/subscribe', json=body).status_code == 200
    assert api.post('/api/push/subscribe', json={**body, 'endpoint': 'https://10.0.0.1/x'}).status_code == 400
    assert api.post('/api/push/subscribe', json={**body, 'endpoint': FCM + '2'}).status_code == 200
    assert api.get('/api/push/config').json()['devices'] == 2
    with mock.patch.object(push, '_webpush') as webpush:
        assert api.post('/api/push/test', json={'endpoint': FCM}).json()['sent'] == 1
    assert webpush.call_args.kwargs['subscription_info']['endpoint'] == FCM
    assert api.post('/api/push/unsubscribe', json={'endpoint': FCM}).json()['removed']
    assert api.post('/api/push/test', json={'endpoint': FCM}).status_code == 502


def test_push_api_not_configured(api, monkeypatch):
    """Sin VAPID la suscripción responde 503."""
    monkeypatch.delenv('VAPID_PUBLIC_KEY', raising=False)
    assert api.get('/api/push/config').json()['enabled'] is False
    assert api.post('/api/push/subscribe', json={'endpoint': FCM, 'keys': {'p256dh': 'k', 'auth': 'a'}}).status_code == 503


def test_alert_push_channel(vapid):
    """Una alerta con canal push avisa a los dispositivos de la cuenta dueña."""
    from tasks import notification_tasks
    push.subscribe(7, FCM, 'k', 'a')
    with mock.patch.object(push, '_webpush') as webpush, accounts.as_user(7):
        sent = notification_tasks.notify_alert({'name': 'Python', 'channels': ['push']},
                                               [{'Title': 'Backend'}, {'Title': 'Data'}])
    assert sent == {'push': True}
    payload = json.loads(webpush.call_args.kwargs['data'])
    assert payload['title'] == '2 ofertas nuevas: Python' and payload['body'] == 'Backend y 1 más'
    assert payload['url'] == '/alerts'


def test_account_deletion_removes_subscriptions(vapid):
    """Borrar la cuenta borra sus dispositivos."""
    uid = accounts.register('ana@example.com', 'clave-larga-1')
    push.subscribe(uid, FCM, 'k', 'a')
    accounts.delete_account(uid)
    assert push.device_count(uid) == 0
