# Usa una imagen oficial de Python que ya tiene Playwright y sus dependencias listas
FROM mcr.microsoft.com/playwright/python:v1.65.1-noble

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

# Copia todo el código fuente del proyecto
COPY . .

# Expone el puerto 5000
EXPOSE 5000

# El comando por defecto para el contenedor web
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "5000"]
