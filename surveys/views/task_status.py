from celery.result import AsyncResult
from django.http import JsonResponse


def task_status_view(request, task_id):
    r = AsyncResult(str(task_id))

    payload = {
        "task_id": str(task_id),
        "state": r.state,
    }

    if r.successful():
        payload["result"] = r.result
    elif r.failed():
        payload["error"] = str(r.result)

    return JsonResponse(payload, status=200)
