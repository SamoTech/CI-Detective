import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from ci_detective import analyze_remote_commit


def test_remote_commit_paginates_when_first_page_is_full(monkeypatch):
    first_page = {"commit": {"message": "large change"}, "files": [{"filename": f"src/file_{i}.py"} for i in range(100)]}
    second_page = {"files": [{"filename": "src/target.py"}]}
    calls = []

    def fake_gh_api(path, method="GET", payload=None):
        calls.append((path, method))
        if path.startswith("repos/SamoTech/CI-Detective/commits/"):
            return first_page
        raise AssertionError(path)

    class Result:
        returncode = 0
        stdout = __import__("json").dumps([first_page, second_page])

    def fake_run(command, **kwargs):
        assert command[:3] == ["gh", "api", "--paginate"]
        return Result()

    monkeypatch.setenv("GH_TOKEN", "token")
    monkeypatch.setattr("ci_detective.gh_api", fake_gh_api)
    monkeypatch.setattr("ci_detective.subprocess.run", fake_run)

    evidence = analyze_remote_commit("SamoTech/CI-Detective", "abc1234", ["src/target.py"])

    assert any("src/target.py" in item and "changed in the failing commit" in item for item in evidence)
    assert any("Likely regression candidate" in item for item in evidence)
    assert any("--paginate" in " ".join(["gh", "api", "--paginate"]) for _ in [0])
