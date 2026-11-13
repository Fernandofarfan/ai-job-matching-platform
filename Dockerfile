# Usa una imagen oficial de Python que ya tiene Playwright y sus dependencias listas
FROM mcr.microsoft.com/playwright/python:v1.42.0-jammy

# Establece el directorio de trabajo
WORKDIR /app

# Dependencias de compilación (se purgan después de instalar los wheels)
RUN apt-get update && apt-get install -y --no-install-recommends \
    default-libmysqlclient-dev \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Actualiza pip
RUN pip install --upgrade pip

# Copia los requerimientos e instálalos
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && apt-get purge -y --auto-remove build-essential default-libmysqlclient-dev \
    && rm -rf /var/lib/apt/lists/*

# Copia todo el código fuente del proyecto
COPY . .

# Entrypoint: alembic upgrade head && uvicorn
RUN chmod +x entrypoint.sh

# Usuario no-root (pwuser viene con la imagen de Playwright)
RUN chown -R pwuser:pwuser /app
USER pwuser

# Expone el puerto 5000
EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=10s --retries=3 --start-period=40s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5000/api/health', timeout=5)"

# El comando por defecto para el contenedor web
CMD ["sh", "./entrypoint.sh"]
