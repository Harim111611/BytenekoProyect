import pytest
from core.utils import logging_utils

def test_log_performance_decorator_runs():
    @logging_utils.log_performance(threshold_ms=0.01)
    def fast_func():
        return 42
    assert fast_func() == 42

def test_log_query_count_decorator_runs():
    @logging_utils.log_query_count
    def dummy_func():
        return 1
    assert dummy_func() == 1

def test_log_user_action_runs():
    result = logging_utils.log_user_action("login", True, user_id=1)
    assert result is None

def test_log_security_event_runs():
    result = logging_utils.log_security_event("login_attempt", severity="INFO", user_id=1)
    assert result is None

def test_log_data_change_runs():
    result = logging_utils.log_data_change("User", "update", 1, user_id=1, field="value")
    assert result is None

def test_structured_logger_methods():
    logger = logging_utils.StructuredLogger("test")
    logger.debug("debug", foo=1)
    logger.info("info", bar=2)
    logger.warning("warn", baz=3)
    logger.error("error", qux=4)
    logger.critical("critical", quux=5)
    logger.exception("exception", corge=6)
    assert hasattr(logger, "_format_message")
