"""Tests de health check, límites de upload y rate limit de IA."""
import io

import pytest


def test_health_endpoint(client):
    """El health check responde 200 con estado ok."""
    response = client.get('/api/health')
    assert response.status_code == 200
    assert response.get_json()['status'] == 'ok'


def test_ready_ok_without_redis(client, monkeypatch):
    """Con la base respondiendo y sin Redis configurado, /api/ready da 200."""
    import main
    monkeypatch.setattr(main, '_check_database', lambda: None)
    for name in main.READY_REDIS_ENV:
        monkeypatch.delenv(name, raising=False)
    response = client.get('/api/ready')
    assert response.status_code == 200
    assert response.get_json() == {'status': 'ok', 'checks': {'database': 'ok', 'redis': 'ok'}}


def test_ready_503_when_database_down(client, monkeypatch):
    """Si la base no responde, /api/ready da 503 sin el error interno; /api/health sigue en 200."""
    import main

    def down():
        raise RuntimeError('secreto interno')
    monkeypatch.setattr(main, '_check_database', down)
    monkeypatch.setattr(main, '_check_redis', lambda: None)
    response = client.get('/api/ready')
    assert response.status_code == 503
    assert response.get_json()['checks'] == {'database': 'error', 'redis': 'ok'}
    assert 'secreto' not in response.get_data(as_text=True)
    assert client.get('/api/health').status_code == 200


def test_ready_pings_each_configured_redis(monkeypatch):
    """Hace ping a cada Redis configurado (una vez por URL) y falla si alguno no responde."""
    import redis

    import main
    pinged = []

    class FakeRedis:
        def __init__(self, url):
            self.url = url

        def ping(self):
            pinged.append(self.url)
            if 'down' in self.url:
                raise redis.ConnectionError('no')

        def close(self):
            pass
    monkeypatch.setattr(redis.Redis, 'from_url', staticmethod(lambda url, **kw: FakeRedis(url)))
    monkeypatch.setenv('REDIS_URL', 'redis://a:6379/0')
    monkeypatch.setenv('RATELIMIT_STORAGE_URI', 'redis://a:6379/0')
    monkeypatch.setenv('CELERY_BROKER_URL', 'memory://')
    main._check_redis()
    assert pinged == ['redis://a:6379/0']
    monkeypatch.setenv('CELERY_BROKER_URL', 'redis://down:6379/0')
    with pytest.raises(redis.ConnectionError):
        main._check_redis()


def test_upload_too_large_redirects(client, app):
    """Un upload que supera MAX_CONTENT_LENGTH redirige al perfil."""
    previous = app.config['MAX_CONTENT_LENGTH']
    app.config['MAX_CONTENT_LENGTH'] = 10
    try:
        data = {'role_type': 'dev', 'resume': (io.BytesIO(b'x' * 100), 'cv.txt')}
        response = client.post('/upload_resume', data=data, content_type='multipart/form-data')
        assert response.status_code == 302
    finally:
        app.config['MAX_CONTENT_LENGTH'] = previous


@pytest.fixture
def limited_api(api):
    """Cliente FastAPI con el middleware de rate limit de IA de main.py."""
    import main
    import rate_limit
    api.app.middleware('http')(main.rate_limit_ai)
    rate_limit.reset()
    yield api
    rate_limit.reset()


def test_ai_endpoints_are_rate_limited(limited_api):
    """Las rutas /api/ai/* devuelven 429 al superar el límite; el resto no."""
    codes = [limited_api.post('/api/ai/copilot', json={'message': 'hola'}).status_code for _ in range(35)]
    assert 429 in codes
    assert all(limited_api.get('/api/tracker/jobs').status_code != 429 for _ in range(35))


def test_ai_limit_is_shared_across_ai_routes(limited_api):
    """El límite es por IP para todas las rutas de IA, no por endpoint."""
    for _ in range(30):
        limited_api.post('/api/ai/copilot', json={'message': 'hola'})
    assert limited_api.post('/api/ai/rewrite-bullet', json={'bullet': 'x'}).status_code == 429


def test_ai_limit_fails_open_when_storage_down(monkeypatch):
    """Si Redis no responde, la llamada de IA se permite en vez de dar error."""
    import rate_limit

    def broken_limiter():
        raise ConnectionError('redis caído')
    monkeypatch.setattr(rate_limit, '_limiter', broken_limiter)
    assert rate_limit.hit_ai_limit('1.2.3.4') is True


def test_ai_limit_reads_env_on_first_use(monkeypatch):
    """AI_RATE_LIMIT se lee en el primer uso (después de load_dotenv), no al importar."""
    import rate_limit
    monkeypatch.setenv('AI_RATE_LIMIT', '2 per minute')
    rate_limit.reset()
    assert [rate_limit.hit_ai_limit('9.9.9.9') for _ in range(3)] == [True, True, False]
    monkeypatch.delenv('AI_RATE_LIMIT')
    rate_limit.reset()


def test_api_upload_too_large_returns_json_413(client, app):
    """En rutas /api/ un request demasiado grande devuelve 413 en JSON."""
    previous = app.config['MAX_CONTENT_LENGTH']
    app.config['MAX_CONTENT_LENGTH'] = 10
    try:
        response = client.post('/api/save_applications', json={'filename': 'x' * 100})
        assert response.status_code == 413
        assert 'error' in response.get_json()
    finally:
        app.config['MAX_CONTENT_LENGTH'] = previous


def test_invalid_ai_rate_limit_falls_back_to_default(monkeypatch):
    """Un AI_RATE_LIMIT mal escrito aplica el límite por defecto en vez de dejar pasar todo."""
    import rate_limit
    monkeypatch.setenv('AI_RATE_LIMIT', 'muchas por minuto')
    rate_limit.reset()
    results = [rate_limit.hit_ai_limit('8.8.8.8') for _ in range(31)]
    assert results[:30] == [True] * 30 and results[30] is False
    monkeypatch.delenv('AI_RATE_LIMIT')
    rate_limit.reset()


def test_concurrent_first_hits_share_one_counter(monkeypatch):
    """Las primeras llamadas simultáneas usan un solo contador."""
    import threading
    import rate_limit
    monkeypatch.setenv('AI_RATE_LIMIT', '5 per minute')
    rate_limit.reset()
    results = []
    def hit():
        results.append(rate_limit.hit_ai_limit('7.7.7.7'))

    threads = [threading.Thread(target=hit) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert results.count(True) == 5
    monkeypatch.delenv('AI_RATE_LIMIT')
    rate_limit.reset()
