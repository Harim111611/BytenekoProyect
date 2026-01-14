# Usar una imagen base de Python moderna y soportada
FROM python:3.11-slim-bookworm

# Establecer variables de entorno para evitar prompts interactivos
ENV PYTHONUNBUFFERED 1
ENV PYTHONDONTWRITEBYTECODE 1

# Definir el directorio de trabajo dentro del contenedor
WORKDIR /usr/src/app

# Instalar dependencias del sistema necesarias para PostgreSQL y para WeasyPrint
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    gcc \
    fontconfig \
    fonts-dejavu-core \
    fonts-liberation \
    libcairo2 \
    pango1.0-tools \
    gdk-pixbuf2.0-0 \
    libffi-dev \
    libgdk-pixbuf2.0-0 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libglib2.0-0 \
    libxml2 \
    libxslt1.1 \
    libjpeg-dev \
    libpng-dev \
    shared-mime-info \
    && rm -rf /var/lib/apt/lists/*

# --- Instalar dependencias para compilar extensiones C++ ---
RUN apt-get update && \
    apt-get install -y build-essential python3-dev

# --- Instalar pybind11 antes de compilar la extensión C++ ---
RUN pip install pybind11

# Copiar requirements.txt e instalar dependencias
COPY requirements.txt /usr/src/app/
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

# --- Copiar y compilar el módulo cpp_csv (opcional) ---
COPY tools/cpp_csv /usr/src/app/tools/cpp_csv
WORKDIR /usr/src/app/tools/cpp_csv
RUN pip install . || echo "Warning: cpp_csv module could not be installed"
WORKDIR /usr/src/app

# Copiar el código de la aplicación
COPY . /usr/src/app/

# Copiar y dar permisos al script de entrada
COPY docker-entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# Instalar netcat para verificar conexiones
RUN apt-get update && apt-get install -y netcat-openbsd && rm -rf /var/lib/apt/lists/*

# Exponer el puerto de Django
EXPOSE 8000

# Usar el script de entrada
ENTRYPOINT ["docker-entrypoint.sh"]

# Comando por defecto
CMD ["gunicorn", "byteneko.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "120"]