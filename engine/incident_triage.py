"""
Incident Triage Engine — Event 2 handler.

Orchestrates the pipeline for an issues.opened event where the issue carries
the "incident" label:
  1. Extract issue metadata.
  2. Search Pinecone for similar past incidents.
  3. Ask Claude to generate a structured triage brief.
  4. Format and post the brief as the first GitHub issue comment.
  5. Persist the incident to SQLite.
"""

from typing import Any, Dict, List

from clients import anthropic_client, github_client, pinecone_client
from db import database
from utils.logger import EventLogger

log = EventLogger("incident_triage")

_CONFIDENCE_LABEL = {
    "high": "🟢 High",
    "medium": "🟡 Medium",
    "low": "🔴 Low",
}


def _confidence_tier(confidence: float) -> str:
    """Convert a 0.0-1.0 confidence score to a tier label."""
    if confidence >= 0.75:
        return "high"
    if confidence >= 0.5:
        return "medium"
    return "low"


def _format_triage_comment(
    issue: Dict[str, Any],
    brief: Dict[str, Any],
    similar_incidents: List[Dict[str, Any]],
) -> str:
    """
    Render the triage brief as a structured GitHub markdown comment.

    Args:
        issue:            Issue metadata dict.
        brief:            Structured dict from anthropic_client.generate_triage_brief.
        similar_incidents: List of similar incident dicts from Pinecone.

    Returns:
        Markdown string ready to post as a GitHub issue comment.
    """
    confidence = brief.get("confidence", 0.0)
    confidence_pct = int(confidence * 100)
    confidence_tier = _confidence_tier(confidence)
    confidence_label = _CONFIDENCE_LABEL[confidence_tier]
    eta = brief.get("estimated_resolution_minutes", "unknown")

    lines = [
        "## 🔍 Relic.ai Instant Triage Brief",
        "",
        f"> **Root Cause Confidence:** {confidence_label} ({confidence_pct}%)  |  "
        f"**Estimated Resolution:** ~{eta} minutes",
        "",
        "### Most Likely Root Cause",
        "",
        brief.get("likely_cause", "Unable to determine root cause from available context."),
        "",
        "### Recommended Resolution Steps",
        "",
    ]

    for i, step in enumerate(brief.get("resolution_steps", []), 1):
        lines.append(f"{i}. {step}")

    lines += [
        "",
        "### Similar Past Incidents",
        "",
    ]
    for inc in similar_incidents[:3]:
        sim_pct = int(inc.get("similarity_score", 0) * 100)
        url = inc.get("url", "#")
        lines.append(
            f"- [{inc.get('incident_id', 'INC')} — {inc.get('title', '')}]({url}) "
            f"*(similarity: {sim_pct}%, resolved in {inc.get('time_to_resolution_minutes', '?')}m)*"
        )
        lines.append(f"  > {inc.get('root_cause', '')}")
        lines.append("")

    lines += [
        "---",
        "*Relic.ai — institutional memory for your codebase. "
        "When this incident is closed, learnings will be automatically stored to improve future triage.*",
    ]

    return "\n".join(lines)


def process_incident_opened(payload: Dict[str, Any]) -> None:
    """
    Full pipeline handler for an issues.opened event with label "incident".

    Runs in a background thread; never raises — all errors are logged.

    Args:
        payload: Raw GitHub webhook payload dict for the issues event.
    """
    issue = payload.get("issue", {})
    issue_number = issue.get("number")
    issue_title = issue.get("title", "Untitled Incident")
    issue_body = issue.get("body") or ""
    issue_author = issue.get("user", {}).get("login", "unknown")
    issue_labels = [lbl.get("name", "") for lbl in issue.get("labels", [])]

    log.info("incident_triage_start", "Starting incident triage", issue_number=issue_number)

    incident_details = {
        "number": issue_number,
        "title": issue_title,
        "body": issue_body,
        "author": issue_author,
        "labels": issue_labels,
    }

    query_text = f"{issue_title}\n{issue_body}"

    try:
        similar_incidents = pinecone_client.search_similar_incidents(query_text, top_k=5)
    except Exception as exc:
        log.error("pinecone_search_failed", f"Pinecone search failed: {exc}", issue_number=issue_number)
        similar_incidents = []

    try:
        brief = anthropic_client.generate_triage_brief(incident_details, similar_incidents)
    except Exception as exc:
        log.error("triage_brief_failed", f"Claude triage brief failed: {exc}", issue_number=issue_number)
        return

    comment_body = _format_triage_comment(issue, brief, similar_incidents)

    try:
        github_client.post_issue_comment(issue_number, comment_body)
        log.info("triage_comment_posted", "Triage brief posted to GitHub", issue_number=issue_number)
    except Exception as exc:
        log.error("triage_comment_failed", f"Failed to post triage comment: {exc}", issue_number=issue_number)

    try:
        database.log_incident(
            issue_number=issue_number,
            title=issue_title,
            triage_brief=brief,
        )
    except Exception as exc:
        log.error("db_write_failed", f"Failed to persist incident: {exc}", issue_number=issue_number)

    log.info(
        "incident_triage_complete",
        "Incident triage complete",
        issue_number=issue_number,
        confidence=brief.get("confidence"),
        eta_minutes=brief.get("estimated_resolution_minutes"),
    )
