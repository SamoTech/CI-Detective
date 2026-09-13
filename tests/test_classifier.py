import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from ci_detective import analyze_git_history, classify_failure, extract_traceback_files


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
    evidence = analyze_git_history(
        'File "src/generator.py", line 42, in classify\nTypeError: missing config'
    )

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
    evidence = analyze_git_history(
        'File "src/generator.py", line 42, in classify\nTypeError: missing config'
    )

    assert not any("Likely regression candidate" in item for item in evidence)
    assert any("none of its files changed in HEAD" in item for item in evidence)
