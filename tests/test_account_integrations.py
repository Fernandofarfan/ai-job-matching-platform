"""Mi cuenta: Telegram, vincular la extensión, Gmail y reenvío de verificación."""
import pytest

import accounts
import auth
import integrations
import security_events
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


STATE = 'estado-de-la-extension-123'


def test_extension_link_asks_to_confirm(client, ana):
    response = client.get(f'/account/extension/link?state={STATE}')
    page = response.get_data(as_text=True)
    assert response.status_code == 200 and response.headers['Cache-Control'] == 'no-store'
    assert f'name="state" value="{STATE}"' in page and 'empleoia-extension-link' not in page
    assert client.get('/account/extension/link').status_code == 404
    assert client.get('/account/extension/link?state=corto').status_code == 404
    assert client.get('/account/extension/link?state=' + 'x' * 20 + '%22%3E').status_code == 404


def test_extension_link_passes_token_in_page_not_url(client, ana):
    response = client.post('/account/extension/link', data={'state': STATE})
    page = response.get_data(as_text=True)
    assert response.status_code == 200 and response.headers['Cache-Control'] == 'no-store'
    token = page.split('data-token="')[1].split('"')[0]
    assert f'data-state="{STATE}"' in page and auth.extension_token_user(token) == ana
    assert 'extension_linked' in [e['kind'] for e in security_events.recent(ana)]
    assert client.post('/account/extension/link', data={'state': 'mal estado'}).status_code == 404


def test_extension_link_requires_login(client, accounts_db):
    response = client.get(f'/account/extension/link?state={STATE}')
    assert response.status_code == 302 and '/login' in response.headers['Location']


def test_extension_unlinked(client, ana, monkeypatch):
    revoked = []
    monkeypatch.setattr(integrations, 'revoke_extension_token', revoked.append)
    assert client.post('/account/extension_token/revoke').status_code == 302 and revoked == [ana]


def test_gmail_without_client_and_other_actions(client, ana, monkeypatch, tmp_path, gmail_tracker):  # noqa: F811
    monkeypatch.setenv('GMAIL_OAUTH_CLIENT_FILE', str(tmp_path / 'no-existe.json'))
    assert client.post('/account/gmail/connect').status_code == 302
    assert client.get('/account/gmail/callback?state=x&code=y').status_code in (302, 400)
    assert client.post('/account/gmail/disconnect').status_code == 302
    assert client.post('/account/resend_verification').status_code == 302
