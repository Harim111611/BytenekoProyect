from django.http import JsonResponse

async def create_checkout_basic(request):
    if request.method == "GET":
        return JsonResponse({"message": "Checkout endpoint reached."})
    return JsonResponse({"error": "Method not allowed."}, status=405)
