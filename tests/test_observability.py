"""Métricas Prometheus (/metrics con METRICS_TOKEN) y trazas OpenTelemetry opcionales."""
from fastapi.testclient import TestClient

import ai_usage
import observability


def _value(name, **labels):
    return observability.REGISTRY.get_sample_value(name, labels) or 0


def _client():
    import main
    return TestClient(main.app)


def test_metrics_hidden_without_token(monkeypatch):
    monkeypatch.delenv('METRICS_TOKEN', raising=False)
    assert _client().get('/metrics').status_code == 404


def test_metrics_requires_bearer_token(monkeypatch):
    monkeypatch.setenv('METRICS_TOKEN', 's3creto')
    client = _client()
    assert client.get('/metrics').status_code == 401
    assert client.get('/metrics', headers={'Authorization': 'Bearer otro'}).status_code == 401
    resp = client.get('/metrics', headers={'Authorization': 'Bearer s3creto'})
    assert resp.status_code == 200
    assert 'empleoia_http_requests_total' in resp.text


def test_requests_counted_by_route_template(monkeypatch):
    client = _client()
    before = _value('empleoia_http_requests_total', method='GET', route='/api/health', status='200')
    client.get('/api/health')
    assert _value('empleoia_http_requests_total', method='GET', route='/api/health', status='200') == before + 1
    import main
    scope = {'type': 'http', 'path': '/download_resume/cv.docx', 'method': 'GET', 'root_path': ''}
    assert observability.route_label(main.app, scope) == '/download_resume/{filename}'
    scope['path'] = '/api/tracker/job/7/reminder'
    scope['method'] = 'PUT'
    assert observability.route_label(main.app, scope) == '/api/tracker/job/{job_id}/reminder'
    scope['path'], scope['method'] = '/no/existe/123', 'GET'
    assert observability.route_label(main.app, scope) == 'unmatched'


def test_ai_usage_feeds_token_counters():
    before = _value('empleoia_ai_tokens_total', kind='output')
    calls = _value('empleoia_ai_calls_total')
    ai_usage.record(10, 25)
    assert _value('empleoia_ai_tokens_total', kind='output') == before + 25
    assert _value('empleoia_ai_calls_total') == calls + 1


def test_tracing_off_without_endpoint(monkeypatch):
    monkeypatch.delenv('OTEL_EXPORTER_OTLP_ENDPOINT', raising=False)
    monkeypatch.delenv('OTEL_EXPORTER_OTLP_TRACES_ENDPOINT', raising=False)
    assert observability.setup_tracing() is False


def test_telegram_requests_not_traced(monkeypatch):
    """Las llamadas a Telegram no generan spans: el token del bot viaja en la URL."""
    monkeypatch.setenv('OTEL_PYTHON_REQUESTS_EXCLUDED_URLS', 'example.com/private')
    assert observability.requests_excluded_urls().split(',') == ['api.telegram.org', 'example.com/private']


def test_metrics_endpoint_runs_off_event_loop():
    """/metrics es sincrónico para que las lecturas de Redis no bloqueen el event loop."""
    import asyncio

    import main
    assert not asyncio.iscoroutinefunction(main.metrics)


def test_global_excluded_urls_still_apply(monkeypatch):
    """Sin la variable de requests, se respeta OTEL_PYTHON_EXCLUDED_URLS además de Telegram."""
    monkeypatch.delenv('OTEL_PYTHON_REQUESTS_EXCLUDED_URLS', raising=False)
    monkeypatch.setenv('OTEL_PYTHON_EXCLUDED_URLS', 'internal.example')
    assert observability.requests_excluded_urls().split(',') == ['api.telegram.org', 'internal.example']
