<div align="center">

# 🤖 EmpleoIA

### *Plataforma Inteligente de Búsqueda de Empleo con IA*

[![Python Version](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/fastapi-0.162-green.svg)](https://fastapi.tiangolo.com/)
[![License](https://img.shields.io/badge/license-MIT-orange.svg)](LICENSE)
[![Status](https://img.shields.io/badge/status-active-success.svg)]()
[![Celery](https://img.shields.io/badge/celery-5.3+-brightgreen.svg)](https://docs.celeryq.dev/)
[![Gemini](https://img.shields.io/badge/AI-Gemini%201.5-blueviolet.svg)](https://aistudio.google.com/)

*Automatizá tu búsqueda laboral con scraping inteligente, IA generativa y optimización de CVs*

[Características](#-características) •
[Instalación](#-instalación-rápida) •
[Uso](#-guía-de-uso) •
[Documentación](#-documentación) •
[Contribuir](#-contribuir)

</div>

---

## 📋 Tabla de Contenidos

- [Descripción](#-descripción)
- [Características](#-características)
- [Tecnologías](#-tecnologías)
- [Requisitos](#-requisitos-previos)
- [Instalación Rápida](#-instalación-rápida)
- [Guía de Uso](#-guía-de-uso)
- [Estructura del Proyecto](#-estructura-del-proyecto)
- [Configuración](#-configuración)
- [Extensión de Chrome](#-extensión-de-chrome)
- [Despliegue en la Nube](#-despliegue-en-la-nube)
- [Solución de Problemas](#-solución-de-problemas)
- [Contribuir](#-contribuir)
- [Licencia](#-licencia)
- [Créditos](#-créditos)

---

## 🎯 Descripción

**EmpleoIA** es una plataforma integral de automatización de búsqueda de empleo que combina web scraping multi-plataforma con inteligencia artificial generativa (Google Gemini). Diseñada para profesionales que buscan optimizar su proceso de búsqueda laboral en Argentina y Latinoamérica.

### ¿Qué hace diferente a EmpleoIA?

- ✅ **AI Copilot integrado**: Chat en tiempo real con Gemini para estrategia laboral personalizada
- ✅ **Mock Interviews**: Entrevistas simuladas con feedback instantáneo de IA
- ✅ **Análisis semántico**: Match entre CV y ofertas usando IA generativa (no solo keywords)
- ✅ **Scraping sin APIs**: Extrae ofertas de Indeed, LinkedIn, Bumeran y Computrabajo
- ✅ **Celery + Redis**: Scraping asíncrono, no bloquea la app mientras trabaja en segundo plano
- ✅ **Extensión de Chrome**: Guardá ofertas con 1 click desde cualquier portal de empleo
- ✅ **Notificaciones por Email**: Alertas de follow-up, digest de nuevas ofertas y resúmenes semanales
- ✅ **Análisis salarial**: Detecta y analiza rangos salariales de las ofertas scrapeadas
- ✅ **Despliegue en la nube**: Infraestructura como código con Terraform para GCP

---

## ✨ Características (Versión Enterprise)

### 🚀 **Nueva Arquitectura y Escalabilidad (Fases 1-5 completadas)**
- **Migración a Playwright**: El motor de scraping abandona Selenium y adopta `playwright` asincrónico para máxima velocidad y evitar detecciones.
- **FastAPI Core**: las APIs JSON y las páginas ya migradas (`routers/pages.py`: inicio, scraper, resultados, perfil, entrevista, tracker y analytics; `routers/auth_pages.py`: login, registro, recuperación, verificación en dos pasos y Google; `routers/account_pages.py`: Mi cuenta; `routers/security_pages.py`: segundo factor y passkeys; `routers/admin_pages.py`: Administración; `routers/export_pages.py`: Excel y PDF; `routers/content_pages.py`: resultados y documentos; `routers/profile_pages.py`: perfiles de CV; `routers/alert_pages.py`: alertas y "me interesa") y `routers/scraper_pages.py`: búsquedas y conexiones) corren en FastAPI (`main.py`). Flask ya no forma parte del proyecto; las sesiones abiertas antes siguen valiendo (`web_settings.py`).
- **Entorno DevContainer**: Repositorio "Docker-first" con `.devcontainer` que soluciona conflictos de C++ y restricciones de Windows Defender para dependencias de IA.
- **Web Speech API**: Interfaz de *Mock Interviews* actualizada con funcionalidad de voz-a-texto en la UI.
- **Autonomías Externas**: Tracker automático para Gmail vía OAuth e introducción de auto-aplicación en LinkedIn.

### 🤖 **IA Generativa (Validada)**
- **AI Copilot**: Chat lateral con Gemini en todas las páginas — preguntá sobre tu búsqueda, estrategia, salarios, LinkedIn
- **Mock Interviews**: Entrevistas simuladas con preguntas personalizadas, timer, evaluación STAR y feedback en tiempo real
- **Análisis completo de ofertas**: Cultura de empresa, skills requeridas vs tus skills, rango salarial inferido, red flags
- **Reescritura de CV**: Mejora bullet points de tu CV para hacer match perfecto con una oferta
- **Plan de aprendizaje**: Genera ruta de skills para cerrar el gap con una posición target
- **Insights de mercado**: Salarios, demanda y tendencias por rol y nivel de experiencia

### 🔍 **Scraping Asíncrono Multi-Plataforma (MEJORADO)**
- Búsqueda automatizada en **Indeed**, **LinkedIn**, **Bumeran** y **Computrabajo**
- **Celery + Redis**: Scraping en segundo plano sin congelar la app web
- **Flower Dashboard**: Monitor de tareas en `localhost:5555` para ver el progreso
- **🚀 Scraper Universal**: Ejecuta múltiples plataformas simultáneamente en paralelo
- Filtrado inteligente por habilidades, ubicación y nivel de experiencia
- Chromium sin ventana con Playwright en todos los portales

### 🎨 **Experiencia de Usuario**
- **🌙 Dark Mode**: Tema oscuro nativo para reducir fatiga visual
- **⚡ Filtros Dinámicos**: Búsqueda instantánea en resultados
- **📱 Diseño Responsive**: Interfaz moderna adaptada a todos los dispositivos
- **🌐 Extensión de Chrome**: Guardá ofertas de cualquier portal con 1 click (LinkedIn, Indeed, Bumeran, Computrabajo)

### 📊 **Sistema de Seguimiento (Job Tracker)**
- Tablero Kanban para gestionar postulaciones
- Estados: Guardado → Aplicando → Aplicado → Entrevistando → Negociando → Aceptado
- Filtros avanzados: por estado, empresa, modal
- Notas y recordatorios personalizados

### 💰 **Análisis Salarial (NEW)**
- Extracción automática de rangos salariales de texto libre (regex + NLP)
- Histograma de distribución salarial por CSV
- Ranking de empresas por salario promedio
- Insights de mercado por rol/nivel con caché de 7 días

### 📈 **Analytics y Reportes Avanzados**
- Dashboard interactivo con métricas de embudo (funnels) y tasas de conversión
- Gráficos con Chart.js: heatmap semanal, distribución salarial, progreso
- Exportación a Excel con formato premium (colores por estado, auto-width)
- Exportación a PDF

### 📧 **Notificaciones por Email (NEW)**
- Recordatorios de seguimiento (email o Telegram) para postulaciones con fecha vencida
- Digest de nuevas ofertas encontradas
- Passkeys (WebAuthn): se agregan en Mi cuenta y sirven para entrar sin contraseña ni código, con la huella, la cara o el PIN del dispositivo. `WEBAUTHN_RP_ID` y `WEBAUTHN_ORIGIN` (o `APP_BASE_URL`) fijan el dominio
- Emails por SMTP o SendGrid (`EMAIL_PROVIDER`), con reintentos ante fallas temporales y sin volver a mandar a direcciones que rebotaron o denunciaron spam (webhook firmado `POST /webhooks/sendgrid`)
- Resumen semanal por email (worker con Celery beat y SMTP): ofertas nuevas de las alertas, postulaciones sin respuesta hace `FOLLOWUP_DAYS` días o más, y seguimientos o cierres de los próximos 7 días. No se manda si no hay novedades; cada cuenta lo apaga en Mi cuenta
- Template HTML premium en dark mode
- **Portales:** Computrabajo, Bumeran, ZonaJobs (misma plataforma que Bumeran) y GetOnBoard (API pública, sin navegador) en la búsqueda universal, las alertas y el monitor diario.
- **Puntaje ATS** (`/optimize_resume` → "Calcular puntaje ATS", o `POST /api/ats_score`): puntaje de 0 a 100 sin IA con contacto, secciones, extensión, logros medibles, fechas y palabras clave de la oferta que faltan en el CV.
- **Recordatorios del tracker:** cada postulación acepta fecha de seguimiento, fecha límite y notas. Celery Beat manda un solo aviso diario por email o Telegram con los seguimientos vencidos; sin fecha, avisa `FOLLOWUP_DAYS` días después de postular. Cada recordatorio se manda una vez.
- **Ranking personal:** aprende del tracker a qué ofertas te postulás y cuáles dejás guardadas sin postular (más de `RANKING_STALE_DAYS` días), por palabras del título, empresa, ubicación y portal. Reordena los avisos de alertas y los resultados de búsqueda (columna "Afinidad") mezclando el match del CV con lo aprendido (`RANKING_WEIGHT`, 0.3 por defecto). Con al menos 5 "me interesa" y 5 "no me interesa", cada cuenta usa el peso (0 a 0,8) que mejor ordena lo que marcó; `/api/ranking` muestra el peso y el AUC antes y después en `tuning`. `/api/ranking` muestra qué aprendió; necesita al menos 3 ejemplos de cada tipo. Los botones "me interesa / no me interesa" de los resultados cuentan doble, sacan de las alertas lo descartado y miden el matching: `/api/ranking` (tu cuenta) y `python scripts/feedback_report.py` (todas) dan el AUC del match contra lo que eligieron los usuarios.
- **Alertas de empleo** (`/alerts`): guardá una búsqueda y recibí por email o Telegram solo las ofertas nuevas, sin duplicados entre portales y con match mínimo opcional contra tu CV. Configurá `TELEGRAM_BOT_TOKEN` y `ALERTS_INTERVAL_HOURS` en `.env`; cada cuenta carga su chat de Telegram en **Mi cuenta** (`TELEGRAM_CHAT_ID` queda como chat de la primera cuenta).
- **Exportar mis datos** (**Mi cuenta**): descarga un ZIP con el tracker, el historial de estados, perfiles, CVs originales (descifrados), alertas, resultados de búsquedas y documentos generados. Pide la contraseña y no incluye contraseñas, tokens ni claves push.
- **Sesiones abiertas** (**Mi cuenta**): lista los navegadores con la cuenta abierta (IP, inicio y última actividad) y permite cerrar uno o todos los demás. Salir, cambiar o recuperar la contraseña también cierra las sesiones. Las sesiones vencen a los 31 días sin uso.
- **Verificación en dos pasos** (**Mi cuenta**): app autenticadora (TOTP) con QR, pedida después de la contraseña o de Google, y 10 códigos de recuperación de un uso. El secreto se cifra con `CV_ENCRYPTION_KEY`. Sin el teléfono ni códigos, el administrador la quita desde **Administración**.
- **Idiomas:** español, inglés y portugués, desde el selector de la barra (o según el idioma del navegador). Los textos nuevos se marcan con `{{ _('Texto en español') }}` y se traducen en `translations/en.json` y `translations/pt.json`; los mensajes de progreso que arman los threads o el worker se guardan con `i18n.lazy('Buscando %(position)s...', position=...)` y `/status` los traduce al leerlos. Un test falla si un texto marcado no tiene su traducción.
- **Administración** (`/admin`, solo la cuenta de `ADMIN_EMAIL` o, sin esa variable, la primera): lista las cuentas con fecha de alta, última actividad, verificación en dos pasos y consumo de IA del mes. Permite bloquear y desbloquear (una cuenta bloqueada no entra, pierde sus sesiones, su token de la extensión deja de valer y no recibe avisos), quitar la verificación en dos pasos y borrar la cuenta con todos sus datos; las dos últimas piden la contraseña del administrador. Las demás cuentas reciben 404.
- **Actividad reciente** (**Mi cuenta**): registro de inicios de sesión (con contraseña o Google), contraseñas incorrectas, cambios y recuperación de contraseña, Telegram, Gmail, token de la extensión y exportaciones, con IP y navegador. Un login desde un navegador nuevo manda un aviso por email (`LOGIN_ALERTS=false` lo apaga). Los eventos se borran a los `SECURITY_EVENTS_DAYS` días (180).
- **Notificaciones push** (PWA): en **Mi cuenta** cada dispositivo se suscribe a los avisos de alertas y recordatorios, sin email ni Telegram. Generá las claves con `python scripts/generate_vapid_keys.py` y cargá `VAPID_PUBLIC_KEY` y `VAPID_PRIVATE_KEY` (en Cloud Run, la privada va en `EXTRA_SECRETS_JSON`). En iPhone hay que agregar la app a la pantalla de inicio primero.

### ⚡ **Rendimiento y Modo Offline (PWA)**
- Soporte para Progressive Web App (PWA) con modo de instalación
- Sistema offline utilizando Service Workers (`/sw.js`) y almacenamiento local en IndexedDB; al cerrar sesión o vencer la sesión se borran del navegador
- Acceso continuo a las postulaciones guardadas incluso sin conexión a internet

### 👤 **Gestión de Perfiles**
- Soporte para múltiples perfiles profesionales por rol
- Extracción automática de habilidades desde CVs (PDF/DOCX)
- Historial de postulaciones

### 📝 **Generación de Cartas de Presentación**
- Creación automática personalizada con Gemini
- Selección de tono: formal, semi-formal, casual, audaz
- Análisis de cultura de empresa para adaptar el tono
- Procesamiento por lotes para múltiples aplicaciones
- Exportación a DOCX

---

## 🛠 Tecnologías

<table>
<tr>
<td align="center" width="20%">
<img src="https://www.python.org/static/community_logos/python-logo.png" width="60px" height="60px" alt="Python" />
<br><strong>Python 3.12</strong>
<br><sub>Backend</sub>
</td>
<td align="center" width="20%">
<img src="https://fastapi.tiangolo.com/img/logo-margin/logo-teal.png" width="60px" height="60px" alt="FastAPI" />
<br><strong>FastAPI</strong>
<br><sub>Web Framework</sub>
</td>
<td align="center" width="20%">
<img src="https://playwright.dev/img/playwright-logo.svg" width="60px" height="60px" alt="Playwright" />
<br><strong>Playwright</strong>
<br><sub>Web Scraping</sub>
</td>
<td align="center" width="20%">
<img src="https://www.mysql.com/common/logos/logo-mysql-170x115.png" width="60px" height="60px" alt="MySQL" />
<br><strong>MySQL</strong>
<br><sub>Base de Datos</sub>
</td>
<td align="center" width="20%">
<img src="https://docs.celeryq.dev/en/stable/_static/celery_512.png" width="60px" height="60px" alt="Celery" />
<br><strong>Celery + Redis</strong>
<br><sub>Task Queue</sub>
</td>
</tr>
<tr>
<td align="center" width="20%">
<img src="https://getbootstrap.com/docs/5.3/assets/brand/bootstrap-logo-shadow.png" width="60px" height="60px" alt="Bootstrap" />
<br><strong>Bootstrap 5</strong>
<br><sub>UI Framework</sub>
</td>
<td align="center" width="20%">
<img src="https://upload.wikimedia.org/wikipedia/commons/6/6a/JavaScript-logo.png" width="60px" height="60px" alt="JavaScript" />
<br><strong>JavaScript</strong>
<br><sub>Frontend</sub>
</td>
<td align="center" width="20%">
<img src="https://www.docker.com/wp-content/uploads/2022/03/vertical-logo-monochromatic.png" width="60px" height="60px" alt="Docker" />
<br><strong>Docker</strong>
<br><sub>Containerización</sub>
</td>
<td align="center" width="20%">
<img src="https://upload.wikimedia.org/wikipedia/commons/8/87/Sql_data_base_with_logo.png" width="60px" height="60px" alt="NLP" />
<br><strong>spaCy NLP</strong>
<br><sub>Parsing</sub>
</td>
<td align="center" width="20%">
<img src="https://lh3.googleusercontent.com/qnCkZuSQ0uqIwJoOCZS3l5ZLLcq2T8aPHEqYqCJ19BzxnA6qjhVscOuDoVG1cSo6qg6BxBnM0RKQwRvqWBRN9dkSPQ=s120" width="60px" height="60px" alt="Gemini" />
<br><strong>Google Gemini</strong>
<br><sub>IA Generativa</sub>
</td>
</tr>
</table>

---

## 📦 Requisitos Previos

Antes de comenzar, asegurate de tener instalado:

- ✅ **Python 3.12+** - [Descargar](https://www.python.org/downloads/)
- ✅ **MySQL 8.0+** - [Descargar](https://dev.mysql.com/downloads/)
- ✅ **Chromium de Playwright** - `python -m playwright install --with-deps chromium` (Indeed y las conexiones de LinkedIn todavía usan Google Chrome con Selenium)
- ✅ **Git** - Para clonar el repositorio
- ✅ **Redis** (opcional, para Celery) - [Descargar](https://redis.io/download/) o usar Docker

---

## 🚀 Instalación Rápida

### Opción 1: Instalación Manual

```bash
# 1. Clonar el repositorio
git clone https://github.com/Fernandofarfan/EmpleoIA.git
cd EmpleoIA

# 2. Crear entorno virtual
python -m venv .venv
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # Mac/Linux

# 3. Instalar dependencias. requirements.txt trae versión y hash de cada paquete, resuelto para
#    Linux (Docker y CI); en Windows/Mac usá requirements.in (mismas dependencias directas, sin hashes)
pip install --require-hashes -r requirements.txt   # Linux
# pip install -r requirements.in                   # Windows/Mac

# 4. Instalar modelo de spaCy (IMPORTANTE)
python -m spacy download en_core_web_sm

# 5. Configurar base de datos MySQL
mysql -u root -p -e "CREATE DATABASE IF NOT EXISTS job_tracker CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
alembic upgrade head   # crea y actualiza todas las tablas

# 6. Configurar variables de entorno
cp .env.example .env
# Editar .env con tus credenciales

# 7. Ejecutar la aplicación (levanta main:app con uvicorn)
python app.py
```

> [!TIP]
> Para aprovechar el scraping asíncrono con Celery, también ejecutá en terminales separadas:
> ```bash
> # Terminal 2: Celery Worker
> celery -A celery_app worker --loglevel=info -Q scraping,ai_processing,notifications
>
> # Con AI_BACKEND=celery, las cartas y CVs en lote también corren en el worker
> # (GENERATED_DIR tiene que apuntar a una carpeta compartida con la web).
>
> # Terminal 3: Flower Dashboard (monitor de tareas)
> celery -A celery_app flower --port=5555
> ```
> Flower estará disponible en `http://localhost:5555`

### Opción 2: Docker (Todo incluido)

```bash
# Copia y configura las variables de entorno
cp .env.example .env
# Editar .env con GEMINI_API_KEY y DB_PASSWORD

# Levanta todo: web (FastAPI) + MySQL + Redis + Celery + Flower
docker-compose up -d

# Ver logs
docker-compose logs -f web
```

### 🌐 Acceder a la Aplicación

| Servicio | URL |
|----------|-----|
| **EmpleoIA App** | `http://localhost:5000` |
| **Flower (monitor)** | `http://localhost:5555` |
| **Redis** | `localhost:6379` |

---

## 📖 Guía de Uso

### 1️⃣ Configuración Inicial

#### Cargar tu Currículum
1. Navegá a **Perfil** en el menú
2. Seleccioná tu tipo de rol (Data Analyst, Software Engineer, etc.)
3. Subí tu CV en formato PDF o DOCX
4. El sistema extraerá automáticamente tus habilidades

#### Configurar el AI Copilot
1. Agregá `GEMINI_API_KEY` a tu archivo `.env` ([obtenela gratis aquí](https://aistudio.google.com/app/apikey))
2. El ícono 🤖 aparecerá en la esquina inferior derecha de todas las páginas
3. Hacé clic para abrir el chat con el AI Copilot

### 2️⃣ Buscar Empleos

#### Instalar la Extensión de Chrome (Recomendado)
1. Abrí Chrome y andá a `chrome://extensions`
2. Activá el **Modo desarrollador**
3. Hacé clic en **Cargar descomprimida** y seleccioná la carpeta `chrome_extension/`
4. La extensión 🤖 aparecerá en la barra de herramientas

#### Usar el Scraper Integrado
- **LinkedIn**: Andá a **Buscar Empleos** → LinkedIn → Configurá credenciales → Iniciar
- **Indeed**: Andá a **Buscar Empleos** → Indeed → Configurá credenciales → Iniciar
- **Universal**: Ejecuta Computrabajo + Bumeran simultáneamente

### 3️⃣ Mock Interviews (NEW)

1. Andá a **Entrevistas** en el menú
2. Seleccioná un trabajo del tracker o ingresá el puesto manualmente
3. Configurá la dificultad (Junior/Medio/Senior) y cantidad de preguntas
4. Respondé las preguntas y recibí feedback instantáneo de IA
5. Descargá el reporte de tu sesión de práctica

### 4️⃣ Analizar Ofertas con IA

1. Andá a **Resultados** y abrí un CSV
2. Hacé clic en **🤖 Analizar con IA** en cualquier fila
3. La IA muestra: compatibilidad con tu CV, skills faltantes, cultura de empresa, salario estimado

### 5️⃣ Seguimiento de Aplicaciones

1. Andá a **Tracker**
2. Agregá trabajos desde resultados, manualmente o con la extensión de Chrome
3. Arrastrá y soltá entre columnas del Kanban
4. Agregá notas y fechas de follow-up
5. Activá las notificaciones por email para recordatorios automáticos

---

### Calidad del matching

`python scripts/eval_matching.py` ordena las ofertas de `eval/matching_dataset.json` para cada CV etiquetado y muestra NDCG@5, precisión@3 y MRR. Con `MATCHING_BACKEND=embeddings` (y `GEMINI_API_KEY`) mide el matching por embeddings, y `--compare` mide los dos seguidos, en total y por idioma del CV, con la diferencia entre ambos. El workflow "Comparar matching" lo corre los lunes y a pedido con el secreto `GEMINI_API_KEY`, y deja el JSON como artefacto. El dataset tiene CVs y ofertas en inglés, español y portugués. `--min-ndcg 0.9` sale con código 1 si el promedio queda por debajo. Para cubrir un caso nuevo, sumá ofertas o CVs con sus etiquetas al JSON.

## 📁 Estructura del Proyecto

```
EmpleoIA/
│
├── 📂 scrapers/              # Módulos de web scraping
│   ├── common.py              # Chromium de Playwright compartido (timeouts, reintentos)
│   ├── linkedin_pw.py         # LinkedIn (Playwright)
│   ├── bumeran_scraper.py     # Bumeran y ZonaJobs (Playwright)
│   ├── computrabajo_scraper.py # Computrabajo (Playwright)
│   ├── indeed_scraper.py      # Indeed (Playwright)
│   └── linkedin_connection.py # Solicitudes de conexión (Selenium)
│
├── 📂 tasks/                 # 🆕 Tareas asíncronas Celery
│   ├── scraping_tasks.py     # Scraping en background
│   ├── ai_tasks.py           # Análisis IA por lotes
│   └── notification_tasks.py # Envío de notificaciones (email, Telegram, push)
│
├── 📂 templates/             # Plantillas HTML (Frontend)
│   ├── base.html             # Plantilla base + AI Copilot
│   ├── index.html            # Página principal
│   ├── scraper.html          # Interfaz de scraping
│   ├── results.html          # Visualización de resultados
│   ├── job_tracker.html      # Tablero Kanban
│   ├── analytics.html        # Dashboard de analytics
│   ├── mock_interview.html   # 🆕 Entrevistas simuladas
│   └── profile.html          # Gestión de perfiles
│
├── 📂 static/css/            # Estilos por módulo
│   ├── mock_interview.css    # 🆕 Estilos de entrevistas
│   └── ...
│
├── 📂 chrome_extension/      # 🆕 Extensión de Chrome
│   ├── manifest.json
│   ├── popup.html / popup.js
│   ├── content.js
│   └── background.js
│
├── 📂 terraform/             # 🆕 Infraestructura como código (GCP)
│   ├── main.tf
│   └── variables.tf
│
├── 📄 main.py                # App FastAPI (routers, login, límites, métricas, páginas de error)
├── 📄 app.py                 # Arma la web (web_settings.py) y sus servicios (AppServices)
├── 📁 services/              # Perfiles, búsquedas de Indeed/LinkedIn, conexiones y pruebas de scrapers
├── 📁 routers/               # Páginas y APIs de FastAPI por área
├── 📄 ai_engine.py           # 🆕 Motor de IA centralizado (Gemini)
├── 📄 celery_app.py          # 🆕 Configuración de Celery
├── 📄 models.py              # 🆕 Modelos SQLAlchemy ORM
├── 📄 market_analyzer.py     # 🆕 Análisis salarial
├── 📄 notifier.py            # 🆕 Notificaciones por email
├── 📄 resume_parser.py       # Parser de CVs
├── 📄 job_matcher.py         # Match entre perfil y oferta
├── 📄 notification_messages.py # Textos de emails y mensajes de Telegram
├── 📄 db_config.py           # Configuración de MySQL
│
├── 📄 requirements.in        # Dependencias directas (se editan acá)
├── 📄 requirements.txt       # Generado con pip-compile: todas las dependencias con hash
├── 📄 docker-compose.yml     # 🆕 Stack completo con Redis + Celery
├── 📄 db_schema.py           # Metadata de los modelos y chequeo de drift contra la base
├── 📄 .env.example           # Plantilla de configuración
└── 📄 README.md              # Este archivo
```

---

## ⚙️ Configuración

### Variables de Entorno (.env)

Creá un archivo `.env` en la raíz del proyecto copiando `.env.example`:

```bash
cp .env.example .env
```

#### Variables principales:

```env
# === IA (OBLIGATORIO para funciones de IA) ===
GEMINI_API_KEY=tu_api_key_aqui

# === Seguridad ===
SECRET_KEY=            # obligatoria en producción: python -c "import secrets; print(secrets.token_hex(32))"
ADMIN_EMAIL=           # email obligatorio de la primera cuenta (la que se queda con los datos previos) y administrador de /admin
ALLOW_SIGNUP=false     # true = registro abierto en /register; por defecto solo se crea la primera cuenta
REQUIRE_EMAIL_VERIFICATION=false  # true = las cuentas nuevas entran solo después de confirmar el email (necesita SMTP)
PUBLIC_BASE_URL=               # URL pública de la app para los enlaces de los emails (obligatoria en Cloud Run)
LOGIN_REQUIRED=true    # false = sin login (solo local)
CV_ENCRYPTION_KEY=     # cifra los CVs en uploads/ y los perfiles (texto del CV incluido) en MySQL (Fernet). Sin ella no se pueden leer los ya cifrados
CV_RETENTION_DAYS=0    # >0: Celery borra cada día CVs, perfiles y documentos más viejos que N días
EXTENSION_TOKEN=       # (viejo) token de la extensión para la primera cuenta; cada cuenta genera el suyo en Mi cuenta
GOOGLE_OAUTH_CLIENT_ID=      # "Entrar con Google" (cliente OAuth web; redirect: PUBLIC_BASE_URL + /login/google/callback)
GOOGLE_OAUTH_CLIENT_SECRET=
GMAIL_OAUTH_CLIENT_FILE=credentials.json  # cliente OAuth "aplicación web" de Google para "Conectar Gmail" en Mi cuenta
                       # (redirect URI: PUBLIC_BASE_URL + /account/gmail/callback)
SESSION_COOKIE_SECURE=0  # 1 detrás de HTTPS (también activa HSTS)
CSP_REPORT_ONLY=0      # 1 = la CSP solo informa violaciones (Content-Security-Policy-Report-Only), útil para probar
CSP_REPORT_URI=        # URL que recibe los reportes de violaciones de la CSP (opcional)
ENABLE_API_DOCS=0      # 1 publica /docs, /redoc y /openapi.json; apagado en producción
FLASK_HOST=127.0.0.1   # python app.py solo escucha en localhost; usá 0.0.0.0 para exponerlo
FLASK_PORT=5000
FLASK_DEBUG=0          # 1 activa el modo debug (recarga y /debug/directories): nunca lo expongas a la red
MAX_UPLOAD_MB=16       # tamaño máximo de CV
AI_RATE_LIMIT=30 per minute     # límite por cuenta (o por IP sin sesión) para /api/ai/*
API_RATE_LIMIT=300 per minute   # límite por cuenta para todo /api/*
TRUSTED_PROXY_HOPS=0            # 1 en Cloud Run: toma la IP real de X-Forwarded-For
RATELIMIT_STORAGE_URI=memory:// # usá redis://... con varias instancias
AI_MONTHLY_TOKEN_LIMIT=0        # tope mensual de tokens de Gemini (0 = sin tope); consumo en GET /api/ai/usage.
AI_USER_MONTHLY_TOKEN_LIMIT=0   # tope mensual por cuenta (0 = sin tope); cada cuenta ve su consumo en GET /api/ai/usage.
MATCHING_BACKEND=tfidf          # embeddings = match CV-oferta por significado con Gemini (cuenta en el tope); tfidf = palabras en común.
                                # Al llegar al tope, la carga de CV sigue funcionando con el parser local (regex + spaCy), sin IA
AI_CACHE_TTL=3600               # caché de respuestas de IA deterministas (temperatura ≤ 0.5), compartida en Redis si RATELIMIT_STORAGE_URI es redis://; 0 la apaga
GEMINI_LIGHT_MODEL=gemini-2.5-flash-lite  # modelo barato para extraer salarios y clasificar correos de Gmail; vacío = GEMINI_MODEL
AI_PRICE_INPUT_PER_MTOK=        # USD por millón de tokens, para el costo estimado (opcional)
AI_PRICE_OUTPUT_PER_MTOK=
SCRAPER_PAGE_TIMEOUT=30  # segundos máximos de carga de cada página en los scrapers
SCRAPER_HEADLESS=true    # false abre la ventana de Chromium (para depurar)
PLAYWRIGHT_WS_ENDPOINT=  # opcional: navegador remoto (ws://...) en vez de lanzar Chromium
SCRAPER_MAX_ATTEMPTS=3   # intentos por página (espera 2 s, 4 s… entre intentos)

# === Observabilidad (opcional) ===
LOG_LEVEL=INFO
SENTRY_DSN=                      # errores 500 y tareas fallidas a Sentry (solo el id de la cuenta, sin cookies ni emails)
SENTRY_ENVIRONMENT=development   # en Cloud Run lo pone Terraform
SENTRY_TRACES_SAMPLE_RATE=0
METRICS_TOKEN=                  # /metrics (Prometheus) con 'Authorization: Bearer <token>'; vacío = 404
OTEL_EXPORTER_OTLP_ENDPOINT=    # trazas OpenTelemetry (web + worker); ver docs/observability.md

# === Base de Datos ===
DB_HOST=127.0.0.1
DB_USER=root
DB_PASSWORD=tu_password_mysql
DB_NAME=job_tracker

# === Redis (para Celery) ===
REDIS_URL=redis://localhost:6379/0

# === Notificaciones por Email ===
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=tu_email@gmail.com
SMTP_PASSWORD=tu_app_password_google
NOTIFICATION_EMAIL=tu_email@gmail.com
```

> [!NOTE]
> En `docker-compose.yml`, MySQL (`3307`), Redis (`6379`) y Flower (`5555`) solo se publican en `127.0.0.1`. Los CVs subidos deben ser PDF, DOCX o TXT y se guardan con un nombre sanitizado.

> [!IMPORTANT]
> **Nunca subas el archivo `.env` al repositorio**. Está incluido en `.gitignore`.

> [!TIP]
> **Gmail + 2FA**: Creá una "Contraseña de Aplicación" en [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords) para usar como `SMTP_PASSWORD`.

---

## 🌐 Extensión de Chrome

La extensión **EmpleoIA Saver** permite guardar ofertas de trabajo con 1 click.

### Instalación en Chrome

1. Abrí `chrome://extensions`
2. Activá el **Modo desarrollador** (esquina superior derecha)
3. Clic en **Cargar descomprimida**
4. Seleccioná la carpeta `chrome_extension/`

### Plataformas compatibles

- ✅ LinkedIn Jobs
- ✅ Indeed (ar.indeed.com)
- ✅ Bumeran y ZonaJobs
- ✅ Computrabajo (ar.computrabajo.com y computrabajo.com.ar)
- ✅ GetOnBoard (getonbrd.com)
- ✅ Click derecho → Guardar en EmpleoIA (cualquier página; usa el JobPosting de schema.org si la página lo publica)

### Servidor y vinculación

En ⚙️ cargá la URL de tu EmpleoIA y tocá **Vincular con mi cuenta**: se abre Mi cuenta, confirmás y la extensión queda vinculada (guarda en el tracker de esa cuenta). No hay que copiar ningún token: se guarda solo en ese dispositivo (`chrome.storage.local`), no se sincroniza a otros Chrome, y **Mi cuenta → Desvincular** lo revoca. Para un servidor que no sea `localhost:5000` (por ejemplo Cloud Run), tocá **Permitir acceso a este servidor**: la extensión solo pide permiso para ese origen.

### Publicar en el Chrome Web Store

`python scripts/package_extension.py` valida el manifest y deja `dist/empleoia-saver-<versión>.zip`; el CI lo publica como artefacto `chrome-extension`. Los pasos y los textos para la ficha están en [docs/chrome-web-store.md](docs/chrome-web-store.md).

---

## ☁️ Despliegue en la Nube

`terraform/` despliega EmpleoIA en **Google Cloud Platform**, con un estado por ambiente (`staging` y `prod`).

| Recurso | Detalle |
|---|---|
| Cloud Run `empleoia-web-<env>` | Web (uvicorn), cuenta de servicio propia, solo tráfico a IPs privadas por la VPC |
| Cloud Run worker pool `empleoia-worker-<env>` | Celery worker + beat (scraping, alertas, retención de CVs); 1 instancia |
| Cloud Run job `empleoia-migrate-<env>` | `alembic upgrade head`, se corre en cada deploy antes de actualizar la web |
| Cloud SQL MySQL 8.0 | Solo IP privada, backups diarios (`backup_retention_count`) y point-in-time recovery de 7 días; en prod regional y con protección contra borrado. La restauración se verifica cada mes (`docs/backup-restore.md`) |
| Memorystore Redis 7 | Rate limit, caché de IA y broker de Celery (HA en prod) |
| Bucket `<proyecto>-empleoia-uploads-<env>` | CVs montados en `/app/uploads`; privado, sin versionado y con borrado por antigüedad si `cv_retention_days > 0` |
| Bucket `<proyecto>-empleoia-results-<env>` | Resultados de búsqueda montados en `/app/results`, compartidos entre el worker y la web |
| Cloud Monitoring | Uptime check de `/api/ready` (app, base y Redis), alertas de 5xx, latencia p95 y disco de Cloud SQL; por email con `alert_email` (`docs/observability.md`) |
| Secret Manager | `DB_PASSWORD`, `SECRET_KEY`, `GEMINI_API_KEY`, `CV_ENCRYPTION_KEY` y `extra_secrets` |

Los valores no secretos de cada ambiente están en `terraform/envs/<env>.tfvars`. Los secretos se pasan como `TF_VAR_*` y nunca van al repo (quedan en el estado de Terraform, así que el bucket del estado debe ser privado).

### Deploy automático (GitHub Actions)

- **`Terraform`**: en cada PR que toca `terraform/` corre `fmt`, `validate` y `terraform test` (con un provider simulado, sin credenciales).
- **`Deploy a GCP`**: cada push a `main` despliega en staging: build de la imagen con el SHA del commit, migraciones, `terraform apply` y smoke test de `/api/ready`. Producción se despliega con "Run workflow" eligiendo `prod`. En los PRs publica el `terraform plan` de staging en el resumen del job.

El deploy se saltea hasta que crees la variable de repositorio `GCP_DEPLOY_ENABLED=true` y configures, en cada GitHub Environment (`staging`, `prod`):
- **Variables:** `GCP_PROJECT_ID`, `GCP_WORKLOAD_IDENTITY_PROVIDER`, `GCP_DEPLOY_SA`, `TF_STATE_BUCKET` y, opcionalmente, `GCP_REGION`.
- **Secretos:** `DB_PASSWORD`, `GEMINI_API_KEY`, `SECRET_KEY`, `CV_ENCRYPTION_KEY` y, opcionalmente, `EXTRA_SECRETS_JSON` (p. ej. `{"TELEGRAM_BOT_TOKEN":"..."}`).

Conviene exigir aprobación manual en el environment `prod`. La autenticación es por Workload Identity Federation: no hay claves JSON de cuentas de servicio.

### Deploy manual

```bash
cd terraform
gcloud storage buckets create gs://<bucket-del-estado> --location=southamerica-east1 --uniform-bucket-level-access
terraform init -backend-config="bucket=<bucket-del-estado>" -backend-config="prefix=empleoia/staging"

export TF_VAR_project_id=<proyecto> TF_VAR_db_password=... TF_VAR_gemini_api_key=... \
       TF_VAR_app_password=... TF_VAR_secret_key=... TF_VAR_cv_encryption_key=...
export TF_VAR_image=southamerica-east1-docker.pkg.dev/<proyecto>/empleoia-staging/web:<tag>

terraform apply -var-file=envs/staging.tfvars -target=google_artifact_registry_repository.empleoia
docker build -t "$TF_VAR_image" .. && docker push "$TF_VAR_image"
terraform apply -var-file=envs/staging.tfvars -target=google_cloud_run_v2_job.migrate
gcloud run jobs execute "$(terraform output -raw migrate_job)" --region southamerica-east1 --wait
terraform apply -var-file=envs/staging.tfvars
```

---

## 🔧 Solución de Problemas

### ❌ Error: "MySQL connection failed"
```bash
# Verificar que MySQL esté corriendo
mysql -u root -p

# Crear la base de datos manualmente
CREATE DATABASE job_tracker;
```

### ❌ Celery no conecta a Redis
```bash
# Verificar que Redis esté corriendo
redis-cli ping  # Debe responder PONG

# En Windows (WSL):
wsl redis-server

# O con Docker:
docker run -d -p 6379:6379 redis:7-alpine
```

### ❌ AI Copilot no responde
- Verificá que `GEMINI_API_KEY` esté en tu `.env`
- La API key debe estar activa en [aistudio.google.com](https://aistudio.google.com/app/apikey)

### ❌ LinkedIn/Indeed detecta scraping
**Soluciones:**
- Esperá 24h antes de volver a intentar
- Usá la extensión de Chrome en lugar del scraper automático
- Revisá que tenés `LINKEDIN_TOKEN` (cookie `li_at`) en el `.env`

### ❌ Extensión de Chrome no extrae datos
- Recargá la página del trabajo antes de hacer clic en la extensión
- Verificá que EmpleoIA esté corriendo en `localhost:5000`
- Si el portal cambió su estructura de HTML, abrí un issue

---

## 🚀 Future Enhancements

### 🔴 En Desarrollo Activo
- **Auto-Apply** (experimental, apagado por defecto): completa postulaciones "Easy Apply" de LinkedIn. Se activa con `AUTO_APPLY_ENABLED=true` y solo envía con `AUTO_APPLY_SUBMIT=true`. Postular con bots puede violar los términos de LinkedIn y hacer que te bloqueen la cuenta.
- **Email Tracking**: Detección automática de respuestas de empleadores vía Gmail/Outlook
- **Playwright**: Migración de Selenium a Playwright para mayor velocidad y estabilidad

### 🟡 Próximas Funcionalidades
- **API REST Pública**: FastAPI con documentación OpenAPI/Swagger para integraciones
- **Gamificación**: Sistema de logros y estadísticas personales
- **Integración con Calendarios**: Sincronizar entrevistas con Google Calendar/Outlook

### 🟢 Ideas a Largo Plazo
- **Mobile App**: Aplicación nativa para iOS y Android
- **Machine Learning Local**: Modelo de predicción de probabilidad de conseguir entrevista
- **Multiidioma**: Soporte completo para inglés y portugués

---

## 🤝 Contribuir

¡Las contribuciones son bienvenidas! Seguí estos pasos:

1. **Fork** el repositorio
2. Creá una **branch** para tu feature (`git checkout -b feature/AmazingFeature`)
3. **Commit** tus cambios (`git commit -m 'Add: Amazing Feature'`)
4. **Push** a la branch (`git push origin feature/AmazingFeature`)
5. Abrí un **Pull Request**

### Áreas de contribución prioritarias

- 🕷️ Nuevos scrapers (Glassdoor, ZipRecruiter, Getonboard)
- 🤖 Mejoras al AI Copilot y Mock Interview
- 🌍 Soporte para más países latinoamericanos
- 🧪 Tests adicionales

Ver [CONTRIBUTING.md](CONTRIBUTING.md) para más detalles.

---

## 📝 Licencia

Este proyecto está bajo la Licencia MIT. Ver el archivo [LICENSE](LICENSE) para más detalles.

---

## 👥 Créditos

### Desarrollador

- **Fernando Farfan** - Desarrollo y mantenimiento principal
- GitHub: [@Fernandofarfan](https://github.com/Fernandofarfan)

Proyecto desarrollado desde cero para automatizar la búsqueda de empleo con tecnologías modernas de web scraping, procesamiento inteligente de datos e IA generativa.

### Tecnologías

- **Web Scraping**: [Playwright](https://playwright.dev/python/) en todos los portales (Indeed, LinkedIn, Computrabajo, Bumeran y ZonaJobs)
- **Framework**: [FastAPI](https://fastapi.tiangolo.com/)
- **Task Queue**: [Celery](https://docs.celeryq.dev/) + [Redis](https://redis.io/)
- **NLP**: [spaCy](https://spacy.io/)
- **UI**: [Bootstrap 5](https://getbootstrap.com/)
- **IA Generativa**: [Google Gemini](https://ai.google.dev/)
- **Infraestructura**: [Terraform](https://www.terraform.io/) + [Google Cloud](https://cloud.google.com/)

---

## 📞 Soporte

¿Tenés preguntas o problemas?

- 📧 **Email**: fernando.farfan16@gmail.com
- 💬 **Issues**: [GitHub Issues](https://github.com/Fernandofarfan/EmpleoIA/issues)
- 📖 **Wiki**: [Documentación Completa](https://github.com/Fernandofarfan/EmpleoIA/wiki)

---

<div align="center">

### ⭐ Si te resultó útil, dejá una estrella!

**Hecho con ❤️ en Argentina**

[⬆ Volver arriba](#-empleoia)

</div>
