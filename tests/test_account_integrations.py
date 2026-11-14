"""Mi cuenta: Telegram, token de la extensión, Gmail y reenvío de verificación."""
import pytest

import accounts
import integrations
from tests.test_gmail_tracker import gmail_tracker  # noqa: F401  (clientes de Google simulados)

PASSWORD = 'clave-larga-1'


@pytest.fixture
def ana(client, accounts_db):
    client.post('/register', data={'accept_terms': 'on', 'email': 'ana@example.com', 'password': PASSWORD,
                                   'confirm': PASSWORD})
    return accounts.find_user_id('ana@example.com')


def test_telegram_save_and_test(client, ana, monkeypatch):
    saved = []
    monkeypatch.setattr(integrations, 'set_telegram_chat', lambda uid, chat: saved.append((uid, chat)))
    assert client.post('/account/telegram', data={'chat_id': '123'}).status_code == 302
    assert saved == [(ana, '123')]

    def bad(uid, chat):
        raise integrations.IntegrationError('Chat inválido')
    monkeypatch.setattr(integrations, 'set_telegram_chat', bad)
    assert client.post('/account/telegram', data={'chat_id': 'x'}).status_code == 302
    for ok in (True, False):
        monkeypatch.setattr('tasks.notification_tasks.send_telegram', lambda text, ok=ok: ok)
        assert client.post('/account/telegram/test').status_code == 302


def test_extension_token_shown_once_and_revoked(client, ana, monkeypatch):
    monkeypatch.setattr(integrations, 'new_extension_token', lambda uid: 'tok-secreto-123')
    revoked = []
    monkeypatch.setattr(integrations, 'revoke_extension_token', revoked.append)
    response = client.post('/account/extension_token')
    assert 'tok-secreto-123' in response.get_data(as_text=True) and response.headers['Cache-Control'] == 'no-store'
    assert client.post('/account/extension_token/revoke').status_code == 302 and revoked == [ana]


def test_gmail_without_client_and_other_actions(client, ana, monkeypatch, tmp_path, gmail_tracker):  # noqa: F811
    monkeypatch.setenv('GMAIL_OAUTH_CLIENT_FILE', str(tmp_path / 'no-existe.json'))
    assert client.post('/account/gmail/connect').status_code == 302
    assert client.get('/account/gmail/callback?state=x&code=y').status_code in (302, 400)
    assert client.post('/account/gmail/disconnect').status_code == 302
    assert client.post('/account/resend_verification').status_code == 302
