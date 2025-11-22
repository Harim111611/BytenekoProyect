# surveys/models.py
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


class Encuesta(models.Model):
    ESTADO_CHOICES = [
        ('draft', 'Borrador'),
        ('active', 'Activa'),
        ('closed', 'Cerrada'),
    ]

    titulo = models.CharField(max_length=255, verbose_name='Title')
    descripcion = models.TextField(null=True, blank=True, verbose_name='Description')

    # Campo abierto para guardar lo que venga del Select o del Input "Otro"
    categoria = models.CharField(
        max_length=100,
        default='General',
        verbose_name='Category'
    )

    estado = models.CharField(
        max_length=10,
        choices=ESTADO_CHOICES,
        default='draft',
        verbose_name='Status'
    )
    creador = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name='Creator', db_index=True)
    objetivo_muestra = models.PositiveIntegerField(default=0, verbose_name='Sample Goal')
    fecha_creacion = models.DateTimeField(auto_now_add=True, verbose_name='Creation Date')
    fecha_modificacion = models.DateTimeField(auto_now=True, verbose_name='Modification Date')

    def __str__(self):
        return self.titulo

    class Meta:
        ordering = ['-fecha_creacion']
        verbose_name = 'Survey'
        verbose_name_plural = 'Surveys'


class Pregunta(models.Model):
    TIPO_CHOICES = [
        ('text', 'Texto libre'),
        ('number', 'Número'),
        ('scale', 'Escala 1-10'),
        ('single', 'Opción única'),
        ('multi', 'Opción múltiple'),
    ]

    encuesta = models.ForeignKey(
        Encuesta,
        on_delete=models.CASCADE,
        related_name='preguntas',
        verbose_name='Survey'
    )
    texto = models.CharField(max_length=500, verbose_name='Text')
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES, verbose_name='Type')
    es_obligatoria = models.BooleanField(default=False, verbose_name='Is Required')
    orden = models.PositiveIntegerField(default=0, verbose_name='Order')

    def __str__(self):
        return self.texto

    class Meta:
        ordering = ['orden']
        verbose_name = 'Question'
        verbose_name_plural = 'Questions'


class OpcionRespuesta(models.Model):
    pregunta = models.ForeignKey(
        Pregunta,
        on_delete=models.CASCADE,
        related_name='opciones',
        verbose_name='Question'
    )
    texto = models.CharField(max_length=255, verbose_name='Text')

    def __str__(self):
        return self.texto

    class Meta:
        verbose_name = 'Answer Option'
        verbose_name_plural = 'Answer Options'


class RespuestaEncuesta(models.Model):
    encuesta = models.ForeignKey(
        Encuesta,
        on_delete=models.CASCADE,
        related_name='respuestas',
        verbose_name='Survey'
    )
    usuario = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name='User'
    )

    creado_en = models.DateTimeField(default=timezone.now, verbose_name='Created At', db_index=True)
    anonima = models.BooleanField(default=False, verbose_name='Anonymous')

    def __str__(self):
        return f"Respuesta a {self.encuesta.titulo} en {self.creado_en.strftime('%Y-%m-%d')}"

    class Meta:
        verbose_name = 'Survey Response'
        verbose_name_plural = 'Survey Responses'


class RespuestaPregunta(models.Model):
    respuesta_encuesta = models.ForeignKey(
        RespuestaEncuesta,
        on_delete=models.CASCADE,
        related_name='respuestas_pregunta',
        verbose_name='Survey Response'
    )
    pregunta = models.ForeignKey(Pregunta, on_delete=models.CASCADE, verbose_name='Question')
    opcion = models.ForeignKey(
        OpcionRespuesta,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name='Selected Option'
    )
    valor_texto = models.TextField(null=True, blank=True, verbose_name='Text Value')
    valor_numerico = models.IntegerField(null=True, blank=True, verbose_name='Numeric Value')

    def __str__(self):
        return f"Respuesta a: {self.pregunta.texto[:30]}..."

    class Meta:
        verbose_name = 'Question Response'
        verbose_name_plural = 'Question Responses'