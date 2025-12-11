from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

@csrf_exempt
def create_checkout_basic(request):
    if request.method == "GET":
        return JsonResponse({"message": "Checkout endpoint reached."})
    return JsonResponse({"error": "Method not allowed."}, status=405)
