import pytest

def test_import_logging_utils():
    import core.utils.logging_utils as logging_utils
    assert hasattr(logging_utils, "log_performance")
    assert hasattr(logging_utils, "log_query_count")
    assert hasattr(logging_utils, "log_user_action")
    assert hasattr(logging_utils, "log_security_event")
    assert hasattr(logging_utils, "log_data_change")
    assert hasattr(logging_utils, "StructuredLogger")


def test_structured_logger_smoke():
    from core.utils.logging_utils import StructuredLogger
    logger = StructuredLogger("smoke")
    assert hasattr(logger, "info")
    assert hasattr(logger, "debug")
    assert hasattr(logger, "_format_message")
