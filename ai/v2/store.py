"""Durable v2 analysis results (Issue #116).

Stores what the AI returned, never what the user read: page title/content/searchQuery and the
goal text are reduced to SHA-256 hashes before they reach disk. Rationales are model-written
abstractions already screened by validate_pages.

- window_analysis: one row per analysisId (COMPLETED / UNJUDGEABLE / ANALYSIS_FAILED)
- page_result:     the three page rows of a window, kept for every status so retraction can find them
- page_relevance:  embedding scores reused across overlapping windows (same goal+page+model)

SQLite coordinates workers sharing one local file, like the retraction journal. Any storage
error fails closed with AI_NOT_READY instead of silently skipping persistence or deletion.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
import sqlite3
from pathlib import Path

from v2.contracts import V2Error

SCHEMA_VERSION = 1
STATUSES = ("COMPLETED", "UNJUDGEABLE", "ANALYSIS_FAILED")
LABELS = ("DIRECT", "JUSTIFIED_DETOUR", "UNRELATED")

_MIGRATIONS = {
    1: [
        f"""CREATE TABLE window_analysis (
            analysis_id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            window_id TEXT NOT NULL,
            window_index INTEGER NOT NULL,
            input_fingerprint TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN {STATUSES}),
            error_code TEXT,
            response_json TEXT,
            analyzed_at TEXT,
            updated_at TEXT NOT NULL,
            CHECK ((status = 'COMPLETED') = (response_json IS NOT NULL)))""",
        "CREATE INDEX window_analysis_session ON window_analysis(session_id)",
        f"""CREATE TABLE page_result (
            analysis_id TEXT NOT NULL REFERENCES window_analysis(analysis_id) ON DELETE CASCADE,
            position INTEGER NOT NULL CHECK (position BETWEEN 1 AND 3),
            visit_id TEXT NOT NULL,
            label TEXT CHECK (label IS NULL OR label IN {LABELS}),
            semantic_relevance REAL CHECK (semantic_relevance IS NULL OR semantic_relevance BETWEEN -1 AND 1),
            rationale TEXT,
            PRIMARY KEY (analysis_id, position))""",
        "CREATE INDEX page_result_visit ON page_result(visit_id)",
        """CREATE TABLE page_relevance (
            relevance_key TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            visit_id TEXT NOT NULL,
            embedding_model TEXT NOT NULL,
            semantic_relevance REAL NOT NULL CHECK (semantic_relevance BETWEEN -1 AND 1),
            created_at TEXT NOT NULL)""",
        "CREATE INDEX page_relevance_visit ON page_relevance(visit_id)",
        "CREATE INDEX page_relevance_session ON page_relevance(session_id)",
    ],
}


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _hash(value):
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def relevance_key(session_id, goal_text, visit, embedding_model):
    """Reuse only when the goal, the exact page text and the model are unchanged."""
    page = {k: visit[k] for k in ("title", "content", "searchQuery")}
    return _hash(["v2-relevance.1", session_id, visit["visitId"], _hash(goal_text), _hash(page),
                  embedding_model])


class AnalysisResultStore:
    def __init__(self, path):
        self.path = str(Path(path).resolve())
        fd = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o600)
        os.close(fd)
        os.chmod(self.path, 0o600)
        try:
            with self.connect() as db:
                version = db.execute("PRAGMA user_version").fetchone()[0]
                if version > SCHEMA_VERSION:
                    raise V2Error(503, "AI_NOT_READY")
                for target in range(version + 1, SCHEMA_VERSION + 1):
                    for statement in _MIGRATIONS[target]:
                        db.execute(statement)
                    db.execute(f"PRAGMA user_version = {target}")
        except (sqlite3.Error, OSError):
            raise V2Error(503, "AI_NOT_READY") from None

    @contextmanager
    def connect(self):
        db = sqlite3.connect(Path(self.path).as_uri() + "?mode=rw", uri=True, timeout=5)
        try:
            db.execute("PRAGMA synchronous=FULL")
            db.execute("PRAGMA foreign_keys=ON")
            with db:
                yield db
        finally:
            db.close()

    def _run(self, operation):
        try:
            with self.connect() as db:
                return operation(db)
        except (sqlite3.Error, OSError, TypeError, ValueError):
            raise V2Error(503, "AI_NOT_READY") from None

    # --- reads ---
    def get_analysis(self, analysis_id):
        """(inputFingerprint, status, response|None) or None."""
        row = self._run(lambda db: db.execute(
            "SELECT input_fingerprint, status, response_json FROM window_analysis WHERE analysis_id=?",
            (analysis_id,)).fetchone())
        if row is None:
            return None
        return row[0], row[1], json.loads(row[2]) if row[2] is not None else None

    def get_relevance(self, key):
        row = self._run(lambda db: db.execute(
            "SELECT semantic_relevance FROM page_relevance WHERE relevance_key=?", (key,)).fetchone())
        return None if row is None else row[0]

    def page_results(self, analysis_id):
        return self._run(lambda db: db.execute(
            "SELECT position, visit_id, label, semantic_relevance, rationale FROM page_result "
            "WHERE analysis_id=? ORDER BY position", (analysis_id,)).fetchall())

    # --- writes ---
    def save_completed(self, body, response, embedding_model):
        def write(db):
            db.execute("BEGIN IMMEDIATE")
            self._upsert_window(db, body, "COMPLETED", None, json.dumps(response, ensure_ascii=False),
                                response["analyzedAt"])
            for page in response["pageResults"]:
                db.execute("INSERT INTO page_result VALUES (?, ?, ?, ?, ?, ?)",
                           (body["analysisId"], page["position"], page["visitId"], page["label"],
                            page["semanticRelevance"], page["rationale"]))
            for visit, page in zip(body["visits"], response["pageResults"]):
                db.execute("INSERT OR IGNORE INTO page_relevance VALUES (?, ?, ?, ?, ?, ?)",
                           (relevance_key(body["sessionId"], body["goalText"], visit, embedding_model),
                            body["sessionId"], visit["visitId"], embedding_model,
                            page["semanticRelevance"], _now()))
        self._run(write)

    def save_failure(self, body, status, error_code):
        if status not in STATUSES[1:]:
            raise ValueError("failure status required")

        def write(db):
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute("SELECT status FROM window_analysis WHERE analysis_id=?",
                                  (body["analysisId"],)).fetchone()
            if existing and existing[0] == "COMPLETED":
                return  # A completed receipt is never downgraded by a later failure.
            self._upsert_window(db, body, status, error_code, None, None)
            for visit in body["visits"]:
                db.execute("INSERT INTO page_result (analysis_id, position, visit_id) VALUES (?, ?, ?)",
                           (body["analysisId"], visit["position"], visit["visitId"]))
        self._run(write)

    @staticmethod
    def _upsert_window(db, body, status, error_code, response_json, analyzed_at):
        db.execute("DELETE FROM window_analysis WHERE analysis_id=?", (body["analysisId"],))
        db.execute("INSERT INTO window_analysis VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                   (body["analysisId"], body["sessionId"], body["windowId"], body["windowIndex"],
                    body["inputFingerprint"], status, error_code, response_json, analyzed_at, _now()))

    def delete_retracted(self, session_ids=(), visit_ids=()):
        """Remove every stored result touching a retracted session or visit."""
        sessions, visits = list(set(session_ids)), list(set(visit_ids))

        def delete(db):
            db.execute("BEGIN IMMEDIATE")
            for chunk in _chunks(visits):
                marks = ",".join("?" * len(chunk))
                db.execute(f"DELETE FROM window_analysis WHERE analysis_id IN "
                           f"(SELECT analysis_id FROM page_result WHERE visit_id IN ({marks}))", chunk)
                db.execute(f"DELETE FROM page_relevance WHERE visit_id IN ({marks})", chunk)
            for chunk in _chunks(sessions):
                marks = ",".join("?" * len(chunk))
                db.execute(f"DELETE FROM window_analysis WHERE session_id IN ({marks})", chunk)
                db.execute(f"DELETE FROM page_relevance WHERE session_id IN ({marks})", chunk)
        self._run(delete)


def _chunks(values, size=500):
    for i in range(0, len(values), size):
        yield values[i:i + size]


def result_store_from_env():
    """Persistence is opt-in: AI_V2_RESULT_DB=<path> enables it, unset keeps memory-only receipts."""
    path = os.getenv("AI_V2_RESULT_DB")
    return AnalysisResultStore(path) if path else None
