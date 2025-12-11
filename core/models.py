# Importa modelos adicionales definidos fuera de models.py
from .models_reports import *
# BytenekoProyect/core/models.py
from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

class Plan(models.Model):
    """
    Define los niveles de suscripción del sistema SaaS (ej. Free, Pro).
    """
    name = models.CharField(max_length=50, verbose_name="Nombre del Plan")
    slug = models.SlugField(unique=True, verbose_name="Identificador (Slug)")
    price_monthly = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, verbose_name="Precio Mensual")
    
    # --- Límites del Plan ---
    max_surveys = models.PositiveIntegerField(default=5, verbose_name="Máx. Encuestas Activas")
    max_responses_per_survey = models.PositiveIntegerField(default=100, verbose_name="Máx. Respuestas por Encuesta")
    
    # --- Funcionalidades ---
    includes_advanced_analysis = models.BooleanField(default=False, verbose_name="Incluye Análisis Avanzado")
    includes_pdf_export = models.BooleanField(default=False, verbose_name="Incluye Exportación PDF/PPTX")
    
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} (${self.price_monthly})"

    class Meta:
        verbose_name = "Plan SaaS"
        verbose_name_plural = "Planes SaaS"


class Subscription(models.Model):
    """
    Gestiona la relación entre Usuario y Plan.
    """
    STATUS_ACTIVE = 'active'
    STATUS_CANCELED = 'canceled'
    STATUS_EXPIRED = 'expired'
    STATUS_PAST_DUE = 'past_due'

    STATUS_CHOICES = [
        (STATUS_ACTIVE, 'Activa'),
        (STATUS_CANCELED, 'Cancelada'),
        (STATUS_EXPIRED, 'Expirada'),
        (STATUS_PAST_DUE, 'Pago Pendiente'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='subscription', verbose_name="Usuario")
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT, related_name='subscriptions', verbose_name="Plan Actual")
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_ACTIVE, db_index=True)
    start_date = models.DateTimeField(default=timezone.now, verbose_name="Fecha Inicio")
    current_period_end = models.DateTimeField(null=True, blank=True, verbose_name="Fin del Periodo Actual")
    
    stripe_customer_id = models.CharField(max_length=100, blank=True, null=True, verbose_name="ID Cliente Pasarela")
    stripe_subscription_id = models.CharField(max_length=100, blank=True, null=True, verbose_name="ID Suscripción Pasarela")

    def is_valid(self):
        """Verifica si la suscripción está activa y vigente."""
        return self.status == self.STATUS_ACTIVE and (
            self.current_period_end is None or self.current_period_end > timezone.now()
        )

    def __str__(self):
        return f"Suscripción de {self.user.username} - {self.plan.name}"


class UserProfile(models.Model):
    """
    Perfil extendido para freelancers/consultoras.
    """
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    company_name = models.CharField(max_length=100, blank=True, null=True, verbose_name="Empresa / Consultora")
    phone_number = models.CharField(max_length=20, blank=True, null=True, verbose_name="Teléfono")
    is_onboarded = models.BooleanField(default=False, help_text="¿Ha completado el tour inicial?")

    def __str__(self):
        return f"Perfil de {self.user.username}"

# --- SEÑALES AUTOMÁTICAS ---
@receiver(post_save, sender=User)
def create_user_saas_defaults(sender, instance, created, **kwargs):
    """Asigna perfil y plan gratuito al registrarse."""
    if created:
        UserProfile.objects.create(user=instance)
        # Intentar asignar plan gratuito por defecto
        default_plan = Plan.objects.filter(slug='free').first()
        if default_plan:
            Subscription.objects.create(user=instance, plan=default_plan)