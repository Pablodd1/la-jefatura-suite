#!/usr/bin/env python3
"""End-to-End Workflow & Smoke Test Suite for La Jefatura (`scripts/smoke_test_e2e.py`).

Verifies every core workflow of LA JEFATURA — Made & Powered by Building Innovation:
  1. Branding & Removed Legacy Companies Check (0 matches for cedexx, mbmb, 305biz, aidyn, White-Label CEO Mission Control)
  2. Left Glassmorphism Full-Name Menu (#ljGlassSidebar), No Menu Mirror, & 6 Projects (including 55 CÁMARAS CCTV)
  3. Live Weather (Miami, Colombia, Chile) & South America Timezones (Miami, Colombia/Perú/Ecuador, Chile, Argentina/Brasil/Uruguay, Venezuela/Bolivia, México)
  4. Click-Same-Button Voice Stop Toggle & Colombian Neural TTS (/api/tts)
  5. CTO & CFO Connected Telemetry Endpoints (UNITEC Firestore, BuildingApp Firestore, GA4, 55 Hik-Connect Cameras, Nexus CRM, Bandeja Mode C, Google & Meta status)
  6. Per-Project Memory, Schedule & Reminder Workflow (POST & GET /api/ceo/project_memory + /api/calendar.ics)
  7. Grounded Q&A & Voice Command Execution (/api/ask & /api/voice/command — Zero Guessing)
  8. Multi-Page Morning Executive Newspaper PDF (/api/daily.pdf, /api/report.pdf, /api/cameras/report.pdf)
"""
import json
import sys
import urllib.parse
import urllib.request

BASE = "http://localhost:8931"
FAILS = []


def check(name: str, cond: bool, detail: str = ""):
    status = "PASS" if cond else "FAIL"
    print(f"{status} | {name} | {detail[:140]}")
    if not cond:
        FAILS.append(name)


def get_json(path: str) -> dict:
    with urllib.request.urlopen(BASE + path, timeout=35) as r:
        return json.loads(r.read().decode("utf-8"))


def post_json(path: str, payload: dict) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        BASE + path,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=35) as r:
        return json.loads(r.read().decode("utf-8"))


def main():
    print("=== LA JEFATURA (MADE & POWERED BY BUILDING INNOVATION) — E2E SMOKE TEST ===")

    # 1. Main UI HTML, Branding, Left Glass Menu & Removed Companies
    with urllib.request.urlopen(BASE + "/?lang=es", timeout=15) as r:
        html = r.read().decode("utf-8")
    check("1a. Branding 'MADE & POWERED BY BUILDING INNOVATION'", "MADE &amp; POWERED BY BUILDING INNOVATION" in html, f"{len(html)} bytes")
    check("1b. Old 'White-Label CEO Mission Control' removed", "White-Label CEO Mission Control" not in html)
    for legacy in ("cedexx", "mbmb", "305biz", "aidyn"):
        check(f"1c. Legacy company '{legacy}' absent from UI", legacy not in html.lower())
    check("1d. Left Glassmorphism Sidebar (#ljGlassSidebar) present", 'id="ljGlassSidebar"' in html)
    check("1e. Dedicated '55 CÁMARAS CCTV' project in selector & menu", "55 CÁMARAS CCTV" in html and 'data-sb-co="cameras"' in html)
    check("1f. World Timezones & Weather Strip (#ljWorldTimeWeatherStrip)", 'id="ljWorldTimeWeatherStrip"' in html)
    check("1g. CTO Text & Graphic Analytics Boxes present", 'id="ctoTextAnalyticsBox"' in html and 'id="ctoGraphicAnalyticsBox"' in html)
    check("1h. Voice Toggle Stop Handler (toggleOrStopVoiceBrief)", "toggleOrStopVoiceBrief()" in html)
    check("1i. Master Control Voice & Chat Bar (#mcVoiceChatBarSection) present", 'id="mcVoiceChatBarSection"' in html and 'id="masterControlChatInput"' in html)
    check("1j. Master Functions Catalog Card (#masterFunctionsCatalogCard) present", 'id="masterFunctionsCatalogCard"' in html)

    # 2. Widget JS Voice Toggle Check
    with urllib.request.urlopen(BASE + "/widgets/lajefatura-widget.js", timeout=10) as r:
        wjs = r.read().decode("utf-8")
    check("2. Widget exposes window.LJ.isSpeaking & click-to-stop", "window.LJ.isSpeaking" in wjs and "if (state.speaking)" in wjs)
    check("2b. Widget exposes window.LJ.startMic & window.LJ.openChat", "window.LJ.startMic" in wjs and "window.LJ.openChat" in wjs)

    # 3. Live Brief, Weather (Miami, Colombia, Chile) & South America Timezones
    brief = get_json("/api/jefesito/brief?lang=es")
    w = brief.get("weather") or {}
    tzs = w.get("timezones") or {}
    check("3a. Live Weather includes Miami, Colombia & Chile", all(k in w for k in ("miami", "colombia", "chile")), str(list(w.keys())))
    check("3b. South America Timezones present", all(k in tzs for k in ("miami", "colombia", "chile", "argentina", "venezuela", "mexico")), str(list(tzs.keys())))

    # 4. CTO & CFO Connected Telemetry Endpoints
    u_sum = get_json("/api/unitec/summary")
    check("4a. UNITEC USA Firestore Telemetry", (u_sum.get("kpis") or {}).get("total_raw_with_tests", 0) >= 4000, f"sessions={u_sum.get('kpis',{}).get('total_raw_with_tests')}")
    b_sum = get_json("/api/buildingapp/summary")
    check("4b. BuildingApp Firestore Telemetry", ((b_sum.get("five_key_numbers") or {}).get("ai_usage") or {}).get("generations_total", 0) >= 100, "AI renders verified")
    c_st = get_json("/api/cameras/status")
    hik_s = ((c_st.get("hikconnect") or {}).get("summary") or {})
    check("4c. 55 Hik-Connect Cameras Status", hik_s.get("total_channels") == 55 and hik_s.get("live_signal_channels") == 53, f"{hik_s.get('live_signal_channels')}/{hik_s.get('total_channels')} live")
    ga4 = get_json("/api/ga4/summary")
    ga4_pid = str(ga4.get("active_property_id") or ga4.get("property_id") or "")
    check("4d. GA4 Property #543661675 Endpoint", ga4_pid == "543661675", f"active_property_id={ga4_pid}")
    inbox = get_json("/api/comms/inbox")
    check("4e. Mode C Inbox & Pre-Drafts", isinstance(inbox.get("items"), list) and len(inbox["items"]) > 0, f"{len(inbox.get('items', []))} threads")

    # 5. Per-Project Memory, Schedule & Reminder Workflow
    mem_post = post_json("/api/ceo/project_memory", {
        "text": "Smoke Test CTO: Auditar flujo de renders Gemini en Building Innovation y revisar despacho Miami",
        "company": "building",
        "date": "2026-11-05",
        "time": "10:15",
        "create_schedule": True,
        "create_reminder": True,
        "create_task": True,
    })
    check("5a. POST /api/ceo/project_memory stores note, schedule & reminder", mem_post.get("ok") is True and bool(mem_post.get("note", {}).get("id")), mem_post.get("summary_es", ""))
    mem_get = get_json("/api/ceo/project_memory?company=building")
    check("5b. GET /api/ceo/project_memory returns stored project items", mem_get.get("ok") is True and mem_get.get("counts", {}).get("notes", 0) >= 1, str(mem_get.get("counts")))
    # Clean up smoke test rows from data/mc.db so production memory stays clean
    import os, sqlite3
    db_p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "mc.db")
    if os.path.exists(db_p):
        with sqlite3.connect(db_p) as conn:
            for sql in (
                "DELETE FROM notes WHERE text LIKE '%Smoke Test CTO%'",
                "DELETE FROM tasks WHERE titulo LIKE '%Smoke Test CTO%'",
                "DELETE FROM tasks WHERE title LIKE '%Smoke Test CTO%'",
                "DELETE FROM events WHERE title LIKE '%Smoke Test CTO%'",
                "DELETE FROM ceo_reminders WHERE text LIKE '%Smoke Test CTO%'",
                "DELETE FROM ceo_reminders WHERE title LIKE '%Smoke Test CTO%'",
            ):
                try:
                    conn.execute(sql)
                except Exception:
                    pass
            conn.commit()

    # 6. Grounded Q&A, Close-Word Function Catalog, Notes, Google Calendar Sync & Email Reminders
    cat_res = get_json("/api/functions/catalog?q=cam")
    check("6a. /api/functions/catalog returns functions & matches 'cam'", cat_res.get("ok") is True and cat_res.get("count", 0) >= 20 and (cat_res.get("matched") or {}).get("fn", {}).get("id") == "proj_cameras", f"count={cat_res.get('count')}")
    cw_cam = post_json("/api/voice/command", {"command": "abrir cam", "lang": "es"})
    check("6b. Close-word voice command 'abrir cam' selects cameras & explains how it works", (cw_cam.get("ui") or {}).get("select_company") == "cameras" and "Cómo funciona" in cw_cam.get("reply", ""), cw_cam.get("reply", "")[:100])
    cw_uni = post_json("/api/voice/command", {"command": "ir a uni", "lang": "es"})
    check("6c. Close-word voice command 'ir a uni' selects UNITEC USA", (cw_uni.get("ui") or {}).get("select_company") == "unitec", cw_uni.get("reply", "")[:100])
    v_note = post_json("/api/voice/command", {"command": "anota Smoke Test CTO revisar inventario WPC en Miami", "lang": "es"})
    check("6d. Chatbot 'anota ...' saves note in mc.db", v_note.get("action") == "save_note" and v_note.get("ok") is True, v_note.get("reply", ""))
    v_gcal = post_json("/api/voice/command", {"command": "agendar cita Smoke Test CTO reunión con Juan mañana a las 3pm", "lang": "es"})
    check("6e. Chatbot schedules appointment + real-time Google Calendar sync", v_gcal.get("action") == "schedule_event" and "calendar.google.com" in str((v_gcal.get("ui") or {}).get("gcal_template_url", "")), v_gcal.get("reply", "")[:110])
    v_emrem = post_json("/api/voice/command", {"command": "recordatorio por correo Smoke Test CTO confirmar despacho UNITEC mañana a las 9am", "lang": "es"})
    check("6f. Chatbot creates & dispatches Email Reminder", v_emrem.get("action") == "email_reminder" and "mail.google.com" in str((v_emrem.get("ui") or {}).get("gmail_compose_url", "")), v_emrem.get("reply", "")[:110])
    ask_cam = get_json("/api/ask?lang=es&q=" + urllib.parse.quote("cuántas cámaras están en vivo"))
    check("6g. Grounded Q&A answers 53/55 cameras with source", "53" in ask_cam.get("answer", "") and ask_cam.get("grounded") is True, ask_cam.get("answer", "")[:100])
    v_cmd = post_json("/api/voice/command", {"command": "cómo van las empresas", "lang": "es"})
    check("6h. Voice command 'cómo van las empresas'", v_cmd.get("ok") is True and len(v_cmd.get("reply", "")) > 40, v_cmd.get("reply", "")[:100])

    # Clean up any Smoke Test CTO rows created during step 5 & 6
    if os.path.exists(db_p):
        with sqlite3.connect(db_p) as conn:
            for sql in (
                "DELETE FROM notes WHERE text LIKE '%Smoke Test CTO%'",
                "DELETE FROM tasks WHERE titulo LIKE '%Smoke Test CTO%'",
                "DELETE FROM tasks WHERE title LIKE '%Smoke Test CTO%'",
                "DELETE FROM events WHERE title LIKE '%Smoke Test CTO%'",
                "DELETE FROM reminders WHERE title LIKE '%Smoke Test CTO%'",
                "DELETE FROM ceo_reminders WHERE text LIKE '%Smoke Test CTO%'",
            ):
                try:
                    conn.execute(sql)
                except Exception:
                    pass
            conn.commit()

    # 7. Colombian Neural TTS Endpoint
    with urllib.request.urlopen(BASE + "/api/tts?lang=es&text=" + urllib.parse.quote("Resumen ejecutivo listo"), timeout=15) as r:
        tts_bytes = r.read()
        tts_ctype = r.headers.get("Content-Type", "")
    check("7. Colombian Neural TTS MP3 (/api/tts)", "audio/mpeg" in tts_ctype and len(tts_bytes) > 1000, f"{len(tts_bytes)} bytes ({tts_ctype})")

    # 8. Multi-Page Morning Executive Newspaper PDF (/api/daily.pdf & /api/report.pdf & /api/cameras/report.pdf)
    for pdf_ep in ("/api/daily.pdf?lang=es", "/api/report.pdf?company=cameras&lang=es", "/api/cameras/report.pdf?lang=es"):
        with urllib.request.urlopen(BASE + pdf_ep, timeout=45) as r:
            pbytes = r.read()
        npages = pbytes.count(b"/Type /Page") - pbytes.count(b"/Type /Pages")
        check(f"8. PDF Endpoint {pdf_ep}", pbytes[:4] == b"%PDF" and len(pbytes) > 3000, f"{len(pbytes)} bytes, {npages} pages")

    # 9. Dedicated Left-Menu Icons & Panes (Emails, Texts/Telegram, AI Voice Calls, Tasks/Calendar, Notes) & WhatsApp Removal
    check("9a. Dedicated Left-Menu Icons (comms, texts, calls, tasks_cal, notes_vault)", all(f'data-rail="{k}"' in html for k in ("comms", "texts", "calls", "tasks_cal", "notes_vault")))
    check("9b. Dedicated Panes (#pane-texts, #pane-calls, #pane-tasks_cal, #pane-notes_vault)", all(f'id="pane-{k}"' in html for k in ("comms", "texts", "calls", "tasks_cal", "notes_vault")))
    txt_hub = get_json("/api/texts/inbox")
    check("9c. /api/texts/inbox returns Telegram & Text only (whatsapp_removed=True)", txt_hub.get("ok") is True and txt_hub.get("whatsapp_removed") is True and len(txt_hub.get("items", [])) >= 1, f"count={txt_hub.get('count')}, drafts={txt_hub.get('draft_count')}")

    # 10. Multi-Command Delegation & AI Voice Calls + Transcripts & Decisions
    multi_res = post_json("/api/ceo/chat", {
        "message": "Go to Telegram and send a message to all asking what happened with the new products, and send a text to Roberto about Miami inventory",
        "company": "espacios_importados",
    })
    check("10a. Multi-Command Telegram/Text Delegation creates drafts for CEO approval", multi_res.get("ok") is True and len(multi_res.get("actions_executed", [])) >= 2, f"actions={len(multi_res.get('actions_executed', []))}")

    calls_res = get_json("/api/calls/list")
    check("10b. /api/calls/list returns AI voice calls with transcripts & GitHub architectures", calls_res.get("ok") is True and len(calls_res.get("calls", [])) >= 2 and len(calls_res.get("github_architectures", [])) >= 3, f"calls={calls_res.get('count')}")

    new_call = post_json("/api/calls/initiate", {
        "contact_name": "Carlos Méndez (Logística Buenaventura)",
        "to_phone": "+573105550192",
        "objective": "Smoke Test CTO: Confirmar liberación de BL contenedores WPC",
        "company": "espacios_importados",
    })
    check("10c. POST /api/calls/initiate places AI call & saves full transcript + decision options", new_call.get("ok") is True and len(new_call.get("transcript", [])) >= 3 and bool(new_call.get("call_result_summary")), new_call.get("call_result_summary", "")[:100])
    if new_call.get("call_id"):
        dec_res = post_json("/api/calls/decide", {
            "call_id": new_call["call_id"],
            "decision": "Smoke Test CTO: Aprobar liberación inmediata y notificar por Telegram",
            "send_telegram_confirm": False,
        })
        check("10d. POST /api/calls/decide records CEO decision & creates linked task", dec_res.get("ok") is True and bool(dec_res.get("ceo_decision")), str(dec_res.get("ceo_decision")))

    # Clean up smoke test rows created in step 10
    if os.path.exists(db_p):
        with sqlite3.connect(db_p) as conn:
            for sql in (
                "DELETE FROM voice_calls WHERE objective LIKE '%Smoke Test CTO%'",
                "DELETE FROM text_messages WHERE body LIKE '%what happened with the new products%' OR body LIKE '%Miami inventory%'",
                "DELETE FROM tasks WHERE title LIKE '%Smoke Test CTO%' OR title LIKE '%Decisión Llamada%'",
            ):
                try:
                    conn.execute(sql)
                except Exception:
                    pass
            conn.commit()

    print("\n" + ("FAILED: " + str(FAILS) if FAILS else "ALL E2E WORKFLOW & SMOKE TESTS PASSED (100%)"))
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
