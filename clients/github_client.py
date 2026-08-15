"""
GitHub API client for Relic.ai.

All methods check the USE_MOCK_RESPONSES environment variable. When true,
they return realistic mock payloads so the full pipeline can be exercised
without a real GitHub token. When false, they make authenticated requests
to the GitHub REST API v3.

Required env vars (when USE_MOCK_RESPONSES=false):
    GITHUB_TOKEN        — Personal access token with repo scope
    GITHUB_REPO_OWNER   — Repository owner (user or org)
    GITHUB_REPO_NAME    — Repository name
"""

import os
from typing import Any, Dict, List

import requests
from dotenv import load_dotenv

from utils.logger import EventLogger

load_dotenv()

log = EventLogger("github_client")

GITHUB_TOKEN: str = os.getenv("GITHUB_TOKEN", "")
GITHUB_REPO_OWNER: str = os.getenv("GITHUB_REPO_OWNER", "")
GITHUB_REPO_NAME: str = os.getenv("GITHUB_REPO_NAME", "")
USE_MOCK: bool = os.getenv("USE_MOCK_RESPONSES", "true").lower() == "true"

_BASE_URL = "https://api.github.com"
_HEADERS = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}

# ---------------------------------------------------------------------------
# Mock data — realistic payloads that mirror GitHub API responses exactly.
# ---------------------------------------------------------------------------

_MOCK_PR_DIFF = """\
diff --git a/pkg/controller/deployment/deployment_controller.go b/pkg/controller/deployment/deployment_controller.go
index a3f8c12..b7d4e91 100644
--- a/pkg/controller/deployment/deployment_controller.go
+++ b/pkg/controller/deployment/deployment_controller.go
@@ -187,6 +187,18 @@ func (dc *DeploymentController) syncDeployment(ctx context.Context, key string)
        if d.DeletionTimestamp != nil {
                return dc.syncStatusOnly(ctx, d, rsList)
        }
+
+       // New: enforce resource quota before proceeding with rollout
+       if err := dc.checkResourceQuota(ctx, d); err != nil {
+               dc.eventRecorder.Eventf(d, v1.EventTypeWarning, "QuotaExceeded",
+                       "Deployment %s/%s blocked: %v", d.Namespace, d.Name, err)
+               return err
+       }
+
+       dc.logger.V(4).Info("Resource quota check passed",
+               "deployment", klog.KObj(d))
        return dc.sync(ctx, d, rsList)
 }

diff --git a/pkg/controller/deployment/util/deployment_util.go b/pkg/controller/deployment/util/deployment_util.go
index 2c1a3f7..9e8d0b4 100644
--- a/pkg/controller/deployment/util/deployment_util.go
+++ b/pkg/controller/deployment/util/deployment_util.go
@@ -312,7 +312,7 @@ func GetReplicaCountForDeployment(d *apps.Deployment) int32 {
 func MaxUnavailable(deployment apps.Deployment) int32 {
        if !IsRollingUpdate(&deployment) || *(deployment.Spec.Replicas) == 0 {
                return int32(0)
        }
-       _, maxUnavailable, err := ResolveFenceposts(deployment.Spec.Strategy.RollingUpdate.MaxSurge,
+       _, maxUnavailable, err := ResolveFenceposts(deployment.Spec.Strategy.RollingUpdate.MaxSurge,  // BUG: swapped args
                deployment.Spec.Strategy.RollingUpdate.MaxUnavailable,
                *(deployment.Spec.Replicas))

diff --git a/config/rbac/quota_checker_role.yaml b/config/rbac/quota_checker_role.yaml
new file mode 100644
--- /dev/null
+++ b/config/rbac/quota_checker_role.yaml
@@ -0,0 +1,20 @@
+apiVersion: rbac.authorization.k8s.io/v1
+kind: ClusterRole
+metadata:
+  name: quota-checker
+rules:
+- apiGroups: [""]
+  resources: ["resourcequotas"]
+  verbs: ["get", "list", "watch"]
+- apiGroups: ["apps"]
+  resources: ["deployments", "replicasets"]
+  verbs: ["get", "list"]
"""

_MOCK_ISSUE_COMMENTS = [
    {
        "id": 1901234501,
        "user": {"login": "sarah-oncall"},
        "body": (
            "Confirmed: deployment controller is stuck in a reconciliation loop. "
            "Pods are being created and immediately terminated. "
            "Error from kube-controller-manager: `quota exceeded for namespace prod-payments`."
        ),
        "created_at": "2024-11-14T02:17:00Z",
    },
    {
        "id": 1901234502,
        "user": {"login": "marcus-sre"},
        "body": (
            "Checked the resource quota. The `prod-payments` namespace has a hard limit of "
            "20 CPU cores and we're currently at 19.8. The new rollout of `payment-processor` "
            "requests 2 cores per pod and wants to spin up 3 replicas. "
            "Short-term fix: temporarily increase quota. "
            "Root cause: quota check was recently added without accounting for rolling update surge capacity."
        ),
        "created_at": "2024-11-14T02:34:00Z",
    },
    {
        "id": 1901234503,
        "user": {"login": "sarah-oncall"},
        "body": (
            "Applied workaround: `kubectl patch resourcequota compute-quota -n prod-payments "
            "--patch '{\"spec\":{\"hard\":{\"requests.cpu\":\"24\"}}}'`. "
            "Rollout is now completing. Monitoring for 10 minutes."
        ),
        "created_at": "2024-11-14T02:51:00Z",
    },
    {
        "id": 1901234504,
        "user": {"login": "lei-platform"},
        "body": (
            "Rollout completed successfully. All 3 replicas running. "
            "P99 latency back to baseline. Closing incident. "
            "Follow-up: file quota review ticket for all production namespaces before next release."
        ),
        "created_at": "2024-11-14T03:05:00Z",
    },
]


def get_pr_diff(pr_number: int) -> str:
    """
    Fetch the unified diff for a pull request.

    Args:
        pr_number: The GitHub PR number to fetch the diff for.

    Returns:
        The full unified diff as a string.
    """
    if USE_MOCK:
        log.info("pr_diff_mock", "Returning mock PR diff", pr_number=pr_number)
        return _MOCK_PR_DIFF

    # Real call: GET /repos/{owner}/{repo}/pulls/{pull_number} with Accept: diff
    url = f"{_BASE_URL}/repos/{GITHUB_REPO_OWNER}/{GITHUB_REPO_NAME}/pulls/{pr_number}"
    headers = {**_HEADERS, "Accept": "application/vnd.github.v3.diff"}
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        log.info("pr_diff_fetched", "PR diff fetched from GitHub", pr_number=pr_number)
        return response.text
    except requests.RequestException as exc:
        log.error("pr_diff_fetch_failed", f"GitHub API error: {exc}", pr_number=pr_number)
        raise


def post_pr_comment(pr_number: int, body: str) -> Dict[str, Any]:
    """
    Post a comment on a pull request.

    Args:
        pr_number: The target PR number.
        body:      Markdown body of the comment.

    Returns:
        The GitHub API response dict for the created comment.
    """
    if USE_MOCK:
        log.info("pr_comment_mock", "Mock posting PR comment", pr_number=pr_number)
        return {"id": 9900001, "html_url": f"https://github.com/{GITHUB_REPO_OWNER}/{GITHUB_REPO_NAME}/pull/{pr_number}#issuecomment-9900001"}

    url = f"{_BASE_URL}/repos/{GITHUB_REPO_OWNER}/{GITHUB_REPO_NAME}/issues/{pr_number}/comments"
    try:
        response = requests.post(url, headers=_HEADERS, json={"body": body}, timeout=15)
        response.raise_for_status()
        data = response.json()
        log.info("pr_comment_posted", "PR comment posted", pr_number=pr_number, comment_id=data.get("id"))
        return data
    except requests.RequestException as exc:
        log.error("pr_comment_failed", f"Failed to post PR comment: {exc}", pr_number=pr_number)
        raise


def post_issue_comment(issue_number: int, body: str) -> Dict[str, Any]:
    """
    Post a comment on an issue.

    Args:
        issue_number: The target issue number.
        body:         Markdown body of the comment.

    Returns:
        The GitHub API response dict for the created comment.
    """
    if USE_MOCK:
        log.info("issue_comment_mock", "Mock posting issue comment", issue_number=issue_number)
        return {"id": 9900002, "html_url": f"https://github.com/{GITHUB_REPO_OWNER}/{GITHUB_REPO_NAME}/issues/{issue_number}#issuecomment-9900002"}

    url = f"{_BASE_URL}/repos/{GITHUB_REPO_OWNER}/{GITHUB_REPO_NAME}/issues/{issue_number}/comments"
    try:
        response = requests.post(url, headers=_HEADERS, json={"body": body}, timeout=15)
        response.raise_for_status()
        data = response.json()
        log.info("issue_comment_posted", "Issue comment posted", issue_number=issue_number, comment_id=data.get("id"))
        return data
    except requests.RequestException as exc:
        log.error("issue_comment_failed", f"Failed to post issue comment: {exc}", issue_number=issue_number)
        raise


def get_issue_comments(issue_number: int) -> List[Dict[str, Any]]:
    """
    Fetch all comments on an issue, sorted oldest-first.

    Args:
        issue_number: The target issue number.

    Returns:
        List of GitHub comment objects (dicts).
    """
    if USE_MOCK:
        log.info("issue_comments_mock", "Returning mock issue comments", issue_number=issue_number)
        return _MOCK_ISSUE_COMMENTS

    url = f"{_BASE_URL}/repos/{GITHUB_REPO_OWNER}/{GITHUB_REPO_NAME}/issues/{issue_number}/comments"
    params = {"per_page": 100, "direction": "asc"}
    try:
        response = requests.get(url, headers=_HEADERS, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()
        log.info("issue_comments_fetched", f"Fetched {len(data)} comments", issue_number=issue_number)
        return data
    except requests.RequestException as exc:
        log.error("issue_comments_failed", f"Failed to fetch issue comments: {exc}", issue_number=issue_number)
        raise


def get_issue_labels(issue_number: int) -> List[str]:
    """
    Return the label names on a given issue.

    Args:
        issue_number: The target issue number.

    Returns:
        List of label name strings.
    """
    if USE_MOCK:
        log.info("issue_labels_mock", "Returning mock labels", issue_number=issue_number)
        return ["incident", "priority/critical", "area/deployment-controller"]

    url = f"{_BASE_URL}/repos/{GITHUB_REPO_OWNER}/{GITHUB_REPO_NAME}/issues/{issue_number}/labels"
    try:
        response = requests.get(url, headers=_HEADERS, timeout=15)
        response.raise_for_status()
        return [label["name"] for label in response.json()]
    except requests.RequestException as exc:
        log.error("issue_labels_failed", f"Failed to fetch labels: {exc}", issue_number=issue_number)
        raise
