# Runbook de incidentes

Qué mirar y qué hacer cuando algo falla. El mapa del sistema está en [architecture.md](architecture.md).
En los comandos, `<env>` es `staging` o `prod` y la región es `southamerica-east1`.

## Primeros 5 minutos

1. **¿Qué está caído?** `curl -s https://<host>/api/ready` devuelve `{"checks": {"database": ..., "redis": ...}}` y 503 si algo falla. `/api/health` dice qué versión y commit corren.
2. **¿Desde cuándo?** Tablero de Grafana / Cloud Monitoring (5xx, p95, `/api/ready`) y Sentry, que agrupa los errores por versión.
3. **¿Fue un deploy?** Si empezó con una versión nueva, volvé a la anterior (ver [Volver a la versión anterior](#volver-a-la-versión-anterior)) y diagnosticá después.
4. **Logs:**
   - GCP: `gcloud run services logs read empleoia-web-<env> --region southamerica-east1 --limit 200` y `gcloud logging read 'resource.labels.worker_pool_name="empleoia-worker-<env>"' --limit 200`.
   - Local: `docker compose logs --tail 200 web celery_worker`; en disco, `logs/app.log` (rota a 3 × 5 MB).

## Síntomas

### La base no responde (`database: error` en `/api/ready`)

- Cloud SQL: `gcloud sql instances describe empleoia-mysql-<env> --format='value(state)'` tiene que dar `RUNNABLE`. Si está en mantenimiento, esperá; si está detenida, `gcloud sql instances patch empleoia-mysql-<env> --activation-policy=ALWAYS`.
- Disco sobre 85 %: Cloud SQL lo agranda solo (`disk_autoresize`), y no lo achica después. Buscá qué tabla crece (`information_schema.tables`) antes de que el costo suba; las tareas de retención del beat borran sesiones, eventos y CVs viejos.
- Demasiadas conexiones: cada instancia de Cloud Run abre su pool (`db_config.py`); el máximo de instancias es 10 en prod y 3 en staging (`max_instance_count` en `terraform/main.tf`).
- Datos perdidos o corruptos: [backup-restore.md](backup-restore.md). Antes de restaurar, cloná a un momento anterior y verificá.

### Redis no responde (`redis: error`)

- `/api/ready` solo revisa el Redis de los límites de pedidos (`RATELIMIT_STORAGE_URI`): sin él fallan el login y las APIs. El de `REDIS_URL` (Celery, cachés, métricas) tiene respaldo local, pero sin él no corren las tareas del worker ni del beat.
- Memorystore: `gcloud redis instances describe empleoia-redis-<env> --region southamerica-east1 --format='value(state)'`.
- Local: `docker compose exec redis redis-cli -a "$REDIS_PASSWORD" ping`. Si dice `NOAUTH`, falta `REDIS_PASSWORD` en el `.env` de la web o el worker.

### Búsquedas que no terminan o quedan "en curso"

- Con `SCRAPER_BACKEND=celery`, el worker tiene que estar vivo: `docker compose ps celery_worker` o los logs del worker pool. Si no consume tareas, reinicialo; las búsquedas en curso se pierden y el usuario las relanza.
- Con `thread`, un reinicio de la web corta las búsquedas en curso.
- Un solo portal falla: corré `python scripts/scraper_health.py --query python`. `blocked` = captcha (el portal bloquea al navegador, no cambió el HTML); `0 ofertas` o error = probablemente cambió el HTML → arreglá el selector en `scrapers/` y agregá la página guardada a los tests.
- Indeed pide login para ver ofertas desde IPs de servidor: usá `PROXY_SERVER` o `INDEED_SAVE_WITHOUT_DESCRIPTION=true`.

### Errores 5xx o latencia alta

Las alertas de SLO (consumo del presupuesto de errores) llevan acá. La rápida pide actuar ya; la lenta, revisar en el día. Cuánto presupuesto queda: Monitoring → SLOs, servicio `empleoia-web-<entorno>`.

- Sentry muestra la excepción y la release. Si coincide con un deploy, volvé atrás.
- p95 alto sin errores: mirá en Grafana qué ruta sube; las páginas de resultados con CSV grandes y la IA son las más lentas.
- 429 masivos: un cliente supera `API_RATE_LIMIT` o `AI_RATE_LIMIT`. Con varias instancias, `RATELIMIT_STORAGE_URI` tiene que apuntar a Redis.

### La IA no responde o cuesta de más

- `AI_MONTHLY_TOKEN_LIMIT` (instancia) y `AI_USER_MONTHLY_TOKEN_LIMIT` (cuenta) cortan el gasto: al superarse, la IA responde "se alcanzó el límite mensual de tokens" y el resto de la app sigue.
- Clave inválida o cuota de Gemini agotada: rotá `GEMINI_API_KEY` en Secret Manager y redeployá.
- Para apagarla del todo, sacá `GEMINI_API_KEY`: las funciones de IA responden con un error y el matching con embeddings vuelve a TF-IDF.

### Emails que no llegan

- Revisá el proveedor (SMTP o SendGrid) y la lista de rebotes. Los avisos de borrado por inactividad no se cuentan como enviados si el email falla, así que ninguna cuenta se borra sin aviso.

### Sospecha de incidente de seguridad

1. Rotá `SECRET_KEY` (cierra todas las sesiones) y la clave comprometida en Secret Manager; redeployá.
2. No rotes `CV_ENCRYPTION_KEY` sin re-cifrar: los CVs cifrados con la clave vieja dejan de leerse.
3. Revisá eventos de seguridad por cuenta (Administración y Mi cuenta → Seguridad) y bloqueá cuentas desde Administración.
4. Guardá los logs antes de que roten.

## Volver a la versión anterior

El deploy ya vuelve atrás solo en dos casos: la revisión nueva entra sin tráfico, con la etiqueta `candidate`, y si no pasa `/api/ready` nunca recibe tráfico; si lo pasa pero `/api/ready` falla después de darle el tráfico, el workflow lo devuelve a la revisión anterior. El worker y las migraciones no se vuelven atrás solos. Con el servicio privado (`public_access = false`) no hay smoke test HTTP y la revisión nueva recibe el tráfico apenas queda lista.

Producción solo corre tags. Desplegá el tag anterior con "Run workflow" → `Deploy a GCP` → `prod`, eligiendo el tag en "Use workflow from"; la imagen ya existe y no se reconstruye. Para cortar el tráfico ya, mientras tanto:

```bash
gcloud run revisions list --service empleoia-web-prod --region southamerica-east1
gcloud run services update-traffic empleoia-web-prod --region southamerica-east1 --to-revisions <revisión-anterior>=100
```

Las migraciones no se revierten solas: ver [releases.md](releases.md).

## Después del incidente

- Anotá en el issue qué pasó, cuándo, el impacto y la causa.
- Agregá el test o la alerta que lo habría detectado antes.
- Si este runbook no alcanzó, actualizalo en el mismo PR del arreglo.
