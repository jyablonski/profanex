from __future__ import annotations

import pytest
from profanex import Filter


@pytest.fixture(scope="module")
def default_filter() -> Filter:
    return Filter()
