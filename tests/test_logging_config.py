"""Tests cho src.logging_config — idempotency, level sync, handler count."""

import logging

from src.logging_config import get_logger, setup_logging


class TestSetupLogging:
    def test_idempotent_same_level(self):
        setup_logging("INFO")
        setup_logging("INFO")
        root = logging.getLogger()
        assert len(root.handlers) == 1, "Gọi 2 lần không được tạo duplicate handler"

    def test_idempotent_different_levels(self):
        """Regression: gọi 2 lần với level khác nhau — handler level phải sync."""
        setup_logging("WARNING")
        setup_logging("DEBUG")
        root = logging.getLogger()
        assert len(root.handlers) == 1
        assert root.level == logging.DEBUG
        assert root.handlers[0].level == logging.DEBUG, (
            "Handler level phải được cập nhật khi gọi lại setup_logging"
        )

    def test_no_duplicate_handlers_many_calls(self):
        for level in ("DEBUG", "INFO", "WARNING", "ERROR", "INFO"):
            setup_logging(level)
        assert len(logging.getLogger().handlers) == 1

    def test_invalid_level_falls_back_to_info(self):
        setup_logging("NOT_A_LEVEL")
        root = logging.getLogger()
        assert root.level == logging.INFO


class TestGetLogger:
    def test_returns_logger(self):
        logger = get_logger("test-module")
        assert isinstance(logger, logging.Logger)
        assert logger.name == "test-module"

    def test_same_name_same_logger(self):
        assert get_logger("x") is get_logger("x")
