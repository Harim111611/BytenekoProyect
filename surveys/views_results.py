from django.shortcuts import render
from django.utils import timezone

def results_detail(request, survey_id: int):
    # TODO: Replace stub data with real queries to your models.
    # These mirror the metrics in the mockup.
    context = {
        "survey_id": survey_id,
        "now": timezone.now(),
        "kpis": {
            "total_responses": 1750,
            "total_responses_delta": 0.93,   # +93%
            "avg_satisfaction": 7.8,
            "avg_satisfaction_delta": 0.5,   # +0.5 points
            "completion_rate": 0.804,
            "completion_rate_delta": 0.054,  # +5.4%
            "responses_per_day": 250,
            "responses_per_day_delta": 0.47  # +47%
        },
        "top_preferences": [
            {"label": "Agua", "value": 450, "pct": 0.31},
            {"label": "Café", "value": 380, "pct": 0.262},
            {"label": "Refresco", "value": 320, "pct": 0.221},
            {"label": "Té", "value": 180, "pct": 0.124},
            {"label": "Jugo", "value": 120, "pct": 0.083},
        ],
        "status_breakdown": [
            {"label": "Completadas", "value": 1408},
            {"label": "Parciales", "value": 208},
            {"label": "Abandonadas", "value": 134},
        ],
        "trend": {
            "labels": ["15 Oct", "16 Oct", "17 Oct", "18 Oct", "19 Oct", "20 Oct", "21 Oct"],
            "total":   [80, 120, 160, 210, 260, 320, 300],
            "completed":[60, 90, 120, 170, 200, 260, 250],
        },
        "satisfaction_dist": [
            {"range":"1-2", "count":45},
            {"range":"3-4", "count":120},
            {"range":"5-6", "count":380},
            {"range":"7-8", "count":620},
            {"range":"9-10", "count":285},
        ],
        "recent_rows": [
            {"id":"R-001", "date":"21/10/2025", "fav":"Café", "sat":"8/10", "age":"28 años", "state":"Completa"},
            {"id":"R-002", "date":"21/10/2025", "fav":"Agua", "sat":"9/10", "age":"35 años", "state":"Completa"},
            {"id":"R-003", "date":"21/10/2025", "fav":"Té", "sat":"7/10", "age":"42 años", "state":"Completa"},
            {"id":"R-004", "date":"20/10/2025", "fav":"Refresco", "sat":"6/10", "age":"22 años", "state":"Parcial"},
            {"id":"R-005", "date":"20/10/2025", "fav":"Café", "sat":"9/10", "age":"31 años", "state":"Completa"},
            {"id":"R-006", "date":"20/10/2025", "fav":"Agua", "sat":"8/10", "age":"29 años", "state":"Completa"},
            {"id":"R-007", "date":"19/10/2025", "fav":"Jugo", "sat":"7/10", "age":"25 años", "state":"Completa"},
            {"id":"R-008", "date":"19/10/2025", "fav":"Té", "sat":"9/10", "age":"38 años", "state":"Completa"},
        ],
    }
    return render(request, "surveys/results_detail.html", context)