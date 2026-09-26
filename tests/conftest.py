"""Wires the shared app into pytest and gives every test a clean database."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest  # noqa: E402

from _support import app, reset_db  # noqa: E402


@pytest.fixture(autouse=True)
def clean_database():
    """Rebuild the schema before each test so ids and counts are predictable."""
    reset_db()


@pytest.fixture
def flask_app():
    return app


@pytest.fixture
def client():
    return app.test_client()
