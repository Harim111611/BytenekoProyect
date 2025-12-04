# 🧪 Guía de Prueba - Nuevos Logs

## ¿Qué Vamos a Verificar?

Que los nuevos logs se ven correctamente y son útiles.

---

## 📋 Requisitos Previos

- [ ] Django ejecutándose en `python manage.py runserver`
- [ ] Acceso a PowerShell (Windows)
- [ ] Permisos para leer archivos en `logs/`

---

## 🚀 Pasos de Prueba

### Paso 1: Verificar que los logs existen

```powershell
# Abrir PowerShell
ls logs/*.log

# Debería ver:
#   app.log
#   error.log
#   security.log
#   performance.log
#   surveys.log    ← NUEVO
#   server.log     ← Posible
```

### Paso 2: Ver contenido de logs (formato nuevo)

```powershell
# Ver últimas 10 líneas de surveys.log
Get-Content logs\surveys.log -Tail 10

# Debería ver algo como:
# 2025-12-04 14:30:22 | surveys | INFO | invalidate_survey_cache | 📊 Encuesta 271 (modificada) - Caché invalidada | Usuario: Harim
```

### Paso 3: Crear una encuesta de prueba

En el navegador:
1. Ve a `http://localhost:8000/surveys/list`
2. Haz clic en "Crear Encuesta"
3. Completa el formulario
4. Haz clic en "Guardar"

### Paso 4: Observar logs en tiempo real

```powershell
# Monitorear logs de surveys mientras haces cambios
Get-Content logs\surveys.log -Tail 20 -Wait

# Verás algo como:
# ✅ Opción respuesta 1 (creada) - Encuesta 42 - Caché actualizada
# ✅ Opción respuesta 2 (creada) - Encuesta 42 - Caché actualizada
# 📊 Encuesta 42 (creada) - Caché invalidada | Usuario: Harim
```

### Paso 5: Ver logs de HTTP requests

```powershell
# Ver último app.log (requests HTTP)
Get-Content logs\app.log -Tail 20

# Debería ver:
# ✅ POST   201 | /surveys/create/                     | 0.145s | Harim
# ✅ GET    200 | /surveys/list                        | 0.087s | Harim
```

### Paso 6: Usar la herramienta de gestión

```powershell
# Ver menú interactivo
.\scripts\manage_logs.ps1 view

# Sigue las instrucciones
# 1. Elige archivo de log
# 2. Elige cuántas líneas ver
# 3. Disfruta los logs legibles
```

### Paso 7: Ver estadísticas

```powershell
# Ver tamaño y cantidad de logs
.\scripts\manage_logs.ps1 stats

# Debería mostrar:
#   app.log (X MB | Y líneas)
#   error.log (X MB | Y líneas)
#   surveys.log (X MB | Y líneas)
#   Total: X MB
```

### Paso 8: Monitorear en tiempo real

```powershell
# Monitor de logs mientras usas la aplicación
.\scripts\manage_logs.ps1 tail surveys.log

# Ahora haz algo en la aplicación y verás en tiempo real:
# 📊 Encuesta 42 (modificada) - Caché invalidada
# ✅ Opción respuesta 5 (actualizada)
```

---

## ✅ Checklist de Validación

- [ ] Existe archivo `logs/surveys.log`
- [ ] Los logs tienen formato: `timestamp | module | level | function | message`
- [ ] Los logs tienen emojis (📊 ❓ ✅ 📝 📋)
- [ ] Los logs de HTTP requests muestran status y tiempo
- [ ] El script `manage_logs.ps1 view` funciona
- [ ] El script `manage_logs.ps1 tail` monitorea en vivo
- [ ] El script `manage_logs.ps1 stats` muestra estadísticas
- [ ] Los logs son más legibles que antes

---

## 📊 Ejemplos de Lo Que Deberías Ver

### Crear Encuesta
```
📊 Encuesta 42 (creada) - Caché invalidada | Usuario: Harim
✅ POST   201 | /surveys/create/                     | 0.145s | Harim
```

### Editar Preguntas
```
❓ Pregunta 5 (modificada) en encuesta 42 - Caché invalidada
✅ Opción respuesta 10 (creada) - Encuesta 42 - Caché actualizada
✅ Opción respuesta 11 (creada) - Encuesta 42 - Caché actualizada
✅ PUT    200 | /surveys/42/edit/                    | 0.234s | Harim
```

### Usuario Contestando
```
📝 nueva respuesta en encuesta 42 - Caché actualizada
📋 Respuesta a pregunta actualizada en encuesta 42
✅ POST   200 | /surveys/42/respond/                 | 0.089s | anónimo
```

### Algo Lento
```
⚠️ GET    200 | /surveys/analysis/42/                | 2.456s | Harim
```

### Error
```
❌ POST   500 | /surveys/import-multiple/            | 1.234s | Harim
```

---

## 🐛 Troubleshooting

### "No veo logs en surveys.log"
```powershell
# Verificar que el archivo existe y tiene contenido
ls -la logs\surveys.log
(Get-Item logs\surveys.log).Length

# Si está vacío, verifica:
# 1. Que DEBUG=True en settings
# 2. Que hay permisos de escritura en logs/
# 3. Ejecuta: python scripts/test_logging.py
```

### "Los logs no tienen emojis"
```powershell
# Verificar que PowerShell soporta Unicode
$PSVersionTable.PSVersion

# Si es muy vieja (< 5.0), actualizar PowerShell
# O usar Windows Terminal que soporta mejor Unicode
```

### "Las columnas no están alineadas"
```powershell
# Asegúrate de que la ventana es lo suficientemente ancha
# O usa PowerShell con ventana más grande
# Los formatos están diseñados para ~120 caracteres
```

### "El script manage_logs.ps1 no funciona"
```powershell
# Verificar ejecución de scripts
Get-ExecutionPolicy

# Si es restrictiva, cambiar a:
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

---

## 📝 Prueba Final

```powershell
# 1. Ejecutar servidor
python manage.py runserver

# 2. En otra terminal, monitorear logs
.\scripts\manage_logs.ps1 tail surveys.log

# 3. En navegador, hacer acciones:
#    - Crear encuesta
#    - Editar preguntas
#    - Ver análisis

# 4. En PowerShell, deberías ver logs aparecer
#    con emojis y formato legible

# 5. ¡Éxito! Los nuevos logs funcionan correctamente
```

---

## 🎯 Casos de Prueba

| Caso | Acción | Qué buscar en logs |
|------|--------|-------------------|
| 1 | Crear encuesta | `📊 Encuesta X (creada)` |
| 2 | Editar encuesta | `📊 Encuesta X (modificada)` |
| 3 | Agregar pregunta | `❓ Pregunta Y (creada)` |
| 4 | Agregar opción | `✅ Opción respuesta Z (creada)` |
| 5 | Eliminar encuesta | `📊 Encuesta X (eliminada)` |
| 6 | Ver lista de encuestas | `✅ GET 200` con tiempo |
| 7 | Importar CSV | `📊 Encuesta X (creada)` múltiple |
| 8 | Usuario responde | `📝 nueva respuesta` |

---

## 📚 Documentación de Referencia

Mientras haces pruebas, puedes revisar:
- `docs/LOGS_QUICK_START.md` - Comandos útiles
- `docs/LOGS_EXAMPLES.md` - Ejemplos de logs reales
- `logs/README.md` - Documentación completa

---

## ✨ Conclusión

Si puedes ver logs con:
- ✅ Emojis descriptivos
- ✅ Formato alineado
- ✅ Tiempos de respuesta
- ✅ Usuarios autenticados
- ✅ Status HTTP claros

**¡Entonces los nuevos logs funcionan perfecto! 🎉**

---

## 🔧 Limpiar Después de Pruebas

```powershell
# Opcional: Limpiar datos de prueba
python manage.py shell
# En el shell:
# >>> from surveys.models import Survey
# >>> Survey.objects.filter(title__contains="prueba").delete()
# >>> exit()

# Opcional: Archivar logs de prueba
.\scripts\manage_logs.ps1 archive
```

---

**¿Tienes preguntas?**
- Revisa `docs/LOGS_QUICK_START.md`
- Lee `logs/README.md` 
- Mira `docs/LOGS_EXAMPLES.md`
