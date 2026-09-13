#!/usr/bin/env python3
"""CI Detective: deterministic, evidence-first GitHub Actions failure analysis."""
from __future__ import annotations
import json
import os
import re
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
    history: list[str] | None = None

def clean_logs(text: str) -> str:
    return re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", text or "")

def classify_failure(log_text: str) -> Diagnosis:
    text = clean_logs(log_text)
    patterns = [
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
    evidence = []
    for needle, category, summary, confidence in patterns:
        if needle in lowered:
            for line in text.splitlines():
                ll = line.lower()
                if needle in ll or (needle == "test" and ("failed" in ll or "failure" in ll)):
                    cleaned = line.strip()
                    if cleaned and cleaned not in evidence:
                        evidence.append(cleaned[:500])
                    if len(evidence) >= 5:
                        break
            return Diagnosis(category, summary, evidence, confidence, [])
    return Diagnosis("UNKNOWN", "The failure could not be classified by the current deterministic rules.", [], "low", [])

def gh_api(path: str) -> Any:
    token = os.environ.get("GH_TOKEN")
    if not token:
        raise RuntimeError("GH_TOKEN is required")
    result = subprocess.run(["gh", "api", path], check=True, capture_output=True, text=True, env=os.environ.copy())
    return json.loads(result.stdout)

def git_command(*args: str) -> str:
    result = subprocess.run(["git", *args], check=True, capture_output=True, text=True, env=os.environ.copy())
    return result.stdout

def extract_traceback_files(log_text: str) -> list[str]:
    text = clean_logs(log_text)
    found = []
    patterns = [
        r'File ["\']([^"\']+\.(?:py|js|jsx|ts|tsx))["\'], line \d+',
        r'(?:at|in) ([^\s()]+\.(?:js|jsx|ts|tsx|py))(?::\d+)?',
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, text):
            path = match.group(1).replace("\\", "/")
            if path not in found:
                found.append(path)
    return found[:10]

def analyze_git_history(log_text: str) -> list[str]:
    try:
        head = git_command("rev-parse", "HEAD").strip()
        parent = git_command("rev-parse", "HEAD^").strip()
        changed_output = git_command("diff", "--name-only", parent, head)
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []
    changed_files = [x.strip().replace("\\", "/") for x in changed_output.splitlines() if x.strip()]
    traceback_files = extract_traceback_files(log_text)
    evidence = []
    matching = [p for p in traceback_files if any(p == c or p.endswith("/" + c) or c.endswith("/" + p) for c in changed_files)]
    if matching:
        for path in matching[:3]:
            evidence.append(f"Failure traceback references {path}, which changed in HEAD.")
    elif changed_files and traceback_files:
        evidence.append("The failure has a source traceback, but none of its files changed in HEAD.")
    if changed_files:
        evidence.append("HEAD changed: " + ", ".join(changed_files[:10]))
    subject = git_command("log", "-1", "--format=%s", head).strip()
    if subject:
        evidence.append(f"Current commit {head[:7]}: {subject}")
    if matching:
        evidence.append(f"Likely regression candidate: current commit {head[:7]} changed an implicated source file.")
    return evidence

def fetch_job_logs(repo: str, run_id: str, job_id: int) -> str:
    token = os.environ.get("GH_TOKEN")
    if not token:
        raise RuntimeError("GH_TOKEN is required")
    url = f"https://api.github.com/repos/{repo}/actions/jobs/{job_id}/logs"
    direct = subprocess.run(["curl", "-fsSL", "-H", f"Authorization: Bearer {token}", "-H", "Accept: application/vnd.github+json", url], capture_output=True, text=True, env=os.environ.copy())
    if direct.returncode == 0 and direct.stdout.strip():
        return direct.stdout
    fallback = subprocess.run(["gh", "run", "view", run_id, "--repo", repo, "--log-failed", "--color", "never"], capture_output=True, text=True, env=os.environ.copy())
    if fallback.returncode == 0:
        return fallback.stdout
    print("CI Detective: unable to retrieve failed-job logs.", file=sys.stderr)
    return ""

def render_markdown_report(job_name: str, diagnosis: Diagnosis) -> str:
    lines = [
        "## CI Detective — Failure Diagnosis", "",
        f"**Job:** `{job_name}`  ",
        f"**Category:** `{diagnosis.category}`  ",
        f"**Confidence:** **{diagnosis.confidence.upper()}**", "",
        "### Diagnosis", diagnosis.summary,
    ]
    if diagnosis.evidence:
        lines += ["", "### Evidence"] + [f"- `{x}`" for x in diagnosis.evidence[:5]]
    if diagnosis.history:
        lines += ["", "### Git History"] + [f"- {x}" for x in diagnosis.history[:6]]
    if any("Likely regression candidate" in x for x in diagnosis.history or []):
        lines += ["", "### Assessment", "**Likely regression detected:** the current commit modified a source file implicated by the failure traceback."]
    elif diagnosis.category == "UNKNOWN":
        lines += ["", "### Assessment", "No deterministic root cause was established. Treat this result as a triage signal, not a definitive diagnosis."]
    lines += ["", "---", "Generated by CI Detective — deterministic analysis; no external AI required."]
    return "\n".join(lines) + "\n"

def write_step_summary(report: str) -> None:
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(report)

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
        diagnoses = []
        for job in failed_jobs:
            logs = fetch_job_logs(repo, run_id, int(job["id"]))
            diagnosis = classify_failure(logs)
            diagnosis.history = analyze_git_history(logs)
            diagnoses.append((job.get("name", "unknown job"), diagnosis))
        first_job, first = diagnoses[0]
        report = render_markdown_report(first_job, first)
        print(report)
        write_step_summary(report)
        output_path = os.environ.get("GITHUB_OUTPUT")
        if output_path:
            payload = {"category": first.category, "confidence": first.confidence, "summary": first.summary, "history": first.history or []}
            with open(output_path, "a", encoding="utf-8") as handle:
                handle.write(f"diagnosis={json.dumps(payload, separators=(',', ':'))}\n")
                handle.write(f"confidence={first.confidence}\n")
        return 0
    except Exception as exc:
        print(f"CI Detective error: {exc}", file=sys.stderr)
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
