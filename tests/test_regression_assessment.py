import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from ci_detective import Diagnosis, render_markdown_report


def test_changed_traceback_file_is_not_presented_as_proven_causation():
    diagnosis = Diagnosis(
        "TYPE_ERROR",
        "A TypeError was detected.",
        history=[
            "Failure traceback references src/generator.py, which changed in HEAD.",
            "Likely regression candidate: current commit abc1234 changed an implicated source file.",
        ],
        confidence="high",
    )

    report = render_markdown_report("test", diagnosis)

    assert "Likely regression detected:** No." in report
    assert "not sufficient to establish causation" in report
