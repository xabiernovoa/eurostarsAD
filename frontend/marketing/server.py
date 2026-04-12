#!/usr/bin/env python3
"""Eurostars Marketing Dashboard server."""

from __future__ import annotations

import http.server
import json
import socketserver
import sys
import urllib.parse
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from dotenv import load_dotenv  # type: ignore

    load_dotenv(PROJECT_ROOT / ".env")
except ModuleNotFoundError:
    pass

from pipeline.marketing.dashboard_engine import build_dashboard_data, load_context, save_context
from pipeline.marketing.chat_engine import handle_chat_message, refresh_dashboard_cache, generate_campaign_proposals, handle_modify_messaging
from autonomous.live import iter_tick

PORT = 3003
BASE_DIR = Path(__file__).parent.resolve()

MIME_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".jpeg": "image/jpeg",
    ".jpg": "image/jpeg",
    ".png": "image/png",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
}


class MarketingHandler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        print(f"  {args[0]}")

    def _start_chunked_stream(self, content_type: str = "application/x-ndjson; charset=utf-8"):
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-cache, no-transform")
        self.send_header("Connection", "keep-alive")
        self.send_header("Transfer-Encoding", "chunked")
        self.send_header("X-Accel-Buffering", "no")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

    def _write_chunk(self, data: bytes) -> None:
        size = f"{len(data):X}".encode("ascii")
        self.wfile.write(size + b"\r\n" + data + b"\r\n")
        self.wfile.flush()

    def _end_chunked_stream(self) -> None:
        self.wfile.write(b"0\r\n\r\n")
        self.wfile.flush()

    def _emit_ndjson(self, event: dict) -> None:
        line = (json.dumps(event, ensure_ascii=False, default=str) + "\n").encode("utf-8")
        self._write_chunk(line)

    def _send(self, code: int, content_type: str, body):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, filepath: Path):
        if not filepath.exists():
            self._send(404, "text/plain; charset=utf-8", "Not found")
            return
        mime = MIME_TYPES.get(filepath.suffix.lower(), "application/octet-stream")
        self._send(200, mime, filepath.read_bytes())

    def _read_json_body(self) -> dict:
        content_length = int(self.headers.get("Content-Length", "0") or "0")
        raw = self.rfile.read(content_length) if content_length else b"{}"
        if not raw:
            return {}
        return json.loads(raw.decode("utf-8"))

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        pathname = urllib.parse.unquote(parsed.path)

        if pathname == "/api/dashboard":
            self._send(200, "application/json; charset=utf-8", json.dumps(build_dashboard_data(), ensure_ascii=False))
            return

        if pathname == "/api/context":
            self._send(200, "application/json; charset=utf-8", json.dumps(load_context(), ensure_ascii=False))
            return

        if pathname == "/api/campaigns":
            self._send(200, "application/json; charset=utf-8",
                       json.dumps(generate_campaign_proposals(), ensure_ascii=False))
            return

        if pathname == "/api/autonomous/stream":
            self._handle_autonomous_stream(parsed.query)
            return

        if pathname.startswith("/api/autonomous/email/"):
            self._handle_email_preview(pathname)
            return

        if pathname == "/":
            self._send_file(BASE_DIR / "index.html")
            return

        self._send_file(BASE_DIR / pathname.lstrip("/"))

    def _handle_email_preview(self, pathname: str) -> None:
        # /api/autonomous/email/{guest_id}
        raw_id = pathname.rsplit("/", 1)[-1]
        # Sanitización estricta: solo alfanuméricos, guiones y guion bajo.
        guest_id = "".join(ch for ch in raw_id if ch.isalnum() or ch in ("-", "_"))
        if not guest_id:
            self._send(400, "application/json; charset=utf-8",
                       json.dumps({"error": "guest_id inválido"}, ensure_ascii=False))
            return
        email_path = PROJECT_ROOT / "autonomous" / "output" / "emails" / f"pre_arrival_{guest_id}.html"
        try:
            email_path = email_path.resolve()
            emails_root = (PROJECT_ROOT / "autonomous" / "output" / "emails").resolve()
            if emails_root not in email_path.parents:
                raise ValueError("path escape")
        except Exception:
            self._send(400, "application/json; charset=utf-8",
                       json.dumps({"error": "ruta inválida"}, ensure_ascii=False))
            return
        if email_path.is_file():
            self._send_file(email_path)
        else:
            self._send(404, "application/json; charset=utf-8",
                       json.dumps({"error": "Email no encontrado"}, ensure_ascii=False))

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        pathname = urllib.parse.unquote(parsed.path)

        if pathname == "/api/context":
            try:
                payload = self._read_json_body()
                context = save_context(payload)
                refresh_dashboard_cache()
                response = {
                    "context": context,
                    "dashboard": build_dashboard_data(),
                }
                self._send(200, "application/json; charset=utf-8", json.dumps(response, ensure_ascii=False))
            except Exception as exc:
                self._send(
                    400,
                    "application/json; charset=utf-8",
                    json.dumps({"error": str(exc)}, ensure_ascii=False),
                )
            return

        if pathname == "/api/chat":
            try:
                payload = self._read_json_body()
                message = payload.get("message", "").strip()
                history = payload.get("history", [])
                if not message:
                    self._send(400, "application/json; charset=utf-8",
                               json.dumps({"error": "No message provided"}, ensure_ascii=False))
                    return
                result = handle_chat_message(message, history)
                self._send(200, "application/json; charset=utf-8",
                           json.dumps(result, ensure_ascii=False))
            except Exception as exc:
                self._send(
                    500,
                    "application/json; charset=utf-8",
                    json.dumps({"error": str(exc)}, ensure_ascii=False),
                )
            return

        if pathname == "/api/campaigns/modify":
            try:
                payload = self._read_json_body()
                campaign_id = payload.get("campaign_id", "").strip()
                instructions = payload.get("instructions", "").strip()
                if not campaign_id or not instructions:
                    self._send(400, "application/json; charset=utf-8",
                               json.dumps({"error": "campaign_id and instructions required"}, ensure_ascii=False))
                    return
                result = handle_modify_messaging(campaign_id, instructions)
                self._send(200, "application/json; charset=utf-8",
                           json.dumps(result, ensure_ascii=False))
            except Exception as exc:
                self._send(
                    500,
                    "application/json; charset=utf-8",
                    json.dumps({"error": str(exc)}, ensure_ascii=False),
                )
            return

        self._send(404, "application/json; charset=utf-8", json.dumps({"error": "Not found"}))

    def _handle_autonomous_stream(self, query: str) -> None:
        params = urllib.parse.parse_qs(query or "")

        def _flag(name: str, default: bool = False) -> bool:
            raw = params.get(name, [""])[0].lower()
            if raw in {"1", "true", "yes", "y", "on"}:
                return True
            if raw in {"0", "false", "no", "n", "off"}:
                return False
            return default

        def _int(name: str, default: int) -> int:
            try:
                return int(params.get(name, [default])[0])
            except (TypeError, ValueError):
                return default

        force_mock = _flag("force_mock", False)
        delay = _int("delay", 2 if force_mock else 10)
        max_recs = max(1, min(50, _int("max", 20)))
        workers = max(1, min(6, _int("workers", 3)))
        campaigns = max(0, min(10, _int("campaigns", 5)))
        # Compatibilidad: clientes antiguos que pasen ``generic_every_n``
        # reciben silencio (el parámetro ya no existe).

        self._start_chunked_stream()
        try:
            for event in iter_tick(
                force_mock=force_mock,
                reset_state=True,
                delay_between_seconds=float(delay),
                max_recommendations=max_recs,
                pacing_seconds=0.15 if force_mock else 0.05,
                recommender_workers=workers,
                campaigns_per_tick=campaigns,
            ):
                try:
                    self._emit_ndjson(event)
                except (BrokenPipeError, ConnectionResetError):
                    # Cliente cerró la conexión — detenemos el tick.
                    return
        except Exception as exc:  # pragma: no cover — defensivo
            try:
                self._emit_ndjson({"type": "error", "stage": "server", "message": str(exc)})
            except Exception:
                pass
        finally:
            try:
                self._end_chunked_stream()
            except Exception:
                pass

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()


class ThreadedHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def main():
    server = ThreadedHTTPServer(("", PORT), MarketingHandler)
    print(f"\n  Eurostars Marketing Dashboard running at http://localhost:{PORT}\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Server stopped.")
        server.server_close()


if __name__ == "__main__":
    main()
