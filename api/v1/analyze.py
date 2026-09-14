from __future__ import annotations

import json
import os
import sys
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from nvidia_ai import analyse_with_fallback  # noqa: E402

MAX_CONTEXT = 50_000
MAX_BODY = 65_536


def _authorized(headers: Any) -> bool:
    expected = os.environ.get("CI_DETECTIVE_ROUTER_TOKEN", "").strip()
    if not expected:
        return False
    supplied = headers.get("Authorization", "")
    return supplied == f"Bearer {expected}"


def _json(handler: BaseHTTPRequestHandler, status: int, payload: dict[str, Any]) -> None:
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


class handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        if self.path.rstrip("/") in {"", "/api/v1/analyze", "/api/v1/health"}:
            _json(self, 200, {"service": "ci-detective-nvidia-router", "status": "ok"})
            return
        _json(self, 404, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path.rstrip("/") != "/api/v1/analyze":
            _json(self, 404, {"error": "not_found"})
            return
        if not _authorized(self.headers):
            _json(self, 401, {"error": "unauthorized"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length <= 0 or length > MAX_BODY:
            _json(self, 413, {"error": "request_too_large"})
            return
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            context = str(payload.get("context", ""))[:MAX_CONTEXT]
            if not context:
                _json(self, 400, {"error": "context_required"})
                return
            result = analyse_with_fallback(context)
            _json(self, 200, result)
        except Exception:
            # Never return upstream credentials, raw provider errors, or request content.
            _json(self, 502, {"error": "upstream_analysis_unavailable"})

    def log_message(self, format: str, *args: Any) -> None:
        return
