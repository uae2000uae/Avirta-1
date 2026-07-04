"""JSON-file backend — wraps the existing on-disk layout.

This backend reads and writes the same files the app uses today:
  - questions:  contents/questions/<category_id>.json   (a JSON array)
  - reports:    questionmanagement/reported_questions/<report_id>.json
  - settings:   contents/admin_controls/<mapped>.json

It exists so call sites can be migrated to the store interface without any
behavior change (this backend is the default). The Firestore backend then
becomes a drop-in swap via ``STATE_BACKEND=firestore``.
"""
from __future__ import annotations

import json
import os
from typing import Any, List, Optional

from .base import QuestionStore, ReportStore, SettingsStore, Record

# Project root = parent directory of this package.
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_QUESTIONS_DIR = os.path.join(_ROOT, "contents", "questions")
_REPORTS_DIR = os.path.join(_ROOT, "questionmanagement", "reported_questions")
_ADMIN_DIR = os.path.join(_ROOT, "contents", "admin_controls")

# Logical settings name -> filename on disk.
_SETTINGS_FILES = {
    "game": "game_settings.json",
    "api": "saved_api_settings.json",
    "model": "model_param_settings.json",
}


def _read_json(path: str, default: Any) -> Any:
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return default


def _write_json(path: str, data: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


class JsonQuestionStore(QuestionStore):
    def __init__(self, questions_dir: str = _QUESTIONS_DIR):
        self.dir = questions_dir

    def _category_path(self, category_id: str) -> str:
        return os.path.join(self.dir, f"{category_id}.json")

    def _load_category(self, category_id: str) -> List[Record]:
        data = _read_json(self._category_path(category_id), [])
        return data if isinstance(data, list) else []

    def categories(self) -> List[str]:
        if not os.path.isdir(self.dir):
            return []
        return sorted(
            os.path.splitext(f)[0]
            for f in os.listdir(self.dir)
            if f.endswith(".json")
        )

    def list_by_category(self, category_id: str, active_only: bool = False) -> List[Record]:
        items = self._load_category(category_id)
        if active_only:
            items = [q for q in items if q.get("active", True)]
        return items

    def list_questions(self, active_only: bool = False) -> List[Record]:
        out: List[Record] = []
        for cat in self.categories():
            out.extend(self.list_by_category(cat, active_only=active_only))
        return out

    def get(self, question_id: str) -> Optional[Record]:
        for q in self.list_questions():
            if q.get("id") == question_id:
                return q
        return None

    def upsert(self, question: Record) -> Record:
        category_id = question.get("category_id")
        if not category_id:
            raise ValueError("question must include 'category_id'")
        items = self._load_category(category_id)
        qid = question.get("id")
        replaced = False
        for i, existing in enumerate(items):
            if qid and existing.get("id") == qid:
                items[i] = question
                replaced = True
                break
        if not replaced:
            items.append(question)
        _write_json(self._category_path(category_id), items)
        return question

    def delete(self, question_id: str) -> bool:
        for cat in self.categories():
            items = self._load_category(cat)
            kept = [q for q in items if q.get("id") != question_id]
            if len(kept) != len(items):
                _write_json(self._category_path(cat), kept)
                return True
        return False


class JsonReportStore(ReportStore):
    def __init__(self, reports_dir: str = _REPORTS_DIR):
        self.dir = reports_dir

    def _path(self, report_id: str) -> str:
        return os.path.join(self.dir, f"{report_id}.json")

    def list_reports(self, status: Optional[str] = None) -> List[Record]:
        if not os.path.isdir(self.dir):
            return []
        out: List[Record] = []
        for f in sorted(os.listdir(self.dir)):
            if not f.endswith(".json"):
                continue
            rec = _read_json(os.path.join(self.dir, f), None)
            if isinstance(rec, dict):
                if status is None or rec.get("status") == status:
                    out.append(rec)
        return out

    def get(self, report_id: str) -> Optional[Record]:
        rec = _read_json(self._path(report_id), None)
        return rec if isinstance(rec, dict) else None

    def upsert(self, report: Record) -> Record:
        rid = report.get("report_id")
        if not rid:
            raise ValueError("report must include 'report_id'")
        _write_json(self._path(rid), report)
        return report

    def delete(self, report_id: str) -> bool:
        path = self._path(report_id)
        if os.path.exists(path):
            os.remove(path)
            return True
        return False


class JsonSettingsStore(SettingsStore):
    def __init__(self, admin_dir: str = _ADMIN_DIR):
        self.dir = admin_dir

    def _path(self, name: str) -> str:
        filename = _SETTINGS_FILES.get(name, f"{name}.json")
        return os.path.join(self.dir, filename)

    def get_all(self, name: str) -> Record:
        data = _read_json(self._path(name), {})
        return data if isinstance(data, dict) else {}

    def get(self, name: str, key: str, default: Any = None) -> Any:
        return self.get_all(name).get(key, default)

    def replace(self, name: str, values: Record) -> Record:
        _write_json(self._path(name), values)
        return values


# --- Factory hooks used by datastore.__init__ ---
def build_question_store() -> QuestionStore:
    return JsonQuestionStore()


def build_report_store() -> ReportStore:
    return JsonReportStore()


def build_settings_store() -> SettingsStore:
    return JsonSettingsStore()
