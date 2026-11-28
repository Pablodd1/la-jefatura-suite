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

import base64
import json
import os
import sys
import tempfile
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import live_review_telemetry  # noqa: E402
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
import daily_company_reports  # noqa: E402
import daily_pdf  # noqa: E402
import ga4_ingest  # noqa: E402
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
import ceo_action_brain  # noqa: E402
import text_messaging  # noqa: E402
import unified_life_os  # noqa: E402
import functions_catalog  # noqa: E402
import voice_calls_engine  # noqa: E402
import sam3_tracker_engine  # noqa: E402
import ceo_live_onboarding  # noqa: E402
import llm_router  # noqa: E402
import llm_observability  # noqa: E402
import csuite_intelligence  # noqa: E402
import twenty_crm_sync  # noqa: E402

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8931
SAMPLES = os.path.join(ROOT, "data", "samples")
ONBOARDING_FILE = os.path.join(ROOT, "data", "onboarding_state.json")

DEFAULT_ONBOARDING = {
    "brand_name": "LA JEFATURA — Made & Powered by Building Innovation",
    "ceo_name": "Juan Garcia",
    "accent_color": "#23d9b0",
    "operating_mode": "C",
    "onboarding_completed": True,
    "integrations": [
        {"id": "gcal", "name": "Google Calendar & Outlook", "category": "Calendars & Schedule", "connected": True, "account": "jgarcia@buildinginnovation.us", "sync_interval": "Real-time"},
        {"id": "gmail", "name": "Gmail / Brevo / Corporate Mail", "category": "Email & Draft Brain", "connected": True, "account": "jgarcia@buildinginnovation.us", "sync_interval": "Real-time"},
        {"id": "meetings", "name": "Google Meet & Zoom Intelligence", "category": "Meetings & Briefs", "connected": True, "account": "Workspace Auto-Notes", "sync_interval": "Post-call"},
        {"id": "nexus", "name": "Nexus CRM Global & Pipelines", "category": "CRM & Sales Data", "connected": True, "account": "nexus-crm-global.ai.studio", "sync_interval": "Every 5m"},
        {"id": "tasks", "name": "La Jefatura Tasks & Escalations", "category": "Task Managers & Assignments", "connected": True, "account": "24h Nudge / 48h Critical", "sync_interval": "Hourly"},
        {"id": "cameras", "name": "55 Cámaras CCTV Hik-Connect Cloud", "category": "Camera Monitoring", "connected": True, "account": "4 Sedes (USA Miami, Pick-In, Espacios, IDEO)", "sync_interval": "Live + Morning Newspaper"},
        {"id": "people", "name": "Staff Velocity & Assignment Monitor", "category": "People Monitoring", "connected": True, "account": "Juan, Jasmel, Equipo UNITEC & Building", "sync_interval": "Continuous"},
        {"id": "clients", "name": "Client Health & Retention Radar", "category": "Clients Monitoring", "connected": True, "account": "UNITEC USA, BuildingApp, Espacios Importados", "sync_interval": "Daily"},
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


def _transcribe_audio_with_gemini(
    audio_base64: str,
    mime_type: str = "audio/webm",
    lang: str = "es",
    timeout: float = 20.0,
) -> dict:
    """Lightweight Gemini inlineData audio transcription helper local to demo_server.py."""
    t0 = time.monotonic()
    raw_b64 = (audio_base64 or "").strip()
    if raw_b64.startswith("data:") and "," in raw_b64:
        header, raw_b64 = raw_b64.split(",", 1)
        m_mime = header[5:].split(";", 1)[0].strip()
        if m_mime:
            mime_type = m_mime
    clean_b64 = "".join(raw_b64.split())
    if not clean_b64:
        return {"ok": False, "transcript": "", "provider": "none", "model": "none", "latency_ms": 0, "error": "empty_audio"}
    try:
        base64.b64decode(clean_b64, validate=True)
    except Exception:
        return {"ok": False, "transcript": "", "provider": "none", "model": "none", "latency_ms": 0, "error": "invalid_base64"}

    api_key = ""
    try:
        api_key = llm_router._load_env_var("GEMINI_API_KEY", "")
    except Exception:
        api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        return {"ok": False, "transcript": "", "provider": "none", "model": "none", "latency_ms": 0, "error": "gemini_api_key_missing"}

    lang_lbl = "English" if str(lang).lower().startswith("en") else "Spanish"
    prompt = (
        f"Transcribe this executive voice audio accurately in {lang_lbl}. "
        "Return ONLY the clean verbatim transcript text with proper punctuation, no extra commentary."
    )
    models = []
    try:
        models = llm_router._gemini_models(prefer_pro=False)
    except Exception:
        models = ["gemini-3.1-flash-lite", "gemini-3-flash-preview", "gemini-flash-latest"]

    errors = []
    for model in models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        payload = {
            "contents": [{
                "role": "user",
                "parts": [
                    {"text": prompt},
                    {"inlineData": {"mimeType": mime_type or "audio/webm", "data": clean_b64}},
                ],
            }],
            "generationConfig": {"temperature": 0.0, "maxOutputTokens": 512},
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8", errors="replace"))
            cands = data.get("candidates") or []
            parts = (cands[0].get("content", {}).get("parts") or []) if cands else []
            txt = "".join(p.get("text", "") for p in parts if isinstance(p, dict) and not p.get("thought") and p.get("text")).strip()
            if not txt and parts:
                txt = "".join(p.get("text", "") for p in parts if isinstance(p, dict) and p.get("text")).strip()
            if txt:
                return {
                    "ok": True,
                    "transcript": txt,
                    "provider": "gemini",
                    "model": model,
                    "latency_ms": int((time.monotonic() - t0) * 1000),
                    "error": None,
                }
            errors.append(f"{model}: empty transcript")
        except urllib.error.HTTPError as exc:
            snippet = ""
            try:
                snippet = exc.read().decode("utf-8", errors="ignore")[:160].replace("\n", " ")
            except Exception:
                pass
            errors.append(f"{model}: HTTP {exc.code} {snippet}".strip())
        except Exception as exc:
            errors.append(f"{model}: {type(exc).__name__}: {exc}")

    return {
        "ok": False,
        "transcript": "",
        "provider": "gemini",
        "model": models[-1] if models else "none",
        "latency_ms": int((time.monotonic() - t0) * 1000),
        "error": " | ".join(errors[-3:]) if errors else "transcription_failed",
    }


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
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Bridge, X-MC-Token")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)
        try:
            if not getattr(self, "_skip_http_telemetry", False) and getattr(self, "command", "") != "OPTIONS":
                t0 = getattr(self, "_t0_req", None)
                dur_ms = int((time.perf_counter() - t0) * 1000) if t0 else 0
                parsed_p = urllib.parse.urlparse(self.path)
                qs_raw = urllib.parse.parse_qs(parsed_p.query)
                qs_flat = {k: (v[0] if len(v) == 1 else v) for k, v in qs_raw.items()}
                fp = live_review_telemetry.actor_fingerprint(self.headers, getattr(self, "client_address", None))
                live_review_telemetry.record_event({
                    "kind": "http",
                    "method": getattr(self, "command", "GET"),
                    "path": parsed_p.path,
                    "query": live_review_telemetry.sanitize_obj(qs_flat) if qs_flat else {},
                    "req_body": live_review_telemetry.sanitize_obj(getattr(self, "_req_body_parsed", None))
                    if getattr(self, "_req_body_parsed", None) else None,
                    "status": int(code),
                    "duration_ms": dur_ms,
                    "res_summary": live_review_telemetry.summarize_response_body(body, ctype),
                    **fp,
                })
        except Exception:
            pass

    def do_OPTIONS(self):
        self._send(200, {"ok": True})

    def _gate(self, path, qs=None) -> bool:
        """Anything under /api/ that arrives through the public tunnel needs X-MC-Token,
        unless it originates from the Mission Control UI hosted on the same tunnel host."""
        if path.startswith("/api/calls/recording/"):
            return True
        if path in (
            "/api/calendar.ics",
            "/api/daily.pdf",
            "/api/cameras/report.pdf",
            "/api/cameras/sam3",
            "/api/cameras/sam3/logs",
            "/api/cameras/people_breaks",
            "/api/cameras/people_breaks/identify",
            "/api/cameras/people_breaks/log",
            "/api/cameras/jev/decide",
            "/api/cameras/jev",
            "/api/whatsapp/webhook",
            "/api/calls/twilio_inbound_webhook",
            "/api/calls/sip_inbound_webhook",
            "/api/calls/outbound_webhook",
            "/api/calls/telnyx_ai_webhook",
            "/api/ceo/live_onboarding_status",
            "/api/ceo/live_onboarding_save",
            "/api/reports/company_daily/html",
            "/api/telemetry/beacon",
            "/api/health",
        ):
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
        self._t0_req = time.perf_counter()
        self._req_body_parsed = None
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        qs = urllib.parse.parse_qs(parsed.query)
        if not self._gate(path, qs):
            return

        if path == "/api/telemetry/summary":
            self._skip_http_telemetry = True
            limit_n = int((qs.get("limit") or ["120"])[0] or 120)
            self._send(200, live_review_telemetry.build_study_summary(limit_recent=limit_n))
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
        if path in ("/api/notes", "/api/tasks", "/api/meetings"):
            kind = path.rsplit("/", 1)[1]
            self._send(200, {kind: knowledge_store.list_items(kind, limit=200)})
            return
        if path == "/api/emails":
            raw_emails = knowledge_store.list_items("emails", limit=200)
            enriched = []
            for em in raw_emails:
                item = dict(em)
                src = str(item.get("source") or "").lower()
                if "hotmail" in src or "outlook" in src:
                    prov = "hotmail"
                elif "hostinger" in src or "titan" in src:
                    prov = "hostinger"
                else:
                    prov = "gmail"
                item["provider"] = prov
                item["triage"] = google_workspace.classify_email_gatekeeper(
                    str(item.get("sender") or ""),
                    str(item.get("subject") or ""),
                    str(item.get("summary") or ""),
                )
                enriched.append(item)
            self._send(200, {"emails": enriched})
            return
        if path == "/api/emails/providers":
            self._send(200, google_workspace.list_email_providers_status())
            return
        if path == "/api/dev_escalations":
            self._send(200, {"escalations": knowledge_store.list_dev_escalations()})
            return
        if path == "/api/events":
            self._send(200, {"events": knowledge_store.list_events()})
            return
        if path == "/api/calendar.ics":
            sp = (qs.get("space") or ["all"])[0]
            self._send(200, unified_life_os.export_calendar_ics(space=sp).encode("utf-8"), "text/calendar; charset=utf-8")
            return
        if path == "/api/export":
            self._send(200, knowledge_store.export_all())
            return

        if path in ("/", "/index.html", "/demo", "/demo.html", "/mock/demo.html", "/assistant", "/chat"):
            html = open(os.path.join(ROOT, "mock", "demo.html"), "rb").read()
            self._send(200, html, "text/html; charset=utf-8")
        elif path.rstrip("/") in ("/ceo-deck", "/deck", "/pitch", "/ceo-presentation"):
            html = open(os.path.join(ROOT, "mock", "ceo_deck.html"), "rb").read()
            self._send(200, html, "text/html; charset=utf-8")
        elif path.rstrip("/") in ("/conectar", "/conectar-juan", "/setup-juan"):
            html = open(os.path.join(ROOT, "mock", "conectar.html"), "rb").read()
            self._send(200, html, "text/html; charset=utf-8")
        elif path == "/robots.txt":
            raw = open(os.path.join(ROOT, "mock", "robots.txt"), "rb").read()
            self._send(200, raw, "text/plain; charset=utf-8")
        elif path == "/sitemap.xml":
            raw = open(os.path.join(ROOT, "mock", "sitemap.xml"), "rb").read()
            self._send(200, raw, "application/xml; charset=utf-8")
        elif path == "/llms.txt":
            raw = open(os.path.join(ROOT, "mock", "llms.txt"), "rb").read()
            self._send(200, raw, "text/plain; charset=utf-8")
        elif path.rstrip("/") in ("/website", "/web", "/presentacion", "/site", "/site.html", "/website-v1", "/website-v2", "/website-v3"):
            html = open(os.path.join(ROOT, "mock", "website.html"), "rb").read()
            self._send(200, html, "text/html; charset=utf-8")
        elif path.rstrip("/") in ("/instagram", "/ig", "/reels", "/carousel", "/social"):
            html = open(os.path.join(ROOT, "mock", "instagram.html"), "rb").read()
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
                    ".pdf": "application/pdf",
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
        elif path.rstrip("/") == "/widgets/clean-workspace-ui.js":
            js_p = os.path.join(ROOT, "widgets", "clean-workspace-ui.js")
            self._send(200, open(js_p, "rb").read(), "application/javascript; charset=utf-8")
        elif path.rstrip("/") == "/widgets/spark-copilot.js":
            js_p = os.path.join(ROOT, "widgets", "spark-copilot.js")
            self._send(200, open(js_p, "rb").read(), "application/javascript; charset=utf-8")
        elif path.rstrip("/") == "/widgets/ceo-splash-3d.js":
            js = open(os.path.join(ROOT, "widgets", "ceo-splash-3d.js"), "rb").read()
            self._send(200, js, "application/javascript; charset=utf-8")
        elif path.rstrip("/") == "/widgets/live-review-beacon.js":
            js = open(os.path.join(ROOT, "widgets", "live-review-beacon.js"), "rb").read()
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
            demo_q = (qs.get("demo") or ["1"])[0] != "0"
            self._send(200, camera_report.get_report(day, mode=mode, include_demo=demo_q))
        elif path == "/api/cameras/vigilant":
            day = (qs.get("date") or [None])[0]
            demo_q = (qs.get("demo") or ["1"])[0] != "0"
            self._send(200, camera_report.build_vigilant_mode_telemetry(day, include_demo=demo_q))
        elif path in ("/api/cameras/jev/decide", "/api/cameras/jev"):
            day = (qs.get("date") or [None])[0]
            demo_q = (qs.get("demo") or ["1"])[0] != "0"
            vig = camera_report.build_vigilant_mode_telemetry(day, include_demo=demo_q)
            self._send(200, vig.get("jev_ai") or {"ok": False})
        elif path in ("/api/cameras/sam3", "/api/cameras/sam3/logs"):
            day = (qs.get("date") or [None])[0]
            demo_q = (qs.get("demo") or ["1"])[0] != "0"
            self._send(200, sam3_tracker_engine.get_sam3_telemetry_and_logs(day, include_demo=demo_q))
        elif path == "/api/cameras/people_breaks":
            day = (qs.get("date") or [None])[0]
            demo_q = (qs.get("demo") or ["1"])[0] != "0"
            self._send(200, sam3_tracker_engine.get_people_breaks_report(day, include_demo=demo_q))
        elif path == "/api/cameras/cv_status":
            import camera_cv_engine
            self._send(200, {"ok": True, "cv_stack": camera_cv_engine.get_cv_stack_status()})
        elif path == "/api/cameras/ceo_deep_report":
            import camera_cv_engine
            day = (qs.get("date") or [None])[0]
            site_q = (qs.get("site") or ["all"])[0]
            lang_q = (qs.get("lang") or ["es"])[0]
            self._send(200, camera_cv_engine.build_ceo_deep_report(day=day, site=site_q, lang=lang_q))
        elif path == "/api/cameras/repeat_entities":
            import camera_cv_engine
            cat_q = (qs.get("category") or ["all"])[0]
            min_v = int((qs.get("min_visits") or ["2"])[0] or 2)
            lim_q = int((qs.get("limit") or ["50"])[0] or 50)
            self._send(200, camera_cv_engine.list_repeat_entities(category=cat_q, min_visits=min_v, limit=lim_q))
        elif path == "/api/cameras/report.pdf":
            day = (qs.get("date") or [None])[0]
            mode = (qs.get("mode") or ["example"])[0]
            lang_q = (qs.get("lang") or ["es"])[0]
            pdf_bytes = camera_report.build_camera_pdf(day=day, mode=mode, lang=lang_q)
            ctype = "application/pdf" if pdf_bytes[:4] == b"%PDF" else "text/markdown; charset=utf-8"
            self._send(200, pdf_bytes, ctype)
        elif path in ("/api/cameras/status", "/api/cameras/hikconnect"):
            force = (qs.get("refresh") or ["0"])[0] == "1"
            st = cameras.status(os.path.join(SAMPLES, "cameras.json"), force=force)
            self._send(200, camera_report.enrich_status_payload(st))
        elif path == "/api/comms/inbox":
            ch_f = (qs.get("channel") or [None])[0]
            self._send(200, comms_brain.list_inbox_with_drafts(channel_filter=ch_f))
        elif path in ("/api/texts/inbox", "/api/telegram/inbox"):
            co = (qs.get("company") or ["all"])[0]
            msgs = text_messaging.list_messages(company=co)
            self._send(200, {
                "ok": True,
                "messages": msgs,
                "items": msgs,
                "count": len(msgs),
                "draft_count": sum(1 for m in msgs if m.get("status") not in ("sent", "replied")),
                "whatsapp_removed": True,
                "watchlist": text_messaging.list_watchlist(),
                "status": text_messaging.get_meta_status(),
            })
        elif path in ("/api/calls/list", "/api/calls"):
            co = (qs.get("company") or ["all"])[0]
            direction = (qs.get("direction") or [None])[0]
            demo_q = (qs.get("demo") or ["0"])[0] == "1"
            self._send(200, voice_calls_engine.list_voice_calls(company=co, direction=direction, include_demo=demo_q))
        elif path in ("/api/whatsapp/status", "/api/telegram/status"):
            self._send(200, text_messaging.get_meta_status())
        elif path == "/api/whatsapp/bridge_status":
            self._send(200, meta_whatsapp.get_status())
        elif path == "/api/whatsapp/webhook":
            code, challenge = meta_whatsapp.verify_webhook(qs)
            self._send(code, challenge.encode("utf-8"), "text/plain; charset=utf-8")
        elif path == "/api/google/status":
            self._send(200, google_workspace.get_status())
        elif path == "/api/ceo/live_onboarding_status":
            self._send(200, ceo_live_onboarding.get_live_onboarding_status())
        elif path == "/api/calls/telephony_status":
            self._send(200, voice_calls_engine.get_telephony_status())
        elif path == "/api/ceo/reminders":
            self._send(200, {"reminders": ceo_action_brain.list_reminders()})
        elif path == "/api/ceo/ideas":
            self._send(200, {"ideas": ceo_action_brain.list_ideas()})
        elif path == "/api/ceo/followups":
            self._send(200, {"followups": ceo_action_brain.list_followups()})
        elif path == "/api/ceo/watchdog":
            co = (qs.get("company") or ["all"])[0]
            self._send(200, ceo_action_brain.get_executive_watchdog_alerts(company=co))
        elif path == "/api/ceo/project_memory":
            co = (qs.get("company") or ["all"])[0]
            self._send(200, knowledge_store.get_project_memory(company=co, limit=30))
        elif path == "/api/ceo/feedback":
            co = (qs.get("company") or ["all"])[0]
            self._send(200, {"ok": True, "items": knowledge_store.list_feedback_requests(company=co, limit=25)})
        elif path == "/api/live/state":
            co = (qs.get("company") or ["all"])[0]
            self._send(200, knowledge_store.get_live_company_state(company=co))
        elif path == "/api/ceo/company_learn":
            co = (qs.get("company") or ["all"])[0]
            self._send(200, {"ok": True, "facts": knowledge_store.list_company_facts(company=co, limit=30)})
        elif path == "/api/functions/catalog":
            q_match = (qs.get("q") or [""])[0].strip()
            cat = functions_catalog.get_catalog()
            matched = functions_catalog.match_function(q_match) if q_match else None
            self._send(200, {"ok": True, "count": len(cat), "functions": cat, "matched": matched})
        elif path in ("/api/ga4/summary", "/api/ga4/live"):
            pid = (qs.get("property_id") or [""])[0]
            self._send(200, ga4_ingest.fetch_live_ga4(property_id_override=pid))
        elif path == "/api/reports/daily_brief":
            slot = (qs.get("slot") or ["morning"])[0]
            force = (qs.get("refresh") or ["0"])[0] == "1"
            self._send(200, daily_brief_pusher.build_brief(slot=slot, force_live=force))
        elif path == "/api/reports/company_daily":
            co = (qs.get("company") or [""])[0]
            if co:
                rep = daily_company_reports.build_company_report(company_slug=co, lang=lang_q)
                rep.pop("chart_bytes", None)
                self._send(200, rep)
            else:
                self._send(200, daily_company_reports.list_archived_reports())
        elif path == "/api/reports/company_daily/html":
            co = (qs.get("company") or ["building"])[0]
            rep = daily_company_reports.build_company_report(company_slug=co, lang=lang_q)
            self._send(200, rep["html_preview_es"].encode("utf-8"), "text/html; charset=utf-8")
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
        elif path.startswith("/api/calls/recording/"):
            fname = os.path.basename(path)
            rec_path = os.path.join(ROOT, "data", "call_recordings", fname)
            if os.path.isfile(rec_path):
                ctype = "audio/wav" if fname.lower().endswith(".wav") else "audio/mpeg"
                self._send(200, open(rec_path, "rb").read(), ctype)
            else:
                self._send(404, {"error": "recording not found"})
        elif path == "/api/health":
            live_flag = (qs.get("live") or ["0"])[0] == "1"
            self._send(200, {
                "ok": True,
                "service": "la-jefatura-suite",
                "port": PORT,
                "ceo_name": (jefesito.get_prefs() or {}).get("ceo_name", "Juan David"),
                "llm": llm_router.health_probe(live_call=live_flag),
            })
        elif path == "/api/ceo/csuite_intelligence":
            co = (qs.get("company") or ["all"])[0]
            ref = (qs.get("refresh") or ["0"])[0] == "1"
            ai_on = (qs.get("ai") or ["1"])[0] != "0"
            self._send(200, csuite_intelligence.build_csuite_boardroom(
                company=co, force_refresh=ref, include_ai_brief=ai_on
            ))
        elif path == "/api/assistant/queue":
            import spark_followup_engine
            self._send(200, spark_followup_engine.get_active_queue(include_turns=True))
        elif path == "/api/assistant/pulse":
            import spark_followup_engine
            self._send(200, spark_followup_engine.get_pulse())
        elif path == "/api/assistant/splash_brief":
            import spark_followup_engine
            lang = (qs.get("lang") or ["es"])[0]
            self._send(200, spark_followup_engine.build_splash_proactive_brief(lang=lang))
        elif path == "/api/mcp/tools":
            self._send(200, {"ok": True, "tools": csuite_intelligence.list_mcp_tools()})
        elif path == "/api/crm/twenty/status":
            self._send(200, twenty_crm_sync.get_status())
        elif path == "/api/llm/observability":
            hrs = int((qs.get("hours") or ["24"])[0] or 24)
            lim = int((qs.get("limit") or ["30"])[0] or 30)
            self._send(200, llm_observability.summary(hours=hrs, limit=lim))
        elif path == "/api/os/space":
            sp = (qs.get("space") or ["all"])[0]
            self._send(200, unified_life_os.get_space_overview(space=sp))
        elif path == "/api/os/memory":
            sp = (qs.get("space") or ["all"])[0]
            q_mem = (qs.get("q") or [""])[0]
            lim = int((qs.get("limit") or ["20"])[0] or 20)
            self._send(200, {"ok": True, "space": sp, "items": unified_life_os.recall(query=q_mem, space=sp, limit=lim)})
        elif path == "/api/os/gatekeeper":
            self._send(200, unified_life_os.get_email_gatekeeper_summary())
        elif path == "/api/os/meeting_prep":
            hrs = int((qs.get("hours") or ["24"])[0] or 24)
            self._send(200, unified_life_os.build_meeting_prep(hours=hrs))
        elif path == "/api/os/browser_tasks":
            self._send(200, unified_life_os.list_browser_tasks())
        elif path == "/api/onboarding/state":
            self._send(200, _get_onboarding())
        elif path == "/api/report.pdf":
            company = (qs.get("company") or ["Building Innovation"])[0]
            lang = (qs.get("lang") or ["es"])[0]
            out = os.path.join(tempfile.gettempdir(), "_demo_report.pdf")
            built_path = reports_pdf.build_report(company, SAMPLES, out, lang=lang)
            pdf = open(built_path, "rb").read()
            ctype = "application/pdf" if built_path.endswith(".pdf") else "text/markdown; charset=utf-8"
            self._send(200, pdf, ctype)
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        self._t0_req = time.perf_counter()
        self._req_body_parsed = None
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        qs = urllib.parse.parse_qs(parsed.query)
        if not self._gate(path, qs):
            return
        n = int(self.headers.get("Content-Length", 0))
        raw_body = self.rfile.read(n) if n > 0 else b""
        ctype_in = (self.headers.get("Content-Type") or "").lower()
        if "application/x-www-form-urlencoded" in ctype_in:
            parsed_form = urllib.parse.parse_qs(raw_body.decode("utf-8", errors="replace"))
            body = {k: (v[0] if v else "") for k, v in parsed_form.items()}
        else:
            try:
                body = json.loads(raw_body or b"{}")
            except ValueError:
                self._send(400, {"error": "invalid JSON"})
                return
        if not isinstance(body, dict):
            self._send(400, {"ok": False, "error": "JSON body must be an object"})
            return
        self._req_body_parsed = body

        if path == "/api/telemetry/beacon":
            self._skip_http_telemetry = True
            fp = live_review_telemetry.actor_fingerprint(self.headers, getattr(self, "client_address", None))
            live_review_telemetry.record_event({
                "kind": "client_beacon",
                "session_id": str(body.get("session_id") or "")[:40],
                "event": str(body.get("event") or "unknown")[:60],
                "page": str(body.get("page") or "")[:180],
                "elapsed_s": body.get("elapsed_s", 0),
                "data": live_review_telemetry.sanitize_obj(body.get("data") or {}),
                **fp,
            })
            self._send(200, {"ok": True})
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
            sync_res = functions_catalog.sync_appointment_realtime(
                title=body.get("title", ""),
                date_str=body.get("date", ""),
                time_str=body.get("time", "10:00"),
                duration_min=int(body.get("duration", 30) or 30),
                company=body.get("company", "all"),
                notes=body.get("notes", ""),
                send_email_invite=bool(body.get("send_email_invite", True)),
            )
            ev_rec = dict(sync_res.get("event") or {})
            ev_rec["gcal_template_url"] = sync_res.get("gcal_template_url")
            ev_rec["gcal_api_status"] = sync_res.get("gcal_api_status")
            self._send(200 if ev_rec.get("ok") else 400, ev_rec)
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
        elif path == "/api/whatsapp/request_pairing":
            self._send(200, meta_whatsapp.request_multidevice_pairing(body.get("phone", "17866575441")))
        elif path == "/api/whatsapp/approve_reply":
            chat_id = str(body.get("chat_id") or "").strip()
            reply_text = str(body.get("text") or body.get("reply_text") or "").strip()
            did = int(body.get("draft_id") or 0)
            if not (chat_id and reply_text):
                self._send(400, {"ok": False, "error": "chat_id y text son requeridos"})
                return
            try:
                receipt = meta_whatsapp.send_message(chat_id, reply_text)
                if did:
                    try:
                        comms_brain.revise(did, reply_text, actor="juan_ceo", reason="approved_group_reply")
                        comms_brain.approve_and_send(did, approver="juan_ceo")
                    except Exception:
                        pass
                self._send(200, {"ok": True, "receipt": receipt, "chat_id": chat_id})
            except Exception as exc:
                self._send(400, {"ok": False, "error": str(exc)})
        elif path == "/api/google/config":
            self._send(200, google_workspace.save_config(body))
        elif path == "/api/emails/providers/save":
            res = google_workspace.save_provider_account(
                provider=body.get("provider", "gmail"),
                email_address=body.get("email_address") or body.get("email") or "",
                password=body.get("password") or body.get("app_password") or "",
                imap_host=body.get("imap_host", ""),
                smtp_host=body.get("smtp_host", ""),
                calendar_ical_url=body.get("calendar_ical_url", ""),
            )
            self._send(200, res)
        elif path == "/api/google/sync":
            g_res = google_workspace.sync_gmail_and_calendar(
                limit=int(body.get("max_emails") or body.get("limit") or 12))
            extra_res = google_workspace.sync_extra_email_providers(limit=8)
            g_res["extra_providers"] = extra_res
            self._send(200, g_res)
        elif path == "/api/crm/twenty/sync":
            res = twenty_crm_sync.sync_from_twenty(
                base_url=body.get("base_url"),
                api_key=body.get("api_key"),
                sample_leads=body.get("sample_leads"),
                sample_visits=body.get("sample_visits"),
            )
            self._send(200 if res.get("ok") else 400, res)
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
        elif path in ("/api/texts/draft", "/api/telegram/draft"):
            self._send(200, text_messaging.create_outgoing_text_draft(
                contact_name=body.get("contact_name", "Grupo General Telegram (@Pegantebot)"),
                message_text=body.get("message_text") or body.get("body") or "",
                to_phone=body.get("to_phone") or body.get("to") or "8897658040",
                company=body.get("company", "espacios_importados"),
                channel=body.get("channel", "telegram"),
                auto_send=bool(body.get("auto_send", False)),
            ))
        elif path in ("/api/texts/edit", "/api/telegram/edit"):
            mid = int(body.get("id") or body.get("message_id") or 0)
            self._send(200, text_messaging.update_text_draft(mid, body.get("body") or body.get("ai_draft_reply") or ""))
        elif path in ("/api/texts/approve_send", "/api/telegram/approve_send"):
            mid = int(body.get("id") or body.get("message_id") or 0)
            edited = body.get("body") if "body" in body else None
            self._send(200, text_messaging.approve_text_draft(mid, edited_text=edited))
        elif path in ("/api/texts/send", "/api/telegram/send"):
            self._send(200, text_messaging.send_text_message(
                to_phone=body.get("to_phone") or body.get("to") or "8897658040",
                message=body.get("message") or body.get("body") or "",
                company=body.get("company", "espacios_importados"),
                channel=body.get("channel", "telegram"),
                contact_name=body.get("contact_name", "Telegram Grupo Ejecutivo"),
            ))
        elif path == "/api/calls/initiate":
            self._send(200, voice_calls_engine.initiate_ai_phone_call(
                contact_name=body.get("contact_name", "Contacto Ejecutivo"),
                to_phone=body.get("to_phone") or body.get("phone") or "",
                objective=body.get("objective") or body.get("message") or "",
                company=body.get("company", "espacios_importados"),
                script_prompt=body.get("script_prompt", ""),
                voice=body.get("voice", "ara"),
                auto_execute=bool(body.get("auto_execute", True)),
            ))
        elif path in ("/api/calls/inbound", "/api/calls/receive"):
            self._send(200, voice_calls_engine.receive_inbound_phone_call(
                caller_name=body.get("caller_name") or body.get("contact_name") or "Llamada Entrante Ejecutiva",
                from_phone=body.get("from_phone") or body.get("to_phone") or body.get("phone") or "+13057729104",
                caller_speech=body.get("caller_speech") or body.get("objective") or body.get("message") or "",
                company=body.get("company", "unitec_usa"),
                voice=body.get("voice", "ara"),
                preferred_callback_time=body.get("preferred_callback_time", "Hoy 16:30"),
                notify_ceo=bool(body.get("notify_ceo", True)),
            ))
        elif path == "/api/calls/inbound_action":
            cid = int(body.get("call_id") or body.get("id") or 0)
            self._send(200, voice_calls_engine.handle_inbound_ceo_action(
                call_id=cid,
                action_type=body.get("action_type") or body.get("action") or "transfer_to_ceo",
                callback_date=body.get("callback_date", ""),
                callback_time=body.get("callback_time", "16:30"),
                ceo_phone=body.get("ceo_phone", ""),
                notes=body.get("notes", ""),
            ))
        elif path in ("/api/calls/twilio_inbound_webhook", "/api/calls/sip_inbound_webhook"):
            twiml = voice_calls_engine.generate_twilio_inbound_twiml(
                from_phone=body.get("From") or body.get("from_phone") or "+13057729104",
                caller_name=body.get("CallerName") or body.get("caller_name") or "",
                speech_result=body.get("SpeechResult") or body.get("speech_result") or "",
            )
            self._send(200, twiml.encode("utf-8"), "application/xml; charset=utf-8")
        elif path in ("/api/calls/outbound_webhook", "/api/calls/telnyx_ai_webhook"):
            q_cid = int(((qs.get("call_id") or ["0"])[0]) or body.get("call_id") or 0)
            notify_flag = str(body.get("notify_ceo", "true")).lower() not in ("0", "false", "no")
            res = voice_calls_engine.ingest_outbound_call_feedback(
                payload=body,
                query_call_id=q_cid,
                notify_ceo=notify_flag,
            )
            if "application/x-www-form-urlencoded" in ctype_in and str(body.get("format", "")).lower() != "json":
                self._send(200, res["twiml"].encode("utf-8"), "application/xml; charset=utf-8")
            else:
                self._send(200, res)
        elif path == "/api/calls/telephony_config":
            self._send(200, voice_calls_engine.save_telephony_config(body))
        elif path == "/api/calls/sync_telnyx":
            res = voice_calls_engine.sync_telnyx_live_call_result(
                call_id=int(body.get("call_id") or 0),
                call_sid=str(body.get("call_sid") or ""),
                to_phone=str(body.get("to_phone") or ""),
            )
            self._send(200, res)
        elif path == "/api/calls/telnyx_autoprovision":
            res = voice_calls_engine.autoprovision_telnyx(
                api_key=body.get("api_key") or body.get("account_sid_or_key") or "",
                from_number=body.get("from_number", ""),
                ceo_direct_phone=body.get("ceo_direct_phone", ""),
                webhook_base=body.get("webhook_base", "https://lajefatura.pocketscribe.online"),
                create_ai_assistant=bool(body.get("create_ai_assistant", True)),
            )
            self._send(200 if res.get("ok") else 400, res)
        elif path == "/api/ceo/live_onboarding_save":
            self._send(200, ceo_live_onboarding.handle_live_onboarding_save(body))
        elif path == "/api/calls/decide":
            cid = int(body.get("call_id") or body.get("id") or 0)
            self._send(200, voice_calls_engine.record_call_decision(
                call_id=cid,
                decision=body.get("decision", ""),
                create_task=bool(body.get("create_task", True)),
                send_telegram_confirm=bool(body.get("send_telegram_confirm", True)),
            ))
        elif path == "/api/behavior/event":
            et = body.get("event_type", "click")
            tg = body.get("target", "ui")
            dt = body.get("detail", {})
            sl = body.get("time_slot")
            self._send(200, behavior_brain.record_event(et, tg, detail=dt, time_slot=sl))
        elif path == "/api/onboarding/save":
            self._send(200, _save_onboarding(body))
        elif path == "/api/ceo/chat":
            msg = body.get("message") or body.get("command") or ""
            co = body.get("company", "all")
            lng = body.get("lang", "es")
            self._send(200, ceo_action_brain.execute_ceo_chat(msg, company=co, lang=lng))
        elif path == "/api/ceo/reminders":
            self._send(200, ceo_action_brain.set_reminder(
                title=body.get("title", ""),
                trigger_time=body.get("trigger_time", ""),
                category=body.get("category", "general"),
                company=body.get("company", "all"),
                recurrence=body.get("recurrence", "once"),
            ))
        elif path == "/api/ceo/reminders/dismiss":
            self._send(200, ceo_action_brain.dismiss_reminder(body.get("id", "")))
        elif path == "/api/ceo/reminders/snooze":
            self._send(200, ceo_action_brain.snooze_reminder(body.get("id", ""), int(body.get("minutes", 15))))
        elif path == "/api/ceo/ideas":
            self._send(200, ceo_action_brain.save_idea(
                title=body.get("title", ""),
                description=body.get("description", ""),
                company=body.get("company", "all"),
                potential=body.get("potential", "high"),
                tags=body.get("tags", ""),
            ))
        elif path == "/api/ceo/followups":
            self._send(200, ceo_action_brain.add_followup(
                who=body.get("who", ""),
                what=body.get("what", ""),
                deadline=body.get("deadline", ""),
                company=body.get("company", "all"),
                notes=body.get("notes", ""),
            ))
        elif path == "/api/os/memory":
            if str(body.get("action") or "").lower() in ("forget", "archive", "delete"):
                self._send(200, unified_life_os.forget(body.get("id", "")))
            else:
                self._send(200, unified_life_os.remember(
                    content=body.get("content", ""),
                    space=body.get("space", "business"),
                    category=body.get("category", "fact"),
                    subject=body.get("subject", ""),
                    provenance=body.get("provenance", "stated"),
                    valid_until=body.get("valid_until", ""),
                ))
        elif path == "/api/os/personal_task":
            if str(body.get("action") or "").lower() == "toggle":
                self._send(200, unified_life_os.toggle_personal_task(int(body.get("id") or 0)))
            else:
                self._send(200, unified_life_os.add_personal_task(
                    title=body.get("title", ""),
                    category=body.get("category", "general"),
                    priority=body.get("priority", "medium"),
                    due_date=body.get("due_date", ""),
                    notes=body.get("notes", ""),
                ))
        elif path == "/api/os/personal_contact":
            self._send(200, unified_life_os.upsert_personal_contact(
                name=body.get("name", ""),
                relationship=body.get("relationship", "vip"),
                phone=body.get("phone", ""),
                email=body.get("email", ""),
                birthday=body.get("birthday", ""),
                preferences=body.get("preferences", ""),
                notes=body.get("notes", ""),
            ))
        elif path == "/api/os/timeblock":
            apply_raw = body.get("apply", True)
            apply_flag = str(apply_raw).lower() not in ("0", "false", "no") if not isinstance(apply_raw, bool) else apply_raw
            self._send(200, unified_life_os.conflict_aware_timeblock(
                target_date=body.get("target_date") or body.get("date") or "",
                space=body.get("space", "all"),
                max_blocks=int(body.get("max_blocks") or 4),
                block_minutes=int(body.get("block_minutes") or 30),
                apply=apply_flag,
            ))
        elif path == "/api/os/walk_and_talk":
            self._send(200, unified_life_os.handle_walk_and_talk(
                transcript_text=body.get("transcript_text") or body.get("text") or body.get("transcript") or body.get("message") or "",
                channel=body.get("channel", "telegram_voice"),
                space=body.get("space", "all"),
                lang=body.get("lang", "es"),
            ))
        elif path == "/api/os/browser_task":
            act_bt = str(body.get("action") or "").lower()
            if act_bt in ("approve", "complete", "done", "cancel", "remove", "reject"):
                self._send(200, unified_life_os.update_browser_task(
                    task_id=str(body.get("id") or body.get("task_id") or ""),
                    action=act_bt,
                    result_summary=str(body.get("result_summary") or ""),
                ))
            else:
                self._send(200, unified_life_os.queue_browser_task(
                    portal_url=body.get("portal_url") or body.get("url") or "",
                    goal=body.get("goal", ""),
                    space=body.get("space", "business"),
                ))
        elif path == "/api/ceo/followups/resolve":
            self._send(200, ceo_action_brain.resolve_followup(body.get("id", "")))
        elif path == "/api/ceo/approve_inline":
            self._send(200, ceo_action_brain.approve_inline_action(
                card_type=body.get("card_type", ""),
                item_id=body.get("id", ""),
                edited_text=body.get("edited_text", ""),
                action=body.get("action", "approve"),
            ))
        elif path == "/api/ceo/brainstorm":
            self._send(200, ceo_action_brain.run_brainstorming_session(
                topic=body.get("topic", ""),
                company=body.get("company", "all"),
                goal=body.get("goal", ""),
            ))
        elif path == "/api/ceo/project_memory":
            res = knowledge_store.memorize_project_directive(
                text=body.get("text", ""),
                company=body.get("company", "all"),
                date_str=body.get("date", ""),
                time_str=body.get("time", "09:00"),
                create_schedule=bool(body.get("create_schedule", True)),
                create_reminder=bool(body.get("create_reminder", True)),
                create_task=bool(body.get("create_task", True)),
                source=body.get("source", "ceo_project_memory"),
            )
            self._send(200 if res.get("ok") else 400, res)
        elif path == "/api/ceo/feedback":
            res = knowledge_store.save_feedback_request(
                message=body.get("message") or body.get("text") or "",
                company=body.get("company", "all"),
                action_type=body.get("action_type", "add_function"),
                author=body.get("author", "CEO / Juan"),
                lang=body.get("lang", "es"),
            )
            self._send(200 if res.get("ok") else 400, res)
        elif path == "/api/ceo/company_learn":
            res = knowledge_store.learn_company_fact(
                fact=body.get("fact") or body.get("text") or body.get("message") or "",
                company=body.get("company", "all"),
                category=body.get("category", "general"),
                source=body.get("source", "ceo_ui"),
            )
            self._send(200 if res.get("ok") else 400, res)
        elif path == "/api/ceo/email_reminder":
            raw_txt = body.get("text") or body.get("title") or ""
            parsed_dt = functions_catalog.parse_natural_datetime(raw_txt)
            rem_res = functions_catalog.send_email_and_telegram_reminder(
                title=body.get("title") or parsed_dt["title"],
                date_str=body.get("date") or parsed_dt["date"],
                time_str=body.get("time") or parsed_dt["time"],
                company=body.get("company") or parsed_dt["company"],
                to_email=body.get("to_email", ""),
                notes=body.get("notes", ""),
                create_db_row=True,
            )
            self._send(200 if rem_res.get("ok") else 400, rem_res)
        elif path == "/api/cameras/events":
            if not mc_auth.token_ok(self.headers.get("X-MC-Token", "")):
                self._send(401, {"error": "X-MC-Token required"})
            else:
                self._send(200, {"ok": True, "stored": camera_report.add_agent_events(body.get("events", []))})
        elif path == "/api/cameras/poll":
            self._send(200, camera_report.poll())
        elif path in ("/api/cameras/vigilant/trigger", "/api/cameras/vigilant/repost"):
            reason = str(body.get("reason") or "manual_vigilant_trigger")
            emails = body.get("emails") if isinstance(body.get("emails"), list) else None
            self._send(200, camera_report.trigger_vigilant_repost(reason=reason, to_emails=emails, include_pdf=True))
        elif path == "/api/cameras/jev/decide":
            import jev_vision_engine
            zone_val = body.get("zone")
            if "zone" in body and zone_val is not None:
                if not isinstance(zone_val, dict):
                    self._send(400, {"ok": False, "error": "zone must be a JSON object"})
                    return
                res = jev_vision_engine.evaluate_zone_with_jev(zone_val, persist=True)
            else:
                vig = camera_report.build_vigilant_mode_telemetry()
                res = jev_vision_engine.evaluate_all_vigilant_zones(vig.get("people_entries_exits", []), persist=True)
            if body.get("auto_repost") and (res.get("auto_repost_recommended") or (res.get("summary") or {}).get("level_2_immediate_repost_count", 0) > 0):
                res["repost_dispatch"] = camera_report.trigger_vigilant_repost(reason="jev_ai_v1_decide_trigger", include_pdf=True)
            self._send(200, res)
        elif path in ("/api/cameras/sam3/track", "/api/cameras/sam3/log"):
            def _opt_int(key: str, default_val=None):
                if key not in body or body.get(key) is None:
                    return True, default_val, ""
                v = body.get(key)
                if isinstance(v, bool):
                    return False, None, f"invalid integer for {key}"
                try:
                    if isinstance(v, str):
                        v_s = v.strip()
                        if not v_s:
                            return False, None, f"invalid integer for {key}"
                        return True, int(v_s), ""
                    return True, int(v), ""
                except (TypeError, ValueError):
                    return False, None, f"invalid integer for {key}"

            ok_i, inst_val, err_i = _opt_int("instances_tracked", None)
            if not ok_i:
                self._send(400, {"ok": False, "error": err_i})
                return
            ok_d, dwell_val, err_d = _opt_int("dwell_minutes", None)
            if not ok_d:
                self._send(400, {"ok": False, "error": err_d})
                return
            ok_r, rec_val, err_r = _opt_int("recommended_max_min", 45)
            if not ok_r:
                self._send(400, {"ok": False, "error": err_r})
                return
            res = sam3_tracker_engine.track_custom_concept(
                concept_prompt=str(body.get("concept_prompt") or body.get("prompt") or "forklift & WPC pallet"),
                site=str(body.get("site") or "Espacios Importados"),
                camera_id=str(body.get("camera_id") or "L12154607-CH23/24 · MUELLE 1 y 2"),
                instances_tracked=inst_val,
                trajectory_path=body.get("trajectory_path"),
                dwell_minutes=dwell_val,
                recommended_max_min=rec_val,
                notes_es=str(body.get("notes_es") or ""),
            )
            self._send(200, res)
        elif path == "/api/cameras/people_breaks/identify":
            res = sam3_tracker_engine.assign_person_identity(
                person_code=str(body.get("person_code") or "PER-003"),
                full_name=str(body.get("full_name") or ""),
                role_title=body.get("role_title"),
                visual_cue_es=body.get("visual_cue_es"),
                identified_by=str(body.get("identified_by") or "CEO Juan David & Jasmel"),
            )
            self._send(200 if res.get("ok") else 400, res)
        elif path == "/api/cameras/people_breaks/log":
            dur_raw = body.get("duration_min")
            if "duration_min" in body and dur_raw is not None:
                if isinstance(dur_raw, bool):
                    self._send(400, {"ok": False, "error": "invalid integer for duration_min"})
                    return
                try:
                    dur_val = int(dur_raw.strip()) if isinstance(dur_raw, str) else int(dur_raw)
                except (TypeError, ValueError):
                    self._send(400, {"ok": False, "error": "invalid integer for duration_min"})
                    return
            else:
                dur_val = 8
            res = sam3_tracker_engine.log_person_break_event(
                person_code=str(body.get("person_code") or "PER-003"),
                event_kind=str(body.get("event_kind") or "bathroom"),
                duration_min=dur_val,
                start_time=body.get("start_time"),
                end_time=body.get("end_time"),
                camera_id=str(body.get("camera_id") or "L12154607-CH10 · BAÑOS Y CAFETIN"),
                notes_es=str(body.get("notes_es") or ""),
            )
            self._send(200, res)
        elif path == "/api/cameras/sync":
            st = cameras.status(os.path.join(SAMPLES, "cameras.json"), force=True)
            self._send(200, camera_report.enrich_status_payload(st))
        elif path == "/api/reports/company_daily/send":
            companies = body.get("companies") or (["building", "unitec"] if not body.get("company") else [body.get("company")])
            self._send(200, daily_company_reports.dispatch_company_reports(
                companies=companies,
                to_emails_override=body.get("emails"),
                send_email=bool(body.get("send_email", True)),
                send_telegram=bool(body.get("send_telegram", True)),
            ))
        elif path == "/api/reports/company_daily/recipients":
            if body.get("discover_telegram"):
                self._send(200, daily_company_reports.discover_juan_telegram_chat_id())
            else:
                self._send(200, daily_company_reports.save_recipients_config(body))
        elif path == "/api/voice/command":
            cmd = (body.get("command") or body.get("message") or "").strip()
            lang = body.get("lang", "es")
            ch = body.get("channel", "text")
            if not cmd:
                self._send(400, {"ok": False, "error": "empty command"})
                return

            # Step A: Fast El Jefesito control (theme, lang, close day, print, name)
            ctl = jefesito.control(cmd, lang=lang)
            if ctl:
                res = {
                    "ok": True,
                    "action": "control",
                    "parsed": {"action": "control"},
                    "reply": ctl["reply"],
                    "ui": ctl.get("ui"),
                    "sources": ctl.get("sources", []),
                    "grounded": True,
                    "dev_ticket": None,
                }
                jefesito.record(cmd, ch, res.get("action"), lang)
                self._send(200, res)
                return

            # Step B: Multi-intent compound orders -> single execution through ceo_action_brain
            clauses = ceo_action_brain.split_compound_commands(cmd)
            if len(clauses) > 1:
                action_res = ceo_action_brain.execute_ceo_chat(cmd, lang=lang)
                intents_lbl = ", ".join(action_res.get("compound_intents") or ["compound"])
                res = {
                    "ok": True,
                    "action": "compound_execution",
                    "is_compound": True,
                    "compound": True,
                    "steps_executed": len(action_res.get("actions_executed", [])),
                    "compound_intents": action_res.get("compound_intents", []),
                    "company": action_res.get("company", "all"),
                    "reply": action_res.get("reply", "Acciones ejecutadas correctamente."),
                    "action_result": action_res.get("action_result"),
                    "actions_executed": action_res.get("actions_executed", []),
                    "inline_cards": action_res.get("inline_cards", []),
                    "ui": {"refresh_calendar": True, "refresh_memory": True},
                    "matched_function": None,
                    "sources": [f"mc.db ({intents_lbl})"],
                    "grounded": True,
                    "dev_ticket": None,
                }
                jefesito.record(cmd, ch, res.get("action"), lang)
                self._send(200, res)
                return

            # Step C: Single-clause routing (skip ceo_delegation in voice_commands to prevent double execution)
            parsed_vc = voice_commands.parse(cmd, lang)
            v_res = None
            if parsed_vc.get("action") != "ceo_delegation":
                v_res = voice_commands.execute(
                    cmd,
                    lang=lang,
                    samples_dir=SAMPLES,
                    channel=ch,
                    auto_escalate=False,
                    allow_unknown_ask=False,
                )

            _VC_ALLOW = (
                "catalog_function", "switch_company", "open_tab", "schedule_event",
                "email_reminder", "save_note", "save_task", "save_meeting", "save_email",
                "control", "read_brief", "download_report", "sync_integrations",
                "approve_draft", "draft_reply", "complete_task", "confirm_coffee",
                "help", "explain_plans", "escalate_dev", "learn_company", "send_twice_daily_report",
                "trigger_camera_vigilant", "status_digest", "switch_slot", "learn_voice",
            )
            if v_res and (v_res.get("action") in _VC_ALLOW or (v_res.get("action") == "ask" and v_res.get("grounded"))):
                res = v_res
            else:
                action_res = ceo_action_brain.execute_ceo_chat(cmd, lang=lang)
                intent_val = action_res.get("intent") or "conversational_chat"
                if intent_val != "unknown" and action_res.get("reply"):
                    ui_merged = dict((v_res or {}).get("ui") or {})
                    ui_merged["refresh_calendar"] = True
                    ui_merged["refresh_memory"] = True
                    res = {
                        "ok": True,
                        "action": intent_val,
                        "company": action_res.get("company", "all"),
                        "reply": action_res.get("reply", ""),
                        "action_result": action_res.get("action_result"),
                        "actions_executed": action_res.get("actions_executed", []),
                        "inline_cards": action_res.get("inline_cards", []),
                        "ui": ui_merged,
                        "matched_function": (v_res or {}).get("matched_function"),
                        "sources": [f"mc.db ({intent_val})"],
                        "grounded": True,
                        "dev_ticket": None,
                    }
                else:
                    res = {
                        "ok": True,
                        "action": "conversational_chat",
                        "reply": "Estoy listo para ayudarte con correos pendientes, agenda, llamadas o métricas.",
                        "ui": {},
                        "grounded": True,
                        "dev_ticket": None,
                    }
            jefesito.record(cmd, ch, res.get("action"), lang)
            self._send(200, res)
        elif path == "/api/voice/transcribe":
            audio_b64 = str(body.get("audio_base64") or body.get("audio") or "").strip()
            mime_t = str(body.get("mime_type") or "audio/webm").strip()
            lng = str(body.get("lang") or "es").strip()
            if not audio_b64:
                self._send(400, {"ok": False, "error": "audio_base64_required", "transcript": ""})
                return
            tr = _transcribe_audio_with_gemini(audio_base64=audio_b64, mime_type=mime_t, lang=lng)
            self._send(200, {
                "ok": bool(tr.get("ok")),
                "transcript": tr.get("transcript", ""),
                "lang": lng,
                "provider": tr.get("provider", "none"),
                "model": tr.get("model", "none"),
                "latency_ms": tr.get("latency_ms", 0),
                "error": tr.get("error"),
            })
        elif path == "/api/assistant/live_turn":
            import spark_followup_engine
            cmd = body.get("command") or body.get("message") or ""
            ch = body.get("channel") or "chat"
            lang = body.get("lang") or "es"
            res = spark_followup_engine.handle_live_turn(cmd, channel=ch, lang=lang, samples_dir=SAMPLES)
            self._send(200 if res.get("ok") else 400, res)
        elif path == "/api/assistant/item_action":
            import spark_followup_engine
            res = spark_followup_engine.handle_item_action(body)
            self._send(200 if res.get("ok") else 400, res)
        elif path == "/api/assistant/sweep":
            import spark_followup_engine
            self._send(200, spark_followup_engine.run_sweep())
        elif path == "/api/cameras/cv_analyze":
            import camera_cv_engine
            src_url = str(body.get("rtsp_url") or body.get("video_source") or "").strip()
            if src_url:
                res = camera_cv_engine.analyze_video_or_rtsp(
                    source=src_url,
                    camera_id=str(body.get("camera_id") or "RTSP-01"),
                    site=str(body.get("site") or "general"),
                    zone=str(body.get("zone") or "general"),
                    max_frames=int(body.get("max_frames") or 20),
                    sample_every_n=int(body.get("sample_every_n") or 10),
                    conf=float(body.get("conf") or 0.30),
                )
            else:
                img_in = body.get("image_base64") or body.get("image_url") or body.get("image_path") or ""
                res = camera_cv_engine.analyze_frame(
                    image_input=img_in,
                    camera_id=str(body.get("camera_id") or "CAM-01"),
                    site=str(body.get("site") or "general"),
                    zone=str(body.get("zone") or "general"),
                    conf=float(body.get("conf") or 0.30),
                )
            self._send(200 if res.get("ok") else 400, res)
        elif path == "/api/telegram/sync":
            import telegram_inbound
            self._send(200, telegram_inbound.sync_telegram_inbox(
                send_reply=bool(body.get("send_reply", True)),
            ))
        elif path == "/api/mcp/call":
            t_name = str(body.get("name") or body.get("tool") or "")
            t_args = body.get("arguments") or {}
            res = csuite_intelligence.call_mcp_tool_endpoint(t_name, t_args)
            self._send(200 if res.get("ok") else 400, res)
        else:
            self._send(404, {"error": "not found"})


if __name__ == "__main__":
    import threading

    def _bg_boot():
        try:
            _seed_if_empty()
            camera_report.start_scheduler()
            daily_brief_pusher.start_scheduler()
            daily_company_reports.start_daily_company_scheduler()
            google_workspace.start_realtime_sync_loop(180)
            import spark_followup_engine
            spark_followup_engine.start_sweeper(60)
        except Exception as e:
            print(f"[boot] background init warning: {e}", flush=True)

    threading.Thread(target=_bg_boot, daemon=True).start()
    http_server_mod = __import__("http.server").server
    http_server_mod.ThreadingHTTPServer.request_queue_size = 64
    http_server_mod.ThreadingHTTPServer.allow_reuse_address = True
    srv = http_server_mod.ThreadingHTTPServer(
        ("0.0.0.0", PORT), Handler)
    print(f"La Jefatura demo -> http://localhost:{PORT}  (Ctrl-C to stop)", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
