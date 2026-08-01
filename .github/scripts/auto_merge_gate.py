"""
Conditional auto-merge gate for SAW-adopting repos.

Merges + deletes the branch ONLY when all four hold:
  (a) CI is green on the PR's head commit
  (b) GitHub reports the PR as mergeable (no conflicts)
  (c) Linear has a comment on the linked ticket containing "Approved for RTE"
      (SAW's QAS handoff evidence)
  (d) none of the PR's changed files match a path in .github/gate.yaml's
      denylist, and the PR touches no more than max_files_changed files

Fails closed on any uncertainty: missing ticket ID, API errors, ambiguous
mergeable state, a missing/unreadable gate.yaml, or anything unexpected all
result in NOT merging. Leaving a PR for manual review is always the safe
outcome; auto-merging is the one that has to earn its way through all four
checks.

Project-specific values (LINEAR_TICKET_PREFIX, MERGE_METHOD) are read from
environment/repo variables; the path denylist lives in .github/gate.yaml
since patterns need real glob support -- see setup notes below.

Set DRY_RUN=true to log the decision without actually merging, for testing
against real PRs before trusting this live.
"""

import fnmatch
import os
import re
import sys
import time

import requests
import yaml

GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]
LINEAR_API_KEY = os.environ.get("LINEAR_API_KEY")
REPO = os.environ["REPO"]
PR_NUMBER = int(os.environ["PR_NUMBER"])
DRY_RUN = os.environ.get("DRY_RUN", "false").lower() == "true"
MERGE_METHOD = os.environ.get("MERGE_METHOD", "squash")

# Project-specific config, not hardcoded -- set LINEAR_TICKET_PREFIX as a
# repo variable (Settings > Secrets and variables > Actions > Variables) in
# each project this is installed in -- e.g. "ABC" for one project, "ENG"
# for another, matching that project's Linear team prefix.
TICKET_PREFIX = os.environ["LINEAR_TICKET_PREFIX"]

GH_API = f"https://api.github.com/repos/{REPO}"
GH_HEADERS = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json",
}

TICKET_ID_PATTERN = re.compile(rf"{re.escape(TICKET_PREFIX)}-\d+")


def get_pr() -> dict:
    r = requests.get(f"{GH_API}/pulls/{PR_NUMBER}", headers=GH_HEADERS, timeout=30)
    r.raise_for_status()
    return r.json()


def post_comment(body: str) -> None:
    requests.post(
        f"{GH_API}/issues/{PR_NUMBER}/comments",
        headers=GH_HEADERS,
        json={"body": body},
        timeout=30,
    )


def extract_ticket_id(pr: dict) -> str | None:
    text = f"{pr['title']} {pr['head']['ref']}"
    match = TICKET_ID_PATTERN.search(text)
    return match.group(0) if match else None


def check_ci_green(pr: dict) -> bool:
    sha = pr["head"]["sha"]
    r = requests.get(f"{GH_API}/commits/{sha}/status", headers=GH_HEADERS, timeout=30)
    if r.status_code != 200:
        return False
    return r.json().get("state") == "success"


def check_mergeable(retries: int = 5, delay: int = 3) -> bool:
    # GitHub computes 'mergeable' asynchronously after PR creation/update;
    # poll briefly rather than trusting a possibly-stale first read.
    for _ in range(retries):
        r = requests.get(f"{GH_API}/pulls/{PR_NUMBER}", headers=GH_HEADERS, timeout=30)
        if r.status_code != 200:
            return False
        data = r.json()
        if data.get("mergeable") is not None:
            return data["mergeable"] is True
        time.sleep(delay)
    return False  # never resolved -> fail closed


def check_qas_approved(ticket_id: str | None) -> bool:
    if not ticket_id or not LINEAR_API_KEY:
        return False
    # NOTE: Linear's GraphQL `issue(id:)` field accepts either the internal
    # UUID or the human-readable identifier (e.g. "ABC-123") in current API
    # versions. Verify this still holds against Linear's live schema before
    # relying on it -- this is the one part of this script not exercised
    # against a real workspace yet.
    query = """
    query($id: String!) {
      issue(id: $id) {
        comments {
          nodes { body }
        }
      }
    }
    """
    r = requests.post(
        "https://api.linear.app/graphql",
        headers={"Authorization": LINEAR_API_KEY, "Content-Type": "application/json"},
        json={"query": query, "variables": {"id": ticket_id}},
        timeout=30,
    )
    if r.status_code != 200:
        return False
    issue = r.json().get("data", {}).get("issue")
    if not issue:
        return False
    comments = issue.get("comments", {}).get("nodes", [])
    return any("Approved for RTE" in (c.get("body") or "") for c in comments)


def check_gate_denylist(pr: dict) -> bool:
    """Condition (d): mechanical path denylist + file-count cap.

    Fails closed if gate.yaml is missing/unreadable, if the changed-files
    list can't be fetched, or if any changed file matches a denylist
    pattern -- this is deliberately conservative. A missing config should
    never be interpreted as "no restrictions."
    """
    try:
        with open(".github/gate.yaml") as f:
            config = yaml.safe_load(f)
    except (FileNotFoundError, yaml.YAMLError):
        return False

    denylist = config.get("denylist", [])
    max_files = config.get("max_files_changed", 10)

    files_changed = []
    page = 1
    while True:
        r = requests.get(
            f"{GH_API}/pulls/{PR_NUMBER}/files",
            headers=GH_HEADERS,
            params={"per_page": 100, "page": page},
            timeout=30,
        )
        if r.status_code != 200:
            return False
        batch = r.json()
        if not batch:
            break
        files_changed.extend(f["filename"] for f in batch)
        page += 1

    if len(files_changed) > max_files:
        return False

    for path in files_changed:
        for pattern in denylist:
            if fnmatch.fnmatch(path, pattern):
                return False

    return True


def merge_and_cleanup(pr: dict) -> None:
    if DRY_RUN:
        post_comment(
            "Auto-merge gate (DRY RUN): all four conditions passed "
            "(CI green, no conflicts, QAS approved, path denylist clear). "
            "Would merge + delete branch, but DRY_RUN is on -- no action taken."
        )
        return

    merge_resp = requests.put(
        f"{GH_API}/pulls/{PR_NUMBER}/merge",
        headers=GH_HEADERS,
        json={"merge_method": MERGE_METHOD},
        timeout=30,
    )
    if merge_resp.status_code != 200:
        post_comment(
            f"Auto-merge gate: all conditions passed, but the merge call "
            f"failed ({merge_resp.status_code}). Left for manual merge. "
            f"Response: {merge_resp.text[:300]}"
        )
        sys.exit(1)

    branch = pr["head"]["ref"]
    requests.delete(f"{GH_API}/git/refs/heads/{branch}", headers=GH_HEADERS, timeout=30)
    post_comment(
        "Auto-merge gate: (a) CI green, (b) no conflicts, (c) QAS approved, "
        "(d) path denylist clear -- merged and branch deleted."
    )


def main() -> None:
    pr = get_pr()
    if pr.get("merged") or pr.get("draft"):
        return

    ticket_id = extract_ticket_id(pr)
    a = check_ci_green(pr)
    b = check_mergeable()
    c = check_qas_approved(ticket_id)
    d = check_gate_denylist(pr)

    if a and b and c and d:
        merge_and_cleanup(pr)
    # Fail closed silently otherwise -- no comment spam on every push.
    # If you want visibility into why a PR *isn't* auto-merging, that's a
    # reasonable follow-up: add a comment here summarizing which of a-d
    # failed, gated to only fire once per PR rather than on every event.


if __name__ == "__main__":
    main()
