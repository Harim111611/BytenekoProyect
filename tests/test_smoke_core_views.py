import pytest

def test_views_importable():
    import core.views
    assert hasattr(core.views, "__file__")


def test_views_ratelimit_importable():
    import core.views_ratelimit
    assert hasattr(core.views_ratelimit, "__file__")
