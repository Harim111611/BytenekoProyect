# Core Dashboard Templates - Dashboards y Configuración

Este subdirectorio contiene templates para dashboards y páginas de configuración.

## Archivos

- **dashboard.html**: Dashboard principal con KPIs
- **results_dashboard.html**: Dashboard de resultados de encuestas
- **settings.html**: Página de configuración del usuario
- **ratelimit_error.html**: Página de error por límite de velocidad

## dashboard.html

Dashboard principal con:
- KPIs y métricas
- Gráficos de actividad
- Resumen de encuestas
- Acciones rápidas

```html
{% extends "base/base.html" %}

{% block title %}Dashboard{% endblock %}

{% block content %}
  <div class="dashboard">
    <div class="kpis">
      <!-- Métrica 1 -->
      <!-- Métrica 2 -->
    </div>
    <div class="charts">
      <!-- Gráficos -->
    </div>
  </div>
{% endblock %}
```

## results_dashboard.html

Dashboard especializado en resultados:
- Gráficos de distribución
- Estadísticas por encuesta
- Exportar datos
- Filtros avanzados

## settings.html

Configuración de usuario:
- Perfil
- Preferencias
- Privacidad
- Cuenta

## ratelimit_error.html

Error cuando se excede límite de solicitudes:
- Mensaje de error
- Botón de reintento
- Tiempo de espera

## Context

Templates requieren contexto:
```python
context = {
    'user': request.user,
    'surveys': surveys,
    'stats': stats,
    'charts': chart_data,
}
```

## Uso

Desde vista:
```python
def dashboard(request):
    stats = get_user_stats(request.user)
    return render(request, 'core/dashboard/dashboard.html', {
        'stats': stats
    })
```
