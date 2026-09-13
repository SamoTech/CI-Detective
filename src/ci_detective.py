#!/usr/bin/env python3
"""CI Detective: deterministic GitHub Actions failure analysis."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from typing import Any


@dataclass
class Diagnosis:
    category: str
    summary: str
    evidence: list[str]
    confidence: str


def classify_failure(log_text: str) -> Diagnosis:
    """Classify common CI failures using deterministic signatures."""
    text = log_text or ""

    patterns: list[tuple[str, str, str, str]] = [
        ("typeerror", "TYPE_ERROR", "A TypeError was detected; inspect the failing call and recent signature changes.", "high"),
        ("assertionerror", "ASSERTION_FAILURE", "An assertion failed; inspect the expected and actual values.", "high"),
        ("modulenotfounderror", "IMPORT_FAILURE", "A Python module import failed; inspect dependencies and import paths.", "high"),
        ("cannot find module", "IMPORT_FAILURE", "A Node.js module import failed; inspect dependencies and package configuration.", "high"),
        ("npm err!", "NPM_FAILURE", "npm reported an installation or script failure.", "medium"),
        ("command not found", "COMMAND_FAILURE", "A required executable was not available in the runner environment.", "high"),
        ("permission denied", "PERMISSION_FAILURE", "A command or file operation was denied by the runner environment.", "high"),
        ("out of memory", "RESOURCE_FAILURE", "The job appears to have exhausted available memory.", "medium"),
        ("timed out", "TIMEOUT", "The job appears to have exceeded a timeout.", "medium"),
        ("test", "TEST_FAILURE", "A test failure was detected.", "high"),
    ]

    lowered = text.lower()
    evidence: list[str] = []
    for needle, category, summary, confidence in patterns:
        if needle in lowered:
            for line in text.splitlines():
                line_lower = line.lower()
                if needle in line_lower or (needle == "test" and ("failed" in line_lower or "failure" in line_lower)):
                    cleaned = line.strip()
                    if cleaned and cleaned not in evidence:
                        evidence.append(cleaned[:500])
                    if len(evidence) >= 5:
                        break
            return Diagnosis(category, summary, evidence, confidence)

    return Diagnosis(
        "UNKNOWN",
        "The failure could not be classified by the current deterministic rules.",
        [],
        "low",
    )


def gh_api(path: str) -> Any:
    token = os.environ.get("GH_TOKEN")
    if not token:
        raise RuntimeError("GH_TOKEN is required")
    result = subprocess.run(
        ["gh", "api", path],
        check=True,
        capture_output=True,
        text=True,
        env=os.environ.copy(),
    )
    return json.loads(result.stdout)


def fetch_job_logs(repo: str, run_id: str, job_id: int) -> str:
    """Fetch a failed job's logs, with a GitHub CLI fallback."""
    direct = subprocess.run(
        ["gh", "api", f"repos/{repo}/actions/jobs/{job_id}/logs"],
        capture_output=True,
        text=True,
        env=os.environ.copy(),
    )
    if direct.returncode == 0 and direct.stdout.strip():
        return direct.stdout

    fallback = subprocess.run(
        ["gh", "run", "view", run_id, "--repo", repo, "--log-failed"],
        capture_output=True,
        text=True,
        env=os.environ.copy(),
    )
    if fallback.returncode == 0:
        return fallback.stdout

    print(
        f"CI Detective: unable to retrieve logs for job {job_id}: "
        f"{direct.stderr.strip() or fallback.stderr.strip() or 'unknown error'}",
        file=sys.stderr,
    )
    return ""


def main() -> int:
    repo = os.environ.get("GITHUB_REPOSITORY")
    run_id = os.environ.get("GITHUB_RUN_ID")
    if not repo or not run_id:
        print("CI Detective: GitHub Actions environment not detected.")
        return 0

    try:
        jobs = gh_api(f"repos/{repo}/actions/runs/{run_id}/jobs?per_page=100")
        failed_jobs = [j for j in jobs.get("jobs", []) if j.get("conclusion") == "failure"]
        if not failed_jobs:
            print("CI Detective: no failed jobs found.")
            return 0

        diagnoses: list[Diagnosis] = []
        for job in failed_jobs:
            logs = fetch_job_logs(repo, run_id, int(job["id"]))
            diagnosis = classify_failure(logs)
            diagnoses.append(diagnosis)
            print(f"CI Detective: {job.get('name', 'unknown job')} -> {diagnosis.category}")
            print(diagnosis.summary)
            for item in diagnosis.evidence:
                print(f"  evidence: {item}")

        output = {
            "category": diagnoses[0].category,
            "confidence": diagnoses[0].confidence,
            "summary": diagnoses[0].summary,
        }
        output_path = os.environ.get("GITHUB_OUTPUT")
        if output_path:
            with open(output_path, "a", encoding="utf-8") as handle:
                handle.write(f"diagnosis={json.dumps(output, separators=(',', ':'))}\n")
                handle.write(f"confidence={diagnoses[0].confidence}\n")
        return 0
    except Exception as exc:
        print(f"CI Detective error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
