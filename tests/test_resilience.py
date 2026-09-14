import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from ci_detective import analyze_remote_commit, gh_api, run_command


def test_run_command_applies_default_timeout(monkeypatch):
    calls = {}

    def fake_run(command, **kwargs):
        calls["command"] = command
        calls.update(kwargs)
        return "result"

    monkeypatch.setattr("ci_detective.subprocess.run", fake_run)
    assert run_command(["example"]) == "result"
    assert calls["timeout"] == 30
    assert "env" in calls


def test_remote_commit_api_failure_is_visible(monkeypatch):
    def fail(_path):
        raise subprocess.CalledProcessError(401, ["gh", "api"])

    monkeypatch.setattr("ci_detective.gh_api", fail)
    evidence = analyze_remote_commit(
        "SamoTech/CI-Detective", "abcdef123456", ["src/generator.py"]
    )

    assert evidence == ["Remote commit analysis unavailable: CalledProcessError."]


def test_gh_api_timeout_is_not_silently_unbounded(monkeypatch):
    captured = {}

    def fake_run(command, **kwargs):
        captured.update(kwargs)
        return type("Result", (), {"stdout": "{}"})()

    monkeypatch.setenv("GH_TOKEN", "token")
    monkeypatch.setattr("ci_detective.subprocess.run", fake_run)
    assert gh_api("repos/example/project") == {}
    assert captured["timeout"] == 30
