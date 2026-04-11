#!/usr/bin/env python3
"""Gmail Demo Server — serves the multi-profile Gmail interface for Eurostars demo."""

import http.server
import json
import re
import urllib.parse
from pathlib import Path

PORT = 3001
BASE_DIR = Path(__file__).parent.resolve()
PROJECT_ROOT = BASE_DIR.parents[1]
EMAIL_OUTPUT_DIR = PROJECT_ROOT / "output"
EUROSTARS_IMAGES = PROJECT_ROOT / "images"

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


class GmailDemoHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print(f"  {args[0]}")

    def _send(self, code, content_type, body):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, filepath: Path):
        if not filepath.exists():
            self._send(404, "text/plain", "Not found")
            return
        ext = filepath.suffix.lower()
        mime = MIME_TYPES.get(ext, "application/octet-stream")
        self._send(200, mime, filepath.read_bytes())

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        pathname = urllib.parse.unquote(parsed.path)

        # API: profiles.json
        if pathname == "/api/profiles":
            self._send_file(BASE_DIR / "profiles.json")
            return

        # API: get email HTML content (rewrite image paths)
        if pathname.startswith("/api/email/"):
            filename = pathname[len("/api/email/"):]
            # Try output dir first, then base dir
            filepath = EMAIL_OUTPUT_DIR / filename
            if not filepath.exists():
                filepath = BASE_DIR / filename
            if not filepath.exists():
                self._send(404, "text/plain", "Not found")
                return
            content = filepath.read_text(encoding="utf-8")
            content = content.replace(
                f'src="{EUROSTARS_IMAGES.as_posix()}/',
                'src="/images/eurostars/',
            )
            content = content.replace(
                'src="/home/xabier/Documentos/eurostars/images/',
                'src="/images/eurostars/',
            )
            self._send(200, "text/html; charset=utf-8", content)
            return

        # Serve eurostars images
        if pathname.startswith("/images/eurostars/"):
            img_rel = pathname[len("/images/eurostars/"):]
            self._send_file(EUROSTARS_IMAGES / img_rel)
            return

        # Serve static files from BASE_DIR
        if pathname == "/":
            self._send_file(BASE_DIR / "index.html")
        else:
            self._send_file(BASE_DIR / pathname.lstrip("/"))

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.end_headers()


def main():
    server = http.server.HTTPServer(("", PORT), GmailDemoHandler)
    print(f"\n  Gmail Demo Server running at http://localhost:{PORT}\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Server stopped.")
        server.server_close()


if __name__ == "__main__":
    main()
