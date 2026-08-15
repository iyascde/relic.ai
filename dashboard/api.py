"""
Dashboard API blueprint for Relic.ai.

Exposes JSON endpoints consumed by the frontend JavaScript modules and the
Docker healthcheck. All data is read from SQLite via the database module.
"""

import os
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request

from db import database
from utils.logger import EventLogger

log = EventLogger("dashboard_api")

api_bp = Blueprint("api", __name__)

USE_MOCK: bool = os.getenv("USE_MOCK_RESPONSES", "true").lower() == "true"
PINECONE_INDEX_NAME: str = os.getenv("PINECONE_INDEX_NAME", "relic-ai-incidents")
GITHUB_REPO_OWNER: str = os.getenv("GITHUB_REPO_OWNER", "")
GITHUB_REPO_NAME: str = os.getenv("GITHUB_REPO_NAME", "")


@api_bp.route("/api/scores", methods=["GET"])
def get_scores():
    """
    Return the most recent risk score rows.

    Query params:
        limit (int, optional): Max rows to return. Default 50.

    Returns:
        JSON array of risk score objects.
    """
    try:
        limit = int(request.args.get("limit", 50))
        scores = database.get_recent_risk_scores(limit=limit)
        log.info("api_scores", f"Returning {len(scores)} risk scores")
        return jsonify({"scores": scores, "count": len(scores)})
    except Exception as exc:
        log.error("api_scores_failed", f"Error fetching scores: {exc}")
        return jsonify({"error": "Failed to fetch scores"}), 500


@api_bp.route("/api/incidents", methods=["GET"])
def get_incidents():
    """
    Return all incident rows.

    Returns:
        JSON object with 'incidents' array and 'count'.
    """
    try:
        incidents = database.get_all_incidents()
        log.info("api_incidents", f"Returning {len(incidents)} incidents")
        return jsonify({"incidents": incidents, "count": len(incidents)})
    except Exception as exc:
        log.error("api_incidents_failed", f"Error fetching incidents: {exc}")
        return jsonify({"error": "Failed to fetch incidents"}), 500


@api_bp.route("/api/memory", methods=["GET"])
def get_memory():
    """
    Return memory store count and a preview of recent incident memories.

    Returns:
        JSON object with 'total', 'memories' array, and index metadata.
    """
    try:
        result = database.get_memory_preview(limit=20)
        result["index_name"] = PINECONE_INDEX_NAME
        result["mock_mode"] = USE_MOCK
        log.info("api_memory", f"Returning memory preview, total={result['total']}")
        return jsonify(result)
    except Exception as exc:
        log.error("api_memory_failed", f"Error fetching memory: {exc}")
        return jsonify({"error": "Failed to fetch memory"}), 500


@api_bp.route("/api/clear", methods=["POST"])
def clear_data():
    """
    Wipe all rows from both SQLite tables.

    Expects JSON body: {"confirm": true} to prevent accidental calls.

    Returns:
        JSON success/error message.
    """
    body = request.get_json(silent=True) or {}
    if not body.get("confirm"):
        return jsonify({"error": "Must send {confirm: true} to clear data"}), 400
    try:
        database.clear_all_data()
        log.warning("api_clear", "All data cleared via dashboard API")
        return jsonify({"message": "All data cleared successfully"})
    except Exception as exc:
        log.error("api_clear_failed", f"Error clearing data: {exc}")
        return jsonify({"error": "Failed to clear data"}), 500


@api_bp.route("/health", methods=["GET"])
def health():
    """
    System health endpoint used by Docker healthcheck and the dashboard sidebar.

    Returns:
        JSON object with component statuses and current timestamp.
    """
    db_ok = True
    db_error = None
    try:
        database.get_recent_risk_scores(limit=1)
    except Exception as exc:
        db_ok = False
        db_error = str(exc)

    return jsonify(
        {
            "status": "ok" if db_ok else "degraded",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "components": {
                "webhook_server": {"status": "ok"},
                "database": {"status": "ok" if db_ok else "error", "error": db_error},
                "pinecone": {"status": "mock" if USE_MOCK else "live"},
                "anthropic": {"status": "mock" if USE_MOCK else "live"},
                "github": {"status": "mock" if USE_MOCK else "live"},
            },
            "mock_mode": USE_MOCK,
            "repo": f"{GITHUB_REPO_OWNER}/{GITHUB_REPO_NAME}",
        }
    )
