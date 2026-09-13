import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from ci_detective import classify_failure


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
