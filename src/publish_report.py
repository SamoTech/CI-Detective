#!/usr/bin/env python3
from __future__ import annotations

import base64
import json
import os
import re
import subprocess
import sys
from pathlib import Path


def run(command: list[str], **kwargs):
    kwargs.setdefault("timeout", 30)
    return subprocess.run(command, **kwargs)


def safe_path(value: str) -> str:
    value = value.strip().replace("\\", "/")
    value = re.sub(r"^/+", "", value)
    value = re.sub(r"(^|/)\.\.?(/|$)", "/", value)
    value = re.sub(r"/{2,}", "/", value).strip("/")
    return value or ".ci-detective/reports/ci-detective.md"


def api_put(repo: str, path: str, content: str, branch: str) -> dict:
    token = os.environ.get("GH_TOKEN")
    if not token:
        raise RuntimeError("GH_TOKEN is required")
    encoded = base64.b64encode(content.encode("utf-8")).decode("ascii")
    payload = json.dumps(
        {
            "message": f"docs: publish CI Detective report for run {os.environ.get('GITHUB_RUN_ID', 'unknown')}",
            "content": encoded,
            "branch": branch,
        },
        separators=(",", ":"),
    )
    cmd = [
        "curl", "-fsSL", "-X", "PUT",
        "-H", f"Authorization: Bearer {token}",
        "-H", "Accept: application/vnd.github+json",
        "-H", "X-GitHub-Api-Version: 2022-11-28",
        "-H", "Content-Type: application/json",
        "--data-binary", payload,
        f"https://api.github.com/repos/{repo}/contents/{path}",
    ]
    result = run(cmd, check=True, capture_output=True, text=True)
    return json.loads(result.stdout) if result.stdout.strip() else {}


def main() -> int:
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary_path or not Path(summary_path).exists():
        print("CI Detective: no markdown summary available; report persistence skipped.")
        return 0

    report = Path(summary_path).read_text(encoding="utf-8")
    if "CI Detective" not in report:
        print("CI Detective: summary does not contain a diagnosis report; persistence skipped.")
        return 0

    workspace = Path(os.environ.get("GITHUB_WORKSPACE", "."))
    local_path = safe_path(os.environ.get("INPUT_REPORT_PATH", ""))
    target = workspace / local_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(report, encoding="utf-8")

    repo = os.environ.get("GITHUB_REPOSITORY", "")
    run_url = f"{os.environ.get('GITHUB_SERVER_URL', 'https://github.com')}/{repo}/actions/runs/{os.environ.get('GITHUB_RUN_ID', '')}"
    mode = os.environ.get("INPUT_REPORT_DESTINATION", "auto").lower()
    branch = os.environ.get("GITHUB_HEAD_REF") or os.environ.get("GITHUB_REF_NAME") or "main"

    published_url = ""
    status = "artifact"
    if mode in {"auto", "repo"} and repo:
        try:
            result = api_put(repo, local_path, report, branch)
            published_url = result.get("content", {}).get("html_url", "")
            if published_url:
                status = "repo"
        except Exception as exc:
            print(f"CI Detective warning: repository report publish unavailable: {type(exc).__name__}", file=sys.stderr)
            if mode == "repo":
                print("CI Detective: repository report was requested but could not be published; keeping workflow successful.", file=sys.stderr)

    if not published_url:
        published_url = run_url

    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with open(output, "a", encoding="utf-8") as handle:
            handle.write(f"report_path={local_path}\n")
            handle.write(f"report_status={status}\n")
            handle.write(f"report_url={published_url}\n")

    print(f"CI Detective report: {published_url}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
