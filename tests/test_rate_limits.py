"""Tests de los límites por cuenta, por email y de la IP real detrás de un proxy."""
import pytest

import accounts
import rate_limit

PASSWORD = 'clave-larga-1'


@pytest.fixture
def limited(app, accounts_db, monkeypatch):
    """Límites de páginas encendidos y con contadores vacíos."""
    monkeypatch.setenv('ALLOW_SIGNUP', 'true')
    monkeypatch.setitem(app.config, 'RATELIMIT_ENABLED', True)
    rate_limit._state.clear()
    yield
    rate_limit._state.clear()


def _login(client, email):
    return client.post('/login', data={'email': email, 'password': PASSWORD})


def test_client_key_prefers_account():
    assert rate_limit.client_key(7, '1.2.3.4') == 'user:7'
    assert rate_limit.client_key(None, '1.2.3.4') == 'ip:1.2.3.4'


@pytest.mark.parametrize('hops, expected', [('0', '10.0.0.1'), ('1', '5.5.5.5'), ('2', '6.6.6.6'),
                                            ('9', '6.6.6.6'), ('x', '10.0.0.1')])
def test_client_ip_trusts_only_configured_proxy_hops(monkeypatch, hops, expected):
    """Solo se toman las IPs que agregó el proxy propio; la primera la puede inventar el cliente."""
    monkeypatch.setenv('TRUSTED_PROXY_HOPS', hops)
    assert rate_limit.client_ip('10.0.0.1', '6.6.6.6, 5.5.5.5') == expected


def test_account_limits_are_per_account_not_per_ip(app, limited, make_client):
    """Dos cuentas en la misma red tienen cada una su límite de tokens de la extensión."""
    accounts.register('ana@example.com', PASSWORD)
    accounts.register('beto@example.com', PASSWORD)
    ana, beto = make_client(), make_client()
    _login(ana, 'ana@example.com')
    _login(beto, 'beto@example.com')
    link = ('/account/extension/link', {'state': 'estado-de-la-extension-123'})
    assert [ana.post(link[0], data=link[1]).status_code for _ in range(6)][-1] == 429
    assert beto.post(link[0], data=link[1]).status_code == 200


def test_login_is_limited_per_email_across_ips(client, limited, monkeypatch):
    """Probar contraseñas de una cuenta desde muchas IPs se corta a las 20 por hora."""
    monkeypatch.setenv('TRUSTED_PROXY_HOPS', '1')
    accounts.register('ana@example.com', PASSWORD)
    codes = [client.post('/login', data={'email': 'ana@example.com', 'password': 'mal'},
                         headers={'X-Forwarded-For': f'7.7.7.{i}'}).status_code for i in range(21)]
    assert 429 not in codes[:20] and codes[20] == 429
    other = client.post('/login', data={'email': 'otro@example.com', 'password': 'mal'},
                        headers={'X-Forwarded-For': '7.7.8.1'})
    assert other.status_code == 200


def test_login_ip_limit_uses_forwarded_ip(client, limited, monkeypatch):
    """Detrás del proxy, el límite por IP del login no bloquea a todos los usuarios juntos."""
    monkeypatch.setenv('TRUSTED_PROXY_HOPS', '1')
    accounts.register('ana@example.com', PASSWORD)
    for i in range(10):
        client.post('/login', data={'email': f'x{i}@example.com', 'password': 'mal'},
                    headers={'X-Forwarded-For': '9.9.9.9'})
    blocked = client.post('/login', data={'email': 'y@example.com', 'password': 'mal'},
                          headers={'X-Forwarded-For': '9.9.9.9'})
    other_ip = client.post('/login', data={'email': 'z@example.com', 'password': 'mal'},
                           headers={'X-Forwarded-For': '9.9.9.10'})
    assert blocked.status_code == 429 and other_ip.status_code == 200


@pytest.fixture
def api_limited(api, monkeypatch):
    """Cliente FastAPI con el middleware de límites de main.py y la cuenta elegida por el test."""
    import main
    who = {'id': None}
    monkeypatch.setattr(accounts, 'current_user_id', lambda: who['id'])
    monkeypatch.setenv('API_RATE_LIMIT', '3 per minute')
    api.app.middleware('http')(main.rate_limit_ai)
    rate_limit.reset()
    yield api, who
    rate_limit.reset()


def test_api_limit_is_per_account(api_limited):
    """API_RATE_LIMIT cuenta por cuenta: que una la agote no frena a otra en la misma IP."""
    api, who = api_limited
    who['id'] = 1
    assert [api.get('/api/tracker/jobs').status_code for _ in range(4)][-1] == 429
    who['id'] = 2
    assert api.get('/api/tracker/jobs').status_code != 429
    who['id'] = None
    assert api.get('/api/health').status_code != 429


def test_extension_token_counts_per_account(api_limited, monkeypatch):
    """Sin cookie, el token de la extensión identifica la cuenta: dos cuentas en la misma IP no comparten límite."""
    import auth
    api, _ = api_limited
    monkeypatch.setattr(auth, 'extension_token_user', lambda token: {'ta': 1, 'tb': 2}.get(token))
    codes = [api.post('/api/tracker/save-from-extension', json={}, headers={'X-Extension-Token': 'ta'}).status_code
             for _ in range(4)]
    assert codes[-1] == 429
    assert api.post('/api/tracker/save-from-extension', json={},
                    headers={'X-Extension-Token': 'tb'}).status_code != 429


def test_invalid_extension_tokens_stop_querying_the_db(api_limited, monkeypatch):
    """Superado el límite de tokens inválidos de una IP, no se consulta más la base; /api/health no consulta."""
    import auth
    api, _ = api_limited
    calls = []
    monkeypatch.setattr(auth, 'extension_token_user', lambda token: calls.append(token))
    for _ in range(6):
        api.post('/api/tracker/save-from-extension', json={}, headers={'X-Extension-Token': 'malo'})
    assert len(calls) == 3
    before = len(calls)
    assert api.post('/api/tracker/save-from-extension', json={},
                    headers={'X-Extension-Token': 'malo'}).status_code == 429
    api.get('/api/health', headers={'X-Extension-Token': 'malo'})
    assert len(calls) == before
