#!/usr/bin/env python3
"""Eurostars Marketing Dashboard server."""

from __future__ import annotations

import http.server
import json
import sys
import urllib.parse
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.marketing.dashboard_engine import build_dashboard_data, load_context, save_context

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
    def log_message(self, fmt, *args):
        print(f"  {args[0]}")

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

        if pathname == "/":
            self._send_file(BASE_DIR / "index.html")
            return

        self._send_file(BASE_DIR / pathname.lstrip("/"))

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        pathname = urllib.parse.unquote(parsed.path)

        if pathname == "/api/context":
            try:
                payload = self._read_json_body()
                context = save_context(payload)
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

        self._send(404, "application/json; charset=utf-8", json.dumps({"error": "Not found"}))

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()


def main():
    server = http.server.HTTPServer(("", PORT), MarketingHandler)
    print(f"\n  📈 Eurostars Marketing Dashboard running at http://localhost:{PORT}\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Server stopped.")
        server.server_close()


if __name__ == "__main__":
    main()
