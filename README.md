# Software SaaS para Análisis de Estudios de Mercado (BytenekoProyect)

Este proyecto es una plataforma web (Software as a Service) diseñada para la creación, gestión y presentación de estudios de mercado. El sistema reemplaza la necesidad de usar herramientas fragmentadas como Google Forms, Excel y PowerPoint, integrando todo el flujo en una sola aplicación.

## Características Principales

* **Autenticación de Usuarios:** Sistema completo de registro, inicio de sesión y cierre de sesión.
* **Módulo de Encuestas (App `surveys`):**
    * Creación, lectura, actualización y eliminación (CRUD) de encuestas.
    * Creador de encuestas visual basado en JavaScript.
    * Soporte para múltiples tipos de preguntas (texto, número, escala, opción única y múltiple).
    * Página pública para responder encuestas.
    * Dashboard de resultados individuales por encuesta.
    * Importación de respuestas desde archivos `.csv`.
* **Módulo de Reportes (App `core`):**
    * Dashboard principal con KPIs y gráfico dinámico de respuestas (últimos 30 días).
    * Generador de reportes avanzado con filtros por rango de fecha.
    * Exportación de análisis a **PDF** (usando WeasyPrint).
    * Exportación de análisis a **PowerPoint (.pptx)** (usando python-pptx).
    * Vista previa dinámica (AJAX) en la página de reportes.

## Instalación y Puesta en Marcha

### 1. Prerrequisitos
* Python (versión 3.9 o superior)
* `pip` (manejador de paquetes de Python)

### 2. Dependencias de Python
Clona el repositorio y, desde la carpeta raíz del proyecto, instala las dependencias de Python:

```bash
pip install -r requirements.txt
```

### 3. Dependencias del Sistema (¡Importante!)

Este proyecto usa `WeasyPrint` para generar PDFs, el cual depende de la biblioteca **GTK3**.

* **En Linux (Ubuntu/Debian):**
    ```bash
    sudo apt-get install libpango-1.0-0 libharfbuzz0b libpangoft2-1.0-0 libharfbuzz-subset0
    ```
* **En macOS (usando Homebrew):**
    ```bash
    brew install pango
    ```
* **En Windows (¡Requerido!):**
    1.  Cierra cualquier terminal o editor de código.
    2.  Instala **MSYS2** desde [msys2.org](https://www.msys2.org/).
    3.  Abre la terminal de MSYS2 (no la de Windows).
    4.  Ejecuta: `pacman -S mingw-w64-x86_64-pango`
    5.  Añade la carpeta `bin` de MSYS2 a tu `PATH` de Windows. Generalmente está en:
        `C:\msys64\mingw64\bin`
    6.  Reinicia tu computadora o, como mínimo, tu editor (PyCharm/VSCode) para que detecte el nuevo `PATH`.

### 4. Base de Datos
Este proyecto usa SQLite por defecto, por lo que no requiere configuración adicional. Ejecuta las migraciones para crear la base de datos:

```bash
python manage.py migrate
```

### 5. Crear un Superusuario
Para poder acceder al dashboard y crear encuestas, necesitas una cuenta de administrador:

```bash
python manage.py createsuperuser
```

### 6. Ejecutar el Servidor
¡Listo! Inicia el servidor de desarrollo:

```bash
python manage.py runserver
```

Puedes acceder a la aplicación en `http://127.0.0.1:8000/`.