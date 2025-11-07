# Patch BytenekoProyect (v2) – 2025-11-07

Correcciones adicionales + guía para el error **Session data corrupted**.

## Qué se corrige
- `surveys/urls.py`: `name="create_step_3"` (sin `.html`).
- `surveys/views.py`: `redirect("surveys:create_step_3")` (sin `.html`).
- `templates/surveys/create_step_2.html`: `{% url 'surveys:create_step_3' %}`.
- `byteneko/urls.py`: ruta `/favicon.ico` que apunta a `/static/img/favicon.ico` (evita 404).
- `byteneko/settings.py`: variables por entorno + `STATIC_ROOT`.

## Cómo arreglar **Session data corrupted**
Esto pasa cuando la cookie de sesión fue firmada con un `SECRET_KEY` distinto al actual.
Soluciones (cualquiera de estas):
1. Borra las cookies del sitio en tu navegador (recomendado en dev).
2. Ejecuta `python manage.py clearsessions` para limpiar sesiones expiradas o corruptas.
3. Asegura que `DJANGO_SECRET_KEY` en tu `.env` **no cambie** entre ejecuciones en el mismo entorno.

### Pasos sugeridos
```bash
# 1) Actualiza dependencias y carga .env
pip install -r requirements.txt
cp .env.example .env  # si no existe
# edita DJANGO_SECRET_KEY por uno fuerte y mantenlo estable

# 2) Limpia sesiones (opcional pero recomendado si ves el warning)
python manage.py clearsessions

# 3) Levanta el server
python manage.py runserver
```

## Notas
- Si tu `base_dashboard.html` usa enlaces `{% url %}` hacia los pasos, usa siempre los nombres:
  - `surveys:create_step_1`
  - `surveys:create_step_2`
  - `surveys:create_step_3`
- No uses `.html` en los nombres de URL (eso se reserva para nombres de *templates*).
