# Changelog

Todos los cambios notables en este proyecto serán documentados en este archivo.

El formato está basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.0.0/),
y este proyecto adhiere a [Semantic Versioning](https://semver.org/lang/es/).


## [Sin publicar] - Habilidades que coinciden y que faltan en cada oferta

- La tabla de resultados tiene la columna "Habilidades": en verde, las del CV que pide la oferta; en gris, "Te falta",
  hasta 8 habilidades que la oferta pide y el CV no tiene (ni como variante: Postgres cuenta como PostgreSQL).
- `skill_catalog.py` reúne el vocabulario de habilidades del parser de CVs; el matching lo usa para leer las ofertas.
  "R" y "Go" no se leen en ofertas, porque aparecen en "R&D" o "go to market".


## [Sin publicar] - Prueba de carga en el CI

- Job `loadtest` del CI: MySQL y Redis reales, una cuenta con 85 postulaciones y marcas (`loadtest/seed.py`) y Locust
  con 20 usuarios durante 90 s. Falla si el p95 pasa de 800 ms o los errores del 1 %; los CSV quedan como artefacto.
- `requirements-loadtest.txt` generado con hashes desde `requirements-loadtest.in`, igual que `requirements.txt`.


## [Sin publicar] - Backend de matching por idioma del CV

- `MATCHING_BACKEND_BY_LANGUAGE` (ej. `es=embeddings,pt=embeddings`) elige el backend según el idioma del CV, por
  encima de `MATCHING_BACKEND`. Vacío por defecto: nada cambia hasta activarlo, y sin `GEMINI_API_KEY` sigue TF-IDF.
- `embeddings.detect_language` distingue español, portugués e inglés por palabras frecuentes, sin dependencias
  nuevas; acierta en los 16 CVs del dataset de evaluación.
- `scripts/eval_matching.py --compare` ignora la variable para medir cada backend puro.

## [Sin publicar] - Extensión de Chrome vinculada desde Mi cuenta

- La extensión (1.2.0) se vincula con "Vincular con mi cuenta": abre `/account/extension/link?state=…`, se confirma
  en la app y el service worker lee el token de esa página solo si el `state` es el que generó. No se copia ningún
  token y el token nunca va en una URL.
- El token se guarda solo en el dispositivo (`chrome.storage.local`); el que versiones anteriores dejaban en
  `storage.sync` se mueve a `local` al actualizar. Mi cuenta muestra si está vinculada y permite desvincularla.
- Se quita "Generar token" de Mi cuenta (lo reemplaza la vinculación) y se registra el evento `extension_linked`.
- E2E con Chromium y la extensión cargada: vinculación, state ajeno, migración desde `sync` y botón del popup.

## [Sin publicar] - Primeros pasos y embudo de activación

- La portada muestra "Primeros pasos" (subí tu CV → primera búsqueda → creá una alerta) con el avance y un botón al
  paso que falta; desaparece cuando la cuenta completa los 3. Los pasos salen de lo que ya está guardado (perfiles,
  CSV de resultados y alertas): no hay tabla nueva y las cuentas viejas cuentan desde el primer día.
- Administración muestra el embudo de activación: cuántas cuentas llegaron a cada paso, en orden, y qué porcentaje
  del paso anterior. Así se ve en qué paso abandonan las cuentas nuevas.

## [Sin publicar] - mypy estricto, etapa 1

- `accounts`, `auth`, `models`, `passkeys`, `security_events`, `two_factor` y `user_sessions` cumplen las reglas de `--strict`
  (override en `pyproject.toml`): todas las funciones tipadas, genéricos con parámetros y sin devolver `Any`.
- `accounts.rowcount()` lee las filas tocadas por un UPDATE/DELETE con su tipo real (`CursorResult`).
- Casos que el chequeo destapó: exportar los datos de una cuenta que se borra a mitad de la exportación, una sesión sin
  `created_at` ni `last_seen_at`, y `is_local_path` con algo que no es texto. Antes daban error 500; ahora se
  rechazan.

## [Sin publicar] - Archivos grandes partidos

Sin cambios de comportamiento: mismas rutas, mismos nombres de ruta y mismos nombres de tareas de Celery.

- `resume_parser.py` (786 líneas) → `resume_parser.py` (lectura del CV) y `job_matcher.py` (`jobMatcher`, `MAX_REQUIRED_YEARS`).
- `routers/account_pages.py` (772) → `account_pages.py` (Mi cuenta), `security_pages.py` (segundo factor y passkeys), `admin_pages.py` y `export_pages.py`.
- `routers/content_pages.py` (602) → `content_pages.py` (resultados y documentos), `profile_pages.py` y `alert_pages.py`.
- `tasks/notification_tasks.py` (561) → las tareas y el envío quedan ahí; los textos de emails y de Telegram pasan a `notification_messages.py`.

## [Sin publicar] - Peso del ranking aprendido de "me interesa / no me interesa"

- `job_ranking.learn_weight()`: con al menos `MIN_TUNING` (5) ofertas marcadas con match de cada lado, elige por cuenta el peso del ranking frente al match (0 a 0,8) que maximiza el AUC de "me interesa" sobre "no me interesa". La preferencia de cada oferta marcada sale de un modelo entrenado sin ella. A igual AUC gana el peso más cercano a `RANKING_WEIGHT`.
- `rank()` usa ese peso; sin marcas suficientes sigue `RANKING_WEIGHT`.
- `/api/ranking` devuelve `weight` y `tuning` (`auc`, `match_auc`, `examples`).

## [Sin publicar] - Acciones e imagen base fijadas por hash

- Todas las GitHub Actions se usan por SHA de commit, con la versión en un comentario (`actions/checkout@11d5960…  # v4.4.0`). Una etiqueta como `@v4` la puede mover quien controle la acción, y el CI correría ese código con acceso a los secretos.
- La imagen base del `Dockerfile` se fija por digest (`@sha256:…`).
- Dependabot ya actualiza los dos (`github-actions` y `docker`) y mantiene el comentario de versión.
- `tests/test_supply_chain.py` falla si se agrega una acción o un `FROM` sin hash.

## [Sin publicar] - Indeed en el monitor de scrapers

- `scripts/scraper_health.py` revisa también Indeed: cuenta las tarjetas de la primera página del listado público (`indeedScraper.listing`), sin abrir descripciones ni guardar CSV. Ubicación con `SCRAPER_HEALTH_INDEED_LOCATION` (por defecto `Remote`).
- Si un portal muestra un captcha, el resultado sale con `"blocked": true` y no abre el issue: un bloqueo no indica que el HTML haya cambiado. Nueva excepción `scrapers.common.PortalBlocked`.
- El workflow del monitor instala `requirements.txt` con hashes.
- Indeed cambió el título de las tarjetas de `<h2>` a `<h3>` y el scraper no encontraba ninguna oferta; ahora se busca por la clase `.jobTitle`.
- Si Indeed manda al login en vez de mostrar una oferta (`from=bot-detection`), la búsqueda se corta con lo encontrado en vez de esperar 10 s por cada oferta.

## [Sin publicar] - Comparación de embeddings con TF-IDF por idioma

- `python scripts/eval_matching.py --compare` muestra NDCG@5, P@3 y MRR en total y por idioma del CV (`en`, `es`, `pt`), y la fila `delta` (embeddings − TF-IDF) cuando se midieron los dos backends. `matching_eval.evaluate()` devuelve también `by_language`.
- Workflow "Comparar matching" (`.github/workflows/matching-compare.yml`): los lunes y a pedido, con el secreto `GEMINI_API_KEY`; deja el JSON como artefacto y en el resumen del job. Sin el secreto mide solo TF-IDF.

## [Sin publicar] - Indeed y conexiones de LinkedIn en Playwright

- `scrapers/indeed_scraper.py` y `scrapers/linkedin_connection.py` usan Playwright (`scrapers.common.Browser`, Chromium sin ventana, `PLAYWRIGHT_WS_ENDPOINT`/`PROXY_SERVER`). Salen del proyecto Selenium, `webdriver-manager` y `undetected-chromedriver`.
- Indeed busca por URL pública, sin login: `date_posted`, `experience_level`, `remote_work` y `salary_range` pasan a parámetros de Indeed; `education_level` se ignora. Ante un captcha la búsqueda se corta y devuelve lo que juntó. El CSV va a la carpeta de resultados de la cuenta.
- Conexiones de LinkedIn: búsqueda de personas en Argentina por URL; solo invita a quien nombra la empresa en su tarjeta; saltea pendientes y perfiles repetidos; "Enviar sin nota".
- Probado con HTML guardado y Chromium; no contra los portales reales.

## [Sin publicar] - Passkeys (WebAuthn)

- Mi cuenta → **Passkeys**: agregar (pide la contraseña actual), ver nombre, alta y último uso, y borrar. Hasta 10 por cuenta.
- Login → **Entrar con una passkey**: sin email ni contraseña (passkeys guardadas en el dispositivo). Se exige verificación del usuario en el dispositivo, así que no pide además el código de la app. Respeta bloqueo de cuenta y email sin confirmar, y registra `login_passkey` en los eventos de seguridad (con aviso de navegador nuevo).
- `passkeys.py` con `webauthn==2.7.1`: desafío de un solo uso en la sesión (5 min), origen y RP ID desde `WEBAUTHN_ORIGIN`/`APP_BASE_URL` y `WEBAUTHN_RP_ID`, contador de firmas. Solo se guarda la clave pública.
- Tabla `passkeys` (migración `0019_passkeys`), borrada con la cuenta.
- E2E con Chromium y un autenticador virtual (CDP WebAuthn).

## [Sin publicar] - Emails por proveedor, con reintentos y rebotes

- `email_delivery.py`: `EMAIL_PROVIDER=smtp` (por defecto; sirve para SES SMTP) o `sendgrid` (`SENDGRID_API_KEY`, `EMAIL_FROM`). Todos los emails pasan por ahí.
- Reintentos: las fallas temporales (SMTP 4xx o conexión caída, HTTP 429/5xx) se reintentan `EMAIL_MAX_ATTEMPTS` veces (3 por defecto), con espera creciente desde `EMAIL_RETRY_SECONDS`. Antes un email que fallaba se perdía sin reintento.
- Rebotes: un rechazo permanente de SMTP sobre el destinatario, y los rebotes, denuncias de spam y `dropped` que informa SendGrid en `POST /webhooks/sendgrid` (firma ECDSA con `SENDGRID_WEBHOOK_PUBLIC_KEY`), agregan la dirección a `email_suppressions`. A esas direcciones no se les manda más. Se guarda solo el SHA-256 del email.
- Resumen semanal: si el worker se corta entre tomar el resumen y mandarlo, a los `WEEKLY_DIGEST_CLAIM_MINUTES` minutos (60 por defecto) se vuelve a mandar. Antes esa semana se perdía.
- Migración `0018_email_delivery`.

## [Sin publicar] - "Me interesa / no me interesa" en las ofertas

- Resultados: cada oferta tiene "me interesa" y "no me interesa"; tocar la marca activa la quita. Se guarda por cuenta en la tabla nueva `job_feedback` (migración `0017_job_feedback`), identificada por título y empresa, así que vale para la misma oferta en otro portal. `POST /api/job_feedback`.
- El ranking personal usa esas marcas con peso doble que las del tracker, y se recalcula apenas marcás una oferta.
- Las alertas no vuelven a mandar ofertas marcadas "no me interesa".
- Medición: `/api/ranking` devuelve en `feedback` cuántas marcaste y el AUC del match (qué tan seguido una "me interesa" tiene más match que una "no me interesa"). `python scripts/feedback_report.py` da lo mismo para todas las cuentas juntas.
- Fix: el ranking personal guardaba en caché un solo modelo para todos, así que durante 10 minutos una cuenta podía ver sus resultados ordenados con lo que eligió otra. Ahora hay uno por cuenta.
- Borrar la cuenta y exportar mis datos incluyen `job_feedback`.

## [Sin publicar] - E2E del recorrido completo

- `tests_integration/test_main_flow.py`: con Chromium contra la app levantada, una cuenta nueva se registra, sube su CV, marca una oferta de sus resultados como postulada, la ve en el tracker, lo exporta a Excel y sale. Corre en el job `integration`.
- Fix: "Guardar" en la página de resultados no guardaba nada en MySQL (respondía `saved: 0`), porque la fecha llegaba como `2026-11-12T17:04:46.496Z`. Ahora se convierte a UTC.

## [Sin publicar] - Chequeo de que la app está lista

- `GET /api/ready`: 200 si la base responde a `SELECT 1` y, si `RATELIMIT_STORAGE_URI` es Redis, ese Redis a `PING` (sin él no andan login ni APIs; `REDIS_URL` tiene respaldo local); 503 si algo falla, sin el error interno. `/api/health` sigue diciendo solo que el proceso está vivo.
- Cloud Run: el startup probe y el uptime check usan `/api/ready`; el liveness sigue en `/api/health`, así una caída de la base no reinicia las instancias en loop.
- Docker Compose: healthcheck de `web` contra `/api/ready`.

## [Sin publicar] - Dependencias con hash, Trivy y SBOM

- `requirements.in` tiene las dependencias directas; `requirements.txt` sale de `pip-compile --generate-hashes` con todas las dependencias (también las indirectas) y su hash. Docker y el CI instalan con `--require-hashes`: si un paquete cambia en PyPI, la instalación se corta.
- CI: falla si `requirements.txt` no coincide con `requirements.in`.
- CI, job nuevo `image`: arma la imagen Docker, falla con vulnerabilidades críticas que ya tienen parche (Trivy) y sube el SBOM CycloneDX como artefacto `sbom`.

## [Sin publicar] - Tablero de Grafana

- `monitoring/grafana/dashboards/empleoia.json`: estado del servicio, costo de IA y salud de los scrapers, con los umbrales de las alertas.
- `docker compose --profile monitoring up`: Prometheus (con `alerts.yml`) y Grafana con el datasource y el tablero ya cargados. Sin el perfil, el compose no cambia.

## [Sin publicar] - Más casos para medir el matching

- `eval/matching_dataset.json`: de 6 CVs y 12 ofertas a 16 CVs y 25 ofertas, con CVs y ofertas en español y portugués, y ofertas que piden más años de los que tiene el CV.
- `resume_parser`: los años de experiencia pedidos también se leen en español y portugués ("3 años de experiencia", "2 anos de experiência", "mínimo 4 años", "pelo menos 5 anos"). Antes esas ofertas contaban como sin requisito.
- `python scripts/eval_matching.py --compare`: mide TF-IDF y embeddings sobre el mismo dataset (embeddings necesita `GEMINI_API_KEY`).
- Línea base del CI: precisión@3 mínima 0,70 (varios CVs nuevos tienen una sola oferta buena).

## [Sin publicar] - Resumen semanal por email

- Tarea semanal `send_weekly_digests` en Celery beat: un email por cuenta activa con las ofertas nuevas de sus alertas, las postulaciones sin respuesta y los próximos pasos del tracker. Si no hay novedades, no se manda. Beat la corre cada hora y cada cuenta recibe el resumen 7 días después del anterior (`users.weekly_digest_sent_at`), así los reinicios del worker no lo postergan y las ofertas no se repiten. Las entrevistas en curso solas no disparan el email.
- Mi cuenta: prender o apagar el resumen (`users.weekly_digest_off_at`, migración `0016_weekly_digest`).

## [Sin publicar] - mypy en todo el proyecto

- mypy revisa todo el código y los tests (antes 36 archivos elegidos a mano); solo quedan afuera las migraciones de Alembic.
- Indeed: `search_jobs` llamaba a `apply_filters`, que no existe, y cortaba cada búsqueda sin filtros; si no encontraba el campo de ubicación, fallaba con un error en vez de reintentar.
- Las rutas de Mi cuenta usan `accounts.require_user_id()`, que falla claro si no hay cuenta en el pedido en vez de pasar `None`.

## [Sin publicar] - Cobertura mínima de tests

- La cobertura se mide solo sobre el código de la app (sin tests, scripts ni migraciones; config en `pyproject.toml`) y el CI exige 57%, antes 20% contando los propios tests. Tests nuevos para conexiones de LinkedIn, búsquedas de Indeed y LinkedIn, notificaciones y análisis de salarios.
- La búsqueda general de conexiones de LinkedIn terminaba siempre como fallida (dividía por la lista de empresas, vacía en ese modo).
- El reintento de login de la búsqueda de LinkedIn perdía el email y la contraseña y volvía a probar sin credenciales.

## [Sin publicar] - Mensajes de progreso traducidos

- Los mensajes de progreso de las búsquedas y de las solicitudes de conexión se muestran en el idioma de la cuenta (español, inglés o portugués). Se guardan como texto en español más sus valores (`i18n.lazy`) y `/status` los traduce al leerlos, así que sirven igual desde un thread o desde el worker de Celery.

## [Sin publicar] - Errores de producción en Sentry

- Con `SENTRY_DSN`, los errores 500 de la web y las tareas de Celery que fallan llegan a Sentry, con el entorno (`SENTRY_ENVIRONMENT`, que Terraform pone en staging/prod), la versión (`SENTRY_RELEASE` o `K_REVISION` de Cloud Run) y el componente (`web` o `worker`). Antes Sentry solo se iniciaba en la web, y los 500 que atrapaba el manejador de errores no llegaban.
- Los eventos no llevan cookies, cabeceras de autenticación, cuerpos de pedidos, query strings ni emails: solo el id de la cuenta. Los `logger.error` quedan como contexto, no como eventos.

## [Sin publicar] - Todo el esquema de la base en Alembic

- Alembic crea y actualiza todas las tablas: `0000_core_tables` crea las que antes creaba `setup_database.sql` y `0015_core_schema` lleva cada tabla a la forma de los modelos, venga la base del script viejo o de `create_all`. Se eliminaron `setup_database.sql` e `init_db.py`.
- La app ya no corre `create_all` al arrancar: hay que correr `alembic upgrade head` antes (Docker Compose lo hace con el servicio `migrate`; en Cloud Run, el job `empleoia-migrate-<env>`).
- Los modelos de `connection_requests`, `networking_exclusions` y `processed_files` suman `user_id` y los únicos por cuenta que ya tenía la base; `connection_requests.status` acepta `declined`.
- Nuevo test de drift (`tests_integration/test_schema.py`): en el CI compara la base migrada con los modelos, partiendo de una base vacía y de una creada con el script viejo. Falla si un modelo cambia sin su migración.

## [Sin publicar] - Caché de IA compartida y modelo barato para tareas simples

- La caché de respuestas de Gemini (temperatura ≤ 0.5, `AI_CACHE_TTL`) se guarda también en Redis cuando `RATELIMIT_STORAGE_URI` es `redis://`: una respuesta generada en una instancia de Cloud Run o en el worker sirve para las demás. Si Redis falla, sigue la caché en memoria.
- `GEMINI_LIGHT_MODEL` (por defecto `gemini-2.5-flash-lite`) se usa para extraer salarios y para asociar correos de Gmail a una empresa del tracker; esa clasificación pasa a temperatura 0 y queda en caché. Vacío = `GEMINI_MODEL`.
- `/api/ai/usage` suma `cache_hits`: llamadas del mes resueltas desde la caché.

## [Sin publicar] - Modelos `Mapped[...]` y SQLAlchemy 2.1

- Todos los modelos (`models.py`, `accounts.py`, `job_alerts.py`, `profile_store.py`, `two_factor.py`, `user_sessions.py`, `security_events.py`, `push.py`, `integrations.py`) usan `DeclarativeBase` y `Mapped[...] = mapped_column(...)` en vez de `declarative_base()` y `Column`. El esquema que generan es idéntico (mismas columnas, nulos, índices y defaults).
- SQLAlchemy sube de 2.0.57 a 2.1.8. `models.py`, `accounts.py`, `push.py` e `integrations.py` pasan a revisarse con mypy.
- `session.query(Model).get(id)`, obsoleto, pasa a `session.get(Model, id)`.

## [Sin publicar] - Medición de la calidad del matching

- `eval/matching_dataset.json`: 6 CVs y 12 ofertas etiquetadas a mano (2 = buena opción, 1 = parcial).
- `matching_eval.py` y `python scripts/eval_matching.py [--min-ndcg X] [--json]`: ordenan las ofertas de cada CV con `jobMatcher.calculate_overall_match` y miden NDCG@5, precisión@3 y MRR. Con `MATCHING_BACKEND=embeddings` mide el matching por embeddings.
- `tests_integration/test_matching_eval.py` falla si un cambio baja las métricas de la línea base con TF-IDF (corre con sklearn real en el job de integración).

## [Sin publicar] - Computrabajo, Bumeran y ZonaJobs en Playwright

- Computrabajo, Bumeran y ZonaJobs usan Chromium de Playwright sin ventana (`scrapers/common.Browser`) en vez de Selenium: no hace falta Chrome ni Xvfb. `SCRAPER_HEADLESS=false` abre la ventana y `PLAYWRIGHT_WS_ENDPOINT` usa un navegador remoto; `SELENIUM_URL` ya no aplica a estos portales.
- Se borra `scrapers/linkedin_scraper.py` (Selenium, sin uso: la búsqueda de LinkedIn ya corre en `linkedin_pw.py`); sus helpers de experiencia y ciudadanía pasan a `linkedin_pw`.
- Fix: al reintentar el login de LinkedIn o terminar la búsqueda se cerraba `scraper.driver`, que el scraper de Playwright no tiene; ahora se cierra el navegador con `close()`.
- Indeed y las solicitudes de conexión de LinkedIn siguen en Selenium.

## [Sin publicar] - app.py partido en servicios

- `app.py` queda en ~90 líneas: arma la web y un `AppServices` tipado. La lógica pasa a `services/`: `profiles.py` (perfiles y CV), `portal_search.py` (Indeed y LinkedIn), `connections.py` (solicitudes de LinkedIn), `probe_tasks.py` (pruebas de scrapers) y `state.py` (`job_status`, parser y matcher).
- Las páginas usan `fastapi_web.services_for(request)` en vez del diccionario de globals de `app.py`; el worker y `scraping_jobs.py` ya no importan `app`.

## [Sin publicar] - Aviso cuando un portal deja de devolver ofertas

- Cada búsqueda anota su resultado por portal (`ok`, `empty`, `error`) en el storage compartido (`RATELIMIT_STORAGE_URI`), así cuentan también las del worker y las alertas de empleo. `/metrics` lo expone como `empleoia_scraper_runs_total{portal,outcome}`.
- Alerta `EmpleoIAPortalSinOfertas`: un portal con 3 o más búsquedas en 24 h y ninguna con ofertas (cambió el HTML o bloquea al scraper). Con test de `promtool`.
- Tests de los helpers de texto de Indeed y LinkedIn con una descripción guardada.

## [Sin publicar] - Términos, Privacidad y permiso para usar la IA

- Páginas públicas `/terms` y `/privacy` en español, inglés y portugués, enlazadas desde el login, el registro y el pie de cada página. `LEGAL_OPERATOR_NAME` y `LEGAL_CONTACT_EMAIL` (por defecto `ADMIN_EMAIL`) completan los textos; revisalos con un abogado antes de abrir el registro.
- Crear una cuenta exige aceptar los Términos y la Privacidad (`users.terms_accepted_at`); entrar por primera vez con Google lo acepta, como avisa el login.
- Las funciones de IA (cartas, CVs, Copilot, entrevista, parseo del CV y embeddings) no mandan nada a Gemini sin el permiso de la cuenta (`users.ai_consent_at`). Se da desde un aviso en todas las páginas o en Mi cuenta, y se puede quitar; sin permiso, el matching usa TF-IDF. Sin login (modo local) no hace falta.
- La exportación incluye las fechas de aceptación y del permiso. Migración `0014_legal_consent`.

## [Sin publicar] - Cabeceras de seguridad y accesibilidad en todas las páginas

- Todas las respuestas llevan CSP con nonce por pedido (sin `'unsafe-inline'` en scripts), `X-Content-Type-Options`, `X-Frame-Options: DENY`, `Referrer-Policy`, `Permissions-Policy` y `Cross-Origin-Opener-Policy`; HSTS solo bajo HTTPS (`X-Forwarded-Proto` o `SESSION_COOKIE_SECURE=1`). `CSP_REPORT_ONLY=1` solo informa y `CSP_REPORT_URI` recibe los reportes.
- Se quitan los `onclick`/`onchange` del HTML: `static/js/actions.js` los reemplaza con `data-onclick` y `data-confirm`. Bootstrap, sus íconos y Chart.js se cargan con versión fija e integridad (SRI).
- La respuesta del Copilot se escapa antes de mostrarla y la tabla de un CSV ya no arma HTML con sus datos (evita XSS).
- `/docs` y `/openapi.json` quedan apagados salvo `ENABLE_API_DOCS=1`.
- axe revisa todas las páginas (antes 7); se corrigen contrastes y barras de progreso sin nombre en búsquedas, conexiones, entrevista y Administración.
- Arreglos: `/connections`, excluir empresas y guardar postulaciones daban 500 (faltaba `db_manager`); búsqueda en lote sin archivos tiraba un error de JavaScript.

## [Sin publicar] - Sin Flask (6/6)

- Se quitan Flask, Flask-WTF, Flask-Limiter y pytest-flask. `web_settings.py` guarda la config (`SECRET_KEY`, `MAX_UPLOAD_MB`, cookies) y firma la cookie `session` con el mismo formato que Flask: las sesiones y los tokens CSRF abiertos antes siguen valiendo.
- Los límites de las páginas (login, registro, Mi cuenta, Administración) usan `rate_limit.py` (librería `limits`, `RATELIMIT_STORAGE_URI`), igual que las APIs.
- Una página que no existe muestra la página de error 404; un 500 ya no muestra el error interno; `/api/*` sigue respondiendo JSON.
- Las métricas de Prometheus etiquetan solo con rutas de FastAPI.

## [Sin publicar] - Páginas de Flask a FastAPI (5/6): búsquedas y conexiones

- FastAPI sirve el arranque de las búsquedas, la prueba de scrapers y las solicitudes de conexión (`routers/scraper_pages.py`); las tareas de Computrabajo, Bumeran y universal pasan a `scraping_jobs.py`. Se quita la carpeta `web/`: Flask ya no tiene vistas.
- `/test_task_status` solo acepta un UUID (antes leía cualquier `.json` con `../`) y solo muestra pruebas de la cuenta.
- `/run_test_scraper` limita `max` a 20 y los errores ya no muestran el mensaje interno.

## [Sin publicar] - Páginas de Flask a FastAPI (4/5): resultados, documentos, perfiles y alertas

- FastAPI sirve ver/descargar/borrar resultados, empresas y conexiones, `/api/save_applications`, cartas y CV optimizado, puntaje ATS, perfiles de CV (subida hasta `MAX_UPLOAD_MB`) y alertas (`routers/content_pages.py`).
- Borrar un CSV ahora es un POST con CSRF (antes un GET) y solo borra `.csv` de la carpeta de la cuenta.
- Los avisos de error ya no muestran el error interno.
- `tracker_stats.py` reemplaza a `web/analytics.py` (se quita la vista vieja de `/analytics`, que ya servía FastAPI).

## [Sin publicar] - Páginas de Flask a FastAPI (3/5): Mi cuenta, Administración y exportación

- FastAPI sirve Mi cuenta (integraciones, contraseña, sesiones, segundo factor, exportar y borrar), `/admin` y `/export/*` (`routers/account_pages.py`), con los mismos límites por cuenta, CSRF y `Cache-Control: no-store`.
- `tracker_export.py` arma los Excel/PDF sin depender del framework. Si la exportación falla, el aviso ya no muestra el error interno.
- Se quitan `web/account.py`, `web/admin.py`, `web/second_factor.py` y `web/exports.py`.

## [Sin publicar] - Páginas de Flask a FastAPI (2/5): login y cuentas

- FastAPI sirve login, registro, salir, recuperar contraseña, verificar email, verificación en dos pasos y login con Google (`routers/auth_pages.py`), con los mismos límites por IP, email y login pendiente, CSRF y `Clear-Site-Data`.
- `account_notify.py` (emails y eventos de seguridad) y `google_oauth.py` (OAuth con PKCE) no dependen del framework: los usan Flask y FastAPI.
- Nueva dependencia `python-multipart` para leer formularios en FastAPI.

## [Sin publicar] - Páginas de Flask a FastAPI (1/5)

- `fastapi_web.py`: sesión, CSRF, avisos (`flash`) y `url_for` para páginas servidas por FastAPI, compatibles con la cookie de Flask (no hace falta volver a entrar).
- FastAPI sirve `/`, `/scraper`, `/results`, `/profile`, `/mock-interview`, `/tracker`, `/lang/<code>` y `/sw.js` (`routers/pages.py`). Sin sesión redirigen a `/login`.
- `main.create_app(flask_app)` arma la app; los tests usan la app completa (FastAPI + Flask) como en producción.

## [Sin publicar] - Python 3.12 y dependencias

- Python 3.12 en todo el proyecto (CI, Docker, Ruff `py312`, mypy); los 385 tests unitarios pasan en 3.12.
- `requirements.txt` con versiones exactas (antes había 25 sin fijar) y el job de tests del CI usa las mismas. SQLAlchemy queda en 2.0.57: la 2.1 rompe los tipos de mypy con los modelos `Column` actuales.
- Playwright 1.55 → 1.65.1 (imagen `mcr.microsoft.com/playwright/python:v1.65.1-noble`). Con esta versión Locust ya no choca con el `greenlet` de Playwright.
- Se quitan dependencias que nada importaba: `waitress`, `nltk`, `Flask-SQLAlchemy` y `APScheduler`.
- `pip-audit` sin vulnerabilidades conocidas.

## [Sin publicar] - Privacidad y seguridad de cuentas

- **Interfaz en inglés y portugués** (`i18n.py`, `translations/en.json`, `translations/pt.json`): selector de idioma en la barra y en las pantallas de ingreso (cookie `lang`, si no `Accept-Language`). Traducidos la barra, el Copilot, inicio, ingreso/registro/recuperación, verificación en dos pasos, Mi cuenta, Administración, errores, mensajes flash y eventos de seguridad. Lo no traducido sigue en español; un test exige que cada texto marcado con `_()` tenga traducción.
- **Panel de administración** (`web/admin.py`, `/admin`, migración `0013_user_disabled`): para la cuenta de `ADMIN_EMAIL` (o la primera). Cuentas con alta, última actividad, segundo factor y tokens de IA del mes; bloquear/desbloquear (`users.disabled_at`: corta login con contraseña y Google, sesiones, token de la extensión y avisos periódicos), quitar el segundo factor y borrar la cuenta (estas dos piden la contraseña del administrador). Todo queda en los eventos de seguridad.
- **Verificación en dos pasos** (`two_factor.py`, `web/second_factor.py`, migración `0012_user_totp`): en **Mi cuenta** se activa con una app autenticadora (QR o clave). Después de la contraseña, o de entrar con Google, se pide el código en `/login/2fa`; un código ya aceptado no vale de nuevo. Hay 10 códigos de recuperación de un uso (guardados como hash, se pueden regenerar). El secreto se guarda cifrado con `CV_ENCRYPTION_KEY` si está definida. Desactivar pide contraseña y código. El ZIP de exportación no incluye el secreto.
- **Límites por cuenta** (`rate_limit.py`): con sesión, los límites de Flask-Limiter, la cuota de IA (`AI_RATE_LIMIT`) y el nuevo `API_RATE_LIMIT` (300/min para todo `/api/*`) cuentan por cuenta; sin sesión, por IP. El login suma un límite por email (20 por hora) y la recuperación de contraseña otro (5 por hora), así probar contraseñas desde muchas IPs también se corta. `TRUSTED_PROXY_HOPS` toma la IP real de `X-Forwarded-For` (Terraform lo pone en 1 para Cloud Run); antes, detrás del proxy, todos los usuarios compartían el mismo límite por IP. Los eventos de seguridad y las sesiones guardan esa IP real.
- **Sesiones abiertas** (`user_sessions.py`, migración `0011_user_sessions`): cada login guarda una fila (hash del id de sesión, IP, navegador, última actividad). La cookie lleva el id y `auth.session_user_id` exige que la fila siga abierta, así una sesión cerrada desde **Mi cuenta** deja de valer también en las APIs de FastAPI. Salir cierra la fila; cambiar o recuperar la contraseña cierra todas. **Las sesiones anteriores a esta versión dejan de valer: hay que volver a entrar una vez.**
- **Eventos de seguridad** (`security_events.py`, migración `0010_security_events`): cada cuenta registra logins, contraseñas incorrectas, registro, verificación, cambios y recuperación de contraseña, Telegram, Gmail, token de la extensión y exportaciones; se ven en **Mi cuenta** → Actividad reciente. Un login desde un navegador no visto en 180 días manda un email de aviso (`LOGIN_ALERTS`). La retención diaria borra los eventos con más de `SECURITY_EVENTS_DAYS` días. Borrar la cuenta borra sus eventos.
- `accounts.delete_account` y `claim_orphans` inspeccionan las tablas antes de escribir (en SQLite la inspección descartaba los borrados pendientes).
- **Exportar mis datos** (`data_export.py`, `POST /account/export`): ZIP con todo lo que la app guarda de la cuenta (tablas propias en JSON, perfiles, CVs originales, CSV de resultados y documentos generados). Pide la contraseña, tiene límite de 5 por hora, se sirve con `Cache-Control: no-store` y deja afuera hash de contraseña, tokens y endpoints push.

## [Sin publicar] - Notificaciones push

- Web Push con VAPID (`push.py`, `/api/push/*`, tabla `push_subscriptions`): cada cuenta suscribe sus dispositivos en **Mi cuenta** y recibe las alertas (canal `push`) y los recordatorios de seguimiento. Los endpoints se limitan a servicios de push conocidos (`PUSH_ALLOWED_HOSTS` agrega otros) y los que el servicio da de baja (404/410) se borran solos.
- Una suscripción push es de la cuenta que la activó en ese navegador: al salir o al entrar con otra cuenta se da de baja, y la cuenta nueva tiene que activarla en **Mi cuenta**.
- Íconos de la PWA (`static/icons/`), que el manifest pedía y no existían.


- Reglas de alerta de Prometheus en `monitoring/prometheus/alerts.yml` (5xx, latencia p95, sin métricas, cola de Celery, cuota de IA al 80 % y agotada), con tests de `promtool` en el CI.
- `terraform/monitoring.tf`: uptime check de `/api/health` y alertas de Cloud Monitoring (5xx, p95, disco de Cloud SQL), por email con `alert_email`.
- Prueba de carga con Locust (`loadtest/locustfile.py`, `requirements-loadtest.txt`) que falla si el p95 o los errores superan el objetivo; línea base en `docs/load-testing.md`.

## [Sin publicar] - Cuentas e integraciones por cuenta

- Limpieza de código muerto: Flask-SocketIO, eventlet y el WebSocket `/ws` (ninguna página los usaba), `routers/views.py` y `routers/scraping.py` (no se montaban), `job_precheck.py` (stubs que siempre aprobaban), tareas de Celery que nadie encolaba (`batch_analyze_jobs`, `batch_generate_cover_letters`, `export_tracker_to_excel`), funciones de IA y salarios sin uso, la tabla heredada `job_tracker` (ya no se crea; el tracker usa `applications`) y `scripts/test_bumeran.py`/`test_linkedin.py`. `CORS_ALLOWED_ORIGINS` ya no se usa.
- Un lote de cartas o CVs que estaba generándose cuando se borró la cuenta se corta y no vuelve a crear sus archivos.

- Resultados del scraping (CSV), documentos generados y progreso de búsquedas separados por cuenta (`results/u<id>`, `GENERATED_DIR/u<id>`); los archivos previos pasan a la primera cuenta.
- `AI_USER_MONTHLY_TOKEN_LIMIT`: tope mensual de tokens de IA por cuenta, además del tope total `AI_MONTHLY_TOKEN_LIMIT`.
- Historial de estados del tracker (`application_status_history`, migración `0006_status_history`); el embudo y los días hasta postular lo usan.
- "Mi cuenta": cambiar la contraseña (cierra las otras sesiones), recuperar la contraseña por email (enlace de 1 hora y un solo uso), verificar el email (`REQUIRE_EMAIL_VERIFICATION`, migración `0007_email_verification`) y borrar la cuenta. Los enlaces usan `PUBLIC_BASE_URL`.
- Integraciones por cuenta (`user_integrations`, migración `0008_user_integrations`): chat de Telegram, token de la extensión de Chrome (solo se guarda el hash, revocable) y Gmail conectado por OAuth web (token cifrado con `CV_ENCRYPTION_KEY`). `TELEGRAM_CHAT_ID`, `EXTENSION_TOKEN` y `token.json` quedan como los de la primera cuenta hasta que los cambie o desconecte.

## [Sin publicar] - Multiusuario

- Cuentas con email y contraseña (hash de Werkzeug) en la tabla `users` (migración `0005_users`); reemplazan a `APP_PASSWORD`.
- La primera cuenta se crea en `/register` (con `ADMIN_EMAIL`, solo con ese email) y se queda con los datos previos; después el registro requiere `ALLOW_SIGNUP=true`.
- `user_id` en tracker, perfiles, alertas, ofertas vistas, exclusiones, solicitudes y archivos procesados: cada cuenta ve y modifica solo lo suyo. Los índices únicos pasan a ser por usuario.
- El usuario se propaga a Flask, FastAPI, threads y tareas de Celery; las tareas periódicas (alertas, recordatorios, retención) corren una vez por cuenta.
- "Borrar mis datos" borra solo los perfiles y CVs de la cuenta. Telegram, Gmail y `EXTENSION_TOKEN` son de la primera cuenta.
- `LOGIN_REQUIRED=false` desactiva el login (solo uso local). Terraform: `admin_email` reemplaza a `app_password`.

## [Unreleased]

### Cambiado
- `db_config.DatabaseManager` usa el engine SQLAlchemy de `models.py` (un solo pool para tracker, perfiles y alertas) en lugar de su pool propio de `mysql.connector`; las consultas y los valores devueltos no cambian.
- Las APIs de documentos (`/api/batch_cover_letters`, `/api/batch_optimize`, `/api/documents/tasks/<id>`, `/api/ats_score`, `/api/optimize_resume`) pasan a FastAPI (`routers/documents.py`); las páginas siguen en Flask. `/api/optimize_resume` y `/api/save_applications` ya no devuelven el mensaje interno del error.
- La API de IA (`/api/ai/*`), notificaciones y `/api/salary/analyze-csv` pasan a FastAPI (`routers/ai.py`); se elimina `web/ai_api.py`. El copiloto vuelve a recibir los conteos del tracker, `/api/salary/analyze-csv` ya no lee archivos fuera de `results/` y los errores de IA no devuelven el mensaje interno.
- `/api/tracker/stats`, `/api/analytics/advanced`, `/api/get_applications`, `/api/all_profiles`, `/api/profile_summary` y `/api/ranking` pasan de Flask a FastAPI (`routers/insights.py`), con el mismo login y formato de error que la API del tracker; los errores internos ya no devuelven el mensaje de la excepción.

### Agregado
- Ranking personal (`job_ranking.py`): Naive Bayes entrenado con el tracker (postuladas vs. guardadas sin postular) que reordena las alertas y los resultados de búsqueda, con columna "Afinidad" y `/api/ranking` para ver qué aprendió.
- Extensión de Chrome lista para el Web Store: íconos y `content.css` que faltaban (Chrome no la cargaba), permiso `contextMenus` (el service worker fallaba al registrarse), botones del popup sin `onclick` inline (la CSP de MV3 los bloqueaba), soporte de ZonaJobs, GetOnBoard y `computrabajo.com.ar`, datos desde JSON-LD, permisos de host mínimos con acceso opcional al servidor configurado, `scripts/package_extension.py` y tests estáticos y E2E con la extensión cargada en Chromium.
- Métricas Prometheus en `/metrics` (protegidas con `METRICS_TOKEN`): pedidos y latencia por ruta, tokens de Gemini, consumo mensual de IA y tareas esperando en cada cola de Celery. Trazas OpenTelemetry opcionales para la web, el worker y las llamadas HTTP salientes (`OTEL_EXPORTER_OTLP_ENDPOINT`). Ver `docs/observability.md`.
- `AI_BACKEND=celery`: las cartas y los CVs adaptados en lote se generan en el worker (cola `ai_processing`) y la página muestra el progreso consultando `/api/documents/tasks/<id>`. Los documentos se guardan en `GENERATED_DIR`, que en GCP es el bucket de resultados compartido por la web y el worker.
- Perfiles cifrados en MySQL y en el JSON de respaldo con `CV_ENCRYPTION_KEY` (incluye el texto extraído del CV). Los perfiles en texto plano se siguen leyendo y la tarea diaria de privacidad los cifra.
- `/analytics`: rendimiento por portal (guardadas, postulaciones, respuestas y tasa de respuesta) y días promedio entre guardar y postular.
- Verificación mensual de restauración de backups de Cloud SQL (`scripts/verify_backup_restore.sh`, `backup-restore-check.yml`, `docs/backup-restore.md`).
- CI: accesibilidad con axe-core (WCAG 2.1 AA, sin violaciones serias ni críticas) y Lighthouse (accesibilidad >= 90, buenas prácticas >= 75).

### Seguridad
- `/view/<archivo>` escapa el título, la empresa y el enlace de las ofertas scrapeadas: antes se insertaban como HTML.
- Auto-Apply de LinkedIn apagado por defecto (`AUTO_APPLY_ENABLED`), sin envío salvo `AUTO_APPLY_SUBMIT=true`, limitado a 10 URLs `https://*.linkedin.com/jobs/`, con tope de pasos en el formulario y el token tomado del entorno en vez del mensaje de Celery.

### Corregido
- `tasks/gmail_tracker.py` usaba `trackerDbClass`, `fetch_all_tracked` y `move_to_stage`, que no existen; ahora mueve la postulación a `interviewing`, y una respuesta vacía de Gemini ya no marca todas las empresas.
- Lotes de cartas y CVs: el nombre del archivo ya no permite leer fuera de `results/`, la cantidad se limita a 50 ofertas, los errores no exponen mensajes internos y la tabla de resultados ya no interpreta como HTML los títulos y empresas de los portales.
- Contraste insuficiente en el indicador Online/Offline, botones outline, textos secundarios y KPIs de Analytics; el botón "Salir" era invisible (blanco sobre blanco).
- Botón de refrescar perfiles sin nombre accesible y columnas del tracker con scroll no alcanzables con teclado.
- `/api/analytics/advanced` ya no devuelve el mensaje interno de la excepción.

### Agregado
- API JSON del tracker (`/api/tracker/jobs`, `/api/tracker/job/...`, `/api/tracker/save-from-extension`) migrada de Flask a FastAPI (`routers/tracker.py`) con modelos Pydantic. Usa la misma cookie de sesión y el mismo token CSRF de Flask; los errores internos ya no devuelven el mensaje de la excepción.
- Portales ZonaJobs (reutiliza el parser de Bumeran) y GetOnBoard (API JSON pública) en búsqueda universal, alertas y monitor de scrapers. El parser de Bumeran ya no toma "Apto discapacidad" como empresa.
- Puntaje ATS sin IA (`ats_score.py`): página en `/optimize_resume` y `POST /api/ats_score`.
- Recordatorios del tracker: fecha de seguimiento, fecha límite y notas editables (`PUT /api/tracker/job/<id>/reminder`), aviso diario único por email o Telegram que no se repite (`last_reminder_at`, migración `0004_tracker_reminders`) y `FOLLOWUP_DAYS` para postulaciones sin fecha.
- Infraestructura GCP reescrita (`terraform/`): la configuración anterior no pasaba `terraform validate`. Ahora hay staging y prod con estado separado en GCS, Cloud SQL con backups diarios, PITR e IP privada vía Private Services Access, worker de Celery en Cloud Run worker pool, job de migraciones de Alembic, bucket privado para los CVs, cuenta de servicio con acceso solo a sus secretos y egress `PRIVATE_RANGES_ONLY` (con `ALL_TRAFFIC` y sin Cloud NAT no había salida a internet). Workflows `Terraform` (fmt, validate, `terraform test`) y `Deploy a GCP` (staging en cada push a `main`, prod manual, plan en PRs).
- Privacidad de CVs: con `CV_ENCRYPTION_KEY` los CVs de `uploads/` se guardan cifrados (Fernet) y los parsers leen una copia temporal descifrada. Una tarea diaria de Celery cifra los CVs viejos y, con `CV_RETENTION_DAYS`, borra los CVs vencidos, sus perfiles y los documentos generados. Botón "Borrar mis datos" en `/profile` (Ley 25.326), que ahora borra los perfiles de todos los roles.
- Tests de integración (`tests_integration/`, job de CI `integration`) contra MySQL 8 y Redis reales, y E2E con Playwright de login, subida de CV y tracker. Se corren con `INTEGRATION=1 python -m pytest tests_integration`.
- Matching semántico opcional (`MATCHING_BACKEND=embeddings`): la similitud de texto CV-oferta usa embeddings de Gemini (`gemini-embedding-001`) con caché en memoria y cuenta en el tope mensual de tokens. Si la IA falla o no está configurada, sigue con TF-IDF.
- Alertas de empleo (`/alerts`): búsquedas guardadas en Computrabajo y Bumeran que Celery Beat revisa cada `ALERTS_INTERVAL_HOURS` y avisan por email o Telegram solo con ofertas nuevas. La misma oferta en dos portales se avisa una vez (huella de título + empresa en `seen_jobs`) y se puede exigir un match mínimo con el CV. Migración Alembic `0002_job_alerts`.
- `SCRAPER_BACKEND=celery`: las búsquedas de la web (Indeed, LinkedIn, Computrabajo, Bumeran y universal) corren en el worker de Celery con el mismo código y el progreso se ve igual en `/status`. Por defecto siguen en un thread. Docker Compose ya usa Celery.
- Lint con Ruff (pyflakes + bugbear) y mypy sobre los módulos nuevos (`pyproject.toml`), en CI y en `.pre-commit-config.yaml` (con gitleaks). Se limpiaron 111 avisos: imports y variables sin uso, f-strings vacíos y redefiniciones.
- `resume_parser` suma sus llamadas a Gemini al contador mensual y respeta `AI_MONTHLY_TOKEN_LIMIT`.
- Control de costos de IA: cada llamada a Gemini suma sus tokens al mes en curso (compartido vía `RATELIMIT_STORAGE_URI`), `AI_MONTHLY_TOKEN_LIMIT` corta las llamadas al llegar al tope y `GET /api/ai/usage` muestra el consumo y el costo estimado.
  Las respuestas con temperatura ≤ 0.5 se cachean `AI_CACHE_TTL` segundos.
- Monitor diario de scrapers (`scripts/scraper_health.py` + workflow `Monitor de scrapers`): busca en Computrabajo y Bumeran y abre un issue si alguno no devuelve ofertas.
- Página `/optimize_resume` (antes daba 500 porque faltaba la plantilla) y enlace "Optimizar CV" en el menú.

### Corregido
- Tracker: `applications.status` acepta los estados del kanban (`bookmarked`, `applying`, `negotiating`); antes MySQL rechazaba esas altas. Migración Alembic `0003_tracker_status`.
- Modo offline: el service worker se sirve en `/sw.js` (antes `/static/sw.js` no podía tomar el scope `/` y nunca se registraba). Los assets son network-first, así un deploy nuevo se ve sin limpiar caché, y `/login` y `/logout` envían `Clear-Site-Data` para que sin sesión no queden páginas ni datos del tracker guardados en el navegador.
- Se quitaron de `base.html` `css/main.css` y `js/main.js`, que no existen y daban 404 en todas las páginas.

### Cambiado
- `/delete_profile` ("Borrar mis datos") solo acepta POST con CSRF; antes un GET borraba todo.
- `app.py` pasó de ~3.080 a ~820 líneas: las rutas se movieron a `web/` (un módulo por área) sin cambiar URLs, endpoints, login, CSRF ni rate limit.
- UI: todo en español (panel de métricas, asistente Copilot) y se eliminaron las plantillas sin uso `view_jobs.html` y `view_file_original.html` (UTF-16, ~18k líneas).
- Accesibilidad: enlace "Saltar al contenido", landmark `<main>`, `aria-label` en la navegación, el botón de menú, los botones de cerrar y en los 32 campos de formulario sin etiqueta asociada.
- Scrapers de Computrabajo y Bumeran: el parseo de tarjetas pasa a `parse_listing(html)` (BeautifulSoup) con tests sobre HTML guardado en `tests/fixtures/`.
  La carga de páginas usa `get_with_retries` (3 intentos con espera exponencial) y timeout de página `SCRAPER_PAGE_TIMEOUT` (30 s).
- El salario de Computrabajo se toma del primer elemento con `$`/`ARS` (antes casi siempre quedaba "Not specified").
- `JobMatcher.calculate_overall_match` tolera perfiles sin `raw_text`/`experience_years`; `test_resume_parser.py` vuelve a correr en CI, con cobertura mínima de 20%.
- Los perfiles de CV por rol se guardan en MySQL (tabla `user_profiles`) en vez de `profiles/user_profiles.json`.
  La primera vez que la app conecta a MySQL importa el JSON existente y lo renombra a `.migrated`.
  Sin MySQL (o con `PROFILE_STORAGE=json`) se sigue usando el JSON.
- Primera migración de Alembic (`alembic upgrade head`); se eliminó `utils.py`, que duplicaba la lógica de perfiles y no se usaba.

### Planeado
- Auto-Apply: Postulación automática a trabajos "Easy Apply" de LinkedIn con Playwright
- Email Tracking: Detección de respuestas vía Gmail/Outlook API
- API REST Pública con FastAPI y documentación OpenAPI/Swagger
- Gamificación: Sistema de logros y estadísticas personales
- Mobile App: Aplicación nativa iOS/Android

### ⚙️ Mantenimiento
- Migración de `google-generativeai` (sin soporte) a `google-genai`; modelo configurable con `GEMINI_MODEL` (por defecto `gemini-2.5-flash`).
- Rate limit en `/api/ai/*` con Flask-Limiter (`AI_RATE_LIMIT`), límite de upload configurable (`MAX_UPLOAD_MB`) y respuesta 413 amigable.
- `/api/health` también disponible en Flask; `LOG_LEVEL` y Sentry opcional (`SENTRY_DSN`).
- Imagen Docker y Playwright 1.55 (Ubuntu noble, Python 3.12); CI en Python 3.12 para todos los PRs.
- CI: job de seguridad (Bandit, pip-audit, Gitleaks) y Dependabot semanal para pip, Actions y Docker.

### 🔐 Seguridad
- Login de usuario único con `APP_PASSWORD` (Flask y rutas FastAPI), rate limit en `/login`, logout por POST y cookies `SameSite=Lax`.
- Protección CSRF (Flask-WTF) en todos los formularios y `fetch` same-origin; la extensión de Chrome usa `EXTENSION_TOKEN`.
- Terraform: `APP_PASSWORD` como secreto obligatorio del Cloud Run público.
- `python app.py` ahora escucha en `127.0.0.1` con debug desactivado; se configura con `FLASK_HOST`, `FLASK_PORT` y `FLASK_DEBUG`.
- `SECRET_KEY` se lee del entorno (si falta, se usa una clave temporal aleatoria). CORS de WebSockets limitado por `CORS_ALLOWED_ORIGINS`.
- `/debug/directories` responde 404 fuera de modo debug.
- Subida de CV: solo PDF/DOCX/TXT y nombre de archivo sanitizado (evita path traversal).
- Token de Gmail guardado como `token.json` en lugar de `pickle`.
- `docker-compose.yml`: MySQL, Redis y Flower publicados solo en `127.0.0.1`. `init_db.py` ya no trae contraseña por defecto.

### 🔧 Correcciones Recientes de Entorno (Local/Docker)
- 🐛 **Dockerfile Oficial**: Creación de `Dockerfile` principal asado en `mcr.microsoft.com/playwright/python:v1.42.0-jammy` listo para correr Selenium y Playwright, solventando problemas con C++ Build Tools en host.
- 🐛 **Resolución de Puertos MySQL**: Modificado `docker-compose.yml` para exponer MySQL en el puerto `3307` del host, evitando el choque `bind: Only one usage of each socket address` con instalaciones locales.
- 🐛 **Dependencias Omitidas**: Añadidos dinámicamente `undetected-chromedriver`, `selenium` y `webdriver-manager` a `requirements.txt` tras rastrear `ModuleNotFoundError` que pausaba el contenedor `web`.

---

## [3.0.0] - 2025-04-12 — EmpleoIA Enterprise 🚀

### 🤖 AI Engine (NEW)
- ✨ **AI Engine Centralizado** (`ai_engine.py`): Motor de IA usando Google Gemini para análisis semántico, reescritura de CVs, chat copilot y insights de mercado
- ✨ **AI Copilot Sidebar**: Chat lateral disponible en todas las páginas con base.html, powered by Gemini, con quick actions y typing indicator animado
- ✨ **Mock Interviews** (`/mock-interview`): Entrevistas simuladas con IA — preguntas personalizadas por rol/dificultad, timer opcional, evaluación STAR, feedback con puntaje y respuesta mejorada, reporte descargable
- ✨ **Análisis Completo de Ofertas** (`/api/ai/analyze-job`): Cultura de empresa, skills match, salario estimado, red flags, red flags y resumen ejecutivo
- ✨ **Reescritura de CV** (`/api/ai/rewrite-bullet`): Mejora bullet points del CV para hacer match con una oferta específica
- ✨ **Plan de Aprendizaje** (`/api/ai/learning-path`): Genera ruta personalizada de skills faltantes para una posición target
- ✨ **Insights de Mercado** (`/api/ai/market-insights`): Salarios, demanda y tendencias por rol y nivel con caché de 7 días

### ⚡ Arquitectura Asíncrona (NEW)
- ✨ **Celery + Redis** (`celery_app.py`): Arquitectura asíncrona completa — scraping en background sin bloquear la app web
- ✨ **Colas especializadas**: `scraping` (alta prioridad), `ai_processing`, `notifications`
- ✨ **Tareas programadas** (Celery Beat): Follow-up reminders automáticos y limpieza de temporales
- ✨ **Flower Dashboard**: Monitor de tareas Celery disponible en `localhost:5555`
- ✨ **tasks/ai_tasks.py**: Análisis IA por lotes, exportación Excel asíncrona, limpieza de temporales
- ✨ **tasks/notification_tasks.py**: Envío de emails asíncrono (follow-ups, digests, resúmenes semanales)
- ✨ **tasks/scraping_tasks.py**: Scraping de Indeed, LinkedIn, Bumeran y Computrabajo como tareas Celery

### 🗄️ Base de Datos (MEJORADO)
- ✨ **SQLAlchemy ORM** (`models.py`): Modelos completos — Application, ConnectionRequest, MarketInsight, MockInterview, UserSettings
- ✨ **SQLAlchemyManager**: Wrapper compatible con db_config.py para migración gradual
- ✨ **Índices optimizados**: Para status, company, applied_date y overall_match
- ✨ **Connection pooling mejorado**: `pool_pre_ping=True`, `pool_recycle=3600`

### 🌐 Extensión de Chrome (NEW)
- ✨ **EmpleoIA Saver** (`chrome_extension/`): Extensión Manifest V3 para guardar ofertas con 1 click
- ✨ **Extractores por plataforma**: LinkedIn, Indeed, Bumeran, Computrabajo con fallback genérico
- ✨ **Auto-extracción**: La extensión extrae datos automáticamente al abrir el popup
- ✨ **Context menu**: Click derecho → "Guardar en EmpleoIA" desde cualquier página
- ✨ **Toast de confirmación**: Indicador visual en la página cuando se guarda correctamente
- ✨ **Endpoint Flask** (`/api/tracker/save-from-extension`): Recibe datos de la extensión

### 📧 Notificaciones (NEW)
- ✨ **NotificationManager** (`notifier.py`): Manager de alto nivel con fallback Celery → SMTP directo
- ✨ **Templates HTML premium**: Emails en dark mode con gradientes y formato responsive
- ✨ **Follow-up reminders**: Alertas automáticas para postulaciones con fecha de seguimiento vencida
- ✨ **Digest de nuevas ofertas**: Email semanal con las mejores ofertas encontradas
- ✨ **Resumen semanal**: Estadísticas de actividad: postulaciones, entrevistas, tasa de respuesta
- ✨ **Test de configuración** (`/api/notifications/test`): Verifica la configuración SMTP enviando un email de prueba
- ✨ **API de notificaciones**: `/api/notifications/config`, `/api/notifications/test`, `/api/notifications/trigger-digest`

### 💰 Análisis Salarial (NEW)
- ✨ **market_analyzer.py**: Extracción de salarios con regex multi-patrón (USD, ARS, EUR)
- ✨ **Análisis de distribución**: Histograma, percentiles, estadísticas descriptivas por CSV
- ✨ **Ranking por empresa**: Top 20 empresas por salario promedio
- ✨ **Enriquecimiento de CSV**: Agrega columnas salary_min, salary_max, salary_avg, currency
- ✨ **API de salarios** (`/api/salary/analyze-csv`): Análisis salarial por CSV scrapeado

### 🏗️ Infraestructura (NEW)
- ✨ **Docker Compose completo** (`docker-compose.yml`): Flask + MySQL + Redis + Celery Worker + Celery Beat + Flower con healthchecks
- ✨ **Terraform para GCP** (`terraform/`): Cloud Run (Flask), Cloud SQL (MySQL 8.0), Memorystore (Redis), Artifact Registry, Secret Manager, VPC privada
- ✨ **Configuraciones de entorno**: Soporte completo dev/staging/prod en Terraform

### 📱 UI/UX (MEJORADO)
- ✨ **base.html unificado**: Navbar actualizada con entrada Mock Interviews
- ✨ **mock_interview.html**: Template completo con animaciones, timer, feedback modal slide-up y gráfico de resultados circular (Canvas API)
- ✨ **mock_interview.css**: Estilos premium dark mode con difficulty selector, mode selector, feedback modal animado y timer urgente pulsante

### 🔌 API Routes (NEW)
- ✨ `POST /api/ai/analyze-job` — Análisis completo de oferta laboral
- ✨ `POST /api/ai/copilot` — Chat con AI Copilot (Gemini)
- ✨ `POST /api/ai/rewrite-bullet` — Reescritura de bullet points del CV
- ✨ `POST /api/ai/interview/generate` — Generación de preguntas de entrevista
- ✨ `POST /api/ai/interview/evaluate` — Evaluación de respuestas de entrevista
- ✨ `GET/POST /api/ai/market-insights` — Insights salariales de mercado con caché
- ✨ `POST /api/ai/learning-path` — Plan de aprendizaje personalizado
- ✨ `POST /api/tracker/save-from-extension` — Guardado desde extensión de Chrome
- ✨ `POST /api/salary/analyze-csv` — Análisis salarial de CSV
- ✨ `GET /api/notifications/config` — Configuración de notificaciones
- ✨ `POST /api/notifications/test` — Prueba de configuración SMTP
- ✨ `POST /api/notifications/trigger-digest` — Envío manual de digest

### 📦 Dependencias Añadidas
- ✨ `celery[redis]>=5.3.0` — Task queue asíncrono
- ✨ `redis>=5.0.0` — Broker y backend de Celery
- ✨ `SQLAlchemy>=2.0.0` — ORM para MySQL
- ✨ `Flask-SQLAlchemy>=3.1.0` — Integración Flask-SQLAlchemy
- ✨ `alembic>=1.13.0` — Migraciones de base de datos
- ✨ `openpyxl>=3.1.0` — Exportación Excel premium

## [2.2.0] - 2025-12-10

### Added
- ✨ **LinkedIn Email/Password Login**: Nuevo método de autenticación con credenciales como alternativa principal al token `li_at`
- ✨ **Manejo de Verificación de Seguridad**: El scraper de LinkedIn ahora pausa 60s para verificaciones manuales (SMS, email)
- ✨ **Logs Mejorados**: Sistema de logging más detallado para debugging de scrapers

### Fixed
- 🐛 **Indeed Search Input**: Corregidos selectores CSS para entrada de título de trabajo en diferentes idiomas
- 🐛 **Indeed Google Login**: Eliminado texto basura en campo de email mediante limpieza manual con `Ctrl+A` + `Delete`
- 🐛 **Partial Results Path**: Resultados parciales de Indeed ahora se guardan correctamente en `results/` en lugar de la raíz
- 🐛 **Job Matching KeyError**: Corregida extracción de perfil de usuario que causaba crash al calcular matches
- 🐛 **LinkedIn Environment Variable**: Cambiado `LINKEDIN_TOKEN` a `LI_AT_TOKEN` para coincidir con la configuración de `.env`
- 🐛 **LinkedIn Redirect Loop**: Mejorada lógica de cookies para prevenir bucles infinitos de redirección
- 🐛 **Flask Port Conflict**: Implementado cleanup de procesos duplicados antes de reiniciar el servidor

### Changed
- 🔄 **LinkedIn Scraper Priority**: Email/password ahora es el método primario, token `li_at` como fallback
- 🔄 **Resume Parsing**: Sistema optimizado de extracción de habilidades y experiencia con algoritmos mejorados

## [2.1.0] - 2025-11-28

### Added
- ✨ **Super Botón de Acción**: Botón unificado "Postular y Seguir" que combina postulación, seguimiento y marcado como aplicado en un solo clic
- ✨ **Networking UI Premium**: Rediseño completo de la página de conexiones de LinkedIn con estilo moderno
- ✨ **Parsing Inteligente de CV**: Sistema avanzado de extracción automática de experiencia, habilidades y educación desde CVs
- ✨ **Scraper Universal Mejorado**: Opción "Otros" que ejecuta Computrabajo y Bumeran simultáneamente con seguimiento en tiempo real
- 🎨 **CSS Premium**: Nuevos archivos CSS dedicados para cada página (index, scraper, results, tracker, connections, view_file)

### Changed
- 🔄 **Estructura de Proyecto**: Limpieza de archivos no utilizados (8 archivos eliminados)
- 🔄 **README Actualizado**: Estructura de proyecto simplificada y más clara
- 🔄 **Imports Optimizados**: Removidos imports no utilizados de `app.py`

### Fixed
- 🐛 **Indeed Scraper**: Restaurado y corregido con módulo stub `job_precheck.py` para compatibilidad
- 🐛 **LinkedIn Scraper**: Restaurado desde git para mantener estabilidad
- 🐛 **Compatibilidad**: Creado módulo stub para mantener scrapers funcionando sin dependencias obsoletas

### Removed
- 🗑️ **Archivos Obsoletos**: Eliminados `custom.css`, `.env.backup`, `debug_resume_parser.py`, `list_models.py`
- 🗑️ **Módulos No Utilizados**: Removidos `simple_resume_optimizer.py`, `cover_letter_generator.py`, `MASTER_RESUME_PROMPT.py`
- 🗑️ **Rate Limiting**: Optimización de sistema de matching para evitar problemas de límites de API

## [2.0.0] - 2025-11-27

### Added
- ✨ **Dark Mode**: Tema oscuro completo con persistencia y toggle en barra de navegación
- ✨ **Filtros Dinámicos**: Búsqueda instantánea en tablas de resultados sin recarga
- ✨ **UI v2.0**: Rediseño completo de la interfaz con estilo moderno y consistente
- ✨ **Feedback Visual**: Nuevas animaciones, badges de estado y barras de progreso

### Fixed
- 🐛 **Base de Datos**: Optimización del pool de conexiones para evitar errores de "Too many connections"
- 🐛 **Estabilidad**: Corrección de estructura HTML base y scripts de carga
- 🐛 **Estilos**: Restauración y blindaje de archivos CSS críticos

### Changed
- 🔄 **Navegación**: Menú superior reorganizado y responsive
- 🔄 **Tablas**: Diseño más limpio y legible con acciones agrupadas

## [1.2.0] - 2025-11-27

### Added
- ✨ **Scraper Universal**: Ejecuta Computrabajo y Bumeran simultáneamente
- ✨ Consolidación de resultados en un solo CSV con columna "Fuente"
- ✨ Seguimiento en tiempo real del estado de cada scraper
- ✨ UI mejorada con badges de estado por plataforma
- ✨ Configuración automática de credenciales desde `.env` para LinkedIn

### Changed
- 🔄 LinkedIn token ahora se lee automáticamente del `.env`
- 🔄 Scraper Universal optimizado para solo Computrabajo y Bumeran

### Removed
- 🗑️ Eliminados scrapers de ZonaJobs y Jooble (problemas de compatibilidad)
- 🗑️ Archivos temporales de desarrollo limpiados

### Fixed
- 🐛 Corrección de errores en la lectura de credenciales
- 🐛 Mejoras en el manejo de errores del scraper universal

## [1.1.0] - 2025-11-26

### Added
- ✨ Soporte completo para **Bumeran** y **Computrabajo**
- ✨ Sistema de **Login Automático** para portales de empleo
- ✨ **Deep Scraping**: Extracción de enlaces directos de postulación ("Apply URL")
- ✨ Nuevo botón "Apply" en la interfaz de resultados
- ✨ Mejoras en la organización de archivos CSV exportados

### Fixed
- 🐛 Corrección de selectores CSS para Bumeran
- 🐛 Solución a problemas de carga dinámica con React
- 🐛 Manejo de errores 403 en login de Computrabajo

## [1.0.0] - 2025-01-25

### Added
- ✨ Plataforma completa de búsqueda de empleo
- ✨ Scraping de Indeed y LinkedIn
- ✨ Optimización inteligente de CVs con sistemas ATS
- ✨ Sistema de Job Tracker con Kanban board
- ✨ Generador automático de cartas de presentación
- ✨ Soporte para múltiples perfiles profesionales
- ✨ Bot de conexiones automáticas de LinkedIn
- ✨ Sistema de filtrado inteligente de empleos
- ✨ Optimización por lotes de currículums
- 📝 Documentación profesional completa
- 📝 README.md con badges y guías
- 📝 CONTRIBUTING.md con guías de contribución
- 📝 CHANGELOG.md para tracking de cambios

### Technical
- 🔄 Backend con Flask y Python 3.12
- 🔄 Base de datos MySQL
- 🔄 UI con Bootstrap 5.3
- 🔄 Integración con Google Gemini Pro API
- � Web scraping con Selenium

### Security
- 🔒 Implementación de gitignore para credenciales
- 🔒 Encriptación de tokens de LinkedIn
- 🔒 Sanitización de inputs de usuario
- 🔒 Gestión segura de API keys

---

## Tipos de Cambios

- `Added` - Nuevas funcionalidades
- `Changed` - Cambios en funcionalidades existentes
- `Deprecated` - Funcionalidades que serán removidas
- `Removed` - Funcionalidades removidas
- `Fixed` - Corrección de bugs
- `Security` - Cambios de seguridad

## Emojis Usados

- ✨ Nueva funcionalidad
- 🐛 Bug fix
- 🔒 Seguridad
- 🔄 Cambio/Actualización
- 📝 Documentación
- 🎨 UI/Estilo
- ⚡ Performance
- 🧪 Tests
- 🔧 Configuración
- 🗑️ Deprecación/Remoción
