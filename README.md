<div align="center">

# 🤖 EmpleoIA

### *Plataforma Inteligente de Búsqueda de Empleo con IA*

[![Python Version](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![Flask](https://img.shields.io/badge/flask-2.3.3-green.svg)](https://flask.palletsprojects.com/)
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
- **FastAPI Core**: Transición de Flask a FastAPI (`main.py`) activada para endpoints de IA asincrónicos, preparándose para soporte WebSocket nativo de alta concurrencia.
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
- Sistema anti-detección con `undetected-chromedriver`

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
- Recordatorios de follow-up para postulaciones con fecha vencida
- Digest de nuevas ofertas encontradas
- Resumen semanal de actividad (postulaciones, entrevistas, tasa de respuesta)
- Template HTML premium en dark mode

### ⚡ **Rendimiento y Modo Offline (PWA)**
- Soporte para Progressive Web App (PWA) con modo de instalación
- Sistema offline utilizando Service Workers y almacenamiento local en IndexedDB
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
<img src="https://flask.palletsprojects.com/en/2.3.x/_images/flask-logo.png" width="60px" height="60px" alt="Flask" />
<br><strong>Flask 2.3</strong>
<br><sub>Web Framework</sub>
</td>
<td align="center" width="20%">
<img src="https://www.selenium.dev/images/selenium_logo_square_green.png" width="60px" height="60px" alt="Selenium" />
<br><strong>Selenium</strong>
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
- ✅ **Google Chrome** - Para Selenium WebDriver
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

# 3. Instalar dependencias
pip install -r requirements.txt

# 4. Instalar modelo de spaCy (IMPORTANTE)
python -m spacy download en_core_web_sm

# 5. Configurar base de datos MySQL
mysql -u root -p < setup_database.sql

# 6. Configurar variables de entorno
cp .env.example .env
# Editar .env con tus credenciales

# 7. Ejecutar la aplicación
python app.py
```

> [!TIP]
> Para aprovechar el scraping asíncrono con Celery, también ejecutá en terminales separadas:
> ```bash
> # Terminal 2: Celery Worker
> celery -A celery_app worker --loglevel=info -Q scraping,ai_processing
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

# Levanta todo: Flask + MySQL + Redis + Celery + Flower
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

## 📁 Estructura del Proyecto

```
EmpleoIA/
│
├── 📂 scrapers/              # Módulos de web scraping
│   ├── indeed_scraper.py
│   ├── linkedin_scraper.py
│   ├── bumeran_scraper.py
│   └── computrabajo_scraper.py
│
├── 📂 tasks/                 # 🆕 Tareas asíncronas Celery
│   ├── scraping_tasks.py     # Scraping en background
│   ├── ai_tasks.py           # Análisis IA por lotes
│   └── notification_tasks.py # Notificaciones por email
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
├── 📄 app.py                 # Aplicación principal Flask (+ API routes)
├── 📄 ai_engine.py           # 🆕 Motor de IA centralizado (Gemini)
├── 📄 celery_app.py          # 🆕 Configuración de Celery
├── 📄 models.py              # 🆕 Modelos SQLAlchemy ORM
├── 📄 market_analyzer.py     # 🆕 Análisis salarial
├── 📄 notifier.py            # 🆕 Notificaciones por email
├── 📄 resume_parser.py       # Parser de CVs
├── 📄 db_config.py           # Configuración de MySQL
│
├── 📄 requirements.txt       # Dependencias Python
├── 📄 docker-compose.yml     # 🆕 Stack completo con Redis + Celery
├── 📄 setup_database.sql     # Script de BD
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
- ✅ Bumeran (bumeran.com.ar)
- ✅ Computrabajo (ar.computrabajo.com)
- ✅ Click derecho → Guardar en EmpleoIA (cualquier página)

---

## ☁️ Despliegue en la Nube

EmpleoIA incluye infraestructura como código con Terraform para desplegar en **Google Cloud Platform**.

```bash
cd terraform

# Inicializar
terraform init

# Planificar
terraform plan \
  -var="project_id=tu-proyecto-gcp" \
  -var="db_password=tu-password-segura" \
  -var="gemini_api_key=tu-api-key"

# Aplicar
terraform apply
```

Recursos que se crean:
- **Cloud Run**: Flask app con auto-scaling
- **Cloud SQL**: MySQL 8.0 en VPC privada
- **Memorystore**: Redis para Celery
- **Artifact Registry**: Para imágenes Docker
- **Secret Manager**: Para secretos sensibles

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
- **Auto-Apply**: Postulación automática a trabajos "Easy Apply" de LinkedIn
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

- **Web Scraping**: [Selenium](https://www.selenium.dev/) + [undetected-chromedriver](https://github.com/ultrafunkamsterdam/undetected-chromedriver)
- **Framework**: [Flask](https://flask.palletsprojects.com/) + [Flask-SocketIO](https://flask-socketio.readthedocs.io/)
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
