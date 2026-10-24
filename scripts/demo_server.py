#!/usr/bin/env python3
"""La Jefatura Suite — Full Mission Control Demo & White-Label API Server.

Serves:
  GET  /                         -> mock/demo.html (Multi-tab CEO Mission Control)
  GET  /widgets/lajefatura-widget.js -> Grok 3.0 Voice & DOM-Aware Brain Layer
  GET  /api/nexus/summary        -> Live CRM aggregates from mc.db
  GET  /api/comms/inbox          -> Unified multi-channel inbox + AI pre-drafts + voice profile
  POST /api/comms/draft          -> Generate/regenerate AI draft in CEO's voice
  POST /api/comms/revise         -> Save CEO edit (increments immutable version, updates learning)
  POST /api/comms/approve_send   -> 1-click CEO Approve & Send (Mode C)
  GET  /api/behavior/state       -> CEO Behavioral & Time-of-Day Learning Engine state
  POST /api/behavior/event       -> Record real-time UI/voice/routine telemetry & preferences
  GET  /api/onboarding/state     -> White-label setup & connected integrations state
  POST /api/onboarding/save      -> Save white-label onboarding configuration
  POST /api/voice/command        -> Headless & Grok 3.0 Voice command executor
  GET  /api/report.pdf           -> Real generated Executive PDF (reportlab + matplotlib)

Run:  python scripts/demo_server.py [port]     (default 8931)
"""

import json
import os
import sys
import tempfile
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "server"))

import behavior_brain  # noqa: E402
import buildingapp_ingest  # noqa: E402
import comms_brain  # noqa: E402
import nexus_ingest  # noqa: E402
import reports_pdf  # noqa: E402
import unitec_ingest  # noqa: E402
import voice_commands  # noqa: E402

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8931
SAMPLES = os.path.join(ROOT, "data", "samples")
ONBOARDING_FILE = os.path.join(ROOT, "data", "onboarding_state.json")

DEFAULT_ONBOARDING = {
    "brand_name": "LA JEFATURA",
    "ceo_name": "Jasmel Acosta",
    "accent_color": "#23d9b0",
    "operating_mode": "C",
    "onboarding_completed": True,
    "integrations": [
        {"id": "gcal", "name": "Google Calendar & Outlook", "category": "Calendars & Schedule", "connected": True, "account": "jasmelacosta@gmail.com", "sync_interval": "Real-time"},
        {"id": "gmail", "name": "Gmail / Brevo / Corporate Mail", "category": "Email & Draft Brain", "connected": True, "account": "jasmel@medicalbillingmb.com", "sync_interval": "Real-time"},
        {"id": "meetings", "name": "Google Meet & Zoom Intelligence", "category": "Meetings & Briefs", "connected": True, "account": "Workspace Auto-Notes", "sync_interval": "Post-call"},
        {"id": "nexus", "name": "Nexus CRM Global & Pipelines", "category": "CRM & Sales Data", "connected": True, "account": "nexus-crm-global.ai.studio", "sync_interval": "Every 5m"},
        {"id": "tasks", "name": "Mission Control Tasks & Escalations", "category": "Task Managers & Assignments", "connected": True, "account": "24h Nudge / 48h Critical", "sync_interval": "Hourly"},
        {"id": "cameras", "name": "ONVIF / RTSP AI Security Cameras", "category": "Camera Monitoring", "connected": True, "account": "4 Zones (MBMB / Warehouse)", "sync_interval": "Live + 12h Digest"},
        {"id": "people", "name": "Staff Velocity & Assignment Monitor", "category": "People Monitoring", "connected": True, "account": "Juan, Maria, Carlos, AI Agents", "sync_interval": "Continuous"},
        {"id": "clients", "name": "Client Health & Retention Radar", "category": "Clients Monitoring", "connected": True, "account": "12 Active Accounts (4 Countries)", "sync_interval": "Daily"},
        {"id": "grok_voice", "name": "Grok 3.0 Voice & DOM Brain Layer", "category": "Voice & Behavioral AI", "connected": True, "account": "Bilingual ES/EN + Profile Memory", "sync_interval": "Always-On"},
    ]
}


def _get_onboarding():
    if os.path.isfile(ONBOARDING_FILE):
        try:
            return json.load(open(ONBOARDING_FILE, encoding="utf-8"))
        except Exception:
            pass
    return dict(DEFAULT_ONBOARDING)


def _save_onboarding(payload: dict):
    cur = _get_onboarding()
    cur.update(payload)
    os.makedirs(os.path.dirname(ONBOARDING_FILE), exist_ok=True)
    with open(ONBOARDING_FILE, "w", encoding="utf-8") as f:
        json.dump(cur, f, indent=2, ensure_ascii=False)
    if "operating_mode" in payload and payload["operating_mode"] in ("A", "B", "C", "D"):
        comms_brain.set_mode("default", payload["operating_mode"])
    return cur


def _seed_if_empty():
    s = nexus_ingest.summary()
    if s["kpis"]["leads_activos"] == 0:
        nexus_ingest.load_sample(os.path.join(SAMPLES, "nexus_crm.json"))
    comms_brain.ensure_demo_inbox_seeded()
    behavior_brain.ensure_seeded()
    unitec_ingest.summary()
    buildingapp_ingest.summary()


class Handler(__import__("http.server").server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        data = body if isinstance(body, bytes) else json.dumps(
            body, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Bridge")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self):
        self._send(200, {"ok": True})

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        qs = urllib.parse.parse_qs(parsed.query)

        if path in ("/", "/index.html"):
            html = open(os.path.join(ROOT, "mock", "demo.html"), "rb").read()
            self._send(200, html, "text/html; charset=utf-8")
        elif path == "/favicon.ico":
            self._send(204, b"", "image/x-icon")
        elif path.rstrip("/") == "/widgets/lajefatura-widget.js":
            js = open(os.path.join(ROOT, "widgets", "lajefatura-widget.js"), "rb").read()
            self._send(200, js, "application/javascript; charset=utf-8")
        elif path == "/api/nexus/summary":
            self._send(200, nexus_ingest.summary())
        elif path == "/api/unitec/summary":
            force = (qs.get("refresh") or ["0"])[0] == "1"
            self._send(200, unitec_ingest.summary(force_live=force))
        elif path == "/api/buildingapp/summary":
            force = (qs.get("refresh") or ["0"])[0] == "1"
            self._send(200, buildingapp_ingest.summary(force_live=force))
        elif path == "/api/comms/inbox":
            self._send(200, comms_brain.list_inbox_with_drafts())
        elif path == "/api/behavior/state":
            slot = (qs.get("slot") or [None])[0]
            self._send(200, behavior_brain.get_state(slot=slot))
        elif path == "/api/onboarding/state":
            self._send(200, _get_onboarding())
        elif path == "/api/report.pdf":
            company = (qs.get("company") or ["Medical Billing Miami Beach"])[0]
            lang = (qs.get("lang") or ["es"])[0]
            out = os.path.join(tempfile.gettempdir(), "_demo_report.pdf")
            built_path = reports_pdf.build_report(company, SAMPLES, out, lang=lang)
            pdf = open(built_path, "rb").read()
            ctype = "application/pdf" if built_path.endswith(".pdf") else "text/markdown; charset=utf-8"
            self._send(200, pdf, ctype)
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        n = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(n) or b"{}")

        if path == "/api/nexus/push":
            self._send(200, nexus_ingest.push(
                body, source=self.headers.get("X-Bridge", "direct")))
        elif path == "/api/unitec/push":
            tok = self.headers.get("X-MC-Token", "")
            res = unitec_ingest.push(body, token=tok)
            self._send(200 if res.get("ok") else 401, res)
        elif path == "/api/buildingapp/push":
            tok = self.headers.get("X-MC-Token", "")
            res = buildingapp_ingest.push(body, token=tok)
            self._send(200 if res.get("ok") else 401, res)
        elif path == "/api/comms/draft":
            tid = body.get("thread_id", "")
            ch = body.get("channel", "gmail")
            hints = body.get("style_hints", "")
            self._send(200, comms_brain.create_draft(tid, channel=ch, style_hints=hints))
        elif path == "/api/comms/revise":
            did = int(body.get("draft_id", 0))
            new_body = body.get("body", "")
            behavior_brain.record_event("typing", f"draft_edit_{did}", {"len": len(new_body)})
            self._send(200, comms_brain.revise(did, new_body, actor="jasmel", reason="owner_edit"))
        elif path == "/api/comms/approve_send":
            did = int(body.get("draft_id", 0))
            behavior_brain.record_event("click", f"approve_send_draft_{did}", {"draft_id": did})
            self._send(200, comms_brain.approve_and_send(did, approver="jasmel"))
        elif path == "/api/behavior/event":
            et = body.get("event_type", "click")
            tg = body.get("target", "ui")
            dt = body.get("detail", {})
            sl = body.get("time_slot")
            self._send(200, behavior_brain.record_event(et, tg, detail=dt, time_slot=sl))
        elif path == "/api/onboarding/save":
            self._send(200, _save_onboarding(body))
        elif path == "/api/voice/command":
            cmd = body.get("command", "")
            lang = body.get("lang", "es")
            self._send(200, voice_commands.execute(cmd, lang=lang, samples_dir=SAMPLES))
        else:
            self._send(404, {"error": "not found"})


if __name__ == "__main__":
    _seed_if_empty()
    srv = __import__("http.server").server.HTTPServer(
        ("0.0.0.0", PORT), Handler)
    print(f"La Jefatura demo -> http://localhost:{PORT}  (Ctrl-C to stop)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
