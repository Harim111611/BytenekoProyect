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

### 2. Configuración de Variables de Entorno
1. Copia el archivo de ejemplo:
   ```bash
   cp .env.example .env
   ```
   
2. Edita `.env` y configura tus valores:
   ```env
   SECRET_KEY=tu-clave-secreta-aqui
   DEBUG=True
   ALLOWED_HOSTS=localhost,127.0.0.1
   ```

### 3. Dependencias de Python
Clona el repositorio y, desde la carpeta raíz del proyecto, instala las dependencias de Python:

```bash
pip install -r requirements.txt
```

### 4. Dependencias del Sistema (¡Importante!)

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

### 5. Base de Datos
Este proyecto usa PostgreSQL como base de datos principal. Asegúrate de tener PostgreSQL instalado y configurado. Ejecuta las migraciones para crear la base de datos:

```bash
python manage.py migrate
```

### 6. Crear un Superusuario
Para poder acceder al dashboard y crear encuestas, necesitas una cuenta de administrador:

```bash
python manage.py createsuperuser
```

### 7. Ejecutar el Servidor
¡Listo! Inicia el servidor de desarrollo:

```bash
python manage.py runserver
```

Puedes acceder a la aplicación en `http://127.0.0.1:8000/`.

## Arquitectura del Proyecto

### Estructura Modular (Refactorizada Nov 2025)

El proyecto sigue una arquitectura modular con separación clara de responsabilidades:

```
byteneko/
├── core/                      # App principal de reportes y análisis
│   ├── services/              # Lógica de negocio
│   │   ├── analysis_service.py    # Análisis de datos y preguntas
│   │   └── survey_analysis.py     # Servicio principal de análisis
│   ├── reports/               # Generadores de reportes
│   │   ├── pdf_generator.py       # Exportación a PDF
│   │   └── pptx_generator.py      # Exportación a PowerPoint
│   ├── utils/                 # Utilidades reutilizables
│   │   └── charts.py              # Generación de gráficos
│   └── views.py               # Vistas web (solo lógica de presentación)
│
├── surveys/                   # App de encuestas
│   ├── models.py              # Modelos de datos
│   ├── views.py               # Vistas CRUD
│   └── forms.py               # Formularios
│
├── templates/                 # Plantillas HTML
└── static/                    # Archivos estáticos (CSS, JS)
```

### Ventajas de la Arquitectura Actual

- **Modularidad**: Componentes independientes y reutilizables
- **Testabilidad**: Cada servicio puede testearse aisladamente
- **Mantenibilidad**: Cambios localizados sin efectos secundarios
- **Seguridad**: Variables de entorno para configuración sensible + control de permisos
- **Rendimiento**: Optimizaciones de queries con select_related/prefetch_related
- **Robustez**: Validación centralizada y manejo completo de errores

### Optimizaciones de Rendimiento

El proyecto implementa optimizaciones avanzadas de Django ORM:

- **Select Related**: Reduce N+1 queries en ForeignKeys (82% menos queries)
- **Prefetch Related**: Carga anticipada de relaciones inversas (95% menos queries)
- **Bulk Fetching**: Eliminación de queries en bucles (99% menos queries en importaciones)
- **Database Indexes**: 10 índices estratégicos para acelerar consultas

### Sistema de Validación

Validación robusta en todas las operaciones críticas:

- **Validación de Entrada**: Parámetros, fechas, archivos CSV, respuestas de usuarios
- **Control de Permisos**: Solo el creador puede ver/editar sus encuestas
- **Límites de Seguridad**: CSV máx 10MB, texto máx 5000 chars, DataFrame máx 10,000 filas
- **Logging Estructurado**: Registro completo de operaciones y errores con niveles (info/warning/error)
- **Mensajes Amigables**: Errores específicos en español con formato esperado

- **Mensajes Amigables**: $Env:DJANGO_SETTINGS_MODULE = "byteneko.settings"; python manage.py runserver


Para más detalles sobre la refactorización, consulta:
- [REFACTORING.md](REFACTORING.md) - Resumen general de todas las refactorizaciones
- [REFACTORING_3_QUERIES.md](REFACTORING_3_QUERIES.md) - Detalles de optimización de queries
- [REFACTORING_4_VALIDATION.md](REFACTORING_4_VALIDATION.md) - Detalles de validación y manejo de errores

