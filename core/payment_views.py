try:
    import stripe
except Exception:  # pragma: no cover - optional dependency
    stripe = None
import logging
from django.conf import settings
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from core.models import Plan, Subscription

logger = logging.getLogger(__name__)

# Configurar API Key de Stripe sólo si está disponible
if stripe is not None:
    stripe.api_key = getattr(settings, 'STRIPE_SECRET_KEY', '')

@login_required
def create_checkout_session(request, plan_slug):
    """
    Genera una sesión de pago en Stripe.
    """
    if stripe is None:
        return JsonResponse({'error': 'Dependencia stripe no está instalada en el servidor'}, status=500)
    if not getattr(stripe, 'api_key', None):
        return JsonResponse({'error': 'Stripe no está configurado en el servidor'}, status=500)

    try:
        plan_db = Plan.objects.get(slug=plan_slug)
        stripe_price_id = settings.STRIPE_PRICE_IDS.get(plan_slug)
        if not stripe_price_id:
            return JsonResponse({'error': f'Configuración de precio faltante para {plan_slug}'}, status=400)

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
    if stripe is None:
        return HttpResponse("Stripe library not installed", status=500)

    payload = request.body
    sig_header = request.META.get('HTTP_STRIPE_SIGNATURE')
    webhook_secret = getattr(settings, 'STRIPE_WEBHOOK_SECRET', '')

    if not sig_header or not webhook_secret:
        return HttpResponse("Webhook no configurado", status=400)

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, webhook_secret
        )
    except ValueError:
        return HttpResponse("Payload inválido", status=400)
    except stripe.error.SignatureVerificationError:
        return HttpResponse("Firma inválida", status=400)

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
                'current_period_end': None
            }
        )
        logger.info(f"Suscripción activada para usuario {user.username} - Plan {plan.name}")
    except Exception as e:
        logger.exception(f"Error procesando suscripción exitosa: {e}")


def _handle_payment_failed(session):
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
