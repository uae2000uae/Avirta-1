"""Smoke tests covering core routes and the new security hardening.

These are intentionally lightweight — they verify the app boots, key public
routes respond, and the security headers / cookie settings we added are
actually applied. They form a safety net for future refactoring.
"""


def test_app_imports(app):
    """The application object exists and has a secret key configured."""
    assert app is not None
    assert app.secret_key, "secret_key should always be set"


def test_secret_key_is_not_the_old_committed_value(app):
    """Guard against the previously hardcoded secret being reintroduced."""
    assert app.secret_key != "Pud6FwJ5U/maGx3uS36F+Mkxz/FX2W1SxeDNhhtZ"


def test_index_ok(client):
    resp = client.get("/")
    assert resp.status_code == 200


def test_ping_ok(client):
    resp = client.get("/ping")
    assert resp.status_code == 200
    assert b"pong" in resp.data


def test_health_check_ok(client):
    resp = client.get("/_ah/health")
    assert resp.status_code == 200


def test_security_headers_present(client):
    resp = client.get("/")
    assert resp.headers.get("X-Content-Type-Options") == "nosniff"
    assert resp.headers.get("X-Frame-Options") == "SAMEORIGIN"
    assert "Referrer-Policy" in resp.headers
    assert "Strict-Transport-Security" in resp.headers


def test_session_cookie_hardened(app):
    assert app.config["SESSION_COOKIE_HTTPONLY"] is True
    assert app.config["SESSION_COOKIE_SAMESITE"] == "Lax"


def test_unknown_route_returns_404(client):
    resp = client.get("/definitely-not-a-real-route-xyz")
    assert resp.status_code == 404
