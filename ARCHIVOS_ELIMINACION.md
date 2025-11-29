# 📁 Archivos Involucrados en la Eliminación de Encuestas

## 🎯 Archivos Principales

### 1. **`surveys/views/crud_views.py`** ⭐ (ARCHIVO PRINCIPAL)
**Función**: Contiene toda la lógica de eliminación

**Contenido**:
- **`_fast_delete_surveys(cursor, survey_ids)`** (línea 21)
  - Función que ejecuta la eliminación SQL optimizada
  - Elimina en orden: QuestionResponse → SurveyResponse → AnswerOption → Question → Survey
  - Usa SQL puro con subconsultas para máxima velocidad
  - Deshabilita temporalmente FK checks en PostgreSQL
  
- **`bulk_delete_surveys_view(request)`** (línea 136)
  - Vista para eliminación múltiple (desde el frontend)
  - Valida permisos del usuario
  - Usa `DisableSignals()` para evitar invalidaciones masivas de caché
  - Llama a `_fast_delete_surveys()` para la eliminación real
  
- **`EncuestaDeleteView`** (línea 260)
  - Vista basada en clase para eliminación individual
  - Usa el template `confirm_delete.html`
  - También usa `_fast_delete_surveys()` internamente

---

### 2. **`surveys/signals.py`** 🔔
**Función**: Maneja la invalidación de caché y deshabilitación de señales

**Contenido**:
- **`DisableSignals`** (línea 33)
  - Context manager para deshabilitar señales durante eliminaciones masivas
  - Evita que se disparen cientos de invalidaciones de caché
  
- **`are_signals_enabled()`** (línea 25)
  - Verifica si las señales están habilitadas
  - Usado por todas las señales para decidir si ejecutarse
  
- **Señales de invalidación de caché**:
  - `invalidate_survey_cache()` (línea 69)
  - `invalidate_question_cache()` (línea 111)
  - `invalidate_response_cache()` (línea 173)
  - `invalidate_question_response_cache()` (línea 217)

---

### 3. **`surveys/urls.py`** 🔗
**Función**: Define las rutas URL para las vistas de eliminación

**Rutas**:
- `path('borrar/<int:pk>/', EncuestaDeleteView.as_view(), name='borrar')` - Eliminación individual
- `path('bulk-delete/', bulk_delete_surveys_view, name='bulk_delete')` - Eliminación múltiple

---

## 🎨 Archivos Frontend

### 4. **`templates/surveys/confirm_delete.html`** 📄
**Función**: Template para confirmar eliminación individual

**Características**:
- Formulario de confirmación
- JavaScript con `fetch()` para eliminación asíncrona
- Timeout de 5 minutos para encuestas grandes
- Manejo de errores mejorado

---

### 5. **`templates/surveys/list.html`** 📋
**Función**: Lista de encuestas con eliminación múltiple

**Características**:
- Botón "Eliminación múltiple" para seleccionar varias encuestas
- JavaScript para manejar selección múltiple
- Función `deleteSelectedBtn.addEventListener()` (línea 817)
  - Envía petición `fetch()` a `/surveys/bulk-delete/`
  - Timeout de 10 minutos
  - Manejo de errores específico

---

## 📦 Archivos de Soporte

### 6. **`surveys/views/__init__.py`** 📤
**Función**: Exporta las vistas para uso en URLs

**Exporta**:
- `bulk_delete_surveys_view`
- `EncuestaDeleteView`

---

### 7. **`surveys/models.py`** 🗄️
**Función**: Define los modelos de base de datos

**Modelos relacionados**:
- `Survey` - La encuesta principal
- `Question` - Preguntas de la encuesta
- `AnswerOption` - Opciones de respuesta
- `SurveyResponse` - Respuestas de usuarios
- `QuestionResponse` - Respuestas individuales a preguntas

---

## 🔄 Flujo de Eliminación

### Eliminación Individual:
```
1. Usuario hace clic en "Eliminar" → confirm_delete.html
2. JavaScript envía fetch() → EncuestaDeleteView.delete()
3. EncuestaDeleteView.delete() → _fast_delete_surveys()
4. _fast_delete_surveys() → Ejecuta SQL crudo
5. Invalidación de caché (una sola vez)
```

### Eliminación Múltiple:
```
1. Usuario selecciona encuestas → list.html
2. JavaScript envía fetch() → bulk_delete_surveys_view()
3. bulk_delete_surveys_view() → Valida permisos
4. bulk_delete_surveys_view() → _fast_delete_surveys()
5. _fast_delete_surveys() → Ejecuta SQL crudo
6. Invalidación de caché (una sola vez)
```

---

## 🎯 Funciones Clave

### `_fast_delete_surveys(cursor, survey_ids)`
**Ubicación**: `surveys/views/crud_views.py:21`

**Qué hace**:
1. Deshabilita FK checks en PostgreSQL (`session_replication_role = 'replica'`)
2. Elimina QuestionResponse (tabla más grande)
3. Elimina SurveyResponse
4. Elimina AnswerOption
5. Elimina Question
6. Elimina Survey
7. Restaura FK checks (`session_replication_role = 'origin'`)

**Por qué es rápido**:
- Usa SQL puro (sin ORM overhead)
- Usa subconsultas (no trae IDs a Python)
- Deshabilita FK checks temporalmente
- Todo en una transacción atómica

---

## 📊 Resumen de Archivos

| Archivo | Función | Líneas Clave |
|---------|---------|--------------|
| `surveys/views/crud_views.py` | Lógica de eliminación | 21, 136, 260 |
| `surveys/signals.py` | Control de señales y caché | 33, 25, 69-249 |
| `surveys/urls.py` | Rutas URL | 28, 30 |
| `templates/surveys/confirm_delete.html` | UI eliminación individual | 34-102 |
| `templates/surveys/list.html` | UI eliminación múltiple | 817-883 |
| `surveys/views/__init__.py` | Exportaciones | 20, 56 |
| `surveys/models.py` | Modelos de BD | - |

---

## 🔍 Para Modificar la Eliminación

### Si quieres cambiar la lógica SQL:
→ Edita `surveys/views/crud_views.py` → función `_fast_delete_surveys()`

### Si quieres cambiar el manejo de caché:
→ Edita `surveys/signals.py` → funciones `invalidate_*_cache()`

### Si quieres cambiar la UI:
→ Edita `templates/surveys/confirm_delete.html` o `templates/surveys/list.html`

### Si quieres cambiar las rutas:
→ Edita `surveys/urls.py`



