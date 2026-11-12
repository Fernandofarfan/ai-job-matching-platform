"""Envío de emails: reintentos, rebotes, SendGrid y su webhook firmado."""
import base64
import json
import smtplib
import time
from unittest import mock

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

import email_delivery


@pytest.fixture
def smtp_env(monkeypatch, _accounts_sqlite):
    monkeypatch.setenv('EMAIL_PROVIDER', 'smtp')
    monkeypatch.setenv('SMTP_USER', 'bot@example.com')
    monkeypatch.setenv('SMTP_PASSWORD', 'x')
    monkeypatch.setenv('EMAIL_RETRY_SECONDS', '0')


def _smtp(side_effects):
    """smtplib.SMTP falso cuyo sendmail levanta/devuelve en orden."""
    server = mock.MagicMock()
    server.__enter__.return_value = server
    server.sendmail.side_effect = side_effects
    return mock.patch('email_delivery.smtplib.SMTP', return_value=server), server


def test_retries_temporary_smtp_errors(smtp_env):
    patcher, server = _smtp([smtplib.SMTPServerDisconnected('x'), smtplib.SMTPResponseException(451, b'busy'), {}])
    with patcher:
        assert email_delivery.send('a@example.com', 'Hola', '<p>x</p>') is True
    assert server.sendmail.call_count == 3


def test_gives_up_after_max_attempts(smtp_env, monkeypatch):
    monkeypatch.setenv('EMAIL_MAX_ATTEMPTS', '2')
    patcher, server = _smtp(OSError('down'))
    with patcher:
        assert email_delivery.send('a@example.com', 'Hola', 'x') is False
    assert server.sendmail.call_count == 2


def test_permanent_recipient_error_suppresses(smtp_env):
    refused = smtplib.SMTPRecipientsRefused({'gone@example.com': (550, b'no such user')})
    patcher, server = _smtp(refused)
    with patcher:
        assert email_delivery.send('gone@example.com', 'Hola', 'x') is False
        assert server.sendmail.call_count == 1
        assert email_delivery.is_suppressed('GONE@example.com ')
        assert email_delivery.send('gone@example.com', 'Otra', 'x') is False
        assert server.sendmail.call_count == 1  # ya no se intenta
    assert email_delivery.unsuppress('gone@example.com') is True
    assert not email_delivery.is_suppressed('gone@example.com')


def test_not_configured(monkeypatch):
    monkeypatch.setenv('EMAIL_PROVIDER', 'sendgrid')
    monkeypatch.delenv('SENDGRID_API_KEY', raising=False)
    assert email_delivery.configured() is False
    assert email_delivery.send('a@example.com', 's', 'x') is False


def test_sendgrid_send_and_retry(monkeypatch, _accounts_sqlite):
    monkeypatch.setenv('EMAIL_PROVIDER', 'sendgrid')
    monkeypatch.setenv('SENDGRID_API_KEY', 'SG.test')
    monkeypatch.setenv('EMAIL_FROM', 'no-reply@example.com')
    monkeypatch.setenv('EMAIL_RETRY_SECONDS', '0')
    responses = [mock.Mock(status_code=503), mock.Mock(status_code=202)]
    post = mock.Mock(side_effect=responses)
    monkeypatch.setattr('requests.post', post)
    assert email_delivery.send('a@example.com', 'Hola', '<p>x</p>') is True
    body = post.call_args.kwargs['json']
    assert body['from']['email'] == 'no-reply@example.com' and body['personalizations'][0]['to'][0]['email'] == 'a@example.com'
    assert post.call_args.kwargs['headers']['Authorization'] == 'Bearer SG.test'
    post.side_effect = [mock.Mock(status_code=400)]
    assert email_delivery.send('a@example.com', 'Hola', 'x') is False
    assert not email_delivery.is_suppressed('a@example.com')


def test_sendgrid_events_suppress_bounces_and_spam(_accounts_sqlite):
    events = [{'email': 'b@example.com', 'event': 'bounce', 'type': 'bounce'},
              {'email': 'c@example.com', 'event': 'bounce', 'type': 'blocked'},
              {'email': 'd@example.com', 'event': 'spamreport'},
              {'email': 'e@example.com', 'event': 'dropped', 'reason': 'Bounced Address'},
              {'email': 'f@example.com', 'event': 'delivered'}, 'basura']
    assert email_delivery.handle_sendgrid_events(events) == 3
    assert [email_delivery.is_suppressed(f'{c}@example.com') for c in 'bcdef'] == [True, False, True, True, False]


def _signed(private_key, payload: bytes, timestamp: str) -> str:
    return base64.b64encode(private_key.sign(timestamp.encode() + payload, ec.ECDSA(hashes.SHA256()))).decode()


@pytest.fixture
def webhook_key(monkeypatch):
    private_key = ec.generate_private_key(ec.SECP256R1())
    der = private_key.public_key().public_bytes(serialization.Encoding.DER,
                                                serialization.PublicFormat.SubjectPublicKeyInfo)
    monkeypatch.setenv('SENDGRID_WEBHOOK_PUBLIC_KEY', base64.b64encode(der).decode())
    return private_key


def test_signature_verification(webhook_key):
    payload, ts = b'[]', str(int(time.time()))
    assert email_delivery.verify_sendgrid_signature(payload, _signed(webhook_key, payload, ts), ts)
    assert not email_delivery.verify_sendgrid_signature(b'[{}]', _signed(webhook_key, payload, ts), ts)
    old = str(int(time.time()) - 3600)
    assert not email_delivery.verify_sendgrid_signature(payload, _signed(webhook_key, payload, old), old)
    assert not email_delivery.verify_sendgrid_signature(payload, 'no-base64!', ts)


def test_webhook_route(client, webhook_key, _accounts_sqlite):
    payload = json.dumps([{'email': 'x@example.com', 'event': 'spamreport'}]).encode()
    ts = str(int(time.time()))
    headers = {'X-Twilio-Email-Event-Webhook-Signature': _signed(webhook_key, payload, ts),
               'X-Twilio-Email-Event-Webhook-Timestamp': ts, 'Content-Type': 'application/json'}
    response = client.post('/webhooks/sendgrid', data=payload, headers=headers)
    assert response.status_code == 200 and response.get_json()['suppressed'] == 1
    assert email_delivery.is_suppressed('x@example.com')
    headers['X-Twilio-Email-Event-Webhook-Signature'] = _signed(webhook_key, b'otro', ts)
    assert client.post('/webhooks/sendgrid', data=payload, headers=headers).status_code == 403


def test_temporary_smtp_login_failure_is_retried(smtp_env):
    patcher, server = _smtp([{}])
    server.login.side_effect = [smtplib.SMTPAuthenticationError(454, b'try later'), None]
    with patcher:
        assert email_delivery.send('a@example.com', 'Hola', 'x') is True
    assert server.login.call_count == 2


def test_webhook_rejects_oversized_body_and_reports_db_failure(client, webhook_key, monkeypatch, _accounts_sqlite):
    from routers import webhooks
    monkeypatch.setattr(webhooks, 'MAX_BODY', 64)
    assert client.post('/webhooks/sendgrid', data=b'[' + b' ' * 100 + b']',
                       headers={'Content-Type': 'application/json'}).status_code == 413
    monkeypatch.setattr(webhooks, 'MAX_BODY', 1024 * 1024)
    payload = json.dumps([{'email': 'y@example.com', 'event': 'bounce', 'type': 'bounce'}]).encode()
    ts = str(int(time.time()))
    headers = {'X-Twilio-Email-Event-Webhook-Signature': _signed(webhook_key, payload, ts),
               'X-Twilio-Email-Event-Webhook-Timestamp': ts, 'Content-Type': 'application/json'}
    monkeypatch.setattr(email_delivery, 'suppress', lambda email, reason: False)
    # SendGrid reintenta los webhooks que no reciben 2xx
    assert client.post('/webhooks/sendgrid', data=payload, headers=headers).status_code == 503
