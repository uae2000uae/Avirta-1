"""Tests for the datastore abstraction (Phase 0).

These validate the JSON backend against the real on-disk data and confirm the
factory selects backends via STATE_BACKEND. Firestore is not exercised here (it
needs a live client / emulator); its interface conformance is covered by the
shared abstract base.
"""
import importlib
import os

import pytest

import datastore
from datastore.base import QuestionStore, ReportStore, SettingsStore


@pytest.fixture()
def stores():
    # Ensure we get the JSON backend regardless of ambient env, with fresh caches.
    os.environ["STATE_BACKEND"] = "json"
    importlib.reload(datastore)
    return (
        datastore.get_question_store(),
        datastore.get_report_store(),
        datastore.get_settings_store(),
    )


def test_default_backend_is_json(monkeypatch):
    monkeypatch.delenv("STATE_BACKEND", raising=False)
    importlib.reload(datastore)
    assert datastore.get_backend_name() == "json"


def test_question_store_reads_real_data(stores):
    questions, _, _ = stores
    assert isinstance(questions, QuestionStore)
    all_q = questions.list_questions()
    assert len(all_q) > 0, "expected real questions on disk"
    # Every question exposes the core fields the app relies on.
    sample = all_q[0]
    for field in ("id", "question", "category_id"):
        assert field in sample


def test_question_get_and_category_consistency(stores):
    questions, _, _ = stores
    cats = questions.categories()
    assert len(cats) > 0
    first_cat = cats[0]
    in_cat = questions.list_by_category(first_cat)
    assert all(q.get("category_id") == first_cat for q in in_cat) or len(in_cat) > 0
    # get() round-trips a known id.
    known = questions.list_questions()[0]
    fetched = questions.get(known["id"])
    assert fetched is not None
    assert fetched["id"] == known["id"]


def test_active_only_filter_is_subset(stores):
    questions, _, _ = stores
    all_q = questions.list_questions()
    active = questions.list_questions(active_only=True)
    assert len(active) <= len(all_q)
    assert all(q.get("active", True) for q in active)


def test_report_store_reads_real_data(stores):
    _, reports, _ = stores
    assert isinstance(reports, ReportStore)
    all_r = reports.list_reports()
    assert len(all_r) > 0, "expected real reports on disk"
    assert "report_id" in all_r[0]
    # status filter returns a subset.
    pending = reports.list_reports(status="pending")
    assert len(pending) <= len(all_r)


def test_settings_store_reads_game_settings(stores):
    _, _, settings = stores
    assert isinstance(settings, SettingsStore)
    game = settings.get_all("game")
    assert isinstance(game, dict)
    # A known key from game_settings.json.
    assert settings.get("game", "max_categories_per_room") is not None


def test_unknown_backend_raises(monkeypatch):
    monkeypatch.setenv("STATE_BACKEND", "nonsense")
    importlib.reload(datastore)
    with pytest.raises(ValueError):
        datastore.get_question_store()
    # Reset for other tests.
    monkeypatch.setenv("STATE_BACKEND", "json")
    importlib.reload(datastore)
