#!/usr/bin/env python3
"""Automated regression & feature verification suite for Mission Control upgrades (R1-R5).

Portable across both `la-jefatura-suite` and `ai-ceo-personal`. Runs purely against
isolated temporary SQLite databases (`MC_DB_PATH`) so live `data/mc.db` and
`data/onboarding_state.json` are NEVER mutated.
"""

import atexit
import gc
import glob
import hashlib
import inspect
import json
import os
import py_compile
import re
import sqlite3
import sys
import tempfile
import traceback
from pathlib import Path
from unittest import mock

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_ISO_TMP = tempfile.TemporaryDirectory(prefix="mc_upgrades_iso_", ignore_cleanup_errors=True)
atexit.register(_ISO_TMP.cleanup)
ISO_DB_PATH = os.path.join(_ISO_TMP.name, "test_upgrades_mc.db")
os.environ["MC_DB_PATH"] = ISO_DB_PATH
for _k in (
    "BREVO_API_KEY", "TELEGRAM_BOT_TOKEN", "TG_BOT_TOKEN", "TG_SECONDARY_BOT_TOKEN",
    "TELNYX_API_KEY", "TELNYX_CONNECTION_ID", "TELNYX_FROM_NUMBER",
    "TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "META_WA_ACCESS_TOKEN",
    "JUAN_GMAIL_APP_PASSWORD", "GEMINI_API_KEY",
):
    os.environ[_k] = ""

SERVER_DIR = os.path.join(REPO_ROOT, "server")
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)


def _sha256_if_exists(path: str) -> str | None:
    if not os.path.isfile(path):
        return None
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _init_temp_db(db_path: str):
    """Create minimal schema matching mc.db for isolated unit tests."""
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS events (
            id TEXT PRIMARY KEY,
            title TEXT,
            date TEXT,
            time TEXT,
            duration INTEGER DEFAULT 30,
            company TEXT,
            notes TEXT,
            source TEXT,
            created_at REAL
        );
        CREATE TABLE IF NOT EXISTS tasks (
            id TEXT PRIMARY KEY,
            title TEXT,
            status TEXT DEFAULT 'pending',
            priority TEXT DEFAULT 'medium',
            company TEXT,
            due_date TEXT,
            source_ref TEXT,
            created_at REAL
        );
        CREATE TABLE IF NOT EXISTS comms_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            channel TEXT,
            direction TEXT,
            sender TEXT,
            recipient TEXT,
            company TEXT,
            text TEXT,
            created_at REAL
        );
        CREATE TABLE IF NOT EXISTS drafts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            comms_id INTEGER,
            body TEXT,
            status TEXT DEFAULT 'pending',
            version INTEGER DEFAULT 1,
            created_at REAL
        );
        """
    )
    conn.commit()
    conn.close()


def _set_temp_db_across_modules(tmp_db: str):
    """Bind all knowledge/copilot/voice/comms/camera modules to an isolated temp DB."""
    os.environ["MC_DB_PATH"] = tmp_db
    import knowledge_store
    import voice_commands
    import comms_brain
    import text_messaging
    import voice_calls_engine
    import ceo_action_brain
    import spark_followup_engine
    import cameras
    import camera_report
    import sam3_tracker_engine
    import jefesito

    knowledge_store.DB = tmp_db
    knowledge_store._SCHEMA_DONE = False
    knowledge_store._EV_DONE = False
    knowledge_store._DEV_DONE = False
    voice_commands.DB = tmp_db
    comms_brain.DB = tmp_db
    text_messaging.DB = tmp_db
    voice_calls_engine.DB_PATH = Path(tmp_db)
    ceo_action_brain.DB = tmp_db
    if hasattr(ceo_action_brain, "_SCHEMA_READY"):
        ceo_action_brain._SCHEMA_READY = False
    spark_followup_engine.DB = tmp_db
    if hasattr(spark_followup_engine, "_SCHEMA_READY"):
        spark_followup_engine._SCHEMA_READY = False
    if hasattr(spark_followup_engine, "_LAST_DB_PATH"):
        spark_followup_engine._LAST_DB_PATH = ""
    cameras.DB = tmp_db
    if hasattr(cameras, "_SCHEMA_DONE"):
        cameras._SCHEMA_DONE = False
    if hasattr(camera_report, "_SCHEMA_DONE"):
        camera_report._SCHEMA_DONE = False
    if hasattr(sam3_tracker_engine, "DB_PATH"):
        sam3_tracker_engine.DB_PATH = Path(tmp_db)
    jefesito.DB = tmp_db
    if hasattr(jefesito, "_SCHEMA_DONE"):
        jefesito._SCHEMA_DONE = False


def test_syntax_compile_all():
    server_files = sorted(glob.glob(os.path.join(REPO_ROOT, "server", "*.py")))
    targets = server_files + [os.path.join(REPO_ROOT, "scripts", "demo_server.py")]
    assert len(server_files) >= 15, f"Too few server modules found in {REPO_ROOT}"
    for f in targets:
        assert os.path.exists(f), f"Missing expected file: {f}"
        py_compile.compile(f, doraise=True)
    return f"Compiled {len(targets)} Python modules cleanly in {os.path.basename(REPO_ROOT)}"


def test_no_hardcoded_telegram_tokens():
    leaked_prefixes = ["8678556614:", "8638273831:"]
    targets = sorted(glob.glob(os.path.join(REPO_ROOT, "server", "*.py")))
    for path in targets:
        content = open(path, "r", encoding="utf-8", errors="ignore").read()
        for prefix in leaked_prefixes:
            assert prefix not in content, f"Hardcoded Telegram token found in {path}"
    return f"Zero hardcoded Telegram tokens across {len(targets)} server modules"


def test_voice_calls_fixes():
    import voice_calls_engine

    voice_calls_engine.DB_PATH = Path(ISO_DB_PATH)
    is_personal = "ai-ceo-personal" in REPO_ROOT.lower()
    if not is_personal:
        assert hasattr(voice_calls_engine, "initiate_call"), "initiate_call compatibility wrapper missing"
        assert hasattr(voice_calls_engine, "_try_telnyx_transfer_to_ceo"), "Telnyx transfer helper missing"
    sig = inspect.signature(voice_calls_engine.list_voice_calls)
    if "include_demo" in sig.parameters:
        prod_calls = voice_calls_engine.list_voice_calls(company="all", include_demo=False, db_path=Path(ISO_DB_PATH))
        demo_calls = voice_calls_engine.list_voice_calls(company="all", include_demo=True, db_path=Path(ISO_DB_PATH))
        assert prod_calls["ok"] and demo_calls["ok"]
        assert all(not str(c.get("provider_call_sid") or "").startswith("CA_GROK_") for c in prod_calls["calls"])
        return f"voice_calls verified on isolated DB (real={prod_calls['count']}, with_demo={demo_calls['count']})"
    calls = voice_calls_engine.list_voice_calls(company="all")
    assert calls["ok"]
    return f"voice_calls verified on isolated DB (count={calls.get('count', len(calls.get('calls') or []))})"


def test_comms_brain_subject_and_honest_email():
    import comms_brain

    comms_brain.DB = ISO_DB_PATH
    if hasattr(comms_brain, "_extract_thread_subject"):
        subj = comms_brain._extract_thread_subject(
            "From: bob@example.com\nSubject: Q4 Medical Billing Audit\n\nHi Jasmel, please review."
        )
        assert subj == "Re: Q4 Medical Billing Audit", f"Unexpected extracted subject: {subj!r}"
        assert "\n" not in subj and "\r" not in subj, "CR/LF leaked into Subject header"
        fb = comms_brain._extract_thread_subject("tid-123\ninjected-header: bad")
        assert "\n" not in fb and "\r" not in fb, "CR/LF leaked in fallback Subject"
        return f"_extract_thread_subject returned clean '{subj}' (CR/LF-safe)"
    inbox = comms_brain.list_inbox_with_drafts()
    assert isinstance(inbox, dict) and "items" in inbox, f"Unexpected inbox payload: {inbox}"
    return f"comms_brain mirror API verified on isolated DB ({len(inbox.get('items') or [])} items)"


def test_google_workspace_gatekeeper():
    import google_workspace

    vip = google_workspace.classify_email_gatekeeper(
        sender="carlos@clientclinic.com",
        subject="Urgent: Contract signature needed today",
        body="Hi Jasmel, can we review the proposal at 3pm?",
    )
    news = google_workspace.classify_email_gatekeeper(
        sender="newsletter@digest.substack.com",
        subject="Weekly AI Digest #42",
        body="Click here to unsubscribe from this newsletter.",
    )
    rcpt = google_workspace.classify_email_gatekeeper(
        sender="noreply@stripe.com",
        subject="Your invoice receipt #1029",
        body="Thank you for your payment. Receipt attached.",
    )
    assert vip == "vip_human", f"Expected vip_human, got {vip}"
    assert news == "newsletter_digest", f"Expected newsletter_digest, got {news}"
    assert rcpt == "automated_receipt", f"Expected automated_receipt, got {rcpt}"
    return "Gatekeeper accurately separated vip_human, newsletter_digest, automated_receipt"


def test_unified_life_os_end_to_end():
    import unified_life_os

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        db_path = os.path.join(tmp, "test_mc.db")
        _init_temp_db(db_path)

        conn = sqlite3.connect(db_path)
        conn.execute("ALTER TABLE events ADD COLUMN status TEXT DEFAULT 'scheduled'")
        conn.execute("ALTER TABLE events ADD COLUMN ts REAL DEFAULT 0")
        conn.execute(
            "INSERT INTO events (id, title, date, time, duration, company, notes, source, status, ts) "
            "VALUES ('ev-1', 'Unitec Strategy Review', '2026-11-25', '10:00', 60, 'unitec', 'Review Q4', 'manual', 'scheduled', 1.0)"
        )
        conn.execute(
            "INSERT INTO tasks (id, title, status, priority, company, due_date, source_ref, created_at) "
            "VALUES ('t-1', 'Approve MBMB payer contract', 'pending', 'high', 'mbmb', '2026-11-25', 'ceo', 1.0)"
        )
        conn.commit()
        conn.close()

        m_p = unified_life_os.remember("Mom's birthday is Dec 12", space="personal", category="family", db_path=db_path)
        m_b = unified_life_os.remember("Never schedule calls before 9am", space="business", category="preference", db_path=db_path)
        assert m_p["ok"] and m_b["ok"]
        personal_only = unified_life_os.recall(space="personal", db_path=db_path)
        assert len(personal_only) == 1 and "Mom" in personal_only[0]["content"]
        f_res = unified_life_os.forget(m_p["id"], db_path=db_path)
        assert f_res["ok"]

        pt = unified_life_os.add_personal_task("Book dentist appointment", category="health", due_date="2026-11-26", db_path=db_path)
        assert pt["ok"] and pt["id"]
        tog = unified_life_os.toggle_personal_task(pt["id"], db_path=db_path)
        assert tog["ok"] and tog["status"] == "completed"
        pc1 = unified_life_os.upsert_personal_contact("Dr. Elena Ruiz", relationship="doctor", phone="+13055550199", db_path=db_path)
        pc2 = unified_life_os.upsert_personal_contact("Dr. Elena Ruiz", relationship="family_doctor", phone="+13055550199", notes="Miami Beach", db_path=db_path)
        assert pc1["ok"] and pc2["ok"] and pc1["id"] == pc2["id"] and pc2["updated"] is True
        ps_check = unified_life_os.get_personal_space(db_path=db_path)
        assert len(ps_check["contacts"]) == 1, f"Expected 1 deduplicated VIP contact, got {len(ps_check['contacts'])}"

        tb_dry = unified_life_os.conflict_aware_timeblock(target_date="2026-11-25", space="all", max_blocks=3, apply=False, db_path=db_path)
        assert tb_dry["ok"] and tb_dry["dry_run"] is True and tb_dry["scheduled_count"] >= 1
        conn_chk = sqlite3.connect(db_path)
        cnt_before = conn_chk.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        conn_chk.close()
        assert cnt_before == 1, f"Dry-run timeblock mutated events table ({cnt_before} rows)"

        tb = unified_life_os.conflict_aware_timeblock(target_date="2026-11-25", space="all", max_blocks=3, apply=True, db_path=db_path)
        assert tb["ok"] and tb["applied"] is True and tb["scheduled_count"] >= 1
        for blk in tb["scheduled"]:
            assert blk["time"] != "10:00", f"Timeblock collided with existing 10:00 event: {blk}"

        ics = unified_life_os.export_calendar_ics(db_path=db_path)
        assert "BEGIN:VCALENDAR" in ics and "BEGIN:VEVENT" in ics and "END:VCALENDAR" in ics

        bt = unified_life_os.queue_browser_task(
            portal_url="https://provider.humana.com",
            goal="Download latest Humana ERA remittance",
            space="business",
            db_path=db_path,
        )
        assert bt["ok"] and bt["status"] == "pending_approval"
        bt_ap = unified_life_os.update_browser_task(bt["id"], action="approve", db_path=db_path)
        assert bt_ap["ok"] and bt_ap["status"] == "approved"
        bt_list = unified_life_os.list_browser_tasks(db_path=db_path)
        assert bt_list["ok"] and len(bt_list["items"]) == 1 and bt_list["items"][0]["status"] == "approved"

        wt = unified_life_os.handle_walk_and_talk(
            transcript_text="Remember that my wife loves white orchids for her birthday",
            space="all",
            lang="en",
            db_path=db_path,
        )
        assert wt["ok"] and wt["action"] == "memory_saved"

        ov = unified_life_os.get_space_overview(space="all", db_path=db_path)
        assert ov["ok"]
        gk = unified_life_os.get_email_gatekeeper_summary(db_path=db_path)
        assert gk["ok"]

    return "All 7 Unified Life OS workflows passed against isolated temp DB"


def test_r1_jefesito_and_demo_html_branding_contrast():
    import jefesito

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        try:
            tmp_db = os.path.join(tmp, "r1_mc.db")
            _set_temp_db_across_modules(tmp_db)
            is_personal = "ai-ceo-personal" in REPO_ROOT.lower()
            expected_ceo = "Jasmel" if is_personal else "Juan David"
            assert jefesito.DEFAULTS.get("ceo_name") == expected_ceo, f"Expected ceo_name={expected_ceo}, got {jefesito.DEFAULTS}"

            for lg in ("es", "en"):
                day = jefesito.get_day(lang=lg)
                assert "Building AI" in (day.get("greeting") or ""), f"{lg} greeting missing Building AI: {day.get('greeting')}"
                assert "Building Innovation" not in (day.get("spoken") or ""), f"{lg} spoken still has Building Innovation"
                secs = day.get("sections") or []
                assert len(secs) >= 3, f"{lg} expected >=3 sections, got {len(secs)}"
                titles = [s.get("title", "") for s in secs]
                assert any("Building AI" in t for t in titles), f"{lg} sections missing Building AI: {titles}"
        finally:
            gc.collect()
            _set_temp_db_across_modules(ISO_DB_PATH)

    demo_html = open(os.path.join(REPO_ROOT, "mock", "demo.html"), encoding="utf-8").read()
    assert 'id="brandSub">Centro Ejecutivo Building AI</span>' in demo_html, "#brandSub missing Centro Ejecutivo Building AI"
    assert "$('#brandSub').textContent = 'Centro Ejecutivo Building AI';" in demo_html, "saveOnboardingSetup() does not lock #brandSub"
    assert not re.search(r"anythingNew|ljAnythingNew", demo_html), "#ljAnythingNewSection or handlers still in demo.html"
    assert 'data-theme="limestone"' in demo_html, "limestone theme lock missing"
    hdr_match = re.search(r"<header\b.*?</header>", demo_html, flags=re.S | re.I)
    assert hdr_match and 'id="ljThemePick"' not in hdr_match.group(0), "#ljThemePick found inside <header>"
    assert 'id="ljMainFooter"' in demo_html and 'id="footerWebsiteBtn"' in demo_html and 'id="footerInstagramBtn"' in demo_html
    assert "Sitio Web" in demo_html and "Instagram Studio" in demo_html
    wrap_m = re.search(r'id="selectedCompanyDepartmentsWrapper"[^>]*>', demo_html)
    assert wrap_m and "var(--panel2)" in wrap_m.group(0) and "rgba(15,16,14" not in wrap_m.group(0), "Departments wrapper contrast not limestone"
    assert ".lj-sem.ok{background:#dcfce7;color:#14532d" in demo_html, ".lj-sem.ok missing WCAG-darkened colors"
    assert ".lj-sem.crit{background:#fee2e2;color:#7f1d1d" in demo_html, ".lj-sem.crit missing WCAG-darkened colors"

    clean_ui = open(os.path.join(REPO_ROOT, "widgets", "clean-workspace-ui.js"), encoding="utf-8").read()
    assert "ljCountryClockTicker" in clean_ui, "#ljCountryClockTicker missing in clean-workspace-ui.js"

    return "R1 branding, Building AI brief, limestone contrast, #ljAnythingNew removal & footer verified"


def test_r2_workspace_tabs_and_race_guards():
    clean_ui = open(os.path.join(REPO_ROOT, "widgets", "clean-workspace-ui.js"), encoding="utf-8").read()
    demo_html = open(os.path.join(REPO_ROOT, "mock", "demo.html"), encoding="utf-8").read()

    clean_compact = re.sub(r"\s+", "", clean_ui)
    assert "#ljWorkspaceTabs" in clean_ui and "position:sticky;top:0" in clean_compact
    assert "UI_STATE.activeView = viewId" in clean_ui
    assert "if (UI_STATE.activeView !== expectedView) return;" in clean_ui, "Missing async race guard in renderCompanyFocusPane"
    assert "setCurCompany" in clean_ui and "window.setCurCompany = function" in demo_html, "Missing setCurCompany synchronization"
    assert "liveVideoCallSetupDrawer" in clean_ui and "removeAttribute(\"open\")" in clean_ui, "tab:calls drawer collapse missing"
    assert "viewId === \"home\"" in clean_ui and "isTab" in clean_ui
    return "R2 sticky workspace tabs, setCurCompany sync, calls drawer collapse & async race guards verified"


def test_r3_copilot_nlu_voice_and_no_spurious_dev():
    import llm_router
    import functions_catalog
    import knowledge_store
    import ceo_action_brain
    import spark_followup_engine
    import voice_commands

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        try:
            tmp_db = os.path.join(tmp, "r3_mc.db")
            _set_temp_db_across_modules(tmp_db)
            knowledge_store._db().close()

            # 1. functions_catalog gating
            assert functions_catalog.match_function("¿Qué correos tengo pendientes?") is None
            assert functions_catalog.match_function("¿Cuántos correos sin responder tengo hoy?") is None
            assert functions_catalog.match_function("Hola, buenos días") is None
            assert functions_catalog.match_function("quiero revisar todas las métricas pendientes de hoy ahora") is None
            assert functions_catalog.match_function("abrir blogs") is not None

            # 2. knowledge_store.ask auto_escalate=False safety
            for phrase in ("Hola", "Muchas gracias, perfecto", "¿Tienes datos sobre Marte en 2099?"):
                ans = knowledge_store.ask(phrase, lang="es", auto_escalate=False)
                assert ans.get("dev_ticket") is None, f"Spurious dev_ticket on {phrase!r}"
            assert len(knowledge_store.list_dev_escalations()) == 0, "Spurious dev_escalations row created"

            # 3. Deterministic offline mode (llm_router patched to return ok=False)
            with mock.patch.object(llm_router, "generate_text_with_meta", return_value={"ok": False, "text": "", "provider": "mock_none"}):
                for chat_msg in ("Hola, ¿cómo estás?", "Muchas gracias, perfecto"):
                    r = spark_followup_engine.handle_live_turn(chat_msg, channel="chat", lang="es")
                    assert r.get("ok") and r.get("action") == "conversational_chat", f"Bad chitchat: {r}"
                    assert r.get("dev_escalation") is None
                    assert "Activando función" not in (r.get("reply") or "")

                for mail_q in ("¿Qué correos tengo pendientes?", "¿Tengo correos sin responder?", "¿Qué correos hay que enviar?", "¿A quién le respondo el correo?"):
                    r = spark_followup_engine.handle_live_turn(mail_q, channel="chat", lang="es")
                    assert r.get("ok") and r.get("action") == "list_pending_emails", f"Bad email query {mail_q!r}: {r}"
                    assert "Activando función" not in (r.get("reply") or "")

                r_juan = spark_followup_engine.handle_live_turn("llama a juan y dile que revisemos los contratos", channel="voice", lang="es")
                assert r_juan.get("ok") and "juan david" in json.dumps(r_juan, ensure_ascii=False).lower(), f"Failed juan -> Juan David: {r_juan}"
                assert "equipo ejecutivo" not in (r_juan.get("reply") or "").lower()

                r_dra = spark_followup_engine.handle_live_turn("escríbele a la dra. maria gonzalez que llegamos a las 4", channel="voice", lang="es")
                assert r_dra.get("ok") and "equipo ejecutivo" not in (r_dra.get("reply") or "").lower(), f"Leaked Equipo Ejecutivo: {r_dra}"
                assert "[" not in (r_dra.get("reply") or ""), f"Placeholder bracket leaked: {r_dra}"

                r_ing = spark_followup_engine.handle_live_turn("escríbele al ing. carlos sobre los planos", channel="voice", lang="es")
                assert r_ing.get("ok") and "carlos" in json.dumps(r_ing, ensure_ascii=False).lower()

                r_uni = spark_followup_engine.handle_live_turn("manda un mensaje a unitec sobre el inventario", channel="voice", lang="es")
                assert r_uni.get("ok") and "unitec" in json.dumps(r_uni, ensure_ascii=False).lower()

                vc_mail = voice_commands.execute("¿Cuáles son los correos sin responder?", auto_escalate=False, allow_unknown_ask=False)
                assert vc_mail.get("action") != "catalog_function"

            # 4. Mocked structured JSON LLM response path
            fake_llm_json = json.dumps({
                "intent": "list_pending_emails",
                "company": "all",
                "target_contact": "",
                "executive_reply": "Aquí tienes tus correos pendientes.",
                "email": {},
                "text": {},
                "voice_call": {},
                "calendar": {},
                "reminder": {},
                "task": {},
                "followup": {},
                "note": {},
            })
            with mock.patch.object(llm_router, "generate_text_with_meta", return_value={"ok": True, "text": fake_llm_json, "provider": "mock_gemini", "model": "gemini-test"}):
                r_llm = spark_followup_engine.handle_live_turn("Revisa si alguien me escribió hoy", channel="chat", lang="es")
                assert r_llm.get("ok") and r_llm.get("action") == "list_pending_emails", f"Mock LLM path failed: {r_llm}"

            # 5. Direct contact resolution checks (T1-44 / T4-07 / diana vs espacios)
            assert "Juan David" in ceo_action_brain.resolve_contact_unified("llama a juan y dile que revisemos los contratos", extra_directory=spark_followup_engine.KNOWN_CONTACTS, db_path=tmp_db)["name"]
            assert "Juan David" in ceo_action_brain.resolve_contact_unified("llama a juan david", db_path=tmp_db)["name"]
            assert "Juan Perez" in ceo_action_brain.resolve_contact_unified("llama a juan perez", db_path=tmp_db)["name"]
            assert "Diana" in ceo_action_brain.resolve_contact_unified("escribe a diana de espacios", db_path=tmp_db)["name"]

            assert len(knowledge_store.list_dev_escalations()) == 0, "Unexpected #DEV escalation during R3 NLU suite"

            # Intentional explicit escalation still logs 1 ticket
            esc = knowledge_store.log_dev_escalation("Conectar ERP de pruebas", reason="explicit_test", channel="ui")
            assert esc.get("ok") and len(knowledge_store.list_dev_escalations()) == 1
        finally:
            gc.collect()
            _set_temp_db_across_modules(ISO_DB_PATH)

    # Frontend voice mic contract checks
    w_lj = open(os.path.join(REPO_ROOT, "widgets", "lajefatura-widget.js"), encoding="utf-8").read()
    w_sc = open(os.path.join(REPO_ROOT, "widgets", "spark-copilot.js"), encoding="utf-8").read()
    demo_html = open(os.path.join(REPO_ROOT, "mock", "demo.html"), encoding="utf-8").read()
    assert "window.LJVoice" in w_lj and "stopAllMics" in w_lj and "surfaceMicNotice" in w_lj
    assert "state.starting" in w_lj and "continuous = true" in w_lj
    assert "pendingQueue" in w_sc and "mergeTurnsWithServer" in w_sc and ".ljc-msg.notice" in w_sc
    assert "superStarting" in demo_html and "#mcVoiceMicBtn.is-listening" in demo_html

    return "R3 Copilot NLU, contact precedence, 0 spurious #DEV & voice mic contracts verified"


def test_r4_camera_non_gated_and_provenance():
    import cameras
    import sam3_tracker_engine
    import camera_report
    import jev_vision_engine

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        try:
            tmp_db = os.path.join(tmp, "r4_mc.db")
            _set_temp_db_across_modules(tmp_db)

            # Initialize cameras schema (cam_events, etc.) on temp DB first
            st = camera_report.enrich_status_payload(
                cameras.status(os.path.join(REPO_ROOT, "data", "samples", "cameras.json"), force=False)
            )
            assert isinstance(st.get("cached_fallback"), bool)
            assert (st.get("hikconnect") or {}).get("summary", {}).get("total_devices") == 5
            assert (st.get("hikconnect") or {}).get("summary", {}).get("total_channels") == 55

            # 1. Default include_demo=True non-gated payloads
            pb = sam3_tracker_engine.get_people_breaks_report(db_path=Path(tmp_db))
            tot = pb.get("totals") or {}
            assert tot.get("individuals_tracked") == 6, f"Expected 6 tracked, got {tot}"
            assert tot.get("bathroom_trips_total") == 13 and tot.get("bathroom_minutes_total") == 118, f"Bad bathroom totals: {tot}"
            assert tot.get("smoke_trips_total") == 7 and tot.get("smoke_minutes_total") == 67
            assert tot.get("lunch_trips_total") == 6 and tot.get("lunch_minutes_total") == 338
            assert tot.get("all_break_minutes_total") == 523
            assert len(pb.get("roster") or []) == 6
            assert len(pb.get("recent_events") or []) >= 25
            assert pb.get("data_provenance")

            sam = sam3_tracker_engine.get_sam3_telemetry_and_logs(db_path=Path(tmp_db))
            traces = sam.get("traces") or []
            assert len(traces) >= 5
            assert traces[0].get("trace_id") == traces[0].get("trace_code") and traces[0].get("trace_id"), "Missing trace_id alias"
            assert len(sam.get("audit_log") or []) >= 5
            assert (sam.get("people_breaks") or {}).get("totals", {}).get("individuals_tracked") == 6
            assert sam.get("data_provenance")

            # 2. Strict ?demo=0 isolation
            pb_live = sam3_tracker_engine.get_people_breaks_report(include_demo=False, db_path=Path(tmp_db))
            assert (pb_live.get("totals") or {}).get("individuals_tracked") == 0
            assert (pb_live.get("totals") or {}).get("all_break_minutes_total") == 0
            assert (pb_live.get("data_provenance") or {}).get("source") == "live_only_no_edge_agent"

            ev = sam3_tracker_engine.log_person_break_event("PER-099", "bathroom", 6, db_path=Path(tmp_db))
            assert ev.get("ok")
            pb_live2 = sam3_tracker_engine.get_people_breaks_report(include_demo=False, db_path=Path(tmp_db))
            assert (pb_live2.get("totals") or {}).get("bathroom_trips_total") == 1
            assert (pb_live2.get("totals") or {}).get("bathroom_minutes_total") == 6

            # 3. SAM3 rapid tracking & person identity validation
            t1 = sam3_tracker_engine.track_custom_concept("forklift WPC", db_path=Path(tmp_db))
            t2 = sam3_tracker_engine.track_custom_concept("forklift WPC", db_path=Path(tmp_db))
            assert t1.get("ok") and t2.get("ok") and t1.get("trace_code") != t2.get("trace_code")
            bad_id = sam3_tracker_engine.assign_person_identity("PER-004", "", db_path=Path(tmp_db))
            assert bad_id.get("ok") is False
            ok_id = sam3_tracker_engine.assign_person_identity("PER-004", "Luis Torres", role_title=123, visual_cue_es=456, db_path=Path(tmp_db))
            assert ok_id.get("ok") is True

            # 4. camera_report & jev_vision_engine
            vig = camera_report.build_vigilant_mode_telemetry()
            vt = vig.get("totals") or {}
            assert vt.get("people_tracked") == 201 and vt.get("entries_total") == 217 and vt.get("exits_total") == 213
            assert sum(int(z.get("entries") or 0) for z in (vig.get("people_entries_exits") or [])) == 217
            assert len(vig.get("suspect_activities") or []) >= 5
            assert len(vig.get("recommended_times_check") or []) == 6
            assert len((vig.get("jev_ai") or {}).get("decisions") or []) >= 9
            assert len((vig.get("sam3_tracker") or {}).get("traces") or []) >= 5
            assert vig.get("data_provenance")

            rep = camera_report.build_report(save=False)
            ex = rep.get("example_report") or {}
            tb = float((ex.get("kpis") or {}).get("total_storage_tb") or 0)
            assert tb > 0 and abs(tb - 12.92) > 0.1, f"Storage TB still hardcoded: {tb}"
            assert len(ex.get("docks_summary") or []) == 7
            assert len(ex.get("site_schedule") or []) == 4
            assert len(ex.get("events_by_hour") or {}) == 24
            assert len(ex.get("learned_patterns") or []) >= 5
            assert rep.get("data_provenance") or ex.get("data_provenance")

            jev_res = jev_vision_engine.evaluate_all_vigilant_zones(vig.get("people_entries_exits") or [], persist=False)
            assert jev_res.get("ok") and len(jev_res.get("decisions") or []) >= 9
            assert all(d.get("urgency_score") in (0, 1, 2) for d in jev_res.get("decisions") or [])
        finally:
            gc.collect()
            _set_temp_db_across_modules(ISO_DB_PATH)

    clean_ui = open(os.path.join(REPO_ROOT, "widgets", "clean-workspace-ui.js"), encoding="utf-8").read()
    assert "?demo=1" not in clean_ui, "clean-workspace-ui.js still gates with ?demo=1"
    assert "/api/cameras/sam3" in clean_ui
    for badge_txt in ("TELEMETRÍA NVR EN VIVO", "CACHÉ HIK-CONNECT", "SIMULACIÓN IA", "META / LÍMITE RECOMENDADO"):
        assert badge_txt in clean_ui, f"Missing provenance badge {badge_txt} in clean-workspace-ui.js"

    return "R4 non-gated camera analytics, ?demo=0 isolation, trace_id alias & provenance verified"


def test_r5_repo_portability_and_live_safety():
    assert os.path.normpath(os.environ.get("MC_DB_PATH", "")) == os.path.normpath(ISO_DB_PATH)
    live_db = os.path.join(REPO_ROOT, "data", "mc.db")
    if os.path.isfile(live_db):
        conn = sqlite3.connect(f"file:{live_db}?mode=ro", uri=True, timeout=10.0)
        chk = conn.execute("PRAGMA quick_check").fetchone()[0]
        conn.close()
        assert chk == "ok", f"Live mc.db PRAGMA quick_check failed: {chk}"
    return f"Repo portability ({os.path.basename(REPO_ROOT)}) & live DB quick_check=ok verified"


def test_r6_whatsapp_telegram_voice_and_call_monitoring():
    import base64
    import meta_whatsapp
    import voice_calls_engine

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        r6_db = os.path.join(tmp, "r6_mc.db")
        orig_wa_db = meta_whatsapp.DB
        orig_tr = meta_whatsapp.transcribe_audio_bytes
        try:
            _set_temp_db_across_modules(r6_db)
            meta_whatsapp.DB = r6_db

            # 1. Verify approve_and_send_reply exists and guards unwatched plain names
            assert hasattr(meta_whatsapp, "approve_and_send_reply"), "meta_whatsapp.approve_and_send_reply missing"
            assert hasattr(meta_whatsapp, "send_ceo_summary"), "meta_whatsapp.send_ceo_summary missing"
            bad_r = meta_whatsapp.approve_and_send_reply(target="UnknownPersonNoPhone", reply_text="Hola")
            assert bad_r["ok"] is False and "unwatched_or_no_phone" in bad_r.get("error", ""), f"Unexpected result: {bad_r}"

            # 2. Verify WhatsApp audio webhook transcription path (mocked Gemini)
            meta_whatsapp.transcribe_audio_bytes = lambda ab, mime_type="audio/ogg", lang="es", timeout=20.0: {
                "ok": True,
                "transcript": "Si tengo los productos, lo termino antes de las 2pm",
                "model": "mock-gemini",
                "error": None,
            }
            wa_payload = {
                "entry": [{
                    "changes": [{
                        "value": {
                            "contacts": [{"wa_id": "573001234567", "profile": {"name": "Roberto Colombia"}}],
                            "messages": [{
                                "from": "573001234567",
                                "type": "audio",
                                "audio": {
                                    "mime_type": "audio/ogg",
                                    "audio_base64": base64.b64encode(b"OggS-mock-audio").decode("ascii"),
                                },
                            }],
                        }
                    }]
                }]
            }
            res_wa = meta_whatsapp.handle_webhook_payload(wa_payload)
            assert res_wa["ok"] and res_wa["processed"] == 1, f"WA audio webhook failed: {res_wa}"

            # 3. Verify Telegram voice-note inbound processor (if present)
            try:
                import telegram_inbound
                orig_tg_tr = telegram_inbound.download_and_transcribe_telegram_audio
                try:
                    telegram_inbound.download_and_transcribe_telegram_audio = lambda tok, fid, mime_type="audio/ogg", lang="es": {
                        "ok": True,
                        "transcript": "Recuerdame revisar pedido de Roberto hoy",
                    }
                    tg_item = telegram_inbound.process_telegram_update(
                        {
                            "update_id": 999901,
                            "message": {
                                "chat": {"id": 7838956683, "type": "private"},
                                "from": {"first_name": "Juan", "last_name": "Garcia"},
                                "voice": {"file_id": "mock_fid_123", "duration": 6, "mime_type": "audio/ogg"},
                            },
                        },
                        bot_token="mock-token",
                        ceo_chat_id="7838956683",
                        send_reply=False,
                    )
                    assert tg_item and tg_item["voice_transcribed"] is True and "Roberto" in tg_item["text"], f"TG voice failed: {tg_item}"
                finally:
                    telegram_inbound.download_and_transcribe_telegram_audio = orig_tg_tr
            except ImportError:
                pass

            # 4. Verify outbound call feedback auto-creates a monitored task in isolated temp DB
            call_db = Path(tmp) / "call_monitor.db"
            fb = voice_calls_engine.ingest_outbound_call_feedback(
                payload={
                    "To": "+573001234567",
                    "SpeechResult": "Si Juan, tengo los productos listos y termino antes de las 2pm.",
                    "CallDuration": "32",
                },
                notify_ceo=False,
                db_path=call_db,
            )
            assert fb["ok"] and fb.get("monitored_task_id") is not None, f"Call feedback did not create monitored task: {fb}"
            assert "whatsapp_notified" in fb, f"whatsapp_notified key missing: {fb}"
        finally:
            meta_whatsapp.transcribe_audio_bytes = orig_tr
            meta_whatsapp.DB = orig_wa_db
            gc.collect()
            _set_temp_db_across_modules(ISO_DB_PATH)

    return "WhatsApp approve_and_send_reply + audio transcription, Telegram voice transcription, and call monitored-task creation verified"


def test_r7_camera_cv_counts_repeats_and_behavior():
    import cv2
    import numpy as np
    import camera_cv_engine

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        cv_db = os.path.join(tmp, "r7_cv.db")
        # Build a clean synthetic BGR frame with a distinct red-shirt person region and a blue-car region
        frame = np.full((240, 320, 3), 210, dtype=np.uint8)
        frame[40:180, 30:100] = (30, 35, 210)   # red-ish person crop (BGR)
        frame[120:210, 160:290] = (200, 60, 30)  # blue-ish car crop (BGR)
        frame[180:225, 110:150] = (40, 160, 40)  # green-ish backpack object crop (BGR)

        dets = [
            {"label": "person", "category": "person", "confidence": 0.92, "bbox": [30, 40, 100, 180]},
            {"label": "car", "category": "vehicle", "confidence": 0.89, "bbox": [160, 120, 290, 210]},
            {"label": "backpack", "category": "object", "confidence": 0.81, "bbox": [110, 180, 150, 225]},
        ]

        # Visit 1 on CAM-MUELLE-1 at 10:00
        ts1 = 1795705200.0
        r1 = camera_cv_engine.analyze_frame(
            frame, camera_id="CAM-MUELLE-1", site="espacios", zone="Muelle 1",
            timestamp=ts1, db_path=cv_db, prebuilt_detections=dets,
        )
        assert r1["ok"] and r1["counts"]["people"] == 1 and r1["counts"]["vehicles"] == 1 and r1["counts"]["objects"] == 1

        # Visit 2 on CAM-MUELLE-2 10 minutes later -> must detect BOTH repeat person & repeat car!
        r2 = camera_cv_engine.analyze_frame(
            frame, camera_id="CAM-MUELLE-2", site="espacios", zone="Muelle 2",
            timestamp=ts1 + 600.0, db_path=cv_db, prebuilt_detections=dets,
        )
        assert r2["ok"] and r2["counts"]["repeat_people"] == 1 and r2["counts"]["repeat_vehicles"] == 1, f"Repeat detection failed: {r2}"
        ev_types = {b["event_type"] for b in r2["behaviors"]}
        assert "repeat_person" in ev_types and "repeat_vehicle" in ev_types, f"Expected repeat behavior alerts, got {ev_types}"

        # Verify CEO Deep Report aggregates counts, repeat entities, and behavior alerts deterministically
        rep = camera_cv_engine.build_ceo_deep_report(day=r1["day"], site="espacios", db_path=cv_db)
        assert rep["ok"] and rep["provenance"] == "live_cv_measured"
        assert rep["counts"]["frames_analyzed"] == 2
        assert rep["counts"]["repeat_people_entities"] >= 1 and rep["counts"]["repeat_vehicle_entities"] >= 1
        assert len(rep["behavior_alerts"]) >= 2

    return "YOLO11/OpenCV CV engine: counts (people/cars/objects), cross-camera repeat Re-ID, behavior alerts & CEO deep report verified"


def main():
    live_db = os.path.join(REPO_ROOT, "data", "mc.db")
    live_onb = os.path.join(REPO_ROOT, "data", "onboarding_state.json")
    db_sha_before = _sha256_if_exists(live_db)
    onb_sha_before = _sha256_if_exists(live_onb)

    tests = [
        ("Syntax Compile (All Modules)", test_syntax_compile_all),
        ("No Hardcoded Telegram Tokens", test_no_hardcoded_telegram_tokens),
        ("Voice Calls Fixes (Isolated)", test_voice_calls_fixes),
        ("Comms Brain Subject & Email", test_comms_brain_subject_and_honest_email),
        ("Email Gatekeeper Classifier", test_google_workspace_gatekeeper),
        ("Unified Life OS End-to-End", test_unified_life_os_end_to_end),
        ("R1 Branding, Jefesito & Limestone Contrast", test_r1_jefesito_and_demo_html_branding_contrast),
        ("R2 Workspace Tabs & Race Guards", test_r2_workspace_tabs_and_race_guards),
        ("R3 Copilot NLU, Contact Resolution & Voice Mic", test_r3_copilot_nlu_voice_and_no_spurious_dev),
        ("R4 Camera Non-Gated Analytics & Provenance", test_r4_camera_non_gated_and_provenance),
        ("R5 Repo Portability & Live DB Safety", test_r5_repo_portability_and_live_safety),
        ("R6 WhatsApp/Telegram Voice & Call Monitoring", test_r6_whatsapp_telegram_voice_and_call_monitoring),
        ("R7 Open-Source Camera CV, Repeat Re-ID & Behavior", test_r7_camera_cv_counts_repeats_and_behavior),
    ]
    failed = 0
    for name, fn in tests:
        try:
            msg = fn()
            print(f"[PASS] {name}: {msg}")
        except Exception as exc:
            failed += 1
            print(f"[FAIL] {name}: {exc}")
            traceback.print_exc()

    db_sha_after = _sha256_if_exists(live_db)
    onb_sha_after = _sha256_if_exists(live_onb)
    if db_sha_before != db_sha_after:
        failed += 1
        print(f"[FAIL] Live data/mc.db mutated! {db_sha_before} != {db_sha_after}")
    if onb_sha_before != onb_sha_after:
        failed += 1
        print(f"[FAIL] Live data/onboarding_state.json mutated! {onb_sha_before} != {onb_sha_after}")

    print(f"\nSummary: {len(tests) - failed if failed <= len(tests) else 0}/{len(tests)} passed.")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
