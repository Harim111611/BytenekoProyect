"""
Lightweight standalone narrative utilities used in tests.
These are simplified implementations to avoid heavy dependencies while
keeping API compatibility for tests.
"""
from dataclasses import dataclass
from typing import List, Dict, Any


@dataclass
class NumericNarrative:
    values: List[float]

    def summarize(self) -> Dict[str, Any]:
        if not self.values:
            return {"min": None, "max": None, "avg": 0}
        v = sorted(self.values)
        return {"min": v[0], "max": v[-1], "avg": sum(v) / len(v)}


@dataclass
class DemographicNarrative:
    categories: List[str]

    def top(self, n: int = 3) -> List[str]:
        from collections import Counter
        return [k for k, _ in Counter(self.categories).most_common(n)]


class TextMiningEngine:
    @staticmethod
    def keywords(texts: List[str], top_n: int = 10) -> List[str]:
        words = []
        for t in texts or []:
            words.extend(str(t).split())
        from collections import Counter
        return [w for w, _ in Counter(words).most_common(top_n)]
