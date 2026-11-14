# Changelog

Todos los cambios notables en este proyecto serán documentados en este archivo.

El formato está basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.0.0/),
y este proyecto adhiere a [Semantic Versioning](https://semver.org/lang/es/).

## [Unreleased]

### Agregado
- Control de costos de IA: cada llamada a Gemini suma sus tokens al mes en curso (compartido vía `RATELIMIT_STORAGE_URI`), `AI_MONTHLY_TOKEN_LIMIT` corta las llamadas al llegar al tope y `GET /api/ai/usage` muestra el consumo y el costo estimado.
  Las respuestas con temperatura ≤ 0.5 se cachean `AI_CACHE_TTL` segundos.
- Monitor diario de scrapers (`scripts/scraper_health.py` + workflow `Monitor de scrapers`): busca en Computrabajo y Bumeran y abre un issue si alguno no devuelve ofertas.
- Página `/optimize_resume` (antes daba 500 porque faltaba la plantilla) y enlace "Optimizar CV" en el menú.

### Cambiado
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
