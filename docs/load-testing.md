# Prueba de carga

`loadtest/locustfile.py` simula usuarios con cuenta que entran y navegan el tracker, las estadísticas, el embudo y el ranking. No llama a Gemini ni a los portales: mide la web, MySQL y Redis.

```bash
python -m venv .venv-load && .venv-load/bin/pip install --require-hashes -r requirements-loadtest.txt
LOADTEST_EMAIL=usuario@ejemplo.com LOADTEST_PASSWORD=... python loadtest/seed.py --jobs 85  # solo en una base de prueba
LOADTEST_EMAIL=usuario@ejemplo.com LOADTEST_PASSWORD=... \
  .venv-load/bin/locust -f loadtest/locustfile.py --host http://127.0.0.1:5000 \
  --headless -u 20 -r 5 -t 3m --csv results/loadtest
```

Locust va en un entorno aparte para no sumarle gevent a la app.

- En el CI corre en el job `loadtest` con 20 usuarios durante 90 s y límites de `LOADTEST_P95_MS=800` y 1 % de errores. Los CSV quedan en el artefacto `loadtest`.
- `loadtest/seed.py` crea la cuenta (o reusa la existente) con postulaciones en todos los estados y una marca de "me interesa / no me interesa" por cada una, para que el tracker y el ranking tengan datos.
- Termina con código 1 si el p95 supera `LOADTEST_P95_MS` (1500 ms por defecto) o si los errores pasan `LOADTEST_MAX_FAIL_RATIO` (1 % por defecto), así se puede usar como gate.
- `/login` tiene un rate limit de 10 POST por minuto por IP: el script espera y reintenta los 429, así que con muchos usuarios el arranque tarda.
- Usá una cuenta de prueba, no la tuya, y no lo corras contra prod sin avisar: genera tráfico real contra Cloud SQL.

## Línea base

Local, una instancia de uvicorn, MySQL 8 y Redis en la misma VM, cuenta con 85 postulaciones. 20 usuarios, 3 minutos:

| Ruta | Pedidos | p50 | p95 | p99 |
|---|---|---|---|---|
| `/api/tracker/jobs` | 476 | 18 ms | 30 ms | 45 ms |
| `/api/tracker/stats` | 311 | 16 ms | 27 ms | 33 ms |
| `/tracker` | 202 | 18 ms | 30 ms | 38 ms |
| `/` | 212 | 15 ms | 26 ms | 34 ms |
| `/api/ranking` | 98 | 11 ms | 19 ms | 30 ms |
| `/api/analytics/funnel` | 91 | 10 ms | 16 ms | 26 ms |
| Total | 1593 | 16 ms | 32 ms | 100 ms |

0 errores. El p99 total lo sube `POST /login` (hash de la contraseña). En Cloud Run, repetila contra staging antes de cambiar `max_instance_count` o el tier de Cloud SQL.
