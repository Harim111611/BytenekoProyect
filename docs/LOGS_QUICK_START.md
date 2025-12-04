# 🚀 Guía Rápida de Logs Mejorados

## ¿Qué cambió?

Los logs ahora son **MUCHO más legibles**. Antes veías:
```
Cache invalidated for survey 271 (user: Harim)
Cache invalidated for answer option changes in survey 271
```

Ahora ves:
```
📊 Encuesta 271 (modificada) - Caché invalidada | Usuario: Harim
✅ Opción respuesta 3 (creada) - Encuesta 271 - Caché actualizada
```

---

## 📁 Archivos Clave

| Archivo | Cambio |
|---------|--------|
| `surveys/signals.py` | Logs con emojis y más contexto |
| `core/middleware_logging.py` | Logs de HTTP requests con tiempo y status |
| `byteneko/settings/base.py` | Nuevo formato de log `detailed` |
| `logs/surveys.log` | NUEVO - Log dedicado para encuestas |
| `logs/README.md` | Documentación completa |
| `scripts/manage_logs.ps1` | NUEVO - Herramienta para gestionar logs |
| `docs/LOGS_IMPROVEMENTS.md` | Documentación técnica |
| `docs/LOGS_EXAMPLES.md` | Ejemplos antes/después |

---

## 🎯 Comandos Útiles (Windows PowerShell)

### Ver logs en tiempo real
```powershell
Get-Content logs\surveys.log -Tail 30 -Wait
```

### Ver últimas 20 líneas
```powershell
Get-Content logs\app.log -Tail 20
```

### Buscar algo específico
```powershell
Select-String "Encuesta 271" logs\surveys.log
Select-String "❌" logs\app.log  # Solo errores
Select-String "2\." logs\app.log # Solo requests lentos (> 2s)
```

### Usar la herramienta de gestión
```powershell
.\scripts\manage_logs.ps1 view      # Ver interactivamente
.\scripts\manage_logs.ps1 tail      # Monitorear
.\scripts\manage_logs.ps1 stats     # Estadísticas
.\scripts\manage_logs.ps1 clean     # Limpiar backups
```

---

## 📊 Iconos = Significado

- 📊 = Encuesta (crear, modificar, eliminar)
- ❓ = Pregunta
- ✅ = Opción de respuesta / Request exitoso (200-300)
- 📝 = Respuesta de usuario
- 📋 = Respuesta a pregunta específica
- ⚠️ = Redireccionamiento (300-399)
- ❌ = Error (400-599)

---

## 🔍 Troubleshooting: "¿Qué me dicen los logs?"

### ✅ POST 201 | ... | 0.145s | Harim
**Significa**: Se creó exitosamente, tomó 0.145 segundos

### ❌ GET 404 | ... | 0.045s | anónimo
**Significa**: No encontró el recurso, usuario anónimo

### ⚠️ GET 200 | ... | 2.456s | Harim
**Significa**: Exitoso pero LENTO - probablemente recalculando

### 📊 Encuesta 42 (modificada) - Caché invalidada
**Significa**: Se modificó una encuesta, todo análisis se va a recalcular

### 📝 nueva respuesta en encuesta 42
**Significa**: Alguien respondió, gráficos se actualizarán

---

## 💡 Casos de Uso

### "¿Por qué es lenta la página?"
```powershell
# Ver últimas requests lentas
Get-Content logs\app.log -Tail 100 | Select-String -Pattern "[1-9]\.[0-9]{3}s"
```

### "¿Qué cambios se han hecho?"
```powershell
# Ver todas las invalidaciones de caché
Get-Content logs\surveys.log | Select-String "invalidada|actualizada"
```

### "¿Hay errores?"
```powershell
# Ver últimos 50 errores
Get-Content logs\error.log -Tail 50
```

### "¿Cuántos usuarios han respondido?"
```powershell
# Contar respuestas nuevas
Get-Content logs\surveys.log | Select-String "📝 nueva respuesta" | Measure-Object -Line
```

---

## 🎬 Flujo Típico During Development

```powershell
# Terminal 1: Ejecutar servidor
python manage.py runserver

# Terminal 2: Monitorear logs
.\scripts\manage_logs.ps1 tail surveys.log

# (Ahora ves en tiempo real qué hace la aplicación)
```

---

## 📝 Changelog

- ✅ Añadido formato `detailed` para logs
- ✅ Logs con emojis en signals.py
- ✅ Middleware mejorado con tiempos y status
- ✅ Log separado para surveys (surveys.log)
- ✅ Script manage_logs.ps1 para gestión
- ✅ Documentación completa en logs/README.md
- ✅ Ejemplos en docs/LOGS_EXAMPLES.md

---

## 🚀 Próximos Pasos

1. **Ahora**: Usa `.\scripts\manage_logs.ps1 view` para ver los logs
2. **Prueba**: Crea una encuesta y ve los logs actualizarse
3. **Explora**: Modifica preguntas, agrega respuestas, mira los logs
4. **Documenta**: Si hay operación confusa, lee `docs/LOGS_EXAMPLES.md`

---

## 📞 Need Help?

1. Lee `logs/README.md` - Documentación completa
2. Mira `docs/LOGS_EXAMPLES.md` - Ejemplos reales
3. Lee `docs/LOGS_IMPROVEMENTS.md` - Cambios técnicos
4. Ejecuta `.\scripts\manage_logs.ps1 help` - Comandos

---

**¡Listo! Ahora los logs son REALMENTE útiles para debugging.** 🎉
