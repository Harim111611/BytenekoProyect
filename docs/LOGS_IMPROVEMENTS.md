# 📋 Mejoras de Logging en ByteNeko

## Resumen de Cambios

Se han implementado mejoras significativas en el sistema de logging para que los logs sean más **legibles, informativos y útiles** durante el desarrollo y depuración.

## 🎯 Cambios Realizados

### 1. **Signals.py - Logs Más Descriptivos**
**Ubicación**: `surveys/signals.py`

**Antes**:
```
Cache invalidated for survey 271 (user: Harim)
Cache invalidated for answer option changes in survey 271
Cache invalidated for answer option changes in survey 271
```

**Ahora**:
```
📊 Encuesta 271 (creada) - Caché invalidada | Usuario: Harim
❓ Pregunta 5 (modificada) en encuesta 271 - Caché invalidada
✅ Opción respuesta 3 (creada) - Encuesta 271 - Caché actualizada
📝 nueva respuesta en encuesta 271 - Caché actualizada
📋 Respuesta a pregunta actualizada en encuesta 271
```

**Cambios**:
- ✅ Añadidos iconos emoji para rápida identificación visual
- ✅ Incluida información de acción (creada/modificada/eliminada)
- ✅ Registra más contexto (usuario, survey ID, acción específica)
- ✅ Logs a nivel INFO (más importantes) en lugar de DEBUG

### 2. **Middleware de Logging - Requests HTTP Mejorados**
**Ubicación**: `core/middleware_logging.py`

**Antes**:
```
[REQ] GET /surveys/list from 192.168.1.1
```

**Ahora**:
```
✅ GET    200 | /surveys/list                         | 0.045s | Harim
❌ POST   500 | /surveys/import-multiple/             | 1.234s | Harim
⚠️ GET    302 | /admin/login/?next=/admin/            | 0.012s | anónimo
```

**Cambios**:
- ✅ Icono según status HTTP (✅ éxito, ⚠️ redireccionamiento, ❌ error)
- ✅ Tiempo de respuesta en segundos
- ✅ Usuario autenticado (o "anónimo")
- ✅ Solo loguea requests relevantes (admin, API, surveys) - evita ruido de estáticos
- ✅ Formatos alineados para mejor legibilidad

### 3. **Configuración de Logging - Formato Mejorado**
**Ubicación**: `byteneko/settings/base.py`

**Nuevo Formato**:
```
{asctime} | {name:30} | {levelname:8} | {funcName:20} | {message}
```

**Ejemplo Real**:
```
2025-12-04 14:30:22 | surveys                    | INFO     | invalidate_survey_cache  | 📊 Encuesta 271 (modificada) - Caché invalidada | Usuario: Harim
```

**Cambios**:
- ✅ Columnas alineadas para escanear fácilmente
- ✅ Timestamp con formato legible
- ✅ Nombre del módulo (30 caracteres)
- ✅ Nivel del log (DEBUG, INFO, WARNING, ERROR)
- ✅ Función que generó el log
- ✅ Mensaje descriptivo con iconos

### 4. **Nuevo Archivo de Log Dedicado**
**Archivo**: `logs/surveys.log`

Antes todos los logs de encuestas iban a `app.log`. Ahora:
- `logs/surveys.log` → Todas las operaciones de encuestas (cambios, caché, invalidaciones)
- Separación clara de responsabilidades
- Más fácil filtrar solo lo que interesa

## 📊 Tabla de Iconos en Logs

| Icono | Contexto | Significado |
|-------|----------|-------------|
| 📊 | Surveys | Cambio en encuesta (crear, modificar) |
| ❓ | Questions | Cambio en pregunta |
| ✅ | AnswerOptions | Opción de respuesta creada/actualizada |
| 📝 | Responses | Nueva respuesta de usuario |
| 📋 | QuestionResponse | Respuesta a pregunta específica |
| ✅ | HTTP 200-299 | Request exitoso |
| ⚠️ | HTTP 300-399 | Redireccionamiento |
| ❌ | HTTP 400-599 | Error en request |

## 🔧 Archivo de Gestión de Logs

**Ubicación**: `scripts/manage_logs.ps1`

Nuevo script PowerShell para gestionar logs fácilmente:

```bash
# Ver logs (interactivo)
.\scripts\manage_logs.ps1 view

# Monitorear en tiempo real
.\scripts\manage_logs.ps1 tail surveys.log

# Estadísticas
.\scripts\manage_logs.ps1 stats

# Archivar logs actuales
.\scripts\manage_logs.ps1 archive

# Limpiar backups rotados
.\scripts\manage_logs.ps1 clean

# Ayuda
.\scripts\manage_logs.ps1 help
```

## 📖 Documentación Actualizada

**Ubicación**: `logs/README.md`

Incluye:
- ✅ Tabla de archivos de log disponibles
- ✅ Significado de cada icono
- ✅ Cómo leer logs (con ejemplos)
- ✅ Cómo monitorear en tiempo real (Windows/Linux)
- ✅ Cómo interpretar operaciones comunes
- ✅ Gestión y limpieza de logs
- ✅ Troubleshooting

## 🚀 Cómo Usar

### Monitorear Durante Desarrollo

```powershell
# Terminal 1: Ejecutar Django
python manage.py runserver

# Terminal 2: Monitorear logs
.\scripts\manage_logs.ps1 tail surveys.log

# Ver cambios en tiempo real con colores
```

### Ver Logs Específicos

```powershell
# Ver últimas 20 líneas
Get-Content logs\surveys.log -Tail 20

# Monitorear solo errores
Get-Content logs\error.log -Tail 50 -Wait

# Buscar una encuesta específica
Select-String "Encuesta 271" logs\surveys.log
```

### Estadísticas

```powershell
# Ver tamaño y cantidad de logs
.\scripts\manage_logs.ps1 stats
```

## 🎯 Beneficios

### Para Desarrolladores
- ✅ Logs mucho más legibles y descriptivos
- ✅ Iconos ayudan a identificar rápidamente tipos de eventos
- ✅ Contexto adicional (usuarios, acciones, tiempos)
- ✅ Herramienta para gestionar logs fácilmente

### Para Debugging
- ✅ Tiempos de respuesta claros (detectar lentitud)
- ✅ Status HTTP inmediato (no necesita leer el mensaje)
- ✅ Caché invalidation tracking (saber qué se recalculó)
- ✅ Separación de logs por módulo

### Para Performance
- ✅ Menos logs de debug repetitivos (creaba ruido)
- ✅ Solo logs relevantes en requests HTTP
- ✅ Logs a archivo con rotación automática

## 📝 Ejemplos de Logs Mejorados

### Crear Encuesta
```
📊 Encuesta 42 (creada) - Caché invalidada | Usuario: Harim
```
→ Sé que se creó completamente, se invalidó caché, usuario es Harim

### Cambiar Opciones de Respuesta
```
✅ Opción respuesta 15 (modificada) - Encuesta 42 - Caché actualizada
```
→ Una opción se modificó, caché de análisis se invalida

### Usuarios Contestando
```
📝 nueva respuesta en encuesta 42 - Caché actualizada
```
→ Alguien respondió, los gráficos necesitarán recalcular

### Request Lento
```
❌ POST   500 | /surveys/analysis/42/                 | 2.456s | Harim
```
→ Tomó 2.5 segundos y falló (500 error). Posible problema de performance

## 🔄 Migración

Si ya tienes logs antiguos en `logs/app.log`:

```powershell
# Archivar los antiguos
.\scripts\manage_logs.ps1 archive

# Limpia backups
.\scripts\manage_logs.ps1 clean
```

## 📌 Próximas Mejoras (Roadmap)

- [ ] Dashboard de logs en web (admin panel)
- [ ] Alertas por email en errors críticos
- [ ] Integración con Sentry para tracking remoto
- [ ] Análisis de performance trends
- [ ] Exportar logs a CSV/JSON para análisis

## 📞 Contacto

Para preguntas sobre logging:
1. Revisar `logs/README.md`
2. Ejecutar `.\scripts\manage_logs.ps1 help`
3. Ver este archivo (LOGS_IMPROVEMENTS.md)
