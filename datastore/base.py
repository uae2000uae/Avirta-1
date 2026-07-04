"""Abstract store interfaces and shared types for the datastore layer.

These interfaces describe *what* the application needs from durable storage,
independent of *where* the data lives. Concrete backends (JSON files, Firestore)
implement them in ``json_backend.py`` and ``firestore_backend.py``.

The data shapes mirror the existing on-disk JSON so the JSON backend is a
faithful wrapper and the Firestore backend can be a drop-in replacement.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

# A question / report / settings record is a plain dict to match the current
# JSON schema exactly (no premature modeling). Field references:
#   question: type, question, correct_answer, explanation, points, id,
#             category_id, created_at, updated_at, active, use_count
#   report:   report_id, question_id, reported_at, reporter, status
Record = Dict[str, Any]


class QuestionStore(ABC):
    """Read/write access to the question bank."""

    @abstractmethod
    def list_questions(self, active_only: bool = False) -> List[Record]:
        """Return all questions across all categories."""

    @abstractmethod
    def list_by_category(self, category_id: str, active_only: bool = False) -> List[Record]:
        """Return questions for a single category."""

    @abstractmethod
    def get(self, question_id: str) -> Optional[Record]:
        """Return a single question by id, or None."""

    @abstractmethod
    def categories(self) -> List[str]:
        """Return the list of category ids that currently have questions."""

    @abstractmethod
    def upsert(self, question: Record) -> Record:
        """Insert or update a question (keyed by its ``id``). Returns the record."""

    @abstractmethod
    def delete(self, question_id: str) -> bool:
        """Delete a question by id. Returns True if something was removed."""


class ReportStore(ABC):
    """Read/write access to reported questions."""

    @abstractmethod
    def list_reports(self, status: Optional[str] = None) -> List[Record]:
        """Return all reports, optionally filtered by status."""

    @abstractmethod
    def get(self, report_id: str) -> Optional[Record]:
        """Return a single report by id, or None."""

    @abstractmethod
    def upsert(self, report: Record) -> Record:
        """Insert or update a report (keyed by ``report_id``)."""

    @abstractmethod
    def delete(self, report_id: str) -> bool:
        """Delete a report by id. Returns True if something was removed."""


class SettingsStore(ABC):
    """Read/write access to a named settings document (e.g. ``game``)."""

    @abstractmethod
    def get_all(self, name: str) -> Record:
        """Return the full settings dict for ``name`` (empty dict if missing)."""

    @abstractmethod
    def get(self, name: str, key: str, default: Any = None) -> Any:
        """Return a single setting value."""

    @abstractmethod
    def replace(self, name: str, values: Record) -> Record:
        """Replace the whole settings document for ``name``."""
