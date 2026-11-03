from src import nvidia_ai


def test_validate_ai_result_enforces_resolution_contract():
    result = nvidia_ai._validate_ai_result({
        "summary": "Evidence-backed analysis",
        "root_cause_hypotheses": ["Caller mismatch"],
        "confidence": "HIGH",
        "evidence_refs": ["traceback"],
        "recommended_fix": ["Align the caller with the function signature"],
        "verification_plan": ["Run the focused test"],
        "fix_confidence": "medium",
        "warnings": [],
    })
    assert result["confidence"] == "high"
    assert result["fix_confidence"] == "medium"
    assert result["recommended_fix"]
    assert result["verification_plan"]


def test_render_ai_report_contains_resolution_sections():
    report = nvidia_ai.render_ai_report({
        "model": "test-model",
        "backup_model": "backup-model",
        "confidence": "high",
        "fix_confidence": "medium",
        "summary": "Evidence-backed analysis",
        "root_cause_hypotheses": ["Caller mismatch"],
        "recommended_fix": ["Align the caller with the function signature"],
        "verification_plan": ["Run the focused test"],
        "evidence_refs": ["traceback"],
        "warnings": [],
        "available_free_models": ["test-model", "backup-model"],
    })
    assert "PRIMARY ENHANCED ANALYSIS" in report
    assert "### Recommended Fix" in report
    assert "### Verification Plan" in report


def test_context_from_environment_accepts_json_literal_without_path_stat(monkeypatch):
    payload = '{"schema_version":"1.0","failed_jobs":[{"job":"lint"}]}'
    monkeypatch.setenv("CI_DETECTIVE_AI_CONTEXT", payload)
    monkeypatch.delenv("CI_DETECTIVE_REPORT_FILE", raising=False)
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    assert nvidia_ai._context_from_environment() == payload


def test_context_from_environment_reads_json_file(tmp_path, monkeypatch):
    context_file = tmp_path / "ai-context.json"
    context_file.write_text('{"schema_version":"1.0"}', encoding="utf-8")
    monkeypatch.setenv("CI_DETECTIVE_AI_CONTEXT", str(context_file))
    monkeypatch.delenv("CI_DETECTIVE_REPORT_FILE", raising=False)
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    assert nvidia_ai._context_from_environment() == '{"schema_version":"1.0"}'


def test_context_from_environment_handles_oversized_literal(monkeypatch):
    payload = '{"data":"' + ("x" * 1024) + '"}'
    monkeypatch.setenv("CI_DETECTIVE_AI_CONTEXT", payload)
    monkeypatch.delenv("CI_DETECTIVE_REPORT_FILE", raising=False)
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    assert nvidia_ai._context_from_environment() == payload
