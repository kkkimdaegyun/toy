"""pytest bootstrap: put the project root on sys.path and expose fixtures."""

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tests.helpers import make_table, started_table   # noqa: E402


@pytest.fixture
def table():
    """A three-player room still sitting in the lobby."""
    return make_table(3)


@pytest.fixture
def started():
    """A three-player room already dealt and in 1차 베팅."""
    return started_table(3)
