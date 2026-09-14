import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from ci_detective import classify_failure, render_markdown_report


def test_type_error_missing_argument_gets_specific_root_cause():
    result = classify_failure(
        "FAILED tests/test_generator.py::test_call\n"
        "TypeError: classify() missing 1 required positional argument: 'config'"
    )
    assert result.category == "TYPE_ERROR"
    assert result.implicated_symbol == "classify"
    assert result.root_cause == "The call to classify is missing required argument 'config'. The failure is consistent with a caller/signature mismatch."
    assert "caller/signature mismatch" in result.summary


def test_import_failure_identifies_missing_module():
    result = classify_failure("ModuleNotFoundError: No module named 'requests'")
    assert result.category == "IMPORT_FAILURE"
    assert result.implicated_symbol == "requests"
    assert "requests" in result.root_cause


def test_report_exposes_root_cause_and_symbol():
    result = classify_failure("TypeError: classify() missing 1 required positional argument: 'config'")
    report = render_markdown_report("test", result)
    assert "### Implicated Symbol" in report
    assert "`classify`" in report
    assert "### Diagnosis" in report
    assert "caller/signature mismatch" in report
