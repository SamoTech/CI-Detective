import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from ci_detective import (
    analyze_git_history,
    classify_failure,
    extract_traceback_files,
    post_pr_comment,
    pull_request_number,
    render_markdown_report,
)


def test_type_error_is_classified():
    result = classify_failure("TypeError: classify() missing 1 required positional argument")
    assert result.category == "TYPE_ERROR"
    assert result.confidence == "high"


def test_assertion_failure_is_classified():
    result = classify_failure("E AssertionError: expected 2, got 3")
    assert result.category == "ASSERTION_FAILURE"


def test_unknown_is_safe():
    result = classify_failure("something unusual happened")
    assert result.category == "UNKNOWN"
    assert result.confidence == "low"


def test_extract_traceback_files():
    log = 'Traceback\n  File "src/generator.py", line 42, in classify\nTypeError: missing config'
    assert extract_traceback_files(log) == ["src/generator.py"]


def test_history_identifies_changed_traceback_file(monkeypatch):
    responses = {
        ("rev-parse", "HEAD"): "abcdef123456\n",
        ("rev-parse", "HEAD^"): "123456abcdef\n",
        ("diff", "--name-only", "123456abcdef", "abcdef123456"): "src/generator.py\ntests/test_generator.py\n",
        ("log", "-1", "--format=%s", "abcdef123456"): "refactor generator\n",
    }

    def fake_git_command(*args):
        return responses[args]

    monkeypatch.setattr("ci_detective.git_command", fake_git_command)
    evidence = analyze_git_history('File "src/generator.py", line 42, in classify\nTypeError: missing config')

    assert any("src/generator.py" in item and "changed in HEAD" in item for item in evidence)
    assert any("Likely regression candidate" in item for item in evidence)


def test_history_does_not_blame_unrelated_change(monkeypatch):
    responses = {
        ("rev-parse", "HEAD"): "abcdef123456\n",
        ("rev-parse", "HEAD^"): "123456abcdef\n",
        ("diff", "--name-only", "123456abcdef", "abcdef123456"): "README.md\n",
        ("log", "-1", "--format=%s", "abcdef123456"): "docs update\n",
    }

    def fake_git_command(*args):
        return responses[args]

    monkeypatch.setattr("ci_detective.git_command", fake_git_command)
    evidence = analyze_git_history('File "src/generator.py", line 42, in classify\nTypeError: missing config')

    assert not any("Likely regression candidate" in item for item in evidence)
    assert any("none of its files changed in HEAD" in item for item in evidence)


def test_markdown_report_contains_diagnosis_and_evidence():
    diagnosis = classify_failure("TypeError: classify() missing config")
    diagnosis.history = [
        "Failure traceback references src/generator.py, which changed in HEAD.",
        "Current commit abc1234: refactor generator",
        "Likely regression candidate: current commit abc1234 changed an implicated source file.",
    ]
    report = render_markdown_report("test", diagnosis)
    assert "CI Detective — Failure Diagnosis" in report
    assert "TYPE_ERROR" in report
    assert "HIGH" in report
    assert "src/generator.py" in report
    assert "Likely regression detected" in report


def test_markdown_unknown_report_warns():
    report = render_markdown_report("test", classify_failure("something unusual happened"))
    assert "UNKNOWN" in report
    assert "No deterministic root cause was established" in report


def test_pull_request_number_reads_event_payload(monkeypatch, tmp_path):
    event = tmp_path / "event.json"
    event.write_text(json.dumps({"number": 42}), encoding="utf-8")
    monkeypatch.setenv("GITHUB_EVENT_NAME", "pull_request")
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event))
    assert pull_request_number() == 42


def test_pull_request_number_ignores_non_pr_event(monkeypatch):
    monkeypatch.setenv("GITHUB_EVENT_NAME", "push")
    monkeypatch.delenv("GITHUB_EVENT_PATH", raising=False)
    assert pull_request_number() is None


def test_post_pr_comment_updates_existing_comment(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "ci_detective.gh_api",
        lambda path: [{"id": 123, "body": "<!-- ci-detective -->\nold"}],
    )

    def fake_run(args, **kwargs):
        calls.append(args)
        class Result:
            returncode = 0
            stdout = ""
        return Result()

    monkeypatch.setattr("ci_detective.subprocess.run", fake_run)
    post_pr_comment("SamoTech/CI-Detective", 42, "new report")

    assert calls
    assert calls[0][0:4] == ["gh", "api", "--method", "PATCH"]
    assert "repos/SamoTech/CI-Detective/issues/comments/123" in calls[0]
    assert "body=<!-- ci-detective -->\nnew report" in calls[0]


def test_post_pr_comment_creates_comment_when_missing(monkeypatch):
    calls = []
    monkeypatch.setattr("ci_detective.gh_api", lambda path: [])

    def fake_run(args, **kwargs):
        calls.append(args)
        class Result:
            returncode = 0
            stdout = ""
        return Result()

    monkeypatch.setattr("ci_detective.subprocess.run", fake_run)
    post_pr_comment("SamoTech/CI-Detective", 42, "new report")

    assert calls
    assert calls[0][0:4] == ["gh", "api", "--method", "POST"]
    assert "repos/SamoTech/CI-Detective/issues/42/comments" in calls[0]


def test_end_to_end_pr_failure_probe():
    assert False, "CI Detective PR comment integration probe"
