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

## Tablero de Grafana

`monitoring/grafana/dashboards/empleoia.json` muestra el estado del servicio (instancias, pedidos, errores 5xx, latencia y rutas más lentas), el costo de IA (tope mensual usado, tokens y llamadas a Gemini) y la salud de los scrapers (búsquedas por portal y resultado, portales sin ofertas y colas de Celery). Los umbrales de color son los mismos que los de las alertas.

En local:

```bash
METRICS_TOKEN=un-token-largo docker compose --profile monitoring up -d
# Grafana: http://localhost:3000 (admin / GRAFANA_ADMIN_PASSWORD, por defecto admin). Prometheus: http://localhost:9090
```

Prometheus (`monitoring/prometheus/prometheus.yml`) raspa `web:5000/metrics` con el token y carga `alerts.yml`. Grafana arranca con el datasource y el tablero ya cargados (`monitoring/grafana/provisioning`). En otro Grafana se importa el JSON y se elige un datasource Prometheus con uid `prometheus`.

## Alertas

**Prometheus:** las reglas están en `monitoring/prometheus/alerts.yml`, con tests en `alerts.test.yml`:

| Alerta | Cuándo |
|---|---|
| `EmpleoIAErrores5xx` | Más del 5 % de 5xx durante 10 min |
| `EmpleoIALatenciaAlta` | p95 > 5 s durante 15 min |
| `EmpleoIASinMetricas` | Prometheus no recibe métricas durante 10 min (web caída o `METRICS_TOKEN` cambiado) |
| `EmpleoIAColaCelery` | Más de 20 tareas esperando en una cola durante 15 min |
| `EmpleoIACuotaIA80` / `EmpleoIACuotaIAAgotada` | Consumo de IA del mes ≥ 80 % / 100 % de `AI_MONTHLY_TOKEN_LIMIT` |
| `EmpleoIASLODisponibilidadRapido` / `...Lento` | Los 5xx gastan el presupuesto del SLO a 14,4× (1 h y 5 min) / 6× (6 h y 30 min) |
| `EmpleoIASLOLatenciaRapido` / `...Lento` | Los pedidos de más de 1 s gastan el presupuesto a 14,4× / 6×, con las mismas ventanas |

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

- Uptime check de `/api/ready` cada 5 min y alerta si falla 10 min: avisa si se cae la app, la base o Redis. Solo con `public_access = true`.
- `/api/health` dice solo que el proceso está vivo (liveness de Cloud Run). `/api/ready` además hace `SELECT 1` en la base y `PING` al Redis de `RATELIMIT_STORAGE_URI` si es redis:// (sin él fallan login y APIs; Celery y las cachés de `REDIS_URL` tienen respaldo local) y da 503 si algo falla; Cloud Run la usa como startup probe y Docker Compose como healthcheck de `web`.
- 5xx > 5 % y p95 > 5 s con las métricas de Cloud Run.
- Disco de Cloud SQL > 85 %.

Con `alert_email` en el `.tfvars` llegan por email; vacío, las políticas se crean sin canal y se ven en la consola.

## SLOs y presupuesto de errores

`terraform/slo.tf` crea en Cloud Monitoring un servicio con 2 SLOs sobre 28 días, calculados con las métricas de Cloud Run:

| SLO | Objetivo | Variable | Presupuesto de errores en 28 días |
|---|---|---|---|
| Disponibilidad | 99,5 % de pedidos sin 5xx | `slo_availability_goal` | 0,5 % de los pedidos (≈ 3,4 h de caída total) |
| Latencia | 95 % de pedidos en 1 s o menos (p95 ≤ 1 s) | `slo_latency_goal`, `slo_latency_ms` | 5 % de los pedidos |

Las alertas no son por umbral fijo sino por velocidad de consumo del presupuesto (burn rate), con una ventana larga y una corta que tienen que superarse a la vez:

| Alerta | Burn rate | Ventanas | Significa |
|---|---|---|---|
| Rápida | > 14,4 | 1 h y 5 min | Se gastó el 2 % del presupuesto del mes en una hora: a ese ritmo se agota en 2 días |
| Lenta | > 6 | 6 h y 30 min | Se gastó el 5 % en 6 horas: se agota en 5 días |

La ventana corta hace que la alerta se apague apenas se corrige el problema. En la consola (Monitoring → SLOs) se ve cuánto presupuesto queda en el período. Con el presupuesto agotado conviene frenar los deploys de funciones nuevas y priorizar estabilidad hasta que se recupere.

Las alertas de Prometheus `EmpleoIASLO*` usan los mismos objetivos con las métricas de `/metrics`.

Los counters son por instancia: en Cloud Run con varias instancias, sumalos con `sum(...)`.

## Trazas (OpenTelemetry)

Con `OTEL_EXPORTER_OTLP_ENDPOINT` (o `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT`), la web y el worker envían trazas por OTLP/HTTP:

- Web: cada pedido HTTP, sin `/api/health` ni `/metrics`.
- Worker: cada tarea de Celery.
- Ambos: las llamadas salientes con `requests` (portales, Telegram).

Se configuran con las variables estándar de OpenTelemetry: `OTEL_SERVICE_NAME`, `OTEL_TRACES_SAMPLER=parentbased_traceidratio`, `OTEL_TRACES_SAMPLER_ARG=0.1` y `OTEL_EXPORTER_OTLP_HEADERS` para autenticarse en el colector. Para Cloud Trace, apuntalas a un OpenTelemetry Collector con el exporter `googlecloud`.
