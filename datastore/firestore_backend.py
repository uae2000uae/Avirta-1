"""Firestore backend — durable, multi-instance store.

Collections (see docs/STATE_MIGRATION_SCOPE.md):
    questions/{question_id}
    reports/{report_id}
    settings/{name}          # single doc per logical settings group

The Google client library is imported lazily so that the default JSON backend
works in environments where ``google-cloud-firestore`` is not installed. To use
this backend:

    pip install google-cloud-firestore
    export STATE_BACKEND=firestore
    # Application Default Credentials must be available (they are on Cloud Run).

Nothing imports this module unless STATE_BACKEND=firestore.
"""
from __future__ import annotations

from typing import Any, List, Optional

from .base import QuestionStore, ReportStore, SettingsStore, Record

_QUESTIONS = "questions"
_REPORTS = "reports"
_SETTINGS = "settings"


def _client():
    """Return a Firestore client, importing the lib lazily."""
    try:
        from google.cloud import firestore  # type: ignore
    except ImportError as exc:  # pragma: no cover - depends on env
        raise RuntimeError(
            "STATE_BACKEND=firestore requires the 'google-cloud-firestore' "
            "package. Install it with: pip install google-cloud-firestore"
        ) from exc
    return firestore.Client()


class FirestoreQuestionStore(QuestionStore):
    def __init__(self, client=None):
        self.db = client or _client()
        self.col = self.db.collection(_QUESTIONS)

    def list_questions(self, active_only: bool = False) -> List[Record]:
        query = self.col
        if active_only:
            query = query.where("active", "==", True)
        return [d.to_dict() for d in query.stream()]

    def list_by_category(self, category_id: str, active_only: bool = False) -> List[Record]:
        query = self.col.where("category_id", "==", category_id)
        if active_only:
            query = query.where("active", "==", True)
        return [d.to_dict() for d in query.stream()]

    def get(self, question_id: str) -> Optional[Record]:
        snap = self.col.document(question_id).get()
        return snap.to_dict() if snap.exists else None

    def categories(self) -> List[str]:
        cats = {q.get("category_id") for q in self.list_questions() if q.get("category_id")}
        return sorted(cats)

    def upsert(self, question: Record) -> Record:
        qid = question.get("id")
        if not qid:
            raise ValueError("question must include 'id'")
        self.col.document(qid).set(question)
        return question

    def delete(self, question_id: str) -> bool:
        doc = self.col.document(question_id)
        if doc.get().exists:
            doc.delete()
            return True
        return False


class FirestoreReportStore(ReportStore):
    def __init__(self, client=None):
        self.db = client or _client()
        self.col = self.db.collection(_REPORTS)

    def list_reports(self, status: Optional[str] = None) -> List[Record]:
        query = self.col
        if status is not None:
            query = query.where("status", "==", status)
        return [d.to_dict() for d in query.stream()]

    def get(self, report_id: str) -> Optional[Record]:
        snap = self.col.document(report_id).get()
        return snap.to_dict() if snap.exists else None

    def upsert(self, report: Record) -> Record:
        rid = report.get("report_id")
        if not rid:
            raise ValueError("report must include 'report_id'")
        self.col.document(rid).set(report)
        return report

    def delete(self, report_id: str) -> bool:
        doc = self.col.document(report_id)
        if doc.get().exists:
            doc.delete()
            return True
        return False


class FirestoreSettingsStore(SettingsStore):
    def __init__(self, client=None):
        self.db = client or _client()
        self.col = self.db.collection(_SETTINGS)

    def get_all(self, name: str) -> Record:
        snap = self.col.document(name).get()
        return snap.to_dict() if snap.exists else {}

    def get(self, name: str, key: str, default: Any = None) -> Any:
        return self.get_all(name).get(key, default)

    def replace(self, name: str, values: Record) -> Record:
        self.col.document(name).set(values)
        return values


# --- Factory hooks used by datastore.__init__ ---
def build_question_store() -> QuestionStore:
    return FirestoreQuestionStore()


def build_report_store() -> ReportStore:
    return FirestoreReportStore()


def build_settings_store() -> SettingsStore:
    return FirestoreSettingsStore()
