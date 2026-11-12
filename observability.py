"""Métricas Prometheus (/metrics) y trazas OpenTelemetry opcionales (OTEL_EXPORTER_OTLP_ENDPOINT)."""
import hmac
import logging
import os

from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, Counter, Histogram, generate_latest
from prometheus_client.core import GaugeMetricFamily

logger = logging.getLogger(__name__)

REGISTRY = CollectorRegistry()
HTTP_REQUESTS = Counter('empleoia_http_requests_total', 'Pedidos HTTP atendidos',
                        ['method', 'route', 'status'], registry=REGISTRY)
HTTP_LATENCY = Histogram('empleoia_http_request_duration_seconds', 'Duración de los pedidos HTTP',
                         ['method', 'route'], registry=REGISTRY,
                         buckets=(0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60))
AI_TOKENS = Counter('empleoia_ai_tokens_total', 'Tokens de Gemini consumidos por este proceso',
                    ['kind'], registry=REGISTRY)
AI_CALLS = Counter('empleoia_ai_calls_total', 'Llamadas a Gemini de este proceso', registry=REGISTRY)
CELERY_QUEUES = ('scraping', 'ai_processing', 'notifications')
CONTENT_TYPE = CONTENT_TYPE_LATEST


class _SharedStateCollector:
    """Datos compartidos en Redis: consumo de IA del mes y tareas esperando en cada cola de Celery."""

    def collect(self):
        try:
            import ai_usage
            usage = ai_usage.summary()
            tokens = GaugeMetricFamily('empleoia_ai_month_tokens', 'Tokens de Gemini del mes (todas las instancias)',
                                       labels=['kind'])
            tokens.add_metric(['input'], usage['input_tokens'])
            tokens.add_metric(['output'], usage['output_tokens'])
            yield tokens
            yield GaugeMetricFamily('empleoia_ai_month_calls', 'Llamadas a Gemini del mes', value=usage['calls'])
            if usage.get('monthly_token_limit'):
                yield GaugeMetricFamily('empleoia_ai_month_token_limit', 'Tope mensual de tokens',
                                        value=usage['monthly_token_limit'])
        except Exception as e:
            logger.warning(f"Métricas de IA no disponibles ({e})")
        url = os.getenv('REDIS_URL', '')
        if url.startswith(('redis://', 'rediss://')):
            try:
                import redis
                client = redis.Redis.from_url(url, socket_timeout=1, socket_connect_timeout=1)
                backlog = GaugeMetricFamily('empleoia_celery_queue_length', 'Tareas esperando en la cola',
                                            labels=['queue'])
                for queue in CELERY_QUEUES:
                    backlog.add_metric([queue], client.llen(queue))
                yield backlog
            except Exception as e:
                logger.warning(f"Largo de colas de Celery no disponible ({e})")


REGISTRY.register(_SharedStateCollector())


def observe_ai(input_tokens, output_tokens):
    AI_CALLS.inc()
    AI_TOKENS.labels('input').inc(max(int(input_tokens or 0), 0))
    AI_TOKENS.labels('output').inc(max(int(output_tokens or 0), 0))


def observe_request(method, route, status, seconds):
    HTTP_REQUESTS.labels(method, route, str(status)).inc()
    HTTP_LATENCY.labels(method, route).observe(seconds)


def route_label(asgi_app, scope, flask_app=None):
    """Plantilla de la ruta (/download_resume/<filename>) para no crear una serie por URL."""
    label = _asgi_route(asgi_app.router.routes, scope)
    if label:
        return label
    if flask_app is not None:
        try:
            rule, _ = flask_app.url_map.bind('localhost').match(
                scope['path'], method=scope.get('method', 'GET'), return_rule=True)
            return rule.rule
        except Exception:
            pass
    return 'unmatched'


def _asgi_route(routes, scope, prefix=''):
    from starlette.routing import Match, Mount

    for route in routes:
        if isinstance(route, Mount):
            if route.path and route.matches(scope)[0] == Match.FULL:
                return f'{route.path}/*'
            continue
        if route.matches(scope)[0] != Match.FULL:
            continue
        nested = getattr(route, 'original_router', None)  # FastAPI >= 0.13x agrupa los include_router
        if nested is not None:
            context = getattr(route, 'include_context', None)
            label = _asgi_route(nested.routes, scope, prefix + getattr(context, 'prefix', ''))
            if label:
                return label
            continue
        path = getattr(route, 'path', None)
        if path:
            return prefix + path
    return None


def metrics_allowed(authorization):
    """/metrics solo con METRICS_TOKEN configurado y enviado como Bearer; si falta, devuelve None (404)."""
    token = os.getenv('METRICS_TOKEN', '')
    if not token:
        return None
    return hmac.compare_digest((authorization or '').encode(), f'Bearer {token}'.encode())


def render():
    """Texto de exposición Prometheus del registro global."""
    return generate_latest(REGISTRY)


def requests_excluded_urls():
    """URLs salientes sin trazar: la API de Telegram lleva el token del bot en el path."""
    # Igual que el fallback de RequestsInstrumentor: la variable específica pisa a la global
    extra = os.getenv('OTEL_PYTHON_REQUESTS_EXCLUDED_URLS') or os.getenv('OTEL_PYTHON_EXCLUDED_URLS', '')
    return ','.join(u for u in ('api.telegram.org', extra) if u)


def tracing_enabled():
    return bool(os.getenv('OTEL_EXPORTER_OTLP_ENDPOINT') or os.getenv('OTEL_EXPORTER_OTLP_TRACES_ENDPOINT'))


def setup_tracing(fastapi_app=None, celery_worker=False):
    """Envía trazas por OTLP/HTTP si hay endpoint; el nombre y el muestreo salen de OTEL_SERVICE_NAME/OTEL_TRACES_*."""
    if not tracing_enabled():
        return False
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.requests import RequestsInstrumentor
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        provider = TracerProvider()
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
        trace.set_tracer_provider(provider)
        RequestsInstrumentor().instrument(excluded_urls=requests_excluded_urls())
        if fastapi_app is not None:
            from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
            FastAPIInstrumentor.instrument_app(fastapi_app, excluded_urls='api/health,metrics')
        if celery_worker:
            from opentelemetry.instrumentation.celery import CeleryInstrumentor
            CeleryInstrumentor().instrument()
        return True
    except Exception as e:
        logger.warning(f"No se pudo activar OpenTelemetry ({e})")
        return False
