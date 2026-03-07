"""Shared test fixtures — ensures DB tables exist before any test runs."""

import sys
sys.path.insert(0, ".")

from app.database import init_db


def pytest_configure(config):
    """Create all database tables once at the start of the test session."""
    init_db()
