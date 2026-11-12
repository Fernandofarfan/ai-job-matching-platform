# Observabilidad

## Métricas (Prometheus)

`GET /metrics` responde solo si `METRICS_TOKEN` está configurado y el pedido trae `Authorization: Bearer <METRICS_TOKEN>`. Sin token configurado devuelve 404.

```yaml
# prometheus.yml
scrape_configs:
  - job_name: empleoia
    scheme: https
    authorization:
      credentials: <METRICS_TOKEN>
    static_configs:
      - targets: ["<servicio>.run.app"]
```

| Métrica | Tipo | Qué mide |
|---|---|---|
| `empleoia_http_requests_total{method,route,status}` | counter | Pedidos por plantilla de ruta (`/download_resume/<filename>`, no la URL completa) |
| `empleoia_http_request_duration_seconds{method,route}` | histogram | Latencia |
| `empleoia_ai_calls_total`, `empleoia_ai_tokens_total{kind}` | counter | Llamadas y tokens de Gemini de la instancia |
| `empleoia_ai_month_tokens{kind}`, `empleoia_ai_month_calls`, `empleoia_ai_month_token_limit` | gauge | Consumo del mes compartido en Redis (todas las instancias) |
| `empleoia_celery_queue_length{queue}` | gauge | Tareas esperando en `scraping`, `ai_processing` y `notifications` |

Alertas sugeridas:

```promql
# Más de 5 % de errores 5xx en 10 minutos
sum(rate(empleoia_http_requests_total{status=~"5.."}[10m])) / sum(rate(empleoia_http_requests_total[10m])) > 0.05
# p95 de latencia > 5 s
histogram_quantile(0.95, sum by (le) (rate(empleoia_http_request_duration_seconds_bucket[10m]))) > 5
# Worker caído o saturado
max(empleoia_celery_queue_length) > 20
# Consumo de IA por encima del 80 % del tope
sum(empleoia_ai_month_tokens) / empleoia_ai_month_token_limit > 0.8
```

Los counters son por instancia: en Cloud Run con varias instancias, sumalos con `sum(...)`.

## Trazas (OpenTelemetry)

Con `OTEL_EXPORTER_OTLP_ENDPOINT` (o `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT`), la web y el worker envían trazas por OTLP/HTTP:

- Web: cada pedido HTTP (FastAPI y las rutas de Flask montadas), sin `/api/health` ni `/metrics`.
- Worker: cada tarea de Celery.
- Ambos: las llamadas salientes con `requests` (portales, Telegram).

Se configuran con las variables estándar de OpenTelemetry: `OTEL_SERVICE_NAME`, `OTEL_TRACES_SAMPLER=parentbased_traceidratio`, `OTEL_TRACES_SAMPLER_ARG=0.1` y `OTEL_EXPORTER_OTLP_HEADERS` para autenticarse en el colector. Para Cloud Trace, apuntalas a un OpenTelemetry Collector con el exporter `googlecloud`.
