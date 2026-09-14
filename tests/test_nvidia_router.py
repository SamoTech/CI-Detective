import json

from src import nvidia_ai


def test_match_candidates_only_returns_live_free_code_models():
    live = [
        "deepseek-ai/deepseek-v4-pro-0813",
        "deepseek-ai/deepseek-v4-flash-0731",
        "unrelated-model",
    ]
    matched = nvidia_ai.match_candidates(live)
    names = [x[0] for x in matched]
    assert names == [
        "deepseek-ai/deepseek-v4-pro-0813",
        "deepseek-ai/deepseek-v4-flash-0731",
    ]


def test_choose_models_prefers_live_backup_for_complex_context():
    live = [
        "deepseek-v4-pro-0813",
        "deepseek-v4-flash-0731",
        "laguna-xs-2.1",
    ]
    context = "traceback " * 20 + " regression changed failed job " * 20
    choices = nvidia_ai.choose_models(live, context)
    assert len(choices) == 3
    assert choices[0][0] == "deepseek-v4-pro-0813"
    assert choices[1][0] != choices[0][0]


def test_fallback_uses_next_live_model(monkeypatch):
    monkeypatch.setattr(
        nvidia_ai,
        "available_models",
        lambda: ["deepseek-v4-pro-0813", "deepseek-v4-flash-0731"],
    )
    calls = []

    def fake_request(path, method="GET", payload=None):
        calls.append(payload["model"])
        if len(calls) == 1:
            raise RuntimeError("temporary model failure")
        return {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "summary": "The deterministic evidence is consistent with a TypeError.",
                                "root_cause_hypotheses": ["Caller/value mismatch."],
                                "confidence": "medium",
                                "evidence_refs": ["TypeError evidence"],
                                "recommended_next_checks": ["Inspect the failing call."],
                                "warnings": [],
                            }
                        )
                    }
                }
            ]
        }

    monkeypatch.setattr(nvidia_ai, "_request", fake_request)
    result = nvidia_ai.analyse_with_fallback("TypeError in failed job")
    assert calls == ["deepseek-v4-pro-0813", "deepseek-v4-flash-0731"]
    assert result["model"] == "deepseek-v4-flash-0731"
    assert result["attempt"] == 2
    assert result["deterministic_authority"] is True
