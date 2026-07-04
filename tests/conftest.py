"""Shared pytest fixtures for the Avirta test suite."""
import os
import sys

import pytest

# Ensure the project root is importable when tests run from any CWD.
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


@pytest.fixture(scope="session")
def app():
    """Import the Flask app once per test session in testing mode."""
    from app import app as flask_app

    flask_app.config.update(TESTING=True)
    return flask_app


@pytest.fixture()
def client(app):
    """A Flask test client for issuing requests without a real server."""
    return app.test_client()
