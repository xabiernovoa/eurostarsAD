#!/usr/bin/env python3
"""Gmail demo backed directly by `data/` identities and `output/` emails."""

from __future__ import annotations

import http.server
import json
import re
import sys
import urllib.parse
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEMOS_DIR = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(DEMOS_DIR) not in sys.path:
    sys.path.insert(0, str(DEMOS_DIR))

from guest_directory import build_mail_profiles

PORT = 3001
BASE_DIR = Path(__file__).parent.resolve()
EMAIL_OUTPUT_DIR = PROJECT_ROOT / "output"
EUROSTARS_IMAGES = PROJECT_ROOT / "images"
EMOJI_RE = re.compile(r"[\U0001F1E6-\U0001F1FF\U0001F300-\U0001FAFF\u2600-\u27BF\uFE0F]+", re.UNICODE)

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

    def _safe_output_email_path(self, raw_name: str) -> Path | None:
        filename = Path(raw_name).name
        if filename != raw_name or not filename.endswith(".html"):
            return None
        path = (EMAIL_OUTPUT_DIR / filename).resolve()
        try:
            path.relative_to(EMAIL_OUTPUT_DIR.resolve())
        except ValueError:
            return None
        return path

    def _strip_emojis(self, value):
        if isinstance(value, str):
            return re.sub(r"\s{2,}", " ", EMOJI_RE.sub("", value)).strip()
        if isinstance(value, list):
            return [self._strip_emojis(item) for item in value]
        if isinstance(value, dict):
            return {key: self._strip_emojis(item) for key, item in value.items()}
        return value

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        pathname = urllib.parse.unquote(parsed.path)

        # API: dynamic profiles from CSV + output
        if pathname == "/api/profiles":
            payload = build_mail_profiles()
            self._send(
                200,
                "application/json; charset=utf-8",
                json.dumps(self._strip_emojis(payload), ensure_ascii=False),
            )
            return

        # API: get email HTML content from output/
        if pathname.startswith("/api/email/"):
            filename = pathname[len("/api/email/"):]
            filepath = self._safe_output_email_path(filename)
            if filepath is None or not filepath.exists():
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
            self._send(200, "text/html; charset=utf-8", EMOJI_RE.sub("", content))
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
