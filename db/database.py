"""
SQLite database wrapper for Relic.ai.

Initialises the schema on first run and exposes read/write operations used by
the engine modules and the dashboard API blueprint.  All JSON columns are
serialised/deserialised transparently so callers always work with Python objects.
"""

import json
import os
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

from utils.logger import EventLogger

load_dotenv()

log = EventLogger("database")

DATABASE_PATH: str = os.getenv("DATABASE_PATH", "./db/relic.db")
SCHEMA_PATH: Path = Path(__file__).parent / "schema.sql"

REPO: str = f"{os.getenv('GITHUB_REPO_OWNER', 'unknown')}/{os.getenv('GITHUB_REPO_NAME', 'unknown')}"


def _get_connection() -> sqlite3.Connection:
    """
    Open and return a SQLite connection with row_factory set to Row.

    Returns:
        A configured sqlite3.Connection instance.
    """
    db_path = Path(DATABASE_PATH)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    """
    Create all tables from schema.sql if they do not yet exist.

    Safe to call multiple times; uses CREATE TABLE IF NOT EXISTS throughout.
    """
    try:
        ddl = SCHEMA_PATH.read_text()
        with _get_connection() as conn:
            conn.executescript(ddl)
        log.info("db_init", "Schema initialised successfully", path=DATABASE_PATH)
    except Exception as exc:
        log.error("db_init_failed", f"Failed to initialise schema: {exc}")
        raise


def log_risk_score(
    pr_number: int,
    score: int,
    reasoning: str,
    high_risk_files: Optional[List[Dict]] = None,
    suggested_actions: Optional[List[str]] = None,
    similar_incidents: Optional[List[Dict]] = None,
) -> int:
    """
    Persist the result of a PR risk analysis.

    Args:
        pr_number:        GitHub PR number.
        score:            Risk score 0-100.
        reasoning:        Plain-English explanation from Claude.
        high_risk_files:  List of file-risk dicts.
        suggested_actions: List of action strings.
        similar_incidents: List of similar incident dicts.

    Returns:
        The new row's primary key id.
    """
    try:
        with _get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO risk_scores
                    (pr_number, repo, score, reasoning, high_risk_files,
                     suggested_actions, similar_incidents)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    pr_number,
                    REPO,
                    score,
                    reasoning,
                    json.dumps(high_risk_files or []),
                    json.dumps(suggested_actions or []),
                    json.dumps(similar_incidents or []),
                ),
            )
            row_id = cursor.lastrowid
            log.info("risk_score_logged", "Risk score persisted", pr_number=pr_number, score=score)
            return row_id
    except Exception as exc:
        log.error("risk_score_log_failed", f"Failed to log risk score: {exc}", pr_number=pr_number)
        raise


def log_incident(
    issue_number: int,
    title: str,
    triage_brief: Optional[Dict] = None,
) -> int:
    """
    Create a new incident record when an incident issue is opened.

    Args:
        issue_number:  GitHub issue number.
        title:         Issue title.
        triage_brief:  Structured triage output from Claude.

    Returns:
        The new row's primary key id.
    """
    try:
        with _get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO incidents (issue_number, repo, title, status, triage_brief)
                VALUES (?, ?, ?, 'open', ?)
                """,
                (issue_number, REPO, title, json.dumps(triage_brief or {})),
            )
            row_id = cursor.lastrowid
            log.info("incident_logged", "Incident persisted", issue_number=issue_number)
            return row_id
    except Exception as exc:
        log.error("incident_log_failed", f"Failed to log incident: {exc}", issue_number=issue_number)
        raise


def update_incident_resolved(
    issue_number: int,
    lessons: Dict[str, Any],
) -> None:
    """
    Mark an incident as closed and store the extracted lessons.

    Args:
        issue_number: GitHub issue number.
        lessons:      Structured lessons dict extracted by Claude.
    """
    try:
        with _get_connection() as conn:
            conn.execute(
                """
                UPDATE incidents
                SET status = 'closed',
                    lessons = ?,
                    resolved_at = datetime('now')
                WHERE issue_number = ? AND repo = ?
                """,
                (json.dumps(lessons), issue_number, REPO),
            )
            log.info("incident_resolved", "Incident marked resolved", issue_number=issue_number)
    except Exception as exc:
        log.error("incident_resolve_failed", f"Failed to update incident: {exc}", issue_number=issue_number)
        raise


def get_recent_risk_scores(limit: int = 50) -> List[Dict[str, Any]]:
    """
    Return the most recent risk score rows as plain dicts.

    Args:
        limit: Maximum number of rows to return (default 50).

    Returns:
        List of dicts with all risk_scores columns; JSON fields are deserialised.
    """
    try:
        with _get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM risk_scores ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [_deserialise_risk_row(dict(r)) for r in rows]
    except Exception as exc:
        log.error("db_read_failed", f"Failed to read risk scores: {exc}")
        return []


def get_all_incidents() -> List[Dict[str, Any]]:
    """
    Return all incident rows as plain dicts.

    Returns:
        List of dicts with all incidents columns; JSON fields are deserialised.
    """
    try:
        with _get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM incidents ORDER BY created_at DESC"
            ).fetchall()
        return [_deserialise_incident_row(dict(r)) for r in rows]
    except Exception as exc:
        log.error("db_read_failed", f"Failed to read incidents: {exc}")
        return []


def get_memory_preview(limit: int = 20) -> Dict[str, Any]:
    """
    Return a count and preview of resolved incidents that have lessons stored.

    Args:
        limit: Max number of preview rows.

    Returns:
        Dict with keys: total (int), memories (list of dicts).
    """
    try:
        with _get_connection() as conn:
            total = conn.execute(
                "SELECT COUNT(*) FROM incidents WHERE status='closed' AND lessons != '{}'",
            ).fetchone()[0]
            rows = conn.execute(
                """
                SELECT * FROM incidents
                WHERE status='closed' AND lessons != '{}'
                ORDER BY resolved_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return {
            "total": total,
            "memories": [_deserialise_incident_row(dict(r)) for r in rows],
        }
    except Exception as exc:
        log.error("db_read_failed", f"Failed to read memory preview: {exc}")
        return {"total": 0, "memories": []}


def clear_all_data() -> None:
    """
    Delete all rows from both tables. Used by the Settings danger zone.

    This is irreversible — caller must confirm intent before invoking.
    """
    try:
        with _get_connection() as conn:
            conn.execute("DELETE FROM risk_scores")
            conn.execute("DELETE FROM incidents")
        log.warning("data_cleared", "All data wiped from database")
    except Exception as exc:
        log.error("data_clear_failed", f"Failed to clear data: {exc}")
        raise


def _deserialise_risk_row(row: Dict[str, Any]) -> Dict[str, Any]:
    for field in ("high_risk_files", "suggested_actions", "similar_incidents"):
        if isinstance(row.get(field), str):
            try:
                row[field] = json.loads(row[field])
            except (json.JSONDecodeError, TypeError):
                row[field] = []
    return row


def _deserialise_incident_row(row: Dict[str, Any]) -> Dict[str, Any]:
    for field in ("triage_brief", "lessons"):
        if isinstance(row.get(field), str):
            try:
                row[field] = json.loads(row[field])
            except (json.JSONDecodeError, TypeError):
                row[field] = {}
    return row


# Initialise schema on import so every module can assume the DB is ready.
init_db()
