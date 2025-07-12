import logging
from profanex.filter import logger


def test_debug_mode_sets_logger_level_debug(profanity_filter_debug_fixture):
    assert logger.level == logging.DEBUG


def test_debug_mode_sets_logger_level_info(profanity_filter_fixture):
    assert logger.level == logging.INFO
