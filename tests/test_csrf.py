"""Tests for CSRF protection added in the security pass."""
import re


def _get_token(client):
    body = client.get("/").get_data(as_text=True)
    m = re.search(r'<meta name="csrf-token" content="([0-9a-f]{64})"', body)
    return m.group(1) if m else None


def test_csrf_meta_and_script_present(client):
    body = client.get("/").get_data(as_text=True)
    assert 'name="csrf-token"' in body
    assert "js/csrf.js" in body


def test_token_is_64_hex(client):
    assert _get_token(client) is not None


def test_post_without_token_is_rejected(client):
    resp = client.post("/join_room", data={"room_id": "x", "player_name": "y"})
    assert resp.status_code == 400
    assert "CSRF" in resp.get_data(as_text=True)


def test_post_with_header_token_passes_csrf(client):
    token = _get_token(client)
    resp = client.post(
        "/join_room",
        data={"room_id": "x", "player_name": "y"},
        headers={"X-CSRFToken": token},
    )
    # Passes the CSRF gate (would be 400 otherwise); view then redirects/handles.
    assert resp.status_code != 400


def test_post_with_form_field_token_passes_csrf(client):
    token = _get_token(client)
    resp = client.post(
        "/join_room",
        data={"room_id": "x", "player_name": "y", "csrf_token": token},
    )
    assert resp.status_code != 400


def test_get_requests_are_exempt(client):
    assert client.get("/ping").status_code == 200
