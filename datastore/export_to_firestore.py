"""One-time migration: copy JSON-file data into Firestore.

Reads everything through the JSON backend and writes it through the Firestore
backend, so the two implementations are validated against each other.

Usage:
    pip install google-cloud-firestore
    # Ensure Application Default Credentials + GOOGLE_CLOUD_PROJECT are set.
    python -m datastore.export_to_firestore            # migrate everything
    python -m datastore.export_to_firestore --dry-run  # just report counts

This is idempotent: documents are keyed by id, so re-running overwrites rather
than duplicating. It does NOT delete Firestore docs that are absent from JSON.
"""
from __future__ import annotations

import argparse
import sys

from . import json_backend
from .base import Record


def _count(label: str, items) -> int:
    n = len(items)
    print(f"  {label}: {n}")
    return n


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Export JSON data to Firestore.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Read and count JSON data without writing to Firestore.",
    )
    parser.add_argument(
        "--settings",
        nargs="*",
        default=["game", "api", "model"],
        help="Which settings documents to migrate.",
    )
    args = parser.parse_args(argv)

    # Source: JSON backend (always available).
    src_questions = json_backend.build_question_store()
    src_reports = json_backend.build_report_store()
    src_settings = json_backend.build_settings_store()

    questions = src_questions.list_questions()
    reports = src_reports.list_reports()

    print("Source (JSON) inventory:")
    _count("questions", questions)
    _count("reports", reports)
    settings_docs = {n: src_settings.get_all(n) for n in args.settings}
    for name, doc in settings_docs.items():
        print(f"  settings/{name}: {len(doc)} keys")

    if args.dry_run:
        print("\n--dry-run: nothing written.")
        return 0

    # Destination: Firestore backend (lazy client init happens here).
    from . import firestore_backend

    dst_questions = firestore_backend.build_question_store()
    dst_reports = firestore_backend.build_report_store()
    dst_settings = firestore_backend.build_settings_store()

    print("\nWriting to Firestore...")
    written_q = 0
    for q in questions:
        if q.get("id"):
            dst_questions.upsert(q)
            written_q += 1
    print(f"  questions written: {written_q}")

    written_r = 0
    for r in reports:
        if r.get("report_id"):
            dst_reports.upsert(r)
            written_r += 1
    print(f"  reports written: {written_r}")

    for name, doc in settings_docs.items():
        if doc:
            dst_settings.replace(name, doc)
            print(f"  settings/{name} written")

    # Verify counts round-trip.
    print("\nVerification (Firestore):")
    ok = True
    fq = len(dst_questions.list_questions())
    fr = len(dst_reports.list_reports())
    print(f"  questions in Firestore: {fq} (expected {written_q})")
    print(f"  reports in Firestore:   {fr} (expected {written_r})")
    ok = ok and fq >= written_q and fr >= written_r
    print("\nDONE" if ok else "\nWARNING: counts do not match, review above.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
