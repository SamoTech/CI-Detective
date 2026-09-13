import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from ci_detective import (
    analyze_git_history,
    analyze_remote_commit,
    classify_failure,
    extract_failing_tests,
    extract_traceback_files,
    render_markdown_report,
)


def test_type_error_is_classified_with_context():
    log = '''FAILED tests/test_generator.py::test_classification_is_deterministic
Traceback (most recent call last):
  File "src/generator.py", line 42, in classify
TypeError: classify() missing 1 required positional argument: 'config'
'''
    result = classify_failure(log)
    assert result.category == "TYPE_ERROR"
    assert result.confidence == "high"
    assert result.failing_tests == ["tests/test_generator.py::test_classification_is_deterministic"]
    assert result.traceback_files == ["src/generator.py"]
    assert any("TypeError:" in item for item in result.error_lines)


def test_assertion_failure_is_classified():
    result = classify_failure("E AssertionError: expected 2, got 3")
    assert result.category == "ASSERTION_FAILURE"


def test_unknown_is_safe():
    result = classify_failure("something unusual happened")
    assert result.category == "UNKNOWN"
    assert result.confidence == "low"


def test_extract_failing_tests():
    log = "FAILED tests/test_api.py::test_login - AssertionError"
    assert extract_failing_tests(log) == ["tests/test_api.py::test_login"]


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


def test_remote_commit_fallback(monkeypatch):
    monkeypatch.setattr("ci_detective.gh_api", lambda path: {
        "files": [{"filename": "src/generator.py"}, {"filename": "README.md"}],
        "commit": {"message": "refactor generator"},
    })
    evidence = analyze_remote_commit("SamoTech/CI-Detective", "abcdef123456", ["src/generator.py"])
    assert any("changed in the failing commit" in item for item in evidence)
    assert any("Likely regression candidate" in item for item in evidence)


def test_markdown_report_contains_context_and_evidence():
    diagnosis = classify_failure("FAILED tests/test_generator.py::test_classification\nTypeError: classify() missing config")
    diagnosis.history = [
        "Failure traceback references src/generator.py, which changed in HEAD.",
        "Current commit abc1234: refactor generator",
        "Likely regression candidate: current commit abc1234 changed an implicated source file.",
    ]
    report = render_markdown_report("test", diagnosis)
    assert "CI Detective — Failure Diagnosis" in report
    assert "TYPE_ERROR" in report
    assert "HIGH" in report
    assert "test_generator.py::test_classification" in report
    assert "Likely regression detected" in report


def test_markdown_unknown_report_warns():
    report = render_markdown_report("test", classify_failure("something unusual happened"))
    assert "UNKNOWN" in report
    assert "No deterministic root cause was established" in report
