"""Tests de health check, límites de upload y rate limit de IA."""
import io


def test_health_endpoint(client):
    """El health check responde 200 con estado ok."""
    response = client.get('/api/health')
    assert response.status_code == 200
    assert response.get_json()['status'] == 'ok'


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


def test_ai_endpoints_are_rate_limited(client, app):
    """Las rutas /api/ai/* devuelven 429 al superar el límite; el resto no."""
    import rate_limit
    rate_limit.reset()
    codes = [client.post('/api/ai/copilot', json={'message': 'hola'}).status_code for _ in range(35)]
    assert 429 in codes
    assert all(client.get('/api/health').status_code == 200 for _ in range(35))
    rate_limit.reset()


def test_ai_limit_is_shared_across_ai_routes(client):
    """El límite es por IP para todas las rutas de IA, no por endpoint."""
    import rate_limit
    rate_limit.reset()
    for _ in range(30):
        client.post('/api/ai/copilot', json={'message': 'hola'})
    assert client.post('/api/ai/rewrite-bullet', json={'bullet': 'x'}).status_code == 429
    rate_limit.reset()


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
        response = client.post('/api/tracker/save-from-extension', json={'title': 'x' * 100})
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
    threads = [threading.Thread(target=lambda: results.append(rate_limit.hit_ai_limit('7.7.7.7'))) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert results.count(True) == 5
    monkeypatch.delenv('AI_RATE_LIMIT')
    rate_limit.reset()
