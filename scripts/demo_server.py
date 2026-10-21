#!/usr/bin/env python3
"""La Jefatura Suite — demo server.

Serves:
  GET  /                  -> mock/demo.html (CEO console, EN/ES, client-side PDF)
  GET  /api/nexus/summary -> live aggregates from mc.db (seeded from samples on
                             first run — the exact shape Nexus pushes)
  GET  /api/report.pdf    -> real generated PDF (reportlab+matplotlib+Gemini if key)

Run:  python3 scripts/demo_server.py [port]     (default 8931)
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "server"))

import nexus_ingest  # noqa: E402
import reports_pdf  # noqa: E402

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8931
SAMPLES = os.path.join(ROOT, "data", "samples")


def _seed_if_empty():
    s = nexus_ingest.summary()
    if s["kpis"]["leads_activos"] == 0:
        nexus_ingest.load_sample(os.path.join(SAMPLES, "nexus_crm.json"))


class Handler(__import__("http.server").server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        data = body if isinstance(body, bytes) else json.dumps(
            body, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            html = open(os.path.join(ROOT, "mock", "demo.html"),
                        "rb").read()
            self._send(200, html, "text/html; charset=utf-8")
        elif self.path.rstrip("/") == "/widgets/lajefatura-widget.js":
            js = open(os.path.join(ROOT, "widgets", "lajefatura-widget.js"),
                      "rb").read()
            self._send(200, js, "application/javascript; charset=utf-8")
        elif self.path == "/api/nexus/summary":
            self._send(200, nexus_ingest.summary())
        elif self.path == "/api/report.pdf":
            out = "/tmp/_demo_report.pdf"
            path = reports_pdf.build_report(
                "Medical Billing Miami Beach", SAMPLES, out)
            pdf = open(path, "rb").read()
            self._send(200, pdf, "application/pdf")
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        if self.path == "/api/nexus/push":
            n = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(n) or b"{}")
            self._send(200, nexus_ingest.push(
                body, source=self.headers.get("X-Bridge", "direct")))
        else:
            self._send(404, {"error": "not found"})


if __name__ == "__main__":
    _seed_if_empty()
    srv = __import__("http.server").server.HTTPServer(
        ("0.0.0.0", PORT), Handler)
    print(f"La Jefatura demo → http://localhost:{PORT}  (Ctrl-C to stop)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
