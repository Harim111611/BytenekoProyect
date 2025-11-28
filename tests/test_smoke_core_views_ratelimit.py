import pytest
import importlib

def test_views_ratelimit_importable():
    module = importlib.import_module("core.views_ratelimit")
    assert module is not None
