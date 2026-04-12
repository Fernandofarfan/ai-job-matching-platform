<div align="center">

# 🤖 EmpleoIA

### *Plataforma Inteligente de Búsqueda de Empleo*

[![Python Version](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![Flask](https://img.shields.io/badge/flask-2.3.3-green.svg)](https://flask.palletsprojects.com/)
[![License](https://img.shields.io/badge/license-MIT-orange.svg)](LICENSE)
[![Status](https://img.shields.io/badge/status-active-success.svg)]()

*Automatizá tu búsqueda laboral con scraping inteligente y optimización de CVs*

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
- [Solución de Problemas](#-solución-de-problemas)
- [Contribuir](#-contribuir)
- [Licencia](#-licencia)
- [Créditos](#-créditos)

---

## 🎯 Descripción

**EmpleoIA** es una plataforma integral de automatización de búsqueda de empleo que combina web scraping inteligente con optimización de currículums. Diseñada para profesionales que buscan optimizar su proceso de búsqueda laboral.

### ¿Qué hace diferente a EmpleoIA?

- ✅ **Scraping sin APIs**: Extrae ofertas de Indeed y LinkedIn sin costos de API
- ✅ **Parsing Inteligente**: Sistema de extracción automática de habilidades y matching con 90%+ de compatibilidad ATS
- ✅ **Gestión Completa**: Desde la búsqueda hasta el seguimiento de postulaciones
- ✅ **100% en Español**: Interfaz completamente localizada para Argentina/Latinoamérica
- ✅ **Open Source**: Código abierto y personalizable

---

## ✨ Características

### 🔍 **Scraping Multi-Plataforma**
- Búsqueda automatizada en **Indeed**, **LinkedIn**, **Bumeran** y **Computrabajo**
- **🚀 Scraper Universal**: Ejecuta Computrabajo y Bumeran simultáneamente con un solo clic
- Filtrado inteligente por habilidades, ubicación y nivel de experiencia
- **Extracción Profunda**: Obtención de enlaces directos de postulación ("Apply URL")
- Exportación a CSV consolidado para análisis posterior
- Sistema anti-detección para scraping confiable

### 🎨 **Experiencia de Usuario (v2.0)**
- **🌙 Dark Mode**: Tema oscuro nativo para reducir fatiga visual
- **⚡ Filtros Dinámicos**: Búsqueda instantánea en resultados
- **📱 Diseño Responsive**: Interfaz moderna adaptada a todos los dispositivos

### 🤖 **Optimización de CVs**
- Generación de currículums adaptados con algoritmos avanzados
- Optimización para sistemas ATS (Applicant Tracking Systems)
- Análisis de compatibilidad con descripciones de trabajo
- Procesamiento por lotes para múltiples aplicaciones

### 📊 **Sistema de Seguimiento (Job Tracker)**
- Tablero Kanban para gestionar postulaciones
- Estados: Guardados → Aplicando → Aplicados → Entrevistando → Negociando → Aceptados
- Notas y recordatorios personalizados
- Métricas de progreso

### 📈 **Analytics y Reportes Avanzados**
- Dashboard interactivo con métricas de embudo (funnels) y tasas de conversión
- Gráficos y visualizaciones (heatmap semanal) integrados con Chart.js
- Extracción de Insights impulsados por reglas avanzadas para mejorar la búsqueda
- Exportación de resultados y postulaciones en formatos profesionales (Excel y PDF)

### ⚡ **Rendimiento y Modo Offline (PWA)**
- Soporte para Progressive Web App (PWA) con modo de instalación
- Sistema offline utilizando Service Workers y almacenamiento local en IndexedDB
- Acceso continuo a las postulaciones guardadas incluso sin conexión a internet

### 👤 **Gestión de Perfiles**
- Soporte para múltiples perfiles profesionales
- Extracción automática de habilidades desde CVs
- Almacenamiento seguro de credenciales
- Historial de postulaciones

### 📝 **Generación de Cartas de Presentación**
- Creación automática personalizada
- Personalización según empresa y puesto
- Plantillas profesionales
- Exportación a DOCX

---

## 🛠 Tecnologías

<table>
<tr>
<td align="center" width="25%">
<img src="https://www.python.org/static/community_logos/python-logo.png" width="60px" height="60px" alt="Python" />
<br><strong>Python 3.12</strong>
<br><sub>Backend</sub>
</td>
<td align="center" width="25%">
<img src="https://flask.palletsprojects.com/en/2.3.x/_images/flask-logo.png" width="60px" height="60px" alt="Flask" />
<br><strong>Flask 2.3</strong>
<br><sub>Web Framework</sub>
</td>
<td align="center" width="25%">
<img src="https://www.selenium.dev/images/selenium_logo_square_green.png" width="60px" height="60px" alt="Selenium" />
<br><strong>Selenium</strong>
<br><sub>Web Scraping</sub>
</td>
<td align="center" width="25%">
<img src="https://www.mysql.com/common/logos/logo-mysql-170x115.png" width="60px" height="60px" alt="MySQL" />
<br><strong>MySQL</strong>
<br><sub>Base de Datos</sub>
</td>
</tr>
<tr>
<td align="center" width="25%">
<img src="https://getbootstrap.com/docs/5.3/assets/brand/bootstrap-logo-shadow.png" width="60px" height="60px" alt="Bootstrap" />
<br><strong>Bootstrap 5</strong>
<br><sub>UI Framework</sub>
</td>
<td align="center" width="25%">
<img src="https://upload.wikimedia.org/wikipedia/commons/6/6a/JavaScript-logo.png" width="60px" height="60px" alt="JavaScript" />
<br><strong>JavaScript</strong>
<br><sub>Frontend</sub>
</td>
<td align="center" width="25%">
<img src="https://www.docker.com/wp-content/uploads/2022/03/vertical-logo-monochromatic.png" width="60px" height="60px" alt="Docker" />
<br><strong>Docker</strong>
<br><sub>Containerización</sub>
</td>
<td align="center" width="25%">
<img src="https://upload.wikimedia.org/wikipedia/commons/8/87/Sql_data_base_with_logo.png" width="60px" height="60px" alt="NLP" />
<br><strong>spaCy NLP</strong>
<br><sub>Parsing</sub>
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
# O ejecutar manualmente:
# CREATE DATABASE job_tracker;
# USE job_tracker;
# (copiar y ejecutar el contenido de setup_database.sql)

# 6. Configurar variables de entorno
cp .env.example .env
# Editar .env con tus credenciales:
# - DB_PASSWORD: Tu contraseña de MySQL
# - (Opcional) Credenciales de Indeed y LinkedIn

# 7. Ejecutar la aplicación
python app.py
```

### Opción 2: Docker

```bash
docker-compose up -d
```

### 🌐 Acceder a la Aplicación

Abrí tu navegador en: **http://localhost:5000**

---

## 📖 Guía de Uso

### 1️⃣ Configuración Inicial

#### Cargar tu Currículum
1. Navegá a **Perfil** en el menú
2. Seleccioná tu tipo de rol (Data Analyst, Software Engineer, etc.)
3. Subí tu CV en formato PDF o DOCX
4. El sistema extraerá automáticamente tus habilidades

### 2️⃣ Buscar Empleos

#### 🔵 LinkedIn
1. Andá a **Buscar Empleos** → Pestaña LinkedIn
2. Ingresá puesto y ubicación
3. **Configurá credenciales en `.env`**:
   ```env
   LINKEDIN_EMAIL=tu_email@ejemplo.com
   LINKEDIN_PASSWORD=tu_password
   ```
4. Hacé clic en **Iniciar Scraper**

#### 🟢 Indeed
1. Andá a **Buscar Empleos** → Pestaña Indeed
2. Ingresá credenciales (o configuralas en `.env`)
3. Seleccioná puesto y ubicación
4. Hacé clic en **Iniciar Scraper**

### 3️⃣ Optimizar Currículums

1. Andá a **Resultados**
2. Seleccioná un archivo CSV
3. Hacé clic en **Optimización por Lotes**
4. Los CVs optimizados se guardan en `temp/resumes/`

### 4️⃣ Seguimiento de Aplicaciones

1. Andá a **Seguimiento**
2. Agregá trabajos desde resultados o manualmente
3. Arrastrá y soltá entre columnas del Kanban
4. Agregá notas y fechas de seguimiento

---

## 📁 Estructura del Proyecto

```
EmpleoIA/
│
├── 📂 scrapers/              # Módulos de web scraping
│   ├── indeed_scraper.py     # Scraper de Indeed
│   ├── linkedin_scraper.py   # Scraper de LinkedIn
│   ├── bumeran_scraper.py   # Scraper de Bumeran
│   └── computrabajo_scraper.py # Scraper de Computrabajo
│
├── 📂 templates/             # Plantillas HTML (Frontend)
│   ├── base.html             # Plantilla base
│   ├── index.html            # Página principal
│   ├── scraper.html          # Interfaz de scraping
│   ├── results.html          # Visualización de resultados
│   ├── job_tracker.html      # Tablero Kanban
│   └── profile.html          # Gestión de perfiles
│
├── 📂 uploads/               # CVs subidos por usuarios
├── 📂 results/               # Datos scrapeados (CSV)
├── 📂 profiles/              # Perfiles de usuario
├── 📂 temp/resumes/          # CVs optimizados generados
├── 📂 logs/                  # Logs de la aplicación
│
├── 📄 app.py                 # Aplicación principal Flask
├── 📄 db_config.py           # Configuración de MySQL
├── 📄 resume_parser.py       # Parser de CVs
│
├── 📄 requirements.txt       # Dependencias Python
├── 📄 setup_database.sql     # Script de BD
├── 📄 .env.example           # Plantilla de configuración
├── 📄 .gitignore             # Archivos ignorados
└── 📄 README.md              # Este archivo
```

---

## ⚙️ Configuración

### Variables de Entorno (.env)

Creá un archivo `.env` en la raíz del proyecto copiando `.env.example`:

```bash
cp .env.example .env
```

Luego editá el archivo `.env` con tus credenciales:

```env
# MySQL Database (OBLIGATORIO)
DB_HOST=127.0.0.1
DB_USER=root
DB_PASSWORD=tu_password_mysql
DB_NAME=job_tracker

# Indeed Scraper - Credenciales de Google (Opcional)
# El scraper de Indeed usa autenticación de Google
INDEED_EMAIL=tu_email_google@gmail.com
INDEED_PASSWORD=tu_password_google

# LinkedIn Credentials (Opcional)
# Podés usar email y contraseña:
LINKEDIN_EMAIL=tu_email@ejemplo.com
LINKEDIN_PASSWORD=tu_password
# O el token li_at (más estable):
LINKEDIN_TOKEN=tu_linkedin_cookie_token

# Bumeran & Computrabajo (Opcional - Para extracción profunda)
BUMERAN_EMAIL=tu_email@ejemplo.com
BUMERAN_PASSWORD=tu_password
COMPUTRABAJO_EMAIL=tu_email@ejemplo.com
COMPUTRABAJO_PASSWORD=tu_password
```

> [!IMPORTANT]
> **Nunca subas el archivo `.env` al repositorio**. Este archivo contiene tus credenciales personales y está incluido en `.gitignore`.

> [!TIP]
> **Verificación en 2 pasos (2FA) para Indeed**: Si tenés 2FA activada en tu cuenta de Google, deberás aprobar el inicio de sesión en tu celular cuando arranque el scraper. Alternativamente, podés crear una [contraseña de aplicación](https://support.google.com/accounts/answer/185833) en tu cuenta de Google.

---

## 🔧 Solución de Problemas

### ❌ Error: "MySQL connection failed"
**Solución:**
```bash
# Verificar que MySQL esté corriendo
mysql -u root -p

# Crear la base de datos manualmente
CREATE DATABASE job_tracker;
```

### ❌ LinkedIn no encuentra empleos
**Causas comunes:**
- Credenciales incorrectas o expiradas
- LinkedIn detectó scraping excesivo (esperar 24h)
- Búsqueda demasiado amplia (ser más específico)

### ❌ Indeed requiere 2FA
**Solución:**
- Desactivar 2FA temporalmente en Indeed
- O usar credenciales de una cuenta sin 2FA

### ❌ Archivos CSV no aparecen
**Solución:**
```bash
# Verificar permisos de carpeta
chmod 755 results/

# Verificar logs
tail -f logs/app.log
```

---

## 🚀 Future Enhancements

### 🔴 En Desarrollo Activo
- **Sistema de Notificaciones**: Alertas por email cuando aparecen nuevos trabajos relevantes
- **Más Plataformas**: Glassdoor, ZipRecruiter, Monster, CareerBuilder

### 🟡 Próximas Funcionalidades
- **Filtros Avanzados**: Rango salarial, tipo de contrato, modalidad remota/híbrida
- **Machine Learning**: Predicción de probabilidad de conseguir entrevista
- **Recomendación de Skills**: Sugerir habilidades para aprender basado en el mercado

### 🟢 Ideas a Largo Plazo
- **Machine Learning**: Predicción de probabilidad de conseguir entrevista
- **Recomendación de Skills**: Sugerir habilidades para aprender basado en el mercado
- **Mobile App**: Aplicación nativa para iOS y Android
- **API REST Pública**: Permitir integraciones de terceros
- **Gamificación**: Sistema de logros y estadísticas personales
- **Integración con Calendarios**: Sincronizar entrevistas con Google Calendar/Outlook
- **Multiidioma**: Soporte completo para inglés y portugués

### 💡 Contribuciones Bienvenidas
¿Tenés una idea para mejorar EmpleoIA? ¡Abrí un [issue](https://github.com/Fernandofarfan/EmpleoIA/issues) o enviá un PR!

Ver [CONTRIBUTING.md](CONTRIBUTING.md) para el roadmap completo y áreas de contribución prioritarias.

---

## 🤝 Contribuir

¡Las contribuciones son bienvenidas! Seguí estos pasos:

1. **Fork** el repositorio
2. Creá una **branch** para tu feature (`git checkout -b feature/AmazingFeature`)
3. **Commit** tus cambios (`git commit -m 'Add: Amazing Feature'`)
4. **Push** a la branch (`git push origin feature/AmazingFeature`)
5. Abrí un **Pull Request**

### Guías de Contribución

- Seguí el estilo de código existente
- Agregá tests para nuevas funcionalidades
- Actualizá la documentación
- Escribí mensajes de commit descriptivos

Ver [CONTRIBUTING.md](CONTRIBUTING.md) para más detalles.

---

## 📝 Licencia

Este proyecto está bajo la Licencia MIT. Ver el archivo [LICENSE](LICENSE) para más detalles.

---

## 👥 Créditos

### Desarrollador

- **Fernando Farfan** - Desarrollo y mantenimiento principal
- GitHub: [@Fernandofarfan](https://github.com/Fernandofarfan)

Proyecto desarrollado desde cero para automatizar la búsqueda de empleo con tecnologías modernas de web scraping y procesamiento inteligente de datos.

### Tecnologías

- **Web Scraping**: [Selenium](https://www.selenium.dev/)
- **Framework**: [Flask](https://flask.palletsprojects.com/)
- **NLP**: [spaCy](https://spacy.io/)
- **UI**: [Bootstrap 5](https://getbootstrap.com/)

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
