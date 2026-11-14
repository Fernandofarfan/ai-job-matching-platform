# Usa una imagen oficial de Python que ya tiene Playwright y sus dependencias listas
FROM mcr.microsoft.com/playwright/python:v1.65.1-noble@sha256:0ab41a37431309d72b7a26f40ef1fdb464a62740196b2143965a2f59dc090409

# Establece el directorio de trabajo
WORKDIR /app

# Instala dependencias del sistema adicionales si son necesarias
RUN apt-get update && apt-get install -y \
    default-libmysqlclient-dev \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Actualiza pip
RUN pip install --upgrade pip

# Copia los requerimientos e instálalos: pip verifica el hash de cada paquete (requirements.txt
# sale de pip-compile --generate-hashes) y corta si alguno no coincide
COPY requirements.txt .
RUN pip install --no-cache-dir --require-hashes -r requirements.txt

# Copia todo el código fuente del proyecto (queda de root: la app no puede modificar su propio código)
COPY . .

# Commit del build (deploy.yml y release.yml lo pasan): lo muestran /api/health y Sentry
ARG APP_COMMIT=""
ENV APP_COMMIT=${APP_COMMIT}
LABEL org.opencontainers.image.source="https://github.com/Fernandofarfan/ai-job-matching-platform" \
      org.opencontainers.image.revision="${APP_COMMIT}"

# Usuario sin privilegios. UID 1000 es el usuario habitual del host, así los volúmenes ./uploads, ./results, etc.
# de docker compose quedan escribibles; solo esos directorios son del usuario de la app.
ARG APP_UID=1000
ARG APP_GID=1000
RUN mkdir -p uploads results profiles temp logs \
    && chown -R ${APP_UID}:${APP_GID} uploads results profiles temp logs
USER ${APP_UID}:${APP_GID}

# Expone el puerto 5000
EXPOSE 5000

# El comando por defecto para el contenedor web
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "5000"]
