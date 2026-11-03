"""Official Meta WhatsApp Cloud API & Selective Chat/Group Monitor (`server/text_messaging.py`).

Replaces third-party unofficial bridges (Green API removed) with:
  1. Official Meta WhatsApp Cloud API (`https://graph.facebook.com/v21.0/{PHONE_NUMBER_ID}/messages`)
     — zero ban risk, Meta-verified webhook (`GET / POST /api/whatsapp/webhook`),
     compatible with WhatsApp Business App Coexistence.
  2. Selective Contact & Group Watchlist (`whatsapp_watchlist` table):
     — Jasmel chooses exactly which 1:1 contacts or group chats to monitor.
  3. Unified Auto-Draft + Auto-Task Pipeline:
     — When a watched contact or group sends a message, Mission Control automatically:
       a) Classifies & scores urgency,
       b) Extracts and creates a tracked Task in `mc.db` (`knowledge_store.add_task`),
       c) Pre-drafts a reply in Jasmel Acosta's voice ready for 1-click Approve & Send.
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import time
import urllib.request
from typing import Any

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DB = os.environ.get("MC_DB_PATH") or os.path.join(ROOT, "data", "mc.db")
os.makedirs(os.path.dirname(DB), exist_ok=True)

SCHEMA = """
CREATE TABLE IF NOT EXISTS text_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company TEXT DEFAULT 'personal', -- 'aidyn', 'mbmb', 'jmm', '305biz', 'personal'
    channel TEXT DEFAULT 'whatsapp', -- 'whatsapp', 'sms', 'telegram'
    direction TEXT DEFAULT 'in',     -- 'in', 'out'
    contact_name TEXT,
    contact_phone TEXT,
    chat_type TEXT DEFAULT 'contact', -- 'contact' or 'group'
    message_text TEXT NOT NULL,
    ai_draft_reply TEXT,
    linked_task_id TEXT DEFAULT '',
    linked_task_title TEXT DEFAULT '',
    status TEXT DEFAULT 'unread',    -- 'unread', 'read', 'drafted', 'replied', 'sent'
    ts REAL
);

CREATE TABLE IF NOT EXISTS whatsapp_watchlist (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    label TEXT NOT NULL,
    identifier TEXT NOT NULL UNIQUE,
    chat_type TEXT DEFAULT 'contact', -- 'contact' or 'group'
    company TEXT DEFAULT 'aidyn',
    monitored INTEGER DEFAULT 1,
    auto_draft INTEGER DEFAULT 1,
    auto_task INTEGER DEFAULT 1,
    notes TEXT DEFAULT '',
    created_at REAL
);
"""

DEFAULT_WATCHLIST = [
    {
        "label": "AI Dynamics · Core Dev & Voice Swarm Group",
        "identifier": "grp-aidyn-swarm",
        "chat_type": "group",
        "company": "building",
        "monitored": 1,
        "auto_draft": 1,
        "auto_task": 1,
        "notes": "Carlos Dev + AI Engineers — production deploys & client voice bots",
    },
    {
        "label": "MBMB · Claims, Denials & Appeals Group",
        "identifier": "grp-mbmb-rcm",
        "chat_type": "group",
        "company": "unitec",
        "monitored": 1,
        "auto_draft": 1,
        "auto_task": 1,
        "notes": "Medical Billing Miami Beach senior coders & legal PIP bill team",
    },
    {
        "label": "Dr. Molina (Doral Urgent Care)",
        "identifier": "+1 (305) 555-0199",
        "chat_type": "contact",
        "company": "unitec",
        "monitored": 1,
        "auto_draft": 1,
        "auto_task": 1,
        "notes": "VIP medical billing & AI front-desk client",
    },
    {
        "label": "Atty. Roberto Fernandez (PIP & Legal Billing)",
        "identifier": "+1 (786) 555-0184",
        "chat_type": "contact",
        "company": "unitec",
        "monitored": 1,
        "auto_draft": 1,
        "auto_task": 1,
        "notes": "Legal medical bill organization & settlement disbursements",
    },
    {
        "label": "JasMiamiMethod · HYROX & Triathlon Squad Group",
        "identifier": "grp-jmm-athletes",
        "chat_type": "group",
        "company": "saleinn",
        "monitored": 1,
        "auto_draft": 1,
        "auto_task": 1,
        "notes": "Athlete check-ins, race prep & Garmin/Intervals sync alerts",
    },
    {
        "label": "305 Business LLC · Buyers & Brokers Group",
        "identifier": "grp-305biz-deals",
        "chat_type": "group",
        "company": "espacios",
        "monitored": 1,
        "auto_draft": 1,
        "auto_task": 1,
        "notes": "Miami business marketplace inquiries, NDAs & LOIs",
    },
]

DEFAULT_TEXTS = [
    {
        "company": "building",
        "channel": "whatsapp",
        "direction": "in",
        "contact_name": "AI Dynamics · Core Dev & Voice Swarm Group (Carlos)",
        "contact_phone": "grp-aidyn-swarm",
        "chat_type": "group",
        "message_text": "Jasmel, the v2 voice agent deployment is finished on Railway. Latency is under 420ms. Should we flip traffic to production for Doral Urgent?",
        "ai_draft_reply": "Excelente Carlos. La latencia bajo 420ms está perfecta. Pasemos el 50% del tráfico primero, corramos 3 llamadas de prueba y subimos al 100%.",
        "linked_task_id": "T-WA-01",
        "linked_task_title": "Autorizar paso a producción 100% del agente de voz v2 en Doral Urgent",
        "status": "unread",
    },
    {
        "company": "unitec",
        "channel": "whatsapp",
        "direction": "in",
        "contact_name": "MBMB · Claims, Denials & Appeals Group",
        "contact_phone": "grp-mbmb-rcm",
        "chat_type": "group",
        "message_text": "Jasmel, subimos las 42 apelaciones denegadas de Aetna ($38,500) y el paquete legal de PIP de Brickell Ortho. ¿Confirmas envío hoy antes de las 3 PM?",
        "ai_draft_reply": "Confirmado equipo. Prioricen el envío formal de las 42 apelaciones de Aetna antes de las 3:00 PM y pásenme el acuse de recibo.",
        "linked_task_id": "T-WA-02",
        "linked_task_title": "Supervisar envío de 42 apelaciones Aetna ($38.5k) en MBMB antes de las 3 PM",
        "status": "unread",
    },
    {
        "company": "unitec",
        "channel": "whatsapp",
        "direction": "in",
        "contact_name": "Atty. Roberto Fernandez (PIP Claims)",
        "contact_phone": "+1 (786) 555-0184",
        "chat_type": "contact",
        "message_text": "Jasmel, settlement check for the Brickell Ortho PIP case came in ($18,400). Sending the disbursement sheet for your signature.",
        "ai_draft_reply": "Understood Roberto. Send the DocuSign to jasmel@medicalbillingmb.com and I will review and sign within the hour.",
        "linked_task_id": "T-WA-03",
        "linked_task_title": "Firmar hoja de desembolso PIP Brickell Ortho ($18,400) de Atty. Roberto Fernandez",
        "status": "unread",
    },
    {
        "company": "saleinn",
        "channel": "whatsapp",
        "direction": "in",
        "contact_name": "JasMiamiMethod · HYROX & Triathlon Squad Group",
        "contact_phone": "grp-jmm-athletes",
        "chat_type": "group",
        "message_text": "Coach Jasmel! 6 athletes completed the threshold brick session this morning. Do we keep Saturday's 6:00 AM Key Biscayne ride at Zone 3 tempo?",
        "ai_draft_reply": "Great work squad! Yes, Saturday 6:00 AM Key Biscayne ride stays at steady Zone 3 tempo. Hydrate well tonight.",
        "linked_task_id": "T-WA-04",
        "linked_task_title": "Publicar plan de ciclismo sábado 6:00 AM Key Biscayne en JasMiamiMethod",
        "status": "unread",
    },
    {
        "company": "espacios",
        "channel": "whatsapp",
        "direction": "in",
        "contact_name": "305 Business LLC · Buyers & Brokers Group",
        "contact_phone": "grp-305biz-deals",
        "chat_type": "group",
        "message_text": "Jasmel, el comprador calificado para la clínica estética en Coral Gables firmó el NDA y pide agendar llamada de revisión de EBITDA mañana a las 2 PM.",
        "ai_draft_reply": "Perfecto. Agendemos la revisión de EBITDA para mañana a las 2:00 PM y compartan el dataroom financiero preliminar.",
        "linked_task_id": "T-WA-05",
        "linked_task_title": "Llamada revisión EBITDA clínica Coral Gables (305business.llc) mañana 2 PM",
        "status": "unread",
    },
]


def _db():
    c = sqlite3.connect(DB, timeout=30.0)
    c.row_factory = sqlite3.Row
    c.executescript(SCHEMA)
    # Migrate existing table if missing new columns
    cols = {r["name"] for r in c.execute("PRAGMA table_info(text_messages)").fetchall()}
    if "chat_type" not in cols:
        c.execute("ALTER TABLE text_messages ADD COLUMN chat_type TEXT DEFAULT 'contact'")
    if "linked_task_id" not in cols:
        c.execute("ALTER TABLE text_messages ADD COLUMN linked_task_id TEXT DEFAULT ''")
    if "linked_task_title" not in cols:
        c.execute("ALTER TABLE text_messages ADD COLUMN linked_task_title TEXT DEFAULT ''")
    c.commit()
    return c


def ensure_seeded():
    c = _db()
    w_cnt = c.execute("SELECT COUNT(*) FROM whatsapp_watchlist").fetchone()[0]
    if w_cnt == 0:
        now = time.time()
        for w in DEFAULT_WATCHLIST:
            c.execute(
                """INSERT OR IGNORE INTO whatsapp_watchlist
                   (label, identifier, chat_type, company, monitored, auto_draft, auto_task, notes, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    w["label"],
                    w["identifier"],
                    w["chat_type"],
                    w["company"],
                    w["monitored"],
                    w["auto_draft"],
                    w["auto_task"],
                    w["notes"],
                    now,
                ),
            )
        c.commit()

    cnt = c.execute("SELECT COUNT(*) FROM text_messages").fetchone()[0]
    if cnt == 0:
        now = time.time()
        for idx, t in enumerate(DEFAULT_TEXTS):
            ts = now - (idx * 1800)
            c.execute(
                """INSERT INTO text_messages
                   (company, channel, direction, contact_name, contact_phone, chat_type,
                    message_text, ai_draft_reply, linked_task_id, linked_task_title, status, ts)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    t["company"],
                    t["channel"],
                    t["direction"],
                    t["contact_name"],
                    t["contact_phone"],
                    t.get("chat_type", "contact"),
                    t["message_text"],
                    t["ai_draft_reply"],
                    t.get("linked_task_id", ""),
                    t.get("linked_task_title", ""),
                    t["status"],
                    ts,
                ),
            )
        c.commit()
    c.close()


def _load_env_map() -> dict[str, str]:
    env = dict(os.environ)
    env_p = os.path.join(ROOT, ".env")
    if os.path.isfile(env_p):
        for line in open(env_p, encoding="utf-8", errors="ignore"):
            s = line.strip()
            if s and not s.startswith("#") and "=" in s:
                k, v = s.split("=", 1)
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                if k and v and k not in env:
                    env[k] = v
    return env


def get_meta_status() -> dict[str, Any]:
    """Return Official Meta WhatsApp Cloud API connection status & webhook URL."""
    env = _load_env_map()
    token = env.get("META_WA_ACCESS_TOKEN", "").strip()
    phone_id = env.get("META_WA_PHONE_NUMBER_ID", "").strip()
    waba_id = env.get("META_WA_BUSINESS_ACCOUNT_ID", "").strip()
    verify_tok = env.get("META_WA_VERIFY_TOKEN", "jasmel_ceo_meta_verify_2026").strip()
    configured = bool(token and phone_id)
    return {
        "provider": "meta_cloud_api_v21",
        "green_api_removed": True,
        "configured": configured,
        "has_access_token": bool(token),
        "has_phone_number_id": bool(phone_id),
        "has_waba_id": bool(waba_id),
        "phone_number_id_preview": (phone_id[:6] + "…") if len(phone_id) > 6 else phone_id,
        "webhook_callback_path": "/api/whatsapp/webhook",
        "webhook_verify_token": verify_tok,
        "portal_url": "https://developers.facebook.com/apps/",
    }


def _dispatch_via_meta_cloud_api(to_phone_or_id: str, message: str) -> dict[str, Any]:
    """Send WhatsApp message via Official Meta Graph API v21.0 (`graph.facebook.com`)."""
    env = _load_env_map()
    token = env.get("META_WA_ACCESS_TOKEN", "").strip()
    phone_id = env.get("META_WA_PHONE_NUMBER_ID", "").strip()
    if not (token and phone_id):
        return {
            "provider": "meta_cloud_api_sandbox",
            "delivered": False,
            "reason": "META_WA_ACCESS_TOKEN or META_WA_PHONE_NUMBER_ID not yet set in Vault (.env)",
        }

    digits = re.sub(r"\D+", "", to_phone_or_id or "")
    if len(digits) == 10:
        digits = "1" + digits
    if not digits:
        return {
            "provider": "meta_cloud_api",
            "delivered": False,
            "reason": "Group/thread reply logged in Mission Control (use recipient E.164 phone for direct Graph API push)",
        }

    url = f"https://graph.facebook.com/v21.0/{phone_id}/messages"
    payload = json.dumps(
        {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": digits,
            "type": "text",
            "text": {"preview_url": True, "body": message},
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            resp = json.loads(r.read().decode("utf-8"))
        msg_id = ((resp.get("messages") or [{}])[0]).get("id", "")
        return {"provider": "meta_cloud_api_v21", "delivered": True, "wamid": msg_id}
    except Exception as e:
        return {"provider": "meta_cloud_api_v21", "delivered": False, "error": str(e)}


def list_watchlist() -> list[dict[str, Any]]:
    ensure_seeded()
    c = _db()
    rows = c.execute("SELECT * FROM whatsapp_watchlist ORDER BY monitored DESC, id ASC").fetchall()
    out = [dict(r) for r in rows]
    c.close()
    return out


def add_watchlist_item(
    label: str,
    identifier: str,
    chat_type: str = "contact",
    company: str = "aidyn",
    auto_draft: int = 1,
    auto_task: int = 1,
    notes: str = "",
) -> dict[str, Any]:
    ensure_seeded()
    label = (label or "").strip()
    identifier = (identifier or "").strip()
    if not label or not identifier:
        return {"ok": False, "error": "label and identifier are required"}
    c = _db()
    c.execute(
        """INSERT OR REPLACE INTO whatsapp_watchlist
           (label, identifier, chat_type, company, monitored, auto_draft, auto_task, notes, created_at)
           VALUES (?, ?, ?, ?, 1, ?, ?, ?, ?)""",
        (label, identifier, chat_type, company, int(bool(auto_draft)), int(bool(auto_task)), notes, time.time()),
    )
    c.commit()
    c.close()
    return {"ok": True, "watchlist": list_watchlist()}


def toggle_watchlist_item(item_id: int, field: str = "monitored") -> dict[str, Any]:
    ensure_seeded()
    if field not in ("monitored", "auto_draft", "auto_task"):
        field = "monitored"
    c = _db()
    row = c.execute("SELECT * FROM whatsapp_watchlist WHERE id=?", (int(item_id),)).fetchone()
    if not row:
        c.close()
        return {"ok": False, "error": "Watchlist item not found"}
    new_val = 0 if row[field] else 1
    c.execute(f"UPDATE whatsapp_watchlist SET {field}=? WHERE id=?", (new_val, int(item_id)))
    c.commit()
    c.close()
    return {"ok": True, "id": item_id, "field": field, "value": new_val, "watchlist": list_watchlist()}


def delete_watchlist_item(item_id: int) -> dict[str, Any]:
    ensure_seeded()
    c = _db()
    c.execute("DELETE FROM whatsapp_watchlist WHERE id=?", (int(item_id),))
    c.commit()
    c.close()
    return {"ok": True, "watchlist": list_watchlist()}


def _generate_draft_and_task(
    sender_name: str,
    message_text: str,
    company: str,
    chat_type: str,
) -> dict[str, str]:
    """Use Gemini 3.8 Flash to compose Jasmel's executive reply AND extract a concrete task."""
    env = _load_env_map()
    gemini_key = env.get("GEMINI_API_KEY", "").strip()
    fallback_draft = (
        f"Recibido {sender_name.split()[0]}. Ya lo tengo en el radar de {company.upper()} "
        "y te confirmo el siguiente paso hoy mismo. — Jasmel"
    )
    fallback_task = f"[{company.upper()}] Dar seguimiento a {sender_name}: {message_text[:65]}"
    if not gemini_key:
        return {"draft_reply": fallback_draft, "task_title": fallback_task, "severity": "high"}

    prompt = (
        "You are El Jefesito, executive AI assistant for CEO Jasmel Acosta.\n"
        f"Company context: {company.upper()} (aidyn=AI Dynamics Pro, mbmb=Medical Billing Miami Beach, "
        "jmm=JasMiamiMethod Coaching, 305biz=305 Business LLC, personal=Personal).\n"
        f"Chat type: {chat_type} | Sender: {sender_name}\n"
        f"Incoming WhatsApp message:\n\"{message_text}\"\n\n"
        "Return strictly JSON with:\n"
        '1. "draft_reply": A crisp, natural WhatsApp reply in the SAME language (Spanish or English) as the incoming message, '
        "written in Jasmel Acosta's decisive, warm executive voice (1-2 sentences max).\n"
        '2. "task_title": A concrete action item / task title (max 14 words) to track in Mission Control.\n'
        '3. "severity": "critical" | "high" | "medium"'
    )
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash-lite:generateContent?key={gemini_key}"
    body = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 900,
            "responseMimeType": "application/json",
        },
    }
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
        txt = ""
        for p in (raw.get("candidates") or [{}])[0].get("content", {}).get("parts", []):
            if "text" in p and not p.get("thought", False):
                txt += p["text"]
        parsed = json.loads(txt) if txt else {}
        return {
            "draft_reply": parsed.get("draft_reply") or fallback_draft,
            "task_title": parsed.get("task_title") or fallback_task,
            "severity": parsed.get("severity") or "high",
        }
    except Exception:
        return {"draft_reply": fallback_draft, "task_title": fallback_task, "severity": "high"}


def process_monitored_inbound(
    identifier: str,
    sender_name: str,
    message_text: str,
    company_override: str | None = None,
    chat_type_override: str | None = None,
) -> dict[str, Any]:
    """Check if sender/group is on Jasmel's monitored watchlist; if so, auto-draft reply & create task."""
    import knowledge_store

    ensure_seeded()
    c = _db()
    rows = c.execute("SELECT * FROM whatsapp_watchlist").fetchall()
    norm_in = re.sub(r"\D+", "", identifier or "")

    matched = None
    for r in rows:
        w = dict(r)
        w_norm = re.sub(r"\D+", "", w["identifier"] or "")
        if w["identifier"].lower() == (identifier or "").lower() or (norm_in and w_norm and norm_in[-10:] == w_norm[-10:]):
            matched = w
            break

    if matched and not matched.get("monitored"):
        c.close()
        return {
            "ok": True,
            "ignored": True,
            "reason": f"Chat '{matched['label']}' is currently paused (monitored=0) in your Watchlist.",
        }

    company = company_override or (matched["company"] if matched else "personal")
    chat_type = chat_type_override or (matched["chat_type"] if matched else "contact")
    display_name = matched["label"] if (matched and chat_type == "group") else (sender_name or (matched["label"] if matched else identifier))
    do_draft = bool(matched["auto_draft"]) if matched else True
    do_task = bool(matched["auto_task"]) if matched else True

    ai_out = _generate_draft_and_task(display_name, message_text, company, chat_type)
    draft_reply = ai_out["draft_reply"] if do_draft else ""
    linked_task_id = ""
    linked_task_title = ""

    if do_task and ai_out.get("task_title"):
        linked_task_title = ai_out["task_title"]
        tk = knowledge_store.add_task(
            linked_task_title,
            company=company,
            owner="Jasmel Acosta",
            due="Hoy",
            severity=ai_out.get("severity", "high"),
            source="meta_whatsapp_monitor",
        )
        linked_task_id = str(tk.get("id", "TASK"))

    cursor = c.execute(
        """INSERT INTO text_messages
           (company, channel, direction, contact_name, contact_phone, chat_type,
            message_text, ai_draft_reply, linked_task_id, linked_task_title, status, ts)
           VALUES (?, 'whatsapp', 'in', ?, ?, ?, ?, ?, ?, ?, 'unread', ?)""",
        (
            company,
            display_name,
            identifier,
            chat_type,
            message_text,
            draft_reply,
            linked_task_id,
            linked_task_title,
            time.time(),
        ),
    )
    msg_id = cursor.lastrowid
    c.commit()
    c.close()

    return {
        "ok": True,
        "message_id": msg_id,
        "company": company,
        "chat_type": chat_type,
        "contact_name": display_name,
        "contact_phone": identifier,
        "message_text": message_text,
        "ai_draft_reply": draft_reply,
        "linked_task_id": linked_task_id,
        "linked_task_title": linked_task_title,
    }


def verify_meta_webhook(qs: dict[str, list[str]]) -> tuple[int, str]:
    """Handle Meta Graph API `GET /api/whatsapp/webhook` verification challenge."""
    env = _load_env_map()
    expected = env.get("META_WA_VERIFY_TOKEN", "jasmel_ceo_meta_verify_2026").strip()
    mode = (qs.get("hub.mode") or [""])[0]
    token = (qs.get("hub.verify_token") or [""])[0]
    challenge = (qs.get("hub.challenge") or [""])[0]
    if mode == "subscribe" and token == expected:
        return 200, challenge
    return 403, "verification_failed"


def ingest_meta_webhook(payload: dict[str, Any]) -> dict[str, Any]:
    """Process real Meta WhatsApp Cloud API `POST /api/whatsapp/webhook` events."""
    processed = []
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            val = change.get("value", {})
            contacts = {c.get("wa_id"): (c.get("profile") or {}).get("name", "") for c in val.get("contacts", [])}
            for msg in val.get("messages", []):
                from_id = msg.get("from", "")
                group_id = msg.get("group_id") or (msg.get("context") or {}).get("group_id")
                identifier = group_id or from_id
                chat_type = "group" if group_id else "contact"
                sender_name = contacts.get(from_id) or from_id
                text_body = ""
                if msg.get("type") == "text":
                    text_body = (msg.get("text") or {}).get("body", "")
                elif msg.get("type") in ("image", "document", "audio"):
                    caption = (msg.get(msg["type"]) or {}).get("caption", "")
                    text_body = f"[{msg['type'].upper()} ADJUNTO] {caption}".strip()
                if text_body:
                    res = process_monitored_inbound(
                        identifier=identifier,
                        sender_name=sender_name,
                        message_text=text_body,
                        chat_type_override=chat_type,
                    )
                    processed.append(res)
    return {"ok": True, "processed_count": len(processed), "items": processed}


def list_messages(company=None, channel=None):
    ensure_seeded()
    c = _db()
    query = "SELECT * FROM text_messages WHERE 1=1"
    params = []
    if company and company != "all":
        query += " AND company=?"
        params.append(company)
    if channel:
        query += " AND channel=?"
        params.append(channel)
    query += " ORDER BY ts DESC LIMIT 50"
    rows = c.execute(query, params).fetchall()
    msgs = [dict(r) for r in rows]
    c.close()
    return msgs


def send_text_message(
    to_phone, message, company="personal", channel="whatsapp", contact_name=""
):
    """Send text/WhatsApp message out via Official Meta Cloud API and record in log."""
    ensure_seeded()
    c = _db()
    now = time.time()
    cursor = c.execute(
        """INSERT INTO text_messages
           (company, channel, direction, contact_name, contact_phone, message_text, ai_draft_reply, status, ts)
           VALUES (?, ?, 'out', ?, ?, ?, '', 'sent', ?)""",
        (
            company,
            channel,
            contact_name or to_phone,
            to_phone,
            message,
            now,
        ),
    )
    new_id = cursor.lastrowid
    c.commit()
    c.close()
    gw = _dispatch_via_meta_cloud_api(to_phone, message) if channel in ("whatsapp", "sms") else {}
    return {
        "ok": True,
        "id": new_id,
        "gateway": gw,
        "status": "sent",
        "to": to_phone,
        "msg": message,
        "company": company,
    }


def approve_text_draft(message_id):
    """Approve pre-drafted reply, dispatch via Official Meta Cloud API, and mark as sent."""
    c = _db()
    row = c.execute(
        "SELECT * FROM text_messages WHERE id=?", (int(message_id),)
    ).fetchone()
    if not row:
        c.close()
        return {"error": "Message not found"}

    m = dict(row)
    draft_reply = m.get("ai_draft_reply", "")
    if not draft_reply:
        c.close()
        return {"error": "No draft reply to approve"}

    now = time.time()
    c.execute(
        "UPDATE text_messages SET status='replied' WHERE id=?",
        (int(message_id),),
    )
    c.execute(
        """INSERT INTO text_messages
           (company, channel, direction, contact_name, contact_phone, chat_type, message_text, status, ts)
           VALUES (?, ?, 'out', ?, ?, ?, ?, 'sent', ?)""",
        (
            m["company"],
            m["channel"],
            m["contact_name"],
            m["contact_phone"],
            m.get("chat_type", "contact"),
            draft_reply,
            now,
        ),
    )
    c.commit()
    c.close()

    gw = _dispatch_via_meta_cloud_api(m["contact_phone"], draft_reply)
    return {
        "ok": True,
        "replied_to_id": message_id,
        "reply_text": draft_reply,
        "gateway": gw,
    }


def update_text_draft(message_id, new_draft_text):
    c = _db()
    c.execute(
        "UPDATE text_messages SET ai_draft_reply=? WHERE id=?",
        (new_draft_text, int(message_id)),
    )
    c.commit()
    c.close()
    return {"ok": True}
