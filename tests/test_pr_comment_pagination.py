import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from ci_detective import fetch_all_pr_comments


def test_pr_comment_pagination_finds_comments_beyond_first_page(monkeypatch):
    first_page = [{"id": i, "body": "old"} for i in range(100)]
    second_page = [{"id": 101, "body": "<!-- ci-detective -->\nlatest"}]
    calls = []

    monkeypatch.setenv("GH_TOKEN", "test-token")

    def fake_comment_api(path):
        calls.append(path)
        return first_page

    class Result:
        returncode = 0
        stdout = json.dumps([first_page, second_page])

    def fake_run(command, **kwargs):
        calls.append(command)
        assert command[:3] == ["gh", "api", "--paginate"]
        return Result()

    monkeypatch.setattr("ci_detective.github_comment_api", fake_comment_api)
    monkeypatch.setattr("ci_detective.subprocess.run", fake_run)

    comments = fetch_all_pr_comments("owner/repo", 7)

    assert len(comments) == 101
    assert comments[-1]["id"] == 101
    assert any("issues/7/comments" in str(item) for item in calls)
