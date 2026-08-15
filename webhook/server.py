"""
Relic.ai Flask webhook server.

Listens for GitHub webhook POSTs, verifies HMAC-SHA256 signatures, and
dispatches events to the appropriate engine handler in a background thread so
GitHub always receives a 200 within its 10-second timeout.

Also serves the dashboard UI pages and exposes the JSON API via the dashboard
blueprint.

Run with:
    python -m webhook.server
"""

import hashlib
import hmac
import os
import sys
import threading
from typing import Any, Dict

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request

# Ensure project root is on the path when run as __main__
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

load_dotenv()

from dashboard.api import api_bp
from engine import incident_triage, memory_updater, risk_scorer
from utils.logger import EventLogger

log = EventLogger("webhook_server")

WEBHOOK_SECRET: str = os.getenv("GITHUB_WEBHOOK_SECRET", "")
FLASK_PORT: int = int(os.getenv("FLASK_PORT", "5050"))
FLASK_DEBUG: bool = os.getenv("FLASK_DEBUG", "false").lower() == "true"

INCIDENT_LABEL = "incident"

app = Flask(
    __name__,
    template_folder=os.path.join(os.path.dirname(__file__), "..", "dashboard", "templates"),
    static_folder=os.path.join(os.path.dirname(__file__), "..", "dashboard", "static"),
)
app.register_blueprint(api_bp)


# ---------------------------------------------------------------------------
# Signature verification
# ---------------------------------------------------------------------------


def _verify_signature(payload_bytes: bytes, signature_header: str) -> bool:
    """
    Verify GitHub's HMAC-SHA256 webhook signature.

    Args:
        payload_bytes:      Raw request body bytes.
        signature_header:   Value of the X-Hub-Signature-256 header.

    Returns:
        True if the signature matches, False otherwise.
    """
    if not WEBHOOK_SECRET:
        log.warning("sig_skip", "GITHUB_WEBHOOK_SECRET not set — skipping signature check")
        return True

    if not signature_header or not signature_header.startswith("sha256="):
        return False

    expected = hmac.new(
        WEBHOOK_SECRET.encode("utf-8"),
        payload_bytes,
        hashlib.sha256,
    ).hexdigest()

    provided = signature_header[len("sha256="):]
    return hmac.compare_digest(expected, provided)


# ---------------------------------------------------------------------------
# Webhook endpoint
# ---------------------------------------------------------------------------


@app.route("/webhook", methods=["POST"])
def webhook():
    """
    Main GitHub webhook receiver.

    Validates the signature, determines the event type, and dispatches to the
    correct engine handler in a background thread.
    """
    raw_body = request.get_data()
    signature = request.headers.get("X-Hub-Signature-256", "")

    if not _verify_signature(raw_body, signature):
        log.warning("sig_invalid", "Webhook signature verification failed", ip=request.remote_addr)
        return jsonify({"error": "Invalid signature"}), 401

    event_type = request.headers.get("X-GitHub-Event", "unknown")
    delivery_id = request.headers.get("X-GitHub-Delivery", "unknown")

    log.info("webhook_received", f"Event: {event_type}", delivery_id=delivery_id)

    try:
        payload: Dict[str, Any] = request.get_json(force=True) or {}
    except Exception:
        log.warning("payload_parse_failed", "Could not parse JSON payload")
        return jsonify({"error": "Invalid JSON"}), 400

    action = payload.get("action", "")

    if event_type == "pull_request" and action == "opened":
        _dispatch(risk_scorer.process_pr_opened, payload, label="pr_opened")

    elif event_type == "issues" and action == "opened":
        labels = [lbl.get("name", "") for lbl in payload.get("issue", {}).get("labels", [])]
        if INCIDENT_LABEL in labels:
            _dispatch(incident_triage.process_incident_opened, payload, label="incident_opened")
        else:
            log.debug("issues_skip", "Issue opened without 'incident' label — ignoring")

    elif event_type == "issues" and action == "closed":
        labels = [lbl.get("name", "") for lbl in payload.get("issue", {}).get("labels", [])]
        if INCIDENT_LABEL in labels:
            _dispatch(memory_updater.process_incident_closed, payload, label="incident_closed")
        else:
            log.debug("issues_skip", "Issue closed without 'incident' label — ignoring")

    else:
        log.debug("event_unhandled", f"Unhandled event: {event_type}/{action}")

    return jsonify({"status": "accepted", "event": event_type, "action": action}), 200


def _dispatch(handler, payload: Dict[str, Any], label: str) -> None:
    """
    Fire a handler in a daemon thread so the webhook returns immediately.

    Args:
        handler: Callable that accepts a payload dict.
        payload: GitHub webhook payload dict.
        label:   Human-readable label for logging.
    """
    thread = threading.Thread(target=_safe_run, args=(handler, payload, label), daemon=True)
    thread.start()
    log.info("dispatch", f"Dispatched {label} handler", thread_name=thread.name)


def _safe_run(handler, payload: Dict[str, Any], label: str) -> None:
    """Wrap handler execution to ensure thread exceptions are logged."""
    try:
        handler(payload)
    except Exception as exc:
        log.error("handler_crash", f"Unhandled exception in {label}: {exc}")


# ---------------------------------------------------------------------------
# Dashboard page routes
# ---------------------------------------------------------------------------


@app.route("/", methods=["GET"])
def overview():
    """Serve the overview dashboard page."""
    return render_template("overview.html", page="overview")


@app.route("/risk", methods=["GET"])
def risk():
    """Serve the PR risk analysis page."""
    return render_template("risk.html", page="risk")


@app.route("/incidents", methods=["GET"])
def incidents():
    """Serve the incident intelligence page."""
    return render_template("incidents.html", page="incidents")


@app.route("/memory", methods=["GET"])
def memory():
    """Serve the memory archive page."""
    return render_template("memory.html", page="memory")


@app.route("/settings", methods=["GET"])
def settings():
    """Serve the settings page."""
    env_vars = _get_masked_env_vars()
    return render_template("settings.html", page="settings", env_vars=env_vars)


def _get_masked_env_vars() -> Dict[str, str]:
    """
    Return all Relic.ai env vars with sensitive values masked.

    Returns:
        Dict mapping variable name to masked display value.
    """
    sensitive_keys = {
        "ANTHROPIC_API_KEY",
        "PINECONE_API_KEY",
        "GITHUB_TOKEN",
        "GITHUB_WEBHOOK_SECRET",
    }
    keys = [
        "ANTHROPIC_API_KEY",
        "PINECONE_API_KEY",
        "PINECONE_ENVIRONMENT",
        "PINECONE_INDEX_NAME",
        "GITHUB_TOKEN",
        "GITHUB_REPO_OWNER",
        "GITHUB_REPO_NAME",
        "GITHUB_WEBHOOK_SECRET",
        "FLASK_PORT",
        "FLASK_DEBUG",
        "USE_MOCK_RESPONSES",
        "DATABASE_PATH",
        "LOG_LEVEL",
    ]
    result = {}
    for key in keys:
        value = os.getenv(key, "")
        if key in sensitive_keys and value and not value.endswith("_HERE"):
            result[key] = value[:4] + "••••••••"
        else:
            result[key] = value or "(not set)"
    return result


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    log.info("server_start", f"Starting Relic.ai webhook server on port {FLASK_PORT}")
    app.run(host="0.0.0.0", port=FLASK_PORT, debug=FLASK_DEBUG)
