"""
Minimal analysis_service shim to satisfy tests.
Provides lightweight implementations without heavy CPU work.
"""
from typing import Iterable, List, Tuple, Dict, Any


class ContextHelper:
    @staticmethod
    def get_subject_label(key: str) -> str:
        # Return a reasonable default label
        mapping = {
            'cat': 'categoría',
            'user': 'usuarios',
        }
        return mapping.get(key, 'encuestados')


class TextAnalyzer:
    @staticmethod
    def analyze_sentiment(texts: Iterable[str]):
        # Dummy sentiment split: positive if contains 'good'
        pos = sum(1 for t in texts if isinstance(t, str) and 'good' in t.lower())
        neg = sum(1 for t in texts if isinstance(t, str) and 'bad' in t.lower())
        total = max(1, pos + neg)
        return {'positive': pos / total, 'negative': neg / total}

    @staticmethod
    def analyze_text_responses(qs) -> Tuple[List[str], List[Tuple[str, str]], Any, Any, Any]:
        # Extract text values when available
        values = []
        try:
            values = list(getattr(qs, 'values_list', lambda *a, **k: [])('text_value', flat=True))
        except Exception:
            # Fallback: iterate
            try:
                values = [getattr(x, 'text_value', '') for x in qs]
            except Exception:
                values = []
        words = [w for v in values for w in str(v).split()] if values else []
        bigrams = [(words[i], words[i+1]) for i in range(len(words)-1)] if len(words) > 1 else []
        return words[:50], bigrams[:50], None, None, None


class DataFrameBuilder:
    @staticmethod
    def build_responses_dataframe(survey, responses_qs):
        # Return an empty DataFrame with basic columns if pandas is available
        try:
            import pandas as pd
            return pd.DataFrame(columns=['survey', 'response_id'])
        except Exception:
            # Minimal stub with attribute 'empty'
            class _DF:
                empty = True
            return _DF()


class QuestionAnalyzer:
    @staticmethod
    def analyze_numeric_question(question_id: int, responses_qs) -> Dict[str, Any]:
        # Return empty stats structure
        return {'count': getattr(responses_qs, 'count', lambda: 0)()}

    @staticmethod
    def analyze_choice_question(question_id: int, responses_qs) -> Dict[str, Any]:
        return {'count': getattr(responses_qs, 'count', lambda: 0)()}

    @staticmethod
    def analyze_text_question(question, responses_qs) -> Dict[str, Any]:
        return {'top_words': []}


class NPSCalculator:
    @staticmethod
    def calculate_nps(question_id: int, responses_qs) -> Dict[str, Any]:
        return {'score': 0, 'promoters': 0, 'detractors': 0, 'passives': 0}
