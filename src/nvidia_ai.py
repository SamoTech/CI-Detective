#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

BASE_URL = os.environ.get("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1").rstrip("/")
TIMEOUT = int(os.environ.get("NVIDIA_TIMEOUT", "45"))

FREE_CODE_MODELS = [
    ("deepseek-v4-pro-0813", 100, "coding, reasoning, agentic, long-context"),
    ("deepseek-v4-flash-0731", 95, "coding, reasoning, agentic, long-context, fast"),
    ("laguna-xs-2.1", 90, "coding, reasoning, agentic, tool-use"),
    ("gemma-4-31b-it", 85, "coding, reasoning, agentic"),
    ("nemotron-3-ultra-550b-a55b", 80, "reasoning, coding, planning, tool-use, long-context"),
    ("nemotron-3-super-120b-a12b", 78, "reasoning, coding, planning, tool-use, long-context"),
    ("nemotron-3-nano-30b-a3b", 72, "coding, reasoning, tool-use, long-context"),
    ("gpt-oss-120b", 68, "reasoning, coding, text"),
    ("gpt-oss-20b", 60, "reasoning, coding, text"),
    ("nemotron-3.5-lightning-30b-a3b", 58, "fast agentic tasks"),
    ("muse-glimmer-30b", 45, "reasoning, multimodal, tool-use"),
    ("kimi-k3", 44, "coding, reasoning, agentic, multimodal"),
]


def _request(path: str, method: str = "GET", payload: dict[str, Any] | None = None) -> Any:
    key = os.environ.get("NVIDIA_API_KEY")
    if not key:
        raise RuntimeError("NVIDIA_API_KEY is not configured")
    data = None
    headers = {"Authorization": f"Bearer {key}", "Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(f"{BASE_URL}{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"NVIDIA HTTP {exc.code}: {body}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RuntimeError(f"NVIDIA request failed: {type(exc).__name__}") from exc


def available_models() -> list[str]:
    data = _request("/models")
    return [str(x.get("id", "")) for x in data.get("data", []) if isinstance(x, dict) and x.get("id")]


def _normalise(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def match_candidates(models: list[str]) -> list[tuple[str, int, str]]:
    ranked: list[tuple[str, int, str]] = []
    normalized = {_normalise(x): x for x in models}
    for candidate, score, reason in FREE_CODE_MODELS:
        key = _normalise(candidate)
        actual = normalized.get(key)
        if actual is None:
            actual = next((m for m in models if key in _normalise(m) or _normalise(m) in key), None)
        if actual:
            ranked.append((actual, score, reason))
    return sorted(ranked, key=lambda x: x[1], reverse=True)


def _complexity_score(context: str) -> int:
    score = 0
    low = context.lower()
    score += min(len(context) // 4000, 25)
    score += min(low.count("traceback"), 5) * 3
    score += min(low.count("failed job"), 5) * 2
    score += min(low.count("regression"), 5) * 4
    score += min(low.count("changed"), 5) * 2
    return min(score, 50)


def choose_models(models: list[str], context: str) -> list[tuple[str, int, str]]:
    ranked = match_candidates(models)
    if not ranked:
        return []
    complexity = _complexity_score(context)

    def key(item: tuple[str, int, str]) -> tuple[int, int]:
        _name, score, reason = item
        long_ctx = int("long-context" in reason)
        fast = int("fast" in reason)
        if complexity >= 20:
            return (score + 8 * long_ctx, -fast)
        return (score + 8 * fast, -long_ctx)

    return sorted(ranked, key=key, reverse=True)


def _extract_json(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.I | re.S).strip()
    try:
        value = json.loads(cleaned)
        return value if isinstance(value, dict) else {}
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, re.S)
        if not match:
            return {}
        try:
            value = json.loads(match.group(0))
            return value if isinstance(value, dict) else {}
        except json.JSONDecodeError:
            return {}


def _string_list(value: Any, limit: int) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(x).strip()[:500] for x in value if str(x).strip()][:limit]


def _validate_ai_result(result: dict[str, Any]) -> dict[str, Any]:
    """Keep the model useful without allowing it to change the evidence contract."""
    confidence = str(result.get("confidence", "low")).lower()
    if confidence not in {"low", "medium", "high"}:
        confidence = "low"
    fix_confidence = str(result.get("fix_confidence", confidence)).lower()
    if fix_confidence not in {"low", "medium", "high"}:
        fix_confidence = "low"
    return {
        "summary": str(result.get("summary", "No AI summary returned.")).strip()[:2000],
        "root_cause_hypotheses": _string_list(result.get("root_cause_hypotheses"), 5),
        "confidence": confidence,
        "evidence_refs": _string_list(result.get("evidence_refs"), 8),
        "recommended_fix": _string_list(result.get("recommended_fix"), 6),
        "verification_plan": _string_list(result.get("verification_plan"), 8),
        "fix_confidence": fix_confidence,
        "warnings": _string_list(result.get("warnings"), 5),
    }


def analyse_with_fallback(context: str) -> dict[str, Any]:
    live = available_models()
    choices = choose_models(live, context)
    if not choices:
        raise RuntimeError("No supported free NVIDIA coding/reasoning model is currently available to this API key")
    system = (
        "You are the primary enhanced reasoning layer for CI Detective. The deterministic analyzer is the authoritative evidence source. "
        "Use only the supplied deterministic report and evidence. Never invent files, tests, commits, causes, or fixes. "
        "A changed file is correlation, not causation. If exact evidence is missing, explicitly say it is missing instead of guessing. "
        "Your job is to turn evidence into an actionable diagnosis and a safe resolution plan. Separate confirmed facts from hypotheses. "
        "Do not claim that a proposed fix has been applied or verified. Do not produce executable patches. "
        "Every hypothesis, fix, and verification step must be traceable to supplied evidence. "
        "Return strict JSON with exactly these keys: summary, root_cause_hypotheses, confidence, evidence_refs, "
        "recommended_fix, verification_plan, fix_confidence, warnings. "
        "confidence and fix_confidence must be low, medium, or high. Arrays must contain concise strings."
    )
    user = "CI Detective deterministic evidence:\n" + context[:50000]
    errors: list[str] = []
    for index, (model, _score, reason) in enumerate(choices[:6]):
        payload = {
            "model": model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": 0.1,
            "max_tokens": 1800,
        }
        try:
            data = _request("/chat/completions", "POST", payload)
            content = data["choices"][0]["message"]["content"]
            raw = _extract_json(content)
            required = {"summary", "root_cause_hypotheses", "recommended_fix", "verification_plan"}
            if not raw or not any(key in raw for key in required):
                raise RuntimeError("model returned an empty or incomplete analysis")
            parsed = _validate_ai_result(raw)
            parsed["model"] = model
            parsed["model_selection_reason"] = reason
            parsed["attempt"] = index + 1
            parsed["available_free_models"] = [x[0] for x in choices]
            parsed["backup_model"] = choices[index + 1][0] if index + 1 < len(choices) else None
            parsed["deterministic_authority"] = True
            parsed["analysis_role"] = "primary_enhanced_analysis"
            return parsed
        except Exception as exc:
            errors.append(f"{model}: {type(exc).__name__}")
    raise RuntimeError("All available NVIDIA free-model attempts failed: " + "; ".join(errors))


def render_ai_report(result: dict[str, Any]) -> str:
    lines = [
        "", "## CI Detective — NVIDIA AI Enhanced Analysis", "",
        "**Analysis role:** **PRIMARY ENHANCED ANALYSIS**  ",
        f"**Model:** `{result.get('model', 'unknown')}`  ",
        f"**Backup:** `{result.get('backup_model') or 'none available'}`  ",
        f"**AI Confidence:** **{str(result.get('confidence', 'low')).upper()}**  ",
        f"**Fix Confidence:** **{str(result.get('fix_confidence', 'low')).upper()}**", "",
        "### AI Summary", str(result.get("summary", "No AI summary returned.")),
    ]
    hypotheses = result.get("root_cause_hypotheses") or []
    if hypotheses:
        lines += ["", "### Root-Cause Hypotheses"] + [f"- {x}" for x in hypotheses[:5]]
    fixes = result.get("recommended_fix") or []
    if fixes:
        lines += ["", "### Recommended Fix"] + [f"- {x}" for x in fixes[:6]]
    checks = result.get("verification_plan") or []
    if checks:
        lines += ["", "### Verification Plan"] + [f"- {x}" for x in checks[:8]]
    refs = result.get("evidence_refs") or []
    if refs:
        lines += ["", "### Evidence References"] + [f"- {x}" for x in refs[:8]]
    warnings = result.get("warnings") or []
    if warnings:
        lines += ["", "### Warnings"] + [f"- {x}" for x in warnings[:5]]
    lines += [
        "", f"**Free NVIDIA models detected:** {len(result.get('available_free_models', []))}",
        "", "AI provides the primary enhanced reasoning and resolution plan; deterministic CI Detective evidence remains authoritative.", "",
    ]
    return "\n".join(lines)


def _context_from_environment() -> str:
    explicit = os.environ.get("CI_DETECTIVE_AI_CONTEXT", "")
    report_file = os.environ.get("CI_DETECTIVE_REPORT_FILE", "")
    parts: list[str] = []

    # Central monitor passes a path to the deterministic JSON context. Load the
    # file contents rather than sending the path itself to the model.
    if explicit:
        explicit_path = Path(explicit)
        if explicit_path.is_file():
            try:
                parts.append(explicit_path.read_text(encoding="utf-8"))
            except OSError:
                pass
        else:
            parts.append(explicit)

    if report_file:
        try:
            report = Path(report_file).read_text(encoding="utf-8")
            if report:
                parts.append(report)
        except OSError:
            pass

    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        try:
            summary = Path(summary_path).read_text(encoding="utf-8")
            if summary:
                parts.append(summary)
        except OSError:
            pass
    return "\n\n".join(parts)


def main() -> int:
    if not os.environ.get("NVIDIA_API_KEY"):
        print("CI Detective: NVIDIA AI unavailable; deterministic analysis remains active because NVIDIA_API_KEY is not configured.")
        return 0
    context = _context_from_environment()
    if not context:
        print("CI Detective: NVIDIA AI skipped; no deterministic evidence context available.")
        return 0
    try:
        result = analyse_with_fallback(context)
        report = render_ai_report(result)
        print(report)
        shared_file = os.environ.get("CI_DETECTIVE_REPORT_FILE")
        if shared_file:
            path = Path(shared_file)
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as handle:
                handle.write(report)
        summary = os.environ.get("GITHUB_STEP_SUMMARY")
        if summary:
            with open(summary, "a", encoding="utf-8") as handle:
                handle.write(report)
        output = os.environ.get("GITHUB_OUTPUT")
        if output:
            with open(output, "a", encoding="utf-8") as handle:
                handle.write("ai_status=success\n")
                handle.write(f"ai_model={result.get('model','')}\n")
                handle.write("ai_diagnosis=" + json.dumps(result, separators=(",", ":")) + "\n")
        return 0
    except Exception as exc:
        print(f"CI Detective: NVIDIA AI unavailable; deterministic analysis remains active: {exc}", file=sys.stderr)
        output = os.environ.get("GITHUB_OUTPUT")
        if output:
            with open(output, "a", encoding="utf-8") as handle:
                handle.write("ai_status=unavailable\n")
                handle.write("ai_model=\n")
        return 0


if __name__ == "__main__":
    sys.exit(main())
