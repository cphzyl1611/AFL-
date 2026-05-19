#!/usr/bin/env python3
"""Local Alfresco AE v1 score service.

This is a localhost-only integration smoke service for Alfresco AE v1 scoring.
It does not access Alfresco, does not expose arbitrary execution, and is not a
production platform gateway.
"""

from __future__ import annotations

import argparse
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from model_stage.alfresco_ae_v1_scorer import AlfrescoAEV1Scorer, DEFAULT_META_PATH  # noqa: E402


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 18181
MAX_BODY_BYTES = 1024 * 1024


def json_response(status: int, body: dict[str, Any]) -> tuple[int, bytes]:
    return status, json.dumps(body, ensure_ascii=False, indent=2).encode("utf-8")


def parse_json_body(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    raw_len = handler.headers.get("Content-Length", "0")
    try:
        length = int(raw_len)
    except ValueError as exc:
        raise ValueError("invalid Content-Length") from exc
    if length > MAX_BODY_BYTES:
        raise ValueError("request body too large")
    raw = handler.rfile.read(length) if length else b"{}"
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("invalid JSON body") from exc
    if not isinstance(parsed, dict):
        raise ValueError("JSON body must be an object")
    return parsed


class ScoreServiceHandler(BaseHTTPRequestHandler):
    server_version = "AlfrescoAEV1ScoreService/0.1"

    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stderr.write("%s - - [%s] %s\n" % (self.address_string(), self.log_date_time_string(), fmt % args))

    @property
    def scorer(self) -> AlfrescoAEV1Scorer:
        return self.server.scorer  # type: ignore[attr-defined]

    def send_json(self, status: int, body: dict[str, Any]) -> None:
        status_code, payload = json_response(status, body)
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:
        path = urlparse(self.path).path.rstrip("/") or "/"
        try:
            if path == "/health":
                self.send_json(200, {"status": "ok", "service": "alfresco_ae_v1_score_service"})
                return
            if path == "/model":
                meta = self.scorer.meta
                self.send_json(
                    200,
                    {
                        "model_name": meta.get("model_name", "alfresco_ae_v1"),
                        "model_type": meta.get("model_type", "ae_like_statistical_baseline"),
                        "threshold_low": self.scorer.threshold_low,
                        "threshold_high": self.scorer.threshold_high,
                        "train_sample_count": int(meta.get("train_sample_count", 0)),
                    },
                )
                return
            self.send_json(404, {"error": "not found"})
        except Exception as exc:  # noqa: BLE001 - keep HTTP boundary JSON-only.
            self.send_json(500, {"error": "internal error", "detail": str(exc)})

    def do_POST(self) -> None:
        path = urlparse(self.path).path.rstrip("/") or "/"
        if path != "/score":
            self.send_json(404, {"error": "not found"})
            return
        try:
            sample = parse_json_body(self)
            result = self.scorer.score_sample(sample)
            body = {
                "score": result["score"],
                "pass": bool(result["pass"]),
                "decision": result["decision"],
                "reason": result["reason"],
                "threshold_high": result["threshold_high"],
                "threshold_low": result["threshold_low"],
                "model_name": result["model_name"],
                "model_type": result["model_type"],
                "feature_vector": result.get("feature_vector", []),
            }
            self.send_json(200, body)
        except ValueError as exc:
            self.send_json(400, {"error": str(exc), "decision": "reject"})
        except Exception as exc:  # noqa: BLE001 - do not return traceback.
            self.send_json(500, {"error": "internal error", "detail": str(exc), "decision": "reject"})


class ScoreHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True

    def __init__(self, server_address: tuple[str, int], handler_cls: type[BaseHTTPRequestHandler], scorer: AlfrescoAEV1Scorer):
        super().__init__(server_address, handler_cls)
        self.scorer = scorer


def main() -> int:
    parser = argparse.ArgumentParser(description="Local Alfresco AE v1 score service")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--meta", default=str(DEFAULT_META_PATH))
    args = parser.parse_args()

    scorer = AlfrescoAEV1Scorer(args.meta)
    server = ScoreHTTPServer((args.host, args.port), ScoreServiceHandler, scorer)
    print(f"alfresco-ae-v1-score-service listening on http://{args.host}:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
