"""
Pinecone vector database client for Relic.ai.

Manages two operations: semantic search over stored incident embeddings and
upsert of new incident memories. Checks USE_MOCK_RESPONSES; when true returns
realistic mock incident data. When false, uses the Pinecone Python SDK with a
local embedding step via the Anthropic embeddings API.

Required env vars (when USE_MOCK_RESPONSES=false):
    PINECONE_API_KEY     — API key from app.pinecone.io
    PINECONE_ENVIRONMENT — e.g. us-east-1-aws
    PINECONE_INDEX_NAME  — e.g. relic-ai-incidents
    ANTHROPIC_API_KEY    — Used to generate embeddings via claude-3 (text-embedding-3-large)
"""

import hashlib
import os
from typing import Any, Dict, List

from dotenv import load_dotenv

from utils.logger import EventLogger

load_dotenv()

log = EventLogger("pinecone_client")

PINECONE_API_KEY: str = os.getenv("PINECONE_API_KEY", "")
PINECONE_ENVIRONMENT: str = os.getenv("PINECONE_ENVIRONMENT", "")
PINECONE_INDEX_NAME: str = os.getenv("PINECONE_INDEX_NAME", "relic-ai-incidents")
ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
USE_MOCK: bool = os.getenv("USE_MOCK_RESPONSES", "true").lower() == "true"

# Dimensionality for text-embedding-3-large
EMBEDDING_DIMENSION = 1536

# ---------------------------------------------------------------------------
# Mock incident memories — look like real Kubernetes project incidents
# ---------------------------------------------------------------------------

_MOCK_INCIDENTS: List[Dict[str, Any]] = [
    {
        "incident_id": "INC-2024-0847",
        "title": "Deployment controller maxUnavailable calculation caused mass pod disruption",
        "root_cause": (
            "An off-by-one error in ResolveFenceposts caused maxUnavailable to be computed as "
            "the total replica count instead of the configured percentage, terminating all pods simultaneously."
        ),
        "resolution_summary": (
            "Reverted the utility function change and deployed a hotfix. Full recovery in 34 minutes. "
            "Added a regression test that verifies maxUnavailable never exceeds 50% of replicas."
        ),
        "affected_files": [
            "pkg/controller/deployment/util/deployment_util.go",
            "pkg/controller/deployment/sync.go",
        ],
        "time_to_resolution_minutes": 34,
        "similarity_score": 0.94,
        "url": "https://github.com/kubernetes/kubernetes/issues/118234",
    },
    {
        "incident_id": "INC-2024-0712",
        "title": "Resource quota enforcement blocked critical namespace rollouts for 2 hours",
        "root_cause": (
            "A new quota enforcement feature was rolled out without corresponding quota increases "
            "in production namespaces. The quota check fired on surge pods before old pods were terminated."
        ),
        "resolution_summary": (
            "Increased namespace quotas by 25% across all production namespaces. "
            "Added a pre-release quota validation step to the release runbook. Resolved in 2h 10m."
        ),
        "affected_files": [
            "pkg/controller/deployment/deployment_controller.go",
            "plugin/pkg/admission/resourcequota/admission.go",
        ],
        "time_to_resolution_minutes": 130,
        "similarity_score": 0.91,
        "url": "https://github.com/kubernetes/kubernetes/issues/112891",
    },
    {
        "incident_id": "INC-2023-1104",
        "title": "RBAC ClusterRole with overly broad verbs caused privilege escalation risk",
        "root_cause": (
            "A new controller role included wildcard verbs on core resources to simplify development. "
            "Security scan flagged it as critical; role had to be re-scoped in production."
        ),
        "resolution_summary": (
            "Replaced wildcard verbs with explicit get/list/watch. Re-applied role. "
            "Added a CI policy check using kube-linter to block overly broad RBAC roles."
        ),
        "affected_files": [
            "config/rbac/controller-manager-role.yaml",
            "config/rbac/quota_checker_role.yaml",
        ],
        "time_to_resolution_minutes": 55,
        "similarity_score": 0.87,
        "url": "https://github.com/kubernetes/kubernetes/issues/107654",
    },
    {
        "incident_id": "INC-2023-0891",
        "title": "Rolling update stalled at 50% due to readiness probe misconfiguration",
        "root_cause": (
            "The new readiness probe path returned 503 on the first request post-startup, "
            "causing the rolling update to stall waiting for pods to become ready. "
            "minReadySeconds was set to 0, hiding the latent bug in staging."
        ),
        "resolution_summary": (
            "Updated readiness probe to use /healthz instead of /ready during warm-up period. "
            "Set minReadySeconds=10 as a safer default. Resolved in 1h 12m."
        ),
        "affected_files": [
            "pkg/controller/deployment/rolling.go",
            "deploy/manifests/payment-processor/deployment.yaml",
        ],
        "time_to_resolution_minutes": 72,
        "similarity_score": 0.79,
        "url": "https://github.com/kubernetes/kubernetes/issues/103418",
    },
    {
        "incident_id": "INC-2023-0654",
        "title": "Controller manager OOM killed during large-scale deployment reconciliation",
        "root_cause": (
            "A change to the reconciliation loop introduced a memory leak by not releasing "
            "informer cache entries for deleted namespaces, causing unbounded memory growth "
            "under high deployment churn."
        ),
        "resolution_summary": (
            "Rolled back the reconciliation change. Added finalizer cleanup for namespace informers. "
            "Memory usage returned to baseline within 5 minutes of rollback."
        ),
        "affected_files": [
            "pkg/controller/deployment/deployment_controller.go",
            "pkg/controller/util/endpoint/endpoints_utils.go",
        ],
        "time_to_resolution_minutes": 21,
        "similarity_score": 0.76,
        "url": "https://github.com/kubernetes/kubernetes/issues/99821",
    },
]


def search_similar_incidents(
    query_text: str,
    top_k: int = 5,
) -> List[Dict[str, Any]]:
    """
    Search the Pinecone index for incidents semantically similar to query_text.

    In mock mode, returns a static set of realistic past incidents ordered by
    similarity score. In live mode, embeds query_text and performs an ANN search.

    Args:
        query_text: Free-text description of the PR diff or incident to search for.
        top_k:      Maximum number of results to return (default 5).

    Returns:
        List of incident dicts, each with keys: incident_id, title, root_cause,
        resolution_summary, affected_files, time_to_resolution_minutes,
        similarity_score, url.
    """
    if USE_MOCK:
        log.info("pinecone_search_mock", f"Returning {min(top_k, len(_MOCK_INCIDENTS))} mock incidents")
        return _MOCK_INCIDENTS[:top_k]

    try:
        from pinecone import Pinecone  # type: ignore
        import anthropic

        embedding = _embed_text(query_text)

        pc = Pinecone(api_key=PINECONE_API_KEY)
        index = pc.Index(PINECONE_INDEX_NAME)

        results = index.query(
            vector=embedding,
            top_k=top_k,
            include_metadata=True,
        )

        incidents = []
        for match in results.get("matches", []):
            meta = match.get("metadata", {})
            incidents.append(
                {
                    "incident_id": match["id"],
                    "title": meta.get("title", ""),
                    "root_cause": meta.get("root_cause", ""),
                    "resolution_summary": meta.get("resolution_summary", ""),
                    "affected_files": meta.get("affected_files", []),
                    "time_to_resolution_minutes": meta.get("time_to_resolution_minutes", 0),
                    "similarity_score": round(match.get("score", 0.0), 4),
                    "url": meta.get("url", ""),
                }
            )
        log.info("pinecone_search_complete", f"Found {len(incidents)} similar incidents")
        return incidents
    except Exception as exc:
        log.error("pinecone_search_failed", f"Pinecone search error: {exc}")
        raise


def store_incident_memory(
    incident_id: str,
    text: str,
    metadata: Dict[str, Any],
) -> None:
    """
    Embed text and upsert a new incident vector into the Pinecone index.

    In mock mode, logs the operation without making any network calls.

    Args:
        incident_id: Unique identifier for the incident (e.g. "INC-2024-0901").
        text:        Full text to embed — typically the concatenated lessons fields.
        metadata:    Structured metadata stored alongside the vector for retrieval.
    """
    if USE_MOCK:
        log.info(
            "pinecone_upsert_mock",
            "Mock upsert to Pinecone index",
            incident_id=incident_id,
            index=PINECONE_INDEX_NAME,
        )
        return

    try:
        from pinecone import Pinecone  # type: ignore

        embedding = _embed_text(text)

        pc = Pinecone(api_key=PINECONE_API_KEY)
        index = pc.Index(PINECONE_INDEX_NAME)

        index.upsert(
            vectors=[{"id": incident_id, "values": embedding, "metadata": metadata}]
        )
        log.info("pinecone_upsert_complete", "Incident memory stored", incident_id=incident_id)
    except Exception as exc:
        log.error("pinecone_upsert_failed", f"Pinecone upsert error: {exc}")
        raise


def _embed_text(text: str) -> List[float]:
    """
    Generate a text embedding using the Anthropic embeddings endpoint.

    Args:
        text: The text to embed.

    Returns:
        A list of floats representing the embedding vector.

    Raises:
        RuntimeError: If the Anthropic API key is not set.
    """
    if not ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY is required for live embeddings")

    import anthropic

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    response = client.embeddings.create(
        model="text-embedding-3-large",
        input=text,
    )
    return response.data[0].embedding


def _stable_incident_id(issue_number: int, repo: str) -> str:
    """
    Generate a deterministic incident ID string for Pinecone vector IDs.

    Args:
        issue_number: GitHub issue number.
        repo:         Repository string in "owner/name" format.

    Returns:
        A short stable ID string like "INC-a3f8c12b".
    """
    raw = f"{repo}#{issue_number}"
    digest = hashlib.sha256(raw.encode()).hexdigest()[:8]
    return f"INC-{digest}"
