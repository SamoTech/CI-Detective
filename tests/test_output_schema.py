import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from ci_detective import Diagnosis, build_diagnosis_payload


def test_diagnosis_payload_is_versioned_and_preserves_all_failed_jobs():
    first = Diagnosis("TYPE_ERROR", "first", confidence="high")
    second = Diagnosis("ASSERTION_FAILURE", "second", confidence="medium")

    payload = build_diagnosis_payload([("python", first), ("node", second)])

    assert payload["schema_version"] == "1.0"
    assert [job["job"] for job in payload["failed_jobs"]] == ["python", "node"]
    assert payload["failed_jobs"][0]["category"] == "TYPE_ERROR"
    assert payload["failed_jobs"][1]["category"] == "ASSERTION_FAILURE"
    json.dumps(payload)


def test_diagnosis_payload_has_stable_fields_for_each_job():
    diagnosis = Diagnosis("UNKNOWN", "unknown")
    job = build_diagnosis_payload([("test", diagnosis)])["failed_jobs"][0]

    assert set(job) == {
        "job",
        "category",
        "confidence",
        "summary",
        "root_cause",
        "implicated_symbol",
        "failing_tests",
        "traceback_files",
        "history",
    }
