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
    limiter = app.extensions['limiter']
    limiter_obj = next(iter(limiter)) if isinstance(limiter, set) else limiter
    limiter_obj.reset()
    codes = [client.post('/api/ai/copilot', json={'message': 'hola'}).status_code for _ in range(35)]
    assert 429 in codes
    assert all(client.get('/api/health').status_code == 200 for _ in range(35))
    limiter_obj.reset()


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
