"""
Memory Updater — Event 3 handler.

Orchestrates the pipeline for an issues.closed event where the issue carries
the "incident" label:
  1. Scrape the full issue thread (title, body, all comments).
  2. Ask Claude to extract structured lessons from the thread.
  3. Store the lessons as a new embedding in Pinecone.
  4. Update the incident record in SQLite.
  5. Post a confirmation comment on the issue.
"""

import os
from typing import Any, Dict

from dotenv import load_dotenv

from clients import anthropic_client, github_client, pinecone_client
from db import database
from utils.logger import EventLogger

load_dotenv()

log = EventLogger("memory_updater")

GITHUB_REPO_OWNER: str = os.getenv("GITHUB_REPO_OWNER", "owner")
GITHUB_REPO_NAME: str = os.getenv("GITHUB_REPO_NAME", "repo")

_CONFIRMATION_COMMENT = (
    "✅ **Relic.ai has logged this incident to memory.**\n\n"
    "Future risk assessments and triage briefs will reflect these learnings. "
    "The following was extracted and stored:\n\n"
    "- **Root cause** — confirmed and indexed\n"
    "- **Resolution steps** — stored as reusable playbook\n"
    "- **Time to resolution** — used to calibrate ETA estimates\n"
    "- **Affected files** — will increase risk scores for similar future PRs\n\n"
    "*Relic.ai — institutional memory for your codebase*"
)


def _build_incident_id(issue_number: int) -> str:
    """Generate a stable Pinecone vector ID for this incident."""
    repo = f"{GITHUB_REPO_OWNER}/{GITHUB_REPO_NAME}"
    import hashlib
    digest = hashlib.sha256(f"{repo}#{issue_number}".encode()).hexdigest()[:8]
    return f"INC-{digest}"


def _lessons_to_text(title: str, lessons: Dict[str, Any]) -> str:
    """
    Serialise extracted lessons into a single string suitable for embedding.

    Args:
        title:   Issue title.
        lessons: Structured lessons dict from Claude.

    Returns:
        Plain text representation of the lessons.
    """
    parts = [f"Incident: {title}"]
    parts.append(f"Root cause: {lessons.get('root_cause', 'unknown')}")
    for step in lessons.get("resolution_steps", []):
        parts.append(f"Resolution step: {step}")
    for f_path in lessons.get("affected_files", []):
        parts.append(f"Affected file: {f_path}")
    for action in lessons.get("follow_up_actions", []):
        parts.append(f"Follow-up: {action}")
    return "\n".join(parts)


def process_incident_closed(payload: Dict[str, Any]) -> None:
    """
    Full pipeline handler for an issues.closed event with label "incident".

    Runs in a background thread; never raises — all errors are logged.

    Args:
        payload: Raw GitHub webhook payload dict for the issues event.
    """
    issue = payload.get("issue", {})
    issue_number = issue.get("number")
    issue_title = issue.get("title", "Untitled Incident")
    issue_body = issue.get("body") or ""

    log.info("memory_update_start", "Starting memory update for closed incident", issue_number=issue_number)

    try:
        comments = github_client.get_issue_comments(issue_number)
    except Exception as exc:
        log.error("comments_fetch_failed", f"Could not fetch issue comments: {exc}", issue_number=issue_number)
        comments = []

    try:
        lessons = anthropic_client.extract_incident_lessons(issue_title, issue_body, comments)
    except Exception as exc:
        log.error("lessons_extraction_failed", f"Claude lesson extraction failed: {exc}", issue_number=issue_number)
        return

    incident_id = _build_incident_id(issue_number)
    metadata = {
        "title": issue_title,
        "root_cause": lessons.get("root_cause", ""),
        "resolution_summary": "; ".join(lessons.get("resolution_steps", [])),
        "affected_files": lessons.get("affected_files", []),
        "time_to_resolution_minutes": lessons.get("time_to_resolution_minutes", 0),
        "url": (
            f"https://github.com/{GITHUB_REPO_OWNER}/{GITHUB_REPO_NAME}/issues/{issue_number}"
        ),
        "follow_up_actions": lessons.get("follow_up_actions", []),
    }

    lessons_text = _lessons_to_text(issue_title, lessons)

    try:
        pinecone_client.store_incident_memory(incident_id, lessons_text, metadata)
        log.info("memory_stored", "Incident memory stored in Pinecone", incident_id=incident_id)
    except Exception as exc:
        log.error("memory_store_failed", f"Pinecone upsert failed: {exc}", issue_number=issue_number)

    try:
        database.update_incident_resolved(issue_number, lessons)
    except Exception as exc:
        log.error("db_update_failed", f"Failed to update incident in DB: {exc}", issue_number=issue_number)

    try:
        github_client.post_issue_comment(issue_number, _CONFIRMATION_COMMENT)
        log.info("memory_comment_posted", "Memory confirmation comment posted", issue_number=issue_number)
    except Exception as exc:
        log.error("memory_comment_failed", f"Failed to post confirmation comment: {exc}", issue_number=issue_number)

    log.info(
        "memory_update_complete",
        "Memory update complete",
        issue_number=issue_number,
        incident_id=incident_id,
        ttr_minutes=lessons.get("time_to_resolution_minutes"),
    )
