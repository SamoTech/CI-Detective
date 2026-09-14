import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from ci_detective import Diagnosis, render_multi_job_report


def test_multi_job_report_contains_every_failed_job():
    first = Diagnosis("TYPE_ERROR", "First failure", confidence="high", failing_tests=["tests/test_a.py::test_one"])
    second = Diagnosis("ASSERTION_FAILURE", "Second failure", confidence="medium", failing_tests=["tests/test_b.py::test_two"])

    report = render_multi_job_report([("test-python", first), ("test-node", second)])

    assert "Failed jobs:** **2**" in report
    assert "Failed Job 1: `test-python`" in report
    assert "TYPE_ERROR" in report
    assert "First failure" in report
    assert "Failed Job 2: `test-node`" in report
    assert "ASSERTION_FAILURE" in report
    assert "Second failure" in report
    assert "test_b.py::test_two" in report


def test_multi_job_report_preserves_job_order():
    first = Diagnosis("UNKNOWN", "First", confidence="low")
    second = Diagnosis("COMMAND_FAILURE", "Second", confidence="high")

    report = render_multi_job_report([("alpha", first), ("beta", second)])

    assert report.index("Failed Job 1: `alpha`") < report.index("Failed Job 2: `beta`")
