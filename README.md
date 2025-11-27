# ByteNeko Survey System

Sistema de encuestas empresarial desarrollado con Django, optimizado para producción con grandes volúmenes de usuarios.

## 📚 Documentación

**📖 Ver documentación completa**: [`docs/INDEX.md`](docs/INDEX.md)

Toda la documentación del proyecto está en la carpeta [`docs/`](docs/):

- **[INDEX.md](docs/INDEX.md)** - 📑 **Índice completo de documentación**
- **[README.md](docs/README.md)** - Documentación completa del sistema
- **[PROJECT_STRUCTURE.md](docs/PROJECT_STRUCTURE.md)** - Estructura del proyecto
- **[ORGANIZATION_GUIDE.md](docs/ORGANIZATION_GUIDE.md)** - Guía de organización
- **[DEPLOYMENT.md](docs/DEPLOYMENT.md)** - Guía de despliegue
- **[POSTGRESQL_CONFIG.md](docs/POSTGRESQL_CONFIG.md)** - Configuración PostgreSQL
- **[PRODUCTION_OPTIMIZATIONS_SUMMARY.md](docs/PRODUCTION_OPTIMIZATIONS_SUMMARY.md)** - Optimizaciones implementadas
- **[PRODUCTION_READINESS_ANALYSIS.md](docs/PRODUCTION_READINESS_ANALYSIS.md)** - Análisis de producción
- **[REFACTORING_SUMMARY.md](docs/REFACTORING_SUMMARY.md)** - Historial de refactoring

## 🚀 Inicio Rápido

```bash
# Instalar dependencias
pip install -r requirements.txt

# Configurar base de datos
python manage.py migrate

# Crear superusuario
python manage.py createsuperuser

# Ejecutar servidor de desarrollo
python manage.py runserver
```

## 📁 Estructura del Proyecto

```
BytenekoProyect/
├── byteneko/          # Configuración Django
├── core/              # App principal
├── surveys/           # App de encuestas
├── templates/         # Templates HTML
├── static/            # Archivos estáticos
├── tests/             # Tests de integración
├── data/              # Datos de muestra y backups
│   └── samples/       # CSVs de ejemplo
├── scripts/           # Scripts utilitarios
├── docs/              # 📚 Documentación completa
└── logs/              # Logs de aplicación
```

Ver [`docs/PROJECT_STRUCTURE.md`](docs/PROJECT_STRUCTURE.md) para detalles completos.

## 🎯 Características Principales

- ✅ **CRUD completo** de encuestas
- ✅ **Importación CSV** masiva (hasta 100k filas)
- ✅ **Análisis avanzado** con NPS, heatmaps, word clouds
- ✅ **Reportes PDF y PPTX** automáticos
- ✅ **Caché inteligente** con Redis
- ✅ **Tareas asíncronas** con Celery
- ✅ **Optimizado para producción** (200+ usuarios concurrentes)
- ✅ **Rate limiting** y protección DoS
- ✅ **Logging estructurado** y monitoreo

## 🧪 Tests

```bash
# Ejecutar todos los tests
pytest

# Tests específicos
pytest tests/
pytest core/tests/
pytest surveys/tests/

# Con coverage
pytest --cov=. --cov-report=html
```

## 📊 Scripts Útiles

```bash
# Verificar encuestas
python scripts/check_surveys.py

# Listar todas las encuestas
python scripts/listar_encuestas.py

# Despliegue
bash scripts/deploy.sh
```

## 🔧 Tecnologías

- **Backend:** Django 5.0
- **Base de Datos:** PostgreSQL 17
- **Cache:** Redis
- **Tareas:** Celery
- **Frontend:** Bootstrap 5, Chart.js
- **Reportes:** WeasyPrint, python-pptx
- **Análisis:** pandas, wordcloud, seaborn

## 📝 Licencia

Ver documentación completa en [`docs/`](docs/).

## 🤝 Contribuir

1. Fork el proyecto
2. Crea una rama (`git checkout -b feature/AmazingFeature`)
3. Commit cambios (`git commit -m 'Add AmazingFeature'`)
4. Push a la rama (`git push origin feature/AmazingFeature`)
5. Abre un Pull Request

---

**Desarrollado con ❤️ para gestión empresarial de encuestas**
