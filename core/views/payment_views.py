import stripe
import logging
from django.conf import settings
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from core.models import Plan, Subscription

logger = logging.getLogger(__name__)

# Configurar API Key de Stripe
stripe.api_key = getattr(settings, 'STRIPE_SECRET_KEY', '')

@login_required
def create_checkout_session(request, plan_slug):
    """
    [Faltante Anteproyecto]: Genera una sesión de pago en Stripe.
    Redirige al usuario a la pasarela segura de Stripe para suscribirse.
    """
    if not stripe.api_key:
        return JsonResponse({'error': 'Stripe no está configurado en el servidor'}, status=500)

    try:
        plan_db = Plan.objects.get(slug=plan_slug)
        
        # Mapeo de slug interno a ID de precio de Stripe
        # Esto debería estar en settings.py o en el modelo Plan
        stripe_price_id = settings.STRIPE_PRICE_IDS.get(plan_slug)
        
        if not stripe_price_id:
            return JsonResponse({'error': f'Configuración de precio faltante para {plan_slug}'}, status=400)

        # Crear sesión de Checkout
        checkout_session = stripe.checkout.Session.create(
            customer_email=request.user.email,
            line_items=[{
                'price': stripe_price_id,
                'quantity': 1,
            }],
            mode='subscription',
            success_url=request.build_absolute_uri('/dashboard/billing?success=true&session_id={CHECKOUT_SESSION_ID}'),
            cancel_url=request.build_absolute_uri('/dashboard/billing?canceled=true'),
            metadata={
                'user_id': request.user.id,
                'plan_slug': plan_slug
            }
        )
        
        return JsonResponse({'url': checkout_session.url})
        
    except Plan.DoesNotExist:
        return JsonResponse({'error': 'Plan no encontrado'}, status=404)
    except Exception as e:
        logger.exception(f"Error creando sesión de Stripe: {e}")
        return JsonResponse({'error': str(e)}, status=500)

@csrf_exempt
def stripe_webhook(request):
    """
    [Faltante Anteproyecto]: Webhook para procesar pagos asíncronos.
    Escucha eventos de Stripe y actualiza la base de datos local.
    """
    payload = request.body
    sig_header = request.META.get('HTTP_STRIPE_SIGNATURE')
    webhook_secret = getattr(settings, 'STRIPE_WEBHOOK_SECRET', '')

    if not sig_header or not webhook_secret:
        return HttpResponse("Webhook no configurado", status=400)

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, webhook_secret
        )
    except ValueError as e:
        return HttpResponse("Payload inválido", status=400)
    except stripe.error.SignatureVerificationError as e:
        return HttpResponse("Firma inválida", status=400)

    # Manejar eventos específicos
    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        _handle_successful_subscription(session)
    
    elif event['type'] == 'invoice.payment_failed':
        session = event['data']['object']
        _handle_payment_failed(session)
        
    elif event['type'] == 'customer.subscription.deleted':
        session = event['data']['object']
        _handle_subscription_cancellation(session)

    return HttpResponse(status=200)

def _handle_successful_subscription(session):
    """Activa la suscripción en la base de datos tras pago exitoso."""
    try:
        user_id = session.get('metadata', {}).get('user_id')
        plan_slug = session.get('metadata', {}).get('plan_slug')
        
        if not user_id or not plan_slug:
            logger.error("Metadata incompleta en sesión de Stripe")
            return

        user = User.objects.get(id=user_id)
        plan = Plan.objects.get(slug=plan_slug)
        
        Subscription.objects.update_or_create(
            user=user,
            defaults={
                'plan': plan,
                'status': Subscription.STATUS_ACTIVE,
                'stripe_customer_id': session.get('customer'),
                'stripe_subscription_id': session.get('subscription'),
                'current_period_end': None # Se podría calcular desde Stripe si es necesario
            }
        )
        logger.info(f"Suscripción activada para usuario {user.username} - Plan {plan.name}")
        
    except Exception as e:
        logger.exception(f"Error procesando suscripción exitosa: {e}")

def _handle_payment_failed(session):
    """Marca la suscripción como pendiente de pago."""
    try:
        customer_id = session.get('customer')
        if customer_id:
            sub = Subscription.objects.filter(stripe_customer_id=customer_id).first()
            if sub:
                sub.status = Subscription.STATUS_PAST_DUE
                sub.save()
                logger.warning(f"Pago fallido para usuario {sub.user.username}")
    except Exception as e:
        logger.error(f"Error manejando fallo de pago: {e}")

def _handle_subscription_cancellation(session):
    """Marca la suscripción como cancelada."""
    try:
        customer_id = session.get('customer')
        if customer_id:
            sub = Subscription.objects.filter(stripe_customer_id=customer_id).first()
            if sub:
                sub.status = Subscription.STATUS_CANCELED
                sub.save()
                logger.info(f"Suscripción cancelada para usuario {sub.user.username}")
    except Exception as e:
        logger.error(f"Error manejando cancelación: {e}")