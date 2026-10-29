#!/usr/bin/env python3
"""La Jefatura Suite â€” Full Mission Control Demo & White-Label API Server.

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
_ENV_FILE = os.path.join(ROOT, ".env")
if os.path.isfile(_ENV_FILE):
    with open(_ENV_FILE, encoding="utf-8") as _ef:
        for _line in _ef:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))

sys.path.insert(0, os.path.join(ROOT, "server"))

import behavior_brain  # noqa: E402
import buildingapp_ingest  # noqa: E402
import cameras  # noqa: E402
import camera_report  # noqa: E402
import comms_brain  # noqa: E402
import daily_brief_pusher  # noqa: E402
import daily_pdf  # noqa: E402
import google_workspace  # noqa: E402
import jefesito  # noqa: E402
import knowledge_store  # noqa: E402
import mc_auth  # noqa: E402
import meta_whatsapp  # noqa: E402
import nexus_ingest  # noqa: E402
import reports_pdf  # noqa: E402
import tts_colombia  # noqa: E402
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
    knowledge_store.ensure_demo_knowledge_seeded()
    unitec_ingest.summary()
    buildingapp_ingest.summary()
    # Pre-warm Colombian neural voice cache for today's greeting + opening phrase
    try:
        b = jefesito.get_day(lang="es")
        if b and b.get("spoken"):
            tts_colombia.synthesize(b["spoken"], lang="es")
        tts_colombia.synthesize(
            "Soy El Jefesito. Te atiendo por voz o texto, aprendo de cada interacciÃ³n y puedo cambiar el tema, "
            "el idioma, el saludo, cerrar el dÃ­a o imprimir tu resumen. Â¿QuÃ© hacemos?",
            lang="es"
        )
    except Exception:
        pass


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
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Bridge, X-MC-Token")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self):
        self._send(200, {"ok": True})

    def _gate(self, path, qs=None) -> bool:
        """Anything under /api/ that arrives through the public tunnel needs X-MC-Token,
        unless it originates from the Mission Control UI hosted on the same tunnel host."""
        if path in ("/api/calendar.ics", "/api/daily.pdf", "/api/cameras/report.pdf", "/api/whatsapp/webhook"):
            return True
        if path.startswith("/api/") and mc_auth.is_remote(self.headers):
            q_tok = ((qs or {}).get("token") or [""])[0] if qs else ""
            hdr_tok = self.headers.get("X-MC-Token", "") or q_tok
            if mc_auth.token_ok(hdr_tok):
                return True
            host = (self.headers.get("Host") or "").strip().lower()
            ref = (self.headers.get("Referer") or "").strip().lower()
            orig = (self.headers.get("Origin") or "").strip().lower()
            if host and ((ref and f"://{host}" in ref) or (orig and orig.endswith(f"://{host}"))):
                return True
            self._send(401, {"error": "unauthorized: X-MC-Token required for remote access"})
            return False
        return True

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        qs = urllib.parse.parse_qs(parsed.query)
        if not self._gate(path, qs):
            return

        lang_q = (qs.get("lang") or ["es"])[0]
        if path == "/api/tts":
            text = (qs.get("text") or [""])[0]
            voice = (qs.get("voice") or [None])[0]
            rate = (qs.get("rate") or ["+22%"])[0]
            try:
                mp3 = tts_colombia.synthesize(text, lang=lang_q, voice=voice, rate=rate)
                if mp3:
                    self._send(200, mp3, "audio/mpeg")
                else:
                    self._send(400, {"error": "empty text"})
            except Exception as e:
                self._send(500, {"error": str(e)})
            return
        if path == "/api/prefs":
            self._send(200, jefesito.get_prefs())
            return
        if path == "/api/jefesito/brief":
            self._send(200, jefesito.get_day(lang=lang_q))
            return
        if path == "/api/jefesito/pages":
            self._send(200, {"pages": jefesito.pages(lang_q)})
            return
        if path == "/api/jefesito/profile":
            self._send(200, jefesito.profile())
            return
        if path == "/api/daily.pdf":
            out = os.path.join(tempfile.gettempdir(), "_jefesito_daily.pdf")
            built = daily_pdf.build(out, lang=lang_q)
            ctype = "application/pdf" if built.endswith(".pdf") else "text/markdown; charset=utf-8"
            self._send(200, open(built, "rb").read(), ctype)
            return
        if path == "/api/ask":
            q = (qs.get("q") or [""])[0]
            lang = (qs.get("lang") or ["es"])[0]
            self._send(200, knowledge_store.ask(q, lang=lang))
            return
        if path in ("/api/notes", "/api/tasks", "/api/meetings", "/api/emails"):
            kind = path.rsplit("/", 1)[1]
            self._send(200, {kind: knowledge_store.list_items(kind, limit=200)})
            return
        if path == "/api/dev_escalations":
            self._send(200, {"escalations": knowledge_store.list_dev_escalations()})
            return
        if path == "/api/events":
            self._send(200, {"events": knowledge_store.list_events()})
            return
        if path == "/api/calendar.ics":
            self._send(200, knowledge_store.events_ics().encode("utf-8"), "text/calendar; charset=utf-8")
            return
        if path == "/api/export":
            self._send(200, knowledge_store.export_all())
            return

        if path in ("/", "/index.html", "/demo", "/assistant", "/chat"):
            html = open(os.path.join(ROOT, "mock", "demo.html"), "rb").read()
            self._send(200, html, "text/html; charset=utf-8")
        elif path.rstrip("/") in ("/website", "/web", "/presentacion", "/site", "/website-v1", "/website-v2", "/website-v3"):
            html = open(os.path.join(ROOT, "mock", "website.html"), "rb").read()
            self._send(200, html, "text/html; charset=utf-8")
        elif path.startswith("/assets/"):
            rel = os.path.basename(path)
            fpath = os.path.join(ROOT, "assets", rel)
            if os.path.isfile(fpath):
                ext = os.path.splitext(rel)[1].lower()
                mime = {
                    ".mp4": "video/mp4",
                    ".webm": "video/webm",
                    ".png": "image/png",
                    ".jpg": "image/jpeg",
                    ".jpeg": "image/jpeg",
                    ".svg": "image/svg+xml",
                }.get(ext, "application/octet-stream")
                self._send(200, open(fpath, "rb").read(), mime)
            else:
                self._send(404, {"error": "asset not found"})
        elif path == "/favicon.ico":
            self._send(204, b"", "image/x-icon")
        elif path.rstrip("/") == "/widgets/lajefatura-widget.js":
            js = open(os.path.join(ROOT, "widgets", "lajefatura-widget.js"), "rb").read()
            self._send(200, js, "application/javascript; charset=utf-8")
        elif path.rstrip("/") == "/widgets/brain-network-3d.js":
            js = open(os.path.join(ROOT, "widgets", "brain-network-3d.js"), "rb").read()
            self._send(200, js, "application/javascript; charset=utf-8")
        elif path == "/api/nexus/summary":
            self._send(200, nexus_ingest.summary())
        elif path == "/api/unitec/summary":
            force = (qs.get("refresh") or ["0"])[0] == "1"
            self._send(200, unitec_ingest.summary(force_live=force))
        elif path == "/api/buildingapp/summary":
            force = (qs.get("refresh") or ["0"])[0] == "1"
            self._send(200, buildingapp_ingest.summary(force_live=force))
        elif path == "/api/cameras/report":
            day = (qs.get("date") or [None])[0]
            mode = (qs.get("mode") or qs.get("example") or [None])[0]
            self._send(200, camera_report.get_report(day, mode=mode))
        elif path == "/api/cameras/report.pdf":
            day = (qs.get("date") or [None])[0]
            mode = (qs.get("mode") or ["example"])[0]
            lang_q = (qs.get("lang") or ["es"])[0]
            pdf_bytes = camera_report.build_camera_pdf(day=day, mode=mode, lang=lang_q)
            ctype = "application/pdf" if pdf_bytes[:4] == b"%PDF" else "text/markdown; charset=utf-8"
            self._send(200, pdf_bytes, ctype)
        elif path in ("/api/cameras/status", "/api/cameras/hikconnect"):
            force = (qs.get("refresh") or ["0"])[0] == "1"
            self._send(200, cameras.status(os.path.join(SAMPLES, "cameras.json"), force=force))
        elif path == "/api/comms/inbox":
            self._send(200, comms_brain.list_inbox_with_drafts())
        elif path == "/api/whatsapp/status":
            self._send(200, meta_whatsapp.get_status())
        elif path == "/api/whatsapp/webhook":
            code, challenge = meta_whatsapp.verify_webhook(qs)
            self._send(code, challenge.encode("utf-8"), "text/plain; charset=utf-8")
        elif path == "/api/google/status":
            self._send(200, google_workspace.get_status())
        elif path == "/api/reports/daily_brief":
            slot = (qs.get("slot") or ["morning"])[0]
            force = (qs.get("refresh") or ["0"])[0] == "1"
            self._send(200, daily_brief_pusher.build_brief(slot=slot, force_live=force))
        elif path == "/api/google/auth_url":
            host = self.headers.get("Host", f"localhost:{PORT}")
            proto = self.headers.get("X-Forwarded-Proto", "http")
            redir = (qs.get("redirect_uri") or [f"{proto}://{host}/api/google/oauth2callback"])[0]
            self._send(200, google_workspace.get_oauth_url(redir))
        elif path == "/api/google/oauth2callback":
            code_q = (qs.get("code") or [""])[0]
            host = self.headers.get("Host", f"localhost:{PORT}")
            proto = self.headers.get("X-Forwarded-Proto", "http")
            redir = f"{proto}://{host}/api/google/oauth2callback"
            res = google_workspace.exchange_oauth_code(code_q, redir)
            html_msg = (
                "<html><body style='font-family:sans-serif;background:#070B14;color:#F8FAFC;padding:40px;text-align:center'>"
                f"<h2>{'Conectado: Cuenta Google de Juan' if res.get('ok') else 'Error de OAuth'}</h2>"
                f"<p>{res.get('email') or res.get('error', '')}</p>"
                "<p><a href='/' style='color:#10B981'>Volver a La Jefatura Mission Control</a></p></body></html>"
            )
            self._send(200 if res.get("ok") else 400, html_msg.encode("utf-8"), "text/html; charset=utf-8")
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
        qs = urllib.parse.parse_qs(parsed.query)
        if not self._gate(path, qs):
            return
        n = int(self.headers.get("Content-Length", 0))
        try:
            body = json.loads(self.rfile.read(n) or b"{}")
        except ValueError:
            self._send(400, {"error": "invalid JSON"})
            return

        if path == "/api/tts":
            text = body.get("text", "")
            lang_b = body.get("lang", "es")
            voice = body.get("voice")
            rate = body.get("rate", "+22%")
            try:
                mp3 = tts_colombia.synthesize(text, lang=lang_b, voice=voice, rate=rate)
                if mp3:
                    self._send(200, mp3, "audio/mpeg")
                else:
                    self._send(400, {"error": "empty text"})
            except Exception as e:
                self._send(500, {"error": str(e)})
            return
        if path == "/api/prefs":
            self._send(200, jefesito.set_prefs(body))
        elif path == "/api/jefesito/close_day":
            self._send(200, jefesito.close_day())
        elif path == "/api/jefesito/learn":
            self._send(200, jefesito.record(body.get("text", ""), body.get("channel", "text"),
                                            body.get("action"), body.get("lang", "es")))
        elif path == "/api/notes":
            r = knowledge_store.add_note(body.get("text", ""), source=body.get("source", "api"),
                                         company=body.get("company", "all"))
            self._send(200 if r["ok"] else 400, r)
        elif path == "/api/tasks":
            r = knowledge_store.add_task(body.get("title", ""), company=body.get("company", "all"),
                                         owner=body.get("owner", "CEO"), due=body.get("due", ""),
                                         severity=body.get("severity", "medium"), source=body.get("source", "api"))
            self._send(200 if r["ok"] else 400, r)
        elif path == "/api/dev_escalations":
            r = knowledge_store.log_dev_escalation(
                body.get("request", ""), body.get("reason", "ui_escalation"), body.get("channel", "ui"))
            self._send(200 if r.get("ok") else 400, r)
        elif path == "/api/dev_escalations/resolve":
            self._send(200, knowledge_store.resolve_dev_escalation(body.get("id", ""), body.get("resolution", "Resuelto")))
        elif path == "/api/events":
            r = knowledge_store.add_event(body.get("title", ""), body.get("date", ""), body.get("time", ""),
                                          body.get("duration", 30), body.get("company", "all"),
                                          body.get("notes", ""), body.get("source", "ui"))
            self._send(200 if r["ok"] else 400, r)
        elif path == "/api/events/update":
            r = knowledge_store.update_event(body.get("id", ""), **{k: v for k, v in body.items() if k != "id"})
            self._send(200 if r["ok"] else 400, r)
        elif path == "/api/calendar/sync":
            self._send(200, knowledge_store.sync_calendar_integrations())
        elif path == "/api/events/delete":
            self._send(200, knowledge_store.delete_event(body.get("id", "")))
        elif path == "/api/tasks/update":
            r = knowledge_store.update_task(body.get("id", ""), body.get("title"), body.get("due"), body.get("status"))
            self._send(200 if r["ok"] else 400, r)
        elif path == "/api/tasks/delete":
            self._send(200, knowledge_store.delete_task(body.get("id", "")))
        elif path == "/api/meetings":
            r = knowledge_store.add_meeting_summary(
                body.get("summary", ""), title=body.get("title", ""), attendees=body.get("attendees", ""),
                action_items=body.get("action_items", ""), source=body.get("source", "api"),
                company=body.get("company", "all"))
            self._send(200 if r["ok"] else 400, r)
        elif path == "/api/emails/ingest":
            r = knowledge_store.add_email_summary(
                body.get("summary", ""), sender=body.get("sender", ""), subject=body.get("subject", ""),
                source=body.get("source", "ingest"), company=body.get("company", "all"))
            self._send(200 if r["ok"] else 400, r)
        elif path == "/api/nexus/push":
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
        elif path == "/api/whatsapp/webhook":
            self._send(200, meta_whatsapp.handle_webhook_payload(body))
        elif path == "/api/whatsapp/watchlist":
            self._send(200, meta_whatsapp.upsert_watchlist(body))
        elif path == "/api/whatsapp/watchlist/delete":
            self._send(200, meta_whatsapp.delete_watchlist(body.get("chat_id", "")))
        elif path == "/api/whatsapp/config":
            self._send(200, meta_whatsapp.save_config(body))
        elif path == "/api/google/config":
            self._send(200, google_workspace.save_config(body))
        elif path == "/api/google/sync":
            self._send(200, google_workspace.sync_gmail_and_calendar(
                max_emails=int(body.get("max_emails", 10))))
        elif path == "/api/reports/dispatch_daily":
            self._send(200, daily_brief_pusher.dispatch_brief(
                slot=body.get("slot", "morning"),
                to_whatsapp=body.get("to_whatsapp", ""),
                to_email=body.get("to_email", ""),
            ))
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
        elif path == "/api/cameras/events":
            if not mc_auth.token_ok(self.headers.get("X-MC-Token", "")):
                self._send(401, {"error": "X-MC-Token required"})
            else:
                self._send(200, {"ok": True, "stored": camera_report.add_agent_events(body.get("events", []))})
        elif path == "/api/cameras/poll":
            self._send(200, camera_report.poll())
        elif path == "/api/cameras/sync":
            self._send(200, cameras.status(os.path.join(SAMPLES, "cameras.json"), force=True))
        elif path == "/api/voice/command":
            cmd = body.get("command", "")
            lang = body.get("lang", "es")
            res = voice_commands.execute(cmd, lang=lang, samples_dir=SAMPLES)
            jefesito.record(cmd, body.get("channel", "text"), res.get("action"), lang)
            self._send(200, res)
        else:
            self._send(404, {"error": "not found"})


if __name__ == "__main__":
    _seed_if_empty()
    camera_report.start_scheduler()
    daily_brief_pusher.start_scheduler()
    srv = __import__("http.server").server.ThreadingHTTPServer(
        ("0.0.0.0", PORT), Handler)
    print(f"La Jefatura demo -> http://localhost:{PORT}  (Ctrl-C to stop)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
