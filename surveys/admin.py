# surveys/admin.py
from django.contrib import admin
from .models import Encuesta, Pregunta, OpcionRespuesta, RespuestaEncuesta, RespuestaPregunta

class OpcionInline(admin.TabularInline):
    model = OpcionRespuesta
    extra = 1

class PreguntaInline(admin.TabularInline):
    model = Pregunta
    inlines = [OpcionInline]
    extra = 1

@admin.register(Encuesta)
class EncuestaAdmin(admin.ModelAdmin):
    list_display = ('titulo', 'estado', 'creador', 'fecha_creacion', 'objetivo_muestra')
    list_filter = ('estado', 'creador')
    search_fields = ('titulo', 'descripcion')
    inlines = [PreguntaInline]
    readonly_fields = ('fecha_creacion', 'fecha_modificacion')

@admin.register(Pregunta)
class PreguntaAdmin(admin.ModelAdmin):
    list_display = ('texto', 'encuesta', 'tipo', 'orden')
    list_filter = ('tipo', 'encuesta')
    search_fields = ('texto',)
    inlines = [OpcionInline]

@admin.register(RespuestaEncuesta)
class RespuestaEncuestaAdmin(admin.ModelAdmin):
    list_display = ('id', 'encuesta', 'usuario', 'creado_en', 'anonima')
    list_filter = ('encuesta', 'creado_en', 'anonima')
    readonly_fields = ('creado_en',)