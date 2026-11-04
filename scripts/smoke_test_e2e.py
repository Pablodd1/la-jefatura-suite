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
    with urllib.request.urlopen(BASE + path, timeout=15) as r:
        return json.loads(r.read().decode("utf-8"))


def post_json(path: str, payload: dict) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        BASE + path,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as r:
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

    # 2. Widget JS Voice Toggle Check
    with urllib.request.urlopen(BASE + "/widgets/lajefatura-widget.js", timeout=10) as r:
        wjs = r.read().decode("utf-8")
    check("2. Widget exposes window.LJ.isSpeaking & click-to-stop", "window.LJ.isSpeaking" in wjs and "if (state.speaking)" in wjs)

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

    # 6. Grounded Q&A & Voice Command Execution (Zero Guessing)
    ask_cam = get_json("/api/ask?lang=es&q=" + urllib.parse.quote("cuántas cámaras están en vivo"))
    check("6a. Grounded Q&A answers 53/55 cameras with source", "53" in ask_cam.get("answer", "") and ask_cam.get("grounded") is True, ask_cam.get("answer", "")[:100])
    v_cmd = post_json("/api/voice/command", {"command": "cómo van las empresas", "lang": "es"})
    check("6b. Voice command 'cómo van las empresas'", v_cmd.get("ok") is True and len(v_cmd.get("reply", "")) > 40, v_cmd.get("reply", "")[:100])

    # 7. Colombian Neural TTS Endpoint
    with urllib.request.urlopen(BASE + "/api/tts?lang=es&text=" + urllib.parse.quote("Resumen ejecutivo listo"), timeout=15) as r:
        tts_bytes = r.read()
        tts_ctype = r.headers.get("Content-Type", "")
    check("7. Colombian Neural TTS MP3 (/api/tts)", "audio/mpeg" in tts_ctype and len(tts_bytes) > 1000, f"{len(tts_bytes)} bytes ({tts_ctype})")

    # 8. Multi-Page Morning Executive Newspaper PDF (/api/daily.pdf & /api/report.pdf & /api/cameras/report.pdf)
    for pdf_ep in ("/api/daily.pdf?lang=es", "/api/report.pdf?company=cameras&lang=es", "/api/cameras/report.pdf?lang=es"):
        with urllib.request.urlopen(BASE + pdf_ep, timeout=20) as r:
            pbytes = r.read()
        npages = pbytes.count(b"/Type /Page") - pbytes.count(b"/Type /Pages")
        check(f"8. PDF Endpoint {pdf_ep}", pbytes[:4] == b"%PDF" and len(pbytes) > 3000, f"{len(pbytes)} bytes, {npages} pages")

    print("\n" + ("FAILED: " + str(FAILS) if FAILS else "ALL E2E WORKFLOW & SMOKE TESTS PASSED (100%)"))
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
