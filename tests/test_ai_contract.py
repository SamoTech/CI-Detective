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
