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

## Alertas

**Prometheus:** las reglas están en `monitoring/prometheus/alerts.yml`, con tests en `alerts.test.yml`:

| Alerta | Cuándo |
|---|---|
| `EmpleoIAErrores5xx` | Más del 5 % de 5xx durante 10 min |
| `EmpleoIALatenciaAlta` | p95 > 5 s durante 15 min |
| `EmpleoIASinMetricas` | Prometheus no recibe métricas durante 10 min (web caída o `METRICS_TOKEN` cambiado) |
| `EmpleoIAColaCelery` | Más de 20 tareas esperando en una cola durante 15 min |
| `EmpleoIACuotaIA80` / `EmpleoIACuotaIAAgotada` | Consumo de IA del mes ≥ 80 % / 100 % de `AI_MONTHLY_TOKEN_LIMIT` |

```bash
promtool check rules monitoring/prometheus/alerts.yml
promtool test rules monitoring/prometheus/alerts.test.yml
```

```yaml
# prometheus.yml
rule_files:
  - monitoring/prometheus/alerts.yml
```

**Cloud Monitoring (Terraform):** `terraform/monitoring.tf` crea, sin necesitar Prometheus:

- Uptime check de `/api/health` cada 5 min y alerta si falla 10 min. Solo con `public_access = true`.
- 5xx > 5 % y p95 > 5 s con las métricas de Cloud Run.
- Disco de Cloud SQL > 85 %.

Con `alert_email` en el `.tfvars` llegan por email; vacío, las políticas se crean sin canal y se ven en la consola.

Los counters son por instancia: en Cloud Run con varias instancias, sumalos con `sum(...)`.

## Trazas (OpenTelemetry)

Con `OTEL_EXPORTER_OTLP_ENDPOINT` (o `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT`), la web y el worker envían trazas por OTLP/HTTP:

- Web: cada pedido HTTP (FastAPI y las rutas de Flask montadas), sin `/api/health` ni `/metrics`.
- Worker: cada tarea de Celery.
- Ambos: las llamadas salientes con `requests` (portales, Telegram).

Se configuran con las variables estándar de OpenTelemetry: `OTEL_SERVICE_NAME`, `OTEL_TRACES_SAMPLER=parentbased_traceidratio`, `OTEL_TRACES_SAMPLER_ARG=0.1` y `OTEL_EXPORTER_OTLP_HEADERS` para autenticarse en el colector. Para Cloud Trace, apuntalas a un OpenTelemetry Collector con el exporter `googlecloud`.
