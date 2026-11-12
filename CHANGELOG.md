# Changelog

Todos los cambios notables en este proyecto serán documentados en este archivo.

El formato está basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.0.0/),
y este proyecto adhiere a [Semantic Versioning](https://semver.org/lang/es/).


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
