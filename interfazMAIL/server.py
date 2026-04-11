#!/usr/bin/env python3
"""Gmail Demo Server — serves the fake Gmail interface and Eurostars email HTML files."""

import http.server
import json
import os
import re
import urllib.parse
from pathlib import Path

PORT = 3001
EMAIL_DIR = Path(__file__).parent.resolve()
EUROSTARS_IMAGES = Path("/home/xabier/Documentos/eurostars/images")

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
    ".woff2": "font/woff2",
    ".woff": "font/woff",
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
        data = filepath.read_bytes()
        self._send(200, mime, data)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        pathname = urllib.parse.unquote(parsed.path)

        # API: list email HTML files
        if pathname == "/api/emails":
            files = sorted(
                f for f in os.listdir(EMAIL_DIR)
                if f.endswith(".html") and f != "index.html"
            )
            emails = []
            for idx, filename in enumerate(files):
                content = (EMAIL_DIR / filename).read_text(encoding="utf-8")
                # Extract title
                m = re.search(r"<title>(.*?)</title>", content, re.IGNORECASE)
                title = m.group(1) if m else filename
                # Extract preheader
                m = re.search(
                    r'<div[^>]*style="display:\s*none[^"]*"[^>]*>([\s\S]*?)</div>',
                    content, re.IGNORECASE,
                )
                preheader = m.group(1).strip() if m else ""
                # Determine type
                is_post = filename.startswith("post_stay")
                etype = "post_stay" if is_post else "pre_arrival"
                # Extract numeric ID
                id_m = re.search(r"(\d+)", filename)
                eid = id_m.group(1) if id_m else str(idx)

                emails.append({
                    "id": eid,
                    "filename": filename,
                    "title": title,
                    "preheader": preheader,
                    "type": etype,
                })
            self._send(200, "application/json", json.dumps(emails))
            return

        # API: get single email HTML (rewrite image paths)
        if pathname.startswith("/api/email/"):
            filename = pathname[len("/api/email/"):]
            filepath = EMAIL_DIR / filename
            if not filepath.exists():
                self._send(404, "text/plain", "Not found")
                return
            content = filepath.read_text(encoding="utf-8")
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

        # Serve static files
        if pathname == "/":
            self._send_file(EMAIL_DIR / "index.html")
        else:
            self._send_file(EMAIL_DIR / pathname.lstrip("/"))

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.end_headers()


def main():
    server = http.server.HTTPServer(("", PORT), GmailDemoHandler)
    print(f"\n  📧 Gmail Demo Server running at http://localhost:{PORT}\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Server stopped.")
        server.server_close()


if __name__ == "__main__":
    main()
