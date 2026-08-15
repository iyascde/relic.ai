"""
PR Risk Scorer — Event 1 handler.

Orchestrates the full pipeline for a pull_request opened event:
  1. Extract PR metadata and diff.
  2. Search Pinecone for similar past incidents.
  3. Ask Claude to produce a structured risk assessment.
  4. Format and post the assessment as a GitHub PR comment.
  5. Persist the result to SQLite.
"""

import os
from typing import Any, Dict

from dotenv import load_dotenv

from clients import anthropic_client, github_client, pinecone_client
from db import database
from utils.logger import EventLogger

load_dotenv()

log = EventLogger("risk_scorer")

GITHUB_REPO_OWNER: str = os.getenv("GITHUB_REPO_OWNER", "owner")
GITHUB_REPO_NAME: str = os.getenv("GITHUB_REPO_NAME", "repo")

_RISK_EMOJI = {
    "low": "🟢",
    "medium": "🟡",
    "high": "🔴",
}

_RISK_LABEL = {
    "low": "LOW RISK",
    "medium": "MEDIUM RISK",
    "high": "HIGH RISK",
}


def _risk_tier(score: int) -> str:
    """Classify a 0-100 score into low / medium / high."""
    if score < 40:
        return "low"
    if score < 70:
        return "medium"
    return "high"


def _format_pr_comment(
    pr: Dict[str, Any],
    assessment: Dict[str, Any],
    similar_incidents: list,
) -> str:
    """
    Render the risk assessment as a well-formatted GitHub markdown comment.

    Args:
        pr:               PR metadata dict extracted from the webhook payload.
        assessment:       Structured dict returned by anthropic_client.analyze_risk.
        similar_incidents: List of similar incident dicts from Pinecone.

    Returns:
        A markdown string ready to post as a GitHub comment.
    """
    score = assessment.get("score", 0)
    tier = _risk_tier(score)
    emoji = _RISK_EMOJI[tier]
    label = _RISK_LABEL[tier]
    confidence_pct = int(assessment.get("confidence", 0) * 100)

    lines = [
        f"## {emoji} Relic.ai Risk Assessment — {label} ({score}/100)",
        "",
        f"> **Confidence:** {confidence_pct}%  |  **Assessed by:** Relic.ai",
        "",
        "### Why this score?",
        "",
        assessment.get("reasoning", "No reasoning available."),
        "",
        "### High-Risk Files",
        "",
    ]

    for item in assessment.get("high_risk_files", []):
        lines.append(f"- **`{item.get('file', 'unknown')}`** — {item.get('reason', '')}")

    lines += [
        "",
        "### Suggested Actions Before Merging",
        "",
    ]
    for i, action in enumerate(assessment.get("suggested_actions", []), 1):
        lines.append(f"{i}. {action}")

    lines += [
        "",
        "<details>",
        "<summary>📚 Similar Past Incidents That Influenced This Score</summary>",
        "",
    ]
    for inc in similar_incidents:
        sim_pct = int(inc.get("similarity_score", 0) * 100)
        url = inc.get("url", "#")
        lines.append(
            f"- [{inc.get('incident_id', 'INC')} — {inc.get('title', '')}]({url})  "
            f"*(similarity: {sim_pct}%, resolved in {inc.get('time_to_resolution_minutes', '?')}m)*"
        )
        lines.append(f"  > {inc.get('root_cause', '')}")
        lines.append("")

    lines += [
        "</details>",
        "",
        "---",
        "*Relic.ai — institutional memory for your codebase*",
    ]

    return "\n".join(lines)


def process_pr_opened(payload: Dict[str, Any]) -> None:
    """
    Full pipeline handler for a pull_request.opened webhook event.

    Runs in a background thread; never raises — all errors are logged.

    Args:
        payload: The raw GitHub webhook payload dict for the pull_request event.
    """
    pr = payload.get("pull_request", {})
    pr_number = pr.get("number")
    pr_title = pr.get("title", "Untitled PR")
    pr_author = pr.get("user", {}).get("login", "unknown")
    pr_base = pr.get("base", {}).get("ref", "main")
    pr_head = pr.get("head", {}).get("ref", "")
    pr_body = pr.get("body") or ""

    log.info("pr_processing_start", "Starting PR risk assessment", pr_number=pr_number)

    try:
        diff = github_client.get_pr_diff(pr_number)
    except Exception as exc:
        log.error("pr_diff_fetch_failed", f"Could not fetch diff: {exc}", pr_number=pr_number)
        return

    query_text = f"{pr_title}\n{pr_body}\n{diff[:2000]}"

    try:
        similar_incidents = pinecone_client.search_similar_incidents(query_text, top_k=5)
    except Exception as exc:
        log.error("pinecone_search_failed", f"Pinecone search failed: {exc}", pr_number=pr_number)
        similar_incidents = []

    try:
        assessment = anthropic_client.analyze_risk(diff, similar_incidents)
    except Exception as exc:
        log.error("risk_assessment_failed", f"Claude analysis failed: {exc}", pr_number=pr_number)
        return

    score = assessment.get("score", 0)
    pr_meta = {
        "number": pr_number,
        "title": pr_title,
        "author": pr_author,
        "base": pr_base,
        "head": pr_head,
    }
    comment_body = _format_pr_comment(pr_meta, assessment, similar_incidents)

    try:
        github_client.post_pr_comment(pr_number, comment_body)
        log.info("pr_comment_posted", "Risk comment posted to GitHub", pr_number=pr_number, score=score)
    except Exception as exc:
        log.error("pr_comment_post_failed", f"Failed to post comment: {exc}", pr_number=pr_number)

    try:
        database.log_risk_score(
            pr_number=pr_number,
            score=score,
            reasoning=assessment.get("reasoning", ""),
            high_risk_files=assessment.get("high_risk_files", []),
            suggested_actions=assessment.get("suggested_actions", []),
            similar_incidents=similar_incidents,
        )
    except Exception as exc:
        log.error("db_write_failed", f"Failed to persist risk score: {exc}", pr_number=pr_number)

    log.info("pr_processing_complete", "PR risk assessment complete", pr_number=pr_number, score=score)
