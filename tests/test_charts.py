import pytest
from core.utils.charts import ChartGenerator
import numpy as np

def test_generate_heatmap_runs():
    df = pd.DataFrame(np.random.rand(5, 5))
    result = ChartGenerator.generate_heatmap(df)
    assert isinstance(result, str)
    assert len(result) > 0

def test_generate_nps_chart_runs():
    result = ChartGenerator.generate_nps_chart(5, 3, 2)
    assert isinstance(result, str)
    assert len(result) > 0

def test_generate_vertical_bar_chart_runs():
    labels = ["A", "B", "C"]
    counts = [1, 2, 3]
    result = ChartGenerator.generate_vertical_bar_chart(labels, counts, "Test")
    assert isinstance(result, str)
    assert len(result) > 0

def test_generate_horizontal_bar_chart_runs():
    labels = ["A", "B", "C"]
    counts = [1, 2, 3]
    result = ChartGenerator.generate_horizontal_bar_chart(labels, counts, "Test")
    assert isinstance(result, str)
    assert len(result) > 0
