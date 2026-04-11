#!/usr/bin/env python3
"""Eurostars Check-in Reception Server — serves guest reports for the front-desk demo."""

import http.server
import json
import re
import urllib.parse
from pathlib import Path
from html.parser import HTMLParser

PORT = 3002
BASE_DIR = Path(__file__).parent.resolve()
PROJECT_ROOT = BASE_DIR.parents[1]
REPORT_DIR = PROJECT_ROOT / "output"

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
    ".webp": "image/webp",
}


# ── Guest data extractor ──────────────────────────────────────────────
def extract_guest_data(html_content: str, guest_id: str) -> dict:
    """Parse key data points from a checkin report HTML."""
    data = {"id": guest_id}

    # Name / title
    m = re.search(r'Guest\s*#(\d+)', html_content)
    if m:
        data["guest_number"] = m.group(1)

    # Demographics line: "Masculino · 46-65 años · País: ES"
    m = re.search(r'(Masculino|Femenino|No especificado)\s*·\s*([\d\-\+]+\s*años)\s*·\s*País:\s*(\w+)', html_content)
    if m:
        data["gender"] = m.group(1)
        data["age_range"] = m.group(2)
        data["country"] = m.group(3)

    # Value badge
    if "HIGH VALUE" in html_content:
        data["value"] = "HIGH VALUE"
    elif "MID VALUE" in html_content:
        data["value"] = "MID VALUE"
    elif "LOW VALUE" in html_content:
        data["value"] = "LOW VALUE"
    elif "VIP" in html_content:
        data["value"] = "VIP"
    else:
        data["value"] = "STANDARD"

    # Metrics
    metrics_pattern = re.compile(
        r'font-size:\s*22px;[^>]*>(\d+[\.,]?\d*[€]?)</p>\s*'
        r'<p[^>]*>(Estancias|Hoteles|ADR medio|Nota media)</p>',
        re.DOTALL
    )
    for val, label in metrics_pattern.findall(html_content):
        key = label.lower().replace(" ", "_")
        data[key] = val.strip()

    # Profile / segment
    m = re.search(r'<strong>Perfil:</strong>\s*(\w+)', html_content)
    if m:
        data["profile"] = m.group(1)

    m = re.search(r'<strong>Patrón:</strong>\s*(\w+)', html_content)
    if m:
        data["pattern"] = m.group(1)

    m = re.search(r'<strong>Edad:</strong>\s*(\w+)', html_content)
    if m:
        data["age_segment"] = m.group(1)

    m = re.search(r'<strong>Estancia media:</strong>\s*([\d\.]+)\s*noches', html_content)
    if m:
        data["avg_nights"] = m.group(1)

    # Hotels from history
    hotels = re.findall(r'padding-top:\s*4px;["\']>\s*([^<]+)</td>\s*<td[^>]*>\s*(\d{4}-\d{2}-\d{2})', html_content)
    if hotels:
        data["last_hotel"] = hotels[-1][0].strip()
        data["last_checkin"] = hotels[-1][1].strip()
        data["hotels"] = list(set(h[0].strip() for h in hotels))

    return data


def build_guest_index() -> list:
    """Scan all checkin_report HTML files and extract guest summaries."""
    guests = []
    report_files = sorted(REPORT_DIR.glob("checkin_report_*.html"))
    print(f"  📂 Indexing {len(report_files)} guest reports...")

    for f in report_files:
        guest_id = f.stem.replace("checkin_report_", "")
        try:
            content = f.read_text(encoding="utf-8")
            guest = extract_guest_data(content, guest_id)
            guests.append(guest)
        except Exception as e:
            print(f"  ⚠ Error parsing {f.name}: {e}")

    print(f"  ✅ Indexed {len(guests)} guests")
    return guests


# ── HTTP Server ───────────────────────────────────────────────────────
class ReceptionHandler(http.server.BaseHTTPRequestHandler):
    guest_index = []

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
        query = urllib.parse.parse_qs(parsed.query)

        # API: guest index (searchable)
        if pathname == "/api/guests":
            search = query.get("q", [""])[0].lower()
            results = self.guest_index
            if search:
                results = [
                    g for g in results
                    if search in g.get("id", "").lower()
                    or search in g.get("guest_number", "").lower()
                    or search in g.get("profile", "").lower()
                    or search in g.get("country", "").lower()
                    or search in g.get("value", "").lower()
                    or search in g.get("gender", "").lower()
                    or search in g.get("last_hotel", "").lower()
                    or any(search in h.lower() for h in g.get("hotels", []))
                ]
            self._send(200, "application/json", json.dumps(results))
            return

        # API: single guest report HTML
        if pathname.startswith("/api/report/"):
            guest_id = pathname[len("/api/report/"):]
            filepath = REPORT_DIR / f"checkin_report_{guest_id}.html"
            if not filepath.exists():
                self._send(404, "text/plain", "Report not found")
                return
            content = filepath.read_text(encoding="utf-8")
            self._send(200, "text/html; charset=utf-8", content)
            return

        # Serve static files
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
    # Build the index at startup
    ReceptionHandler.guest_index = build_guest_index()

    server = http.server.HTTPServer(("", PORT), ReceptionHandler)
    print(f"\n  🏨 Eurostars Reception Server running at http://localhost:{PORT}\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Server stopped.")
        server.server_close()


if __name__ == "__main__":
    main()
