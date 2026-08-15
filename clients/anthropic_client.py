"""
Anthropic Claude API client for Relic.ai.

Provides three high-level methods that correspond to the three analysis tasks
the system performs. Each method checks USE_MOCK_RESPONSES; when true it
returns a realistic mock dict. When false it calls the Anthropic API using
carefully engineered system prompts and returns parsed JSON.

Required env vars (when USE_MOCK_RESPONSES=false):
    ANTHROPIC_API_KEY — API key from console.anthropic.com
"""

import json
import os
from typing import Any, Dict, List

from dotenv import load_dotenv

from utils.logger import EventLogger

load_dotenv()

log = EventLogger("anthropic_client")

ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
USE_MOCK: bool = os.getenv("USE_MOCK_RESPONSES", "true").lower() == "true"

MODEL = "claude-sonnet-5"
MAX_TOKENS = 2048

# ---------------------------------------------------------------------------
# System prompts — used only when USE_MOCK_RESPONSES=false
# ---------------------------------------------------------------------------

_RISK_SYSTEM_PROMPT = """\
You are Relic.ai, an autonomous deploy risk intelligence system embedded in a \
software engineering organisation's CI/CD pipeline. Your role is to assess the \
risk of merging a pull request by reasoning over the code diff and a set of \
historically similar incidents retrieved from a vector database of past outages.

Respond ONLY with a single valid JSON object — no markdown fences, no prose, \
no explanation outside the JSON. The schema is exactly:

{
  "score": <integer 0-100>,
  "reasoning": "<plain English explanation, 2-4 sentences>",
  "high_risk_files": [
    {"file": "<path>", "reason": "<why this file is risky>"}
  ],
  "suggested_actions": ["<action string>"],
  "confidence": <float 0.0-1.0>
}

Scoring guide:
- 0-39: Low risk. Routine changes to well-tested, low-blast-radius areas.
- 40-69: Medium risk. Changes to core logic, config, or areas with incident history.
- 70-100: High risk. Changes to critical paths, previously incident-prone files, \
  or broad surface area changes.

Reason over the similar past incidents provided. If a changed file appears in a \
past incident's affected_files, weight the score upward accordingly.
"""

_TRIAGE_SYSTEM_PROMPT = """\
You are Relic.ai, an autonomous incident intelligence system. When a new \
incident is opened, your job is to immediately generate a triage brief that \
gives the on-call engineer a head start by reasoning over similar past incidents.

Respond ONLY with a single valid JSON object — no markdown fences, no prose. \
The schema is exactly:

{
  "likely_cause": "<concise root cause hypothesis, 1-2 sentences>",
  "confidence": <float 0.0-1.0>,
  "estimated_resolution_minutes": <integer>,
  "resolution_steps": ["<actionable step>"],
  "similar_incident_links": ["<URL or incident reference>"]
}

Base your estimated_resolution_minutes on the actual resolution times of the \
similar incidents provided. List resolution_steps in execution order. Be direct \
and actionable — the engineer reading this is under pressure.
"""

_LESSONS_SYSTEM_PROMPT = """\
You are Relic.ai. An incident has just been resolved and the full issue thread \
is provided. Extract structured lessons that will be stored as institutional \
memory and used to improve future risk scores and triage briefs.

Respond ONLY with a single valid JSON object — no markdown fences, no prose. \
The schema is exactly:

{
  "root_cause": "<confirmed root cause, 1-2 sentences>",
  "resolution_steps": ["<step taken>"],
  "time_to_resolution_minutes": <integer>,
  "affected_files": ["<file path or service name>"],
  "follow_up_actions": ["<recommended follow-up>"]
}

Extract only confirmed facts from the thread. Do not speculate. If the thread \
does not contain enough information to populate a field, use an empty list or \
the string "unknown".
"""

# ---------------------------------------------------------------------------
# Mock responses
# ---------------------------------------------------------------------------

_MOCK_RISK_ASSESSMENT: Dict[str, Any] = {
    "score": 74,
    "reasoning": (
        "This PR modifies the core deployment controller reconciliation loop and rolling update "
        "utility functions — two areas with documented incident history involving quota exhaustion "
        "and maxUnavailable miscalculations. The new resource quota check introduces a new code path "
        "that can block deployments cluster-wide, and a comment in the diff flags a possible "
        "argument swap in ResolveFenceposts that could cause excessive pod disruption during rollouts."
    ),
    "high_risk_files": [
        {
            "file": "pkg/controller/deployment/deployment_controller.go",
            "reason": "Modifies the core reconciliation loop; new quota-check path can halt all rollouts in a namespace if misconfigured.",
        },
        {
            "file": "pkg/controller/deployment/util/deployment_util.go",
            "reason": "Inline comment flags a potential argument swap in ResolveFenceposts — historically caused excessive unavailability in INC-2024-0847.",
        },
        {
            "file": "config/rbac/quota_checker_role.yaml",
            "reason": "New ClusterRole with broad read access across resourcequotas and deployments; principle of least privilege not fully scoped.",
        },
    ],
    "suggested_actions": [
        "Add a unit test for checkResourceQuota covering the edge case where available CPU headroom is less than maxSurge * requests.cpu.",
        "Verify the ResolveFenceposts argument order against the function signature — the inline comment suggests a bug.",
        "Run the change against a staging namespace with a tight resource quota configured before merging to main.",
        "Review the ClusterRole scope: consider scoping to a specific namespace rather than cluster-wide.",
    ],
    "confidence": 0.82,
}

_MOCK_TRIAGE_BRIEF: Dict[str, Any] = {
    "likely_cause": (
        "Resource quota exhaustion in the affected namespace is blocking the deployment controller "
        "from completing the rollout. A recently merged change added a quota pre-check that fires "
        "before surge pods are created, but the quota limits were not adjusted to account for "
        "rolling update surge capacity."
    ),
    "confidence": 0.87,
    "estimated_resolution_minutes": 28,
    "resolution_steps": [
        "Run `kubectl describe resourcequota -n <namespace>` to confirm quota limits and current usage.",
        "Calculate required headroom: (maxSurge pods) x (requests.cpu per pod) = additional CPU needed.",
        "Temporarily increase the CPU quota: `kubectl patch resourcequota compute-quota -n <namespace> --patch '{\"spec\":{\"hard\":{\"requests.cpu\":\"<new-value}\"}}}'`.",
        "Monitor the rollout: `kubectl rollout status deployment/<name> -n <namespace>`.",
        "Once the rollout completes, file a ticket to permanently adjust quota limits and add quota headroom to the release checklist.",
    ],
    "similar_incident_links": [
        "https://github.com/kubernetes/kubernetes/issues/118234",
        "https://github.com/kubernetes/kubernetes/issues/112891",
        "https://github.com/kubernetes/kubernetes/issues/107654",
    ],
}

_MOCK_LESSONS: Dict[str, Any] = {
    "root_cause": (
        "The deployment controller's new resource quota pre-check blocked the rollout because the "
        "namespace quota did not account for the additional pods needed during maxSurge. The check "
        "was correct in intent but was merged without a corresponding quota adjustment."
    ),
    "resolution_steps": [
        "Identified quota exhaustion via `kubectl describe resourcequota` in prod-payments namespace.",
        "Calculated required headroom: 3 surge pods x 2 CPU = 6 additional CPUs needed.",
        "Patched compute-quota to increase requests.cpu from 20 to 24.",
        "Confirmed rollout completed: all 3 replicas running, P99 latency returned to baseline.",
    ],
    "time_to_resolution_minutes": 48,
    "affected_files": [
        "pkg/controller/deployment/deployment_controller.go",
        "config/rbac/quota_checker_role.yaml",
    ],
    "follow_up_actions": [
        "Audit resource quotas across all production namespaces before next release.",
        "Add quota headroom validation to the pre-release checklist.",
        "Document maxSurge x resource-request quota formula in the runbooks.",
        "Add an integration test that verifies rollouts succeed when quota is within 10% of limit.",
    ],
}


def analyze_risk(
    pr_diff: str,
    similar_incidents: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Analyse a PR diff against historical incidents and return a structured risk assessment.

    Args:
        pr_diff:           The full unified diff of the pull request.
        similar_incidents: List of similar past incident dicts from Pinecone.

    Returns:
        Dict with keys: score, reasoning, high_risk_files, suggested_actions, confidence.
    """
    if USE_MOCK:
        log.info("analyze_risk_mock", "Returning mock risk assessment")
        return _MOCK_RISK_ASSESSMENT

    try:
        import anthropic  # imported lazily — only needed when not in mock mode

        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

        incidents_context = json.dumps(similar_incidents, indent=2)
        user_message = (
            f"## Pull Request Diff\n\n```diff\n{pr_diff}\n```\n\n"
            f"## Similar Past Incidents (retrieved from memory)\n\n```json\n{incidents_context}\n```\n\n"
            "Assess the risk of merging this pull request."
        )

        message = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=_RISK_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )
        raw = message.content[0].text
        result = json.loads(raw)
        log.info("analyze_risk_complete", "Risk analysis complete", score=result.get("score"))
        return result
    except Exception as exc:
        log.error("analyze_risk_failed", f"Anthropic API error: {exc}")
        raise


def generate_triage_brief(
    incident_details: Dict[str, Any],
    similar_incidents: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Generate an instant triage brief for a newly opened incident.

    Args:
        incident_details:  Dict with keys: number, title, body, labels, author.
        similar_incidents: List of similar past incident dicts from Pinecone.

    Returns:
        Dict with keys: likely_cause, confidence, estimated_resolution_minutes,
                        resolution_steps, similar_incident_links.
    """
    if USE_MOCK:
        log.info("triage_brief_mock", "Returning mock triage brief", issue_number=incident_details.get("number"))
        return _MOCK_TRIAGE_BRIEF

    try:
        import anthropic

        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

        incidents_context = json.dumps(similar_incidents, indent=2)
        user_message = (
            f"## New Incident\n\n"
            f"**Title:** {incident_details.get('title')}\n\n"
            f"**Description:**\n{incident_details.get('body', 'No description provided.')}\n\n"
            f"**Labels:** {', '.join(incident_details.get('labels', []))}\n\n"
            f"## Similar Past Incidents (retrieved from memory)\n\n```json\n{incidents_context}\n```\n\n"
            "Generate the triage brief."
        )

        message = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=_TRIAGE_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )
        raw = message.content[0].text
        result = json.loads(raw)
        log.info("triage_brief_complete", "Triage brief generated", issue_number=incident_details.get("number"))
        return result
    except Exception as exc:
        log.error("triage_brief_failed", f"Anthropic API error: {exc}")
        raise


def extract_incident_lessons(
    title: str,
    body: str,
    comments: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Extract structured lessons from a resolved incident's full thread.

    Args:
        title:    Issue title.
        body:     Issue description (opening post).
        comments: List of GitHub comment dicts with at minimum 'user.login' and 'body'.

    Returns:
        Dict with keys: root_cause, resolution_steps, time_to_resolution_minutes,
                        affected_files, follow_up_actions.
    """
    if USE_MOCK:
        log.info("extract_lessons_mock", "Returning mock incident lessons")
        return _MOCK_LESSONS

    try:
        import anthropic

        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

        thread = f"**Issue Title:** {title}\n\n**Opening Description:**\n{body}\n\n**Thread:**\n"
        for comment in comments:
            author = comment.get("user", {}).get("login", "unknown")
            thread += f"\n---\n**{author}:** {comment.get('body', '')}\n"

        message = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=_LESSONS_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": thread}],
        )
        raw = message.content[0].text
        result = json.loads(raw)
        log.info("extract_lessons_complete", "Lessons extracted successfully")
        return result
    except Exception as exc:
        log.error("extract_lessons_failed", f"Anthropic API error: {exc}")
        raise
