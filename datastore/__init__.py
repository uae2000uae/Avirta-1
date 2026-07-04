"""Pluggable data-store layer for Avirta (Phase 0 of the state migration).

This package introduces a thin abstraction over where durable data lives so the
storage backend can be swapped without touching call sites. It is intentionally
*additive*: nothing in the app is rewired to use it yet, so runtime behavior is
unchanged until call sites are migrated in later phases.

Backends are selected with the ``STATE_BACKEND`` environment variable:

    STATE_BACKEND=json        # default — read/write the existing JSON files
    STATE_BACKEND=firestore   # Google Cloud Firestore (requires the client lib)

Typical usage (later phases will call these instead of the JSON managers)::

    from datastore import get_question_store
    store = get_question_store()
    for q in store.list_questions():
        ...

See ``docs/STATE_MIGRATION_SCOPE.md`` for the full plan.
"""
from __future__ import annotations

import os
from functools import lru_cache

from .base import QuestionStore, ReportStore, SettingsStore

__all__ = [
    "QuestionStore",
    "ReportStore",
    "SettingsStore",
    "get_backend_name",
    "get_question_store",
    "get_report_store",
    "get_settings_store",
]


def get_backend_name() -> str:
    """Return the configured backend name (defaults to ``json``)."""
    return os.environ.get("STATE_BACKEND", "json").strip().lower() or "json"


def _load_backend_module():
    name = get_backend_name()
    if name == "json":
        from . import json_backend as mod
        return mod
    if name == "firestore":
        from . import firestore_backend as mod
        return mod
    raise ValueError(
        f"Unknown STATE_BACKEND={name!r}; expected 'json' or 'firestore'."
    )


# The store objects are stateless wrappers, so caching one instance per process
# is safe and avoids re-reading configuration on every call.
@lru_cache(maxsize=1)
def get_question_store() -> QuestionStore:
    return _load_backend_module().build_question_store()


@lru_cache(maxsize=1)
def get_report_store() -> ReportStore:
    return _load_backend_module().build_report_store()


@lru_cache(maxsize=1)
def get_settings_store() -> SettingsStore:
    return _load_backend_module().build_settings_store()
