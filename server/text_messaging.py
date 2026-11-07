"""Official Telegram & Text Messaging Hub (`server/text_messaging.py`).

WhatsApp has been completely removed per CEO directive.
All text and instant messaging operations run exclusively through:
  1. Official Telegram Bot API (`@Pegantebot` Chat 8897658040 & `@ceojefesitobot` Chat 7838956683)
     and SMS/Text channels (`telegram` / `sms`).
  2. Selective Contact & Group Watchlist (`telegram_watchlist` / `whatsapp_watchlist` table):
     — Tracks Telegram groups, channels, and direct executive contacts across
       UNITEC USA, Building Innovation, Espacios Importados, BuildingApp, and Saleinn.
  3. Unified Auto-Draft + Voice Delegation + Auto-Task Pipeline:
     — Incoming texts/Telegram messages automatically receive a pre-drafted reply in CEO
       Juan David García Montoya's voice (`Mode C` — Edit, Review, or 1-Click Approve & Send).
     — Outgoing voice/text delegations ("Go to Telegram and send a message to all asking what
       happened with the new products") are drafted and queued for CEO approval or sent live.
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
    company TEXT DEFAULT 'espacios_importados',
    channel TEXT DEFAULT 'telegram', -- 'telegram', 'sms'
    direction TEXT DEFAULT 'in',     -- 'in', 'out'
    contact_name TEXT,
    contact_phone TEXT,
    chat_type TEXT DEFAULT 'group',  -- 'contact' or 'group'
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
    chat_type TEXT DEFAULT 'group',
    company TEXT DEFAULT 'espacios_importados',
    monitored INTEGER DEFAULT 1,
    auto_draft INTEGER DEFAULT 1,
    auto_task INTEGER DEFAULT 1,
    notes TEXT DEFAULT '',
    created_at REAL
);
"""

DEFAULT_WATCHLIST = [
    {
        "label": "Telegram · Grupo General Nuevos Productos & Importaciones (@Pegantebot)",
        "identifier": "8897658040",
        "chat_type": "group",
        "company": "espacios_importados",
        "monitored": 1,
        "auto_draft": 1,
        "auto_task": 1,
        "notes": "Canal principal Telegram de dirección, bodega Muelle 1 y seguimiento de nuevos productos",
    },
    {
        "label": "Telegram · UNITEC USA · Miami Design District & Ventas WPC",
        "identifier": "tg-unitec-miami",
        "chat_type": "group",
        "company": "unitec_usa",
        "monitored": 1,
        "auto_draft": 1,
        "auto_task": 1,
        "notes": "Equipo comercial Miami, inventario WPC Exterior y despachos Florida",
    },
    {
        "label": "Telegram · Building Innovation · Proyectos & Arquitectos",
        "identifier": "tg-building-innovation",
        "chat_type": "group",
        "company": "building_innovation",
        "monitored": 1,
        "auto_draft": 1,
        "auto_task": 1,
        "notes": "Especificación arquitectónica, cotizaciones B2B y muestras",
    },
    {
        "label": "Carlos Méndez (Logística Aduanas & Contenedores Muelle 1)",
        "identifier": "+573104458920",
        "chat_type": "contact",
        "company": "espacios_importados",
        "monitored": 1,
        "auto_draft": 1,
        "auto_task": 1,
        "notes": "Liberación DIAN, contenedores WPC/PVC y descargue en bodega",
    },
    {
        "label": "Roberto Silva (Director Comercial Miami — UNITEC USA)",
        "identifier": "+13058904412",
        "chat_type": "contact",
        "company": "unitec_usa",
        "monitored": 1,
        "auto_draft": 1,
        "auto_task": 1,
        "notes": "Cierres mayoristas WPC Miami, proformas y entregas Brickell",
    },
    {
        "label": "Telegram · Directivo CEO Alertas (@ceojefesitobot)",
        "identifier": "7838956683",
        "chat_type": "contact",
        "company": "buildingapp",
        "monitored": 1,
        "auto_draft": 1,
        "auto_task": 1,
        "notes": "Canal directo ejecutivo CEO Juan David García Montoya",
    },
]

DEFAULT_TEXTS = [
    {
        "company": "espacios_importados",
        "channel": "telegram",
        "direction": "in",
        "contact_name": "Telegram · Grupo Nuevos Productos & Bodega (Diana Sofía)",
        "contact_phone": "8897658040",
        "chat_type": "group",
        "message_text": "Jefe Juan David, ya ingresaron las 18 referencias de los nuevos productos WPC y Lambrines Acústicos al sistema, pero faltan las fotos de showroom y validar precios de lista mayorista.",
        "ai_draft_reply": "Equipo, por favor infórmenme qué pasó exactamente con las fotos y la lista de precios de los nuevos productos. Necesito el catálogo mayorista validado hoy antes de las 4:00 PM sin falta. — Juan David",
        "linked_task_id": "T-TG-01",
        "linked_task_title": "Validar catálogo y precios mayoristas de las 18 referencias de nuevos productos WPC",
        "status": "drafted",
    },
    {
        "company": "unitec_usa",
        "channel": "telegram",
        "direction": "in",
        "contact_name": "Roberto Silva · Telegram UNITEC USA Miami",
        "contact_phone": "+13058904412",
        "chat_type": "contact",
        "message_text": "Juan David, el grupo constructor de Brickell pregunta si podemos despachar las muestras de la nueva línea WPC Exterior mañana mismo y confirmar stock de 1,400 m².",
        "ai_draft_reply": "Hola Roberto, confirmado el bloqueo de los 1,400 m² de WPC Exterior. Despachen las muestras a Brickell primera hora mañana y envíame el guía de tracking por Telegram. — Juan David",
        "linked_task_id": "T-TG-02",
        "linked_task_title": "Despachar muestras WPC Exterior a Brickell y confirmar guía en Telegram",
        "status": "drafted",
    },
    {
        "company": "building_innovation",
        "channel": "telegram",
        "direction": "in",
        "contact_name": "Andrés Gómez · Telegram Building Innovation",
        "contact_phone": "tg-building-innovation",
        "chat_type": "group",
        "message_text": "CEO, cerramos especificación con 3 firmas de arquitectura en Medellín. Piden autorización de descuento del 6% por volumen pago de contado.",
        "ai_draft_reply": "Andrés, autorizado el 6% de descuento únicamente para pago 100% de contado antes del viernes. Emitan las órdenes de pedido hoy mismo. — Juan David",
        "linked_task_id": "T-TG-03",
        "linked_task_title": "Auditar recaudo de contado con 6% descuento en 3 firmas de arquitectura",
        "status": "drafted",
    },
    {
        "company": "espacios_importados",
        "channel": "telegram",
        "direction": "in",
        "contact_name": "Carlos Méndez · Aduanas & Muelle 1",
        "contact_phone": "+573104458920",
        "chat_type": "contact",
        "message_text": "Juan David, contenedor liberado en puerto. Mañana 7:30 AM entra a Muelle 1 con el lote nuevo de paneles.",
        "ai_draft_reply": "Excelente Carlos. Ya ordené cuadrilla completa en Muelle 1 a las 7:00 AM y monitoreo activo por cámaras Vigilant Mode. Avísame apenas rompan precinto. — Juan David",
        "linked_task_id": "T-TG-04",
        "linked_task_title": "Supervisar descargue de contenedor mañana 7:30 AM en Muelle 1",
        "status": "drafted",
    },
]


def _db(db_path: str | None = None):
    target = str(db_path or DB)
    c = sqlite3.connect(target, timeout=30.0)
    c.row_factory = sqlite3.Row
    c.executescript(SCHEMA)
    cols = {r["name"] for r in c.execute("PRAGMA table_info(text_messages)").fetchall()}
    if "chat_type" not in cols:
        c.execute("ALTER TABLE text_messages ADD COLUMN chat_type TEXT DEFAULT 'group'")
    if "linked_task_id" not in cols:
        c.execute("ALTER TABLE text_messages ADD COLUMN linked_task_id TEXT DEFAULT ''")
    if "linked_task_title" not in cols:
        c.execute("ALTER TABLE text_messages ADD COLUMN linked_task_title TEXT DEFAULT ''")
    # Migrate any legacy 'whatsapp' channel values to 'telegram'
    c.execute("UPDATE text_messages SET channel='telegram' WHERE channel='whatsapp'")
    c.commit()
    return c


def ensure_seeded():
    c = _db()
    # Replace old non-portfolio seed rows if they still reference legacy 'aidyn'/'mbmb'
    legacy_cnt = c.execute(
        "SELECT COUNT(*) FROM text_messages WHERE contact_name LIKE '%AI Dynamics%' OR contact_name LIKE '%MBMB%'"
    ).fetchone()[0]
    if legacy_cnt > 0:
        c.execute("DELETE FROM text_messages WHERE contact_name LIKE '%AI Dynamics%' OR contact_name LIKE '%MBMB%' OR contact_name LIKE '%JasMiamiMethod%' OR contact_name LIKE '%305 Business%' OR contact_name LIKE '%Roberto Fernandez%'")
        c.execute("DELETE FROM whatsapp_watchlist")
        c.commit()

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
            ts = now - (idx * 1200)
            c.execute(
                """INSERT INTO text_messages
                   (company, channel, direction, contact_name, contact_phone, chat_type,
                    message_text, ai_draft_reply, linked_task_id, linked_task_title, status, ts)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    t["company"],
                    "telegram",
                    t["direction"],
                    t["contact_name"],
                    t["contact_phone"],
                    t.get("chat_type", "group"),
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
    """Return Official Telegram Bot API & Text Hub connection status (WhatsApp removed)."""
    env = _load_env_map()
    tg_token = (
        env.get("TELEGRAM_BOT_TOKEN", "").strip()
        or "8678556614:AAH2bc139543284b3e05c11a847db782f4c"
    )
    tg_chat = env.get("TELEGRAM_CHAT_ID", "8897658040").strip()
    return {
        "provider": "telegram_bot_api_live",
        "whatsapp_removed": True,
        "configured": bool(tg_token),
        "primary_bot": "@Pegantebot",
        "secondary_bot": "@ceojefesitobot",
        "primary_chat_id": tg_chat,
        "secondary_chat_id": "7838956683",
        "channels_supported": ["telegram", "sms"],
    }


def _dispatch_via_telegram_bot(to_target: str, message: str, contact_name: str = "") -> dict[str, Any]:
    """Send message via live Telegram Bot API (`@Pegantebot` & `@ceojefesitobot`)."""
    env = _load_env_map()
    bots = [
        (
            env.get("TELEGRAM_BOT_TOKEN", "").strip()
            or "8678556614:AAH2bc139543284b3e05c11a847db782f4c",
            "8897658040",
            "@Pegantebot",
        ),
        (
            "8638273831:AAFjH7xG6zW9kLmN2pQ5rT8vX1yZ4bC7dE0",
            "7838956683",
            "@ceojefesitobot",
        ),
    ]
    target_chat = "8897658040"
    if str(to_target).strip() in ("7838956683", "8897658040"):
        target_chat = str(to_target).strip()

    header = f"📲 *Telegram / Texto Ejecutivo — La Jefatura*\n"
    if contact_name:
        header += f"👤 *Para:* {contact_name}\n\n"
    full_text = f"{header}{message}"

    delivered_any = False
    last_msg_id = ""
    errors = []

    for token, default_chat, bot_handle in bots:
        if not token:
            continue
        chat_id = target_chat if bot_handle == "@Pegantebot" else default_chat
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = json.dumps(
            {
                "chat_id": chat_id,
                "text": full_text,
                "parse_mode": "Markdown",
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                resp = json.loads(r.read().decode("utf-8"))
                if resp.get("ok"):
                    delivered_any = True
                    last_msg_id = str((resp.get("result") or {}).get("message_id", ""))
        except Exception as e:
            errors.append(f"{bot_handle}: {e}")

    return {
        "provider": "telegram_bot_api",
        "delivered": delivered_any,
        "telegram_message_id": last_msg_id,
        "target_chat": target_chat,
        "errors": errors,
    }


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
    chat_type: str = "group",
    company: str = "espacios_importados",
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
    """Compose CEO Juan David García Montoya's executive Telegram/Text reply AND extract a task."""
    env = _load_env_map()
    gemini_key = env.get("GEMINI_API_KEY", "").strip()
    first_word = (sender_name or "Equipo").split()[0]
    fallback_draft = (
        f"Recibido {first_word}. Por favor confírmame el estatus detallado hoy mismo "
        f"para cerrar este punto en {company.replace('_', ' ').upper()}. — Juan David"
    )
    fallback_task = f"[{company.upper()}] Seguimiento Telegram/Texto a {sender_name}: {message_text[:65]}"
    if not gemini_key:
        return {"draft_reply": fallback_draft, "task_title": fallback_task, "severity": "high"}

    prompt = (
        "Eres La Jefatura, el asistente ejecutivo IA del CEO Juan David García Montoya.\n"
        f"Empresa: {company.upper()} (unitec_usa, building_innovation, espacios_importados, buildingapp, saleinn).\n"
        f"Tipo de chat Telegram/Texto: {chat_type} | Remitente/ Destinatario: {sender_name}\n"
        f"Mensaje o instrucción:\n\"{message_text}\"\n\n"
        "Devuelve estrictamente JSON con:\n"
        '1. "draft_reply": Un mensaje de Telegram/Texto directo, ejecutivo y natural en la voz de Juan David García Montoya (1-2 oraciones).\n'
        '2. "task_title": Título concreto de tarea o seguimiento (máx 14 palabras).\n'
        '3. "severity": "critical" | "high" | "medium"'
    )
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={gemini_key}"
    body = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 600,
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
        with urllib.request.urlopen(req, timeout=12) as resp:
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
    """Process incoming Telegram or SMS message, auto-draft reply in CEO voice, and create task."""
    ensure_seeded()
    c = _db()
    rows = c.execute("SELECT * FROM whatsapp_watchlist").fetchall()
    norm_in = re.sub(r"\D+", "", identifier or "")

    matched = None
    for r in rows:
        w = dict(r)
        w_norm = re.sub(r"\D+", "", w["identifier"] or "")
        if w["identifier"].lower() == (identifier or "").lower() or (norm_in and w_norm and norm_in[-8:] == w_norm[-8:]):
            matched = w
            break

    company = company_override or (matched["company"] if matched else "espacios_importados")
    chat_type = chat_type_override or (matched["chat_type"] if matched else "group")
    display_name = matched["label"] if (matched and chat_type == "group") else (sender_name or (matched["label"] if matched else identifier))
    do_draft = bool(matched["auto_draft"]) if matched else True

    ai_out = _generate_draft_and_task(display_name, message_text, company, chat_type)
    draft_reply = ai_out["draft_reply"] if do_draft else ""
    linked_task_title = ai_out.get("task_title", "")
    linked_task_id = f"T-TG-{int(time.time()) % 10000}"

    cursor = c.execute(
        """INSERT INTO text_messages
           (company, channel, direction, contact_name, contact_phone, chat_type,
            message_text, ai_draft_reply, linked_task_id, linked_task_title, status, ts)
           VALUES (?, 'telegram', 'in', ?, ?, ?, ?, ?, ?, ?, 'drafted', ?)""",
        (
            company,
            display_name,
            identifier or "8897658040",
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
        "channel": "telegram",
        "chat_type": chat_type,
        "contact_name": display_name,
        "contact_phone": identifier or "8897658040",
        "message_text": message_text,
        "ai_draft_reply": draft_reply,
        "linked_task_id": linked_task_id,
        "linked_task_title": linked_task_title,
    }


def create_outgoing_text_draft(
    contact_name: str,
    message_text: str,
    to_phone: str = "8897658040",
    company: str = "espacios_importados",
    channel: str = "telegram",
    chat_type: str = "group",
    auto_send: bool = False,
    db_path: str | None = None,
) -> dict[str, Any]:
    """
    Create a CEO-delegated Telegram or Text draft (e.g. from voice/chat command:
    'Go to Telegram and send a message to all asking what happened with the new products').
    If auto_send=False (Mode C default), saves as 'drafted' ready for 1-click CEO approval.
    If auto_send=True, dispatches immediately via Telegram Bot API.
    """
    ensure_seeded()
    c = _db(db_path)
    clean_channel = "sms" if channel == "sms" else "telegram"
    contact = (contact_name or "Grupo General Telegram (@Pegantebot)").strip()
    target = (to_phone or "8897658040").strip()
    body = (message_text or "").strip()
    now = time.time()

    status = "sent" if auto_send else "drafted"
    context_prompt = f"[Delegado por voz/chat para {contact}]"

    cursor = c.execute(
        """INSERT INTO text_messages
           (company, channel, direction, contact_name, contact_phone, chat_type,
            message_text, ai_draft_reply, linked_task_id, linked_task_title, status, ts)
           VALUES (?, ?, 'out', ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            company or "espacios_importados",
            clean_channel,
            contact,
            target,
            chat_type,
            body if auto_send else context_prompt,
            body,
            f"T-OUT-{int(now) % 10000}",
            f"Seguimiento a respuesta de {contact}: {body[:55]}",
            status,
            now,
        ),
    )
    msg_id = cursor.lastrowid
    c.commit()
    c.close()

    gw = {}
    if auto_send:
        gw = _dispatch_via_telegram_bot(target, body, contact_name=contact)

    return {
        "ok": True,
        "id": msg_id,
        "company": company or "espacios_importados",
        "channel": clean_channel,
        "contact_name": contact,
        "contact_phone": target,
        "ai_draft_reply": body,
        "status": status,
        "gateway": gw,
    }


def verify_meta_webhook(qs: dict[str, list[str]]) -> tuple[int, str]:
    challenge = (qs.get("hub.challenge") or ["telegram_ok"])[0]
    return 200, challenge


def ingest_meta_webhook(payload: dict[str, Any]) -> dict[str, Any]:
    return {"ok": True, "provider": "telegram_only", "processed_count": 0, "items": []}


def list_messages(company=None, channel=None):
    ensure_seeded()
    c = _db()
    query = "SELECT * FROM text_messages WHERE 1=1"
    params = []
    if company and str(company).lower() not in ("all", "todas", "general", ""):
        query += " AND lower(company) LIKE ?"
        params.append(f"%{str(company).lower().split('_')[0]}%")
    if channel and channel != "all":
        clean_ch = "telegram" if channel == "whatsapp" else channel
        query += " AND channel=?"
        params.append(clean_ch)
    query += " ORDER BY ts DESC LIMIT 60"
    rows = c.execute(query, params).fetchall()
    msgs = [dict(r) for r in rows]
    c.close()
    return msgs


def send_text_message(
    to_phone,
    message="",
    company="espacios_importados",
    channel="telegram",
    contact_name="",
    body="",
    db_path=None,
):
    """Send Telegram or SMS text message via live Telegram Bot API and record in `text_messages`."""
    ensure_seeded()
    actual_msg = (message or body or "").strip()
    clean_channel = "sms" if channel == "sms" else "telegram"
    c = _db(db_path)
    now = time.time()
    cursor = c.execute(
        """INSERT INTO text_messages
           (company, channel, direction, contact_name, contact_phone, message_text, ai_draft_reply, status, ts)
           VALUES (?, ?, 'out', ?, ?, ?, '', 'sent', ?)""",
        (
            company or "espacios_importados",
            clean_channel,
            contact_name or to_phone or "Telegram Grupo Ejecutivo",
            to_phone or "8897658040",
            actual_msg,
            now,
        ),
    )
    new_id = cursor.lastrowid
    c.commit()
    c.close()
    gw = _dispatch_via_telegram_bot(
        to_phone or "8897658040",
        actual_msg,
        contact_name=contact_name or str(to_phone),
    )
    return {
        "ok": True,
        "id": new_id,
        "channel": clean_channel,
        "gateway": gw,
        "status": "sent",
        "to": to_phone or "8897658040",
        "contact_name": contact_name or to_phone,
        "msg": actual_msg,
        "company": company,
    }


def approve_text_draft(message_id, edited_text: str | None = None):
    """Approve pre-drafted Telegram/Text message, dispatch via live Telegram Bot API, and mark as sent."""
    ensure_seeded()
    c = _db()
    row = c.execute(
        "SELECT * FROM text_messages WHERE id=?", (int(message_id),)
    ).fetchone()
    if not row:
        c.close()
        return {"ok": False, "error": "Message not found"}

    m = dict(row)
    draft_reply = (edited_text if edited_text is not None else m.get("ai_draft_reply", "")).strip()
    if not draft_reply:
        draft_reply = (m.get("message_text") or "").strip()
    if not draft_reply:
        c.close()
        return {"ok": False, "error": "No draft text to approve"}

    now = time.time()
    if m.get("direction") == "out" and m.get("status") == "drafted":
        c.execute(
            "UPDATE text_messages SET message_text=?, ai_draft_reply=?, status='sent', ts=? WHERE id=?",
            (draft_reply, draft_reply, now, int(message_id)),
        )
    else:
        c.execute(
            "UPDATE text_messages SET ai_draft_reply=?, status='replied' WHERE id=?",
            (draft_reply, int(message_id)),
        )
        c.execute(
            """INSERT INTO text_messages
               (company, channel, direction, contact_name, contact_phone, chat_type, message_text, status, ts)
               VALUES (?, 'telegram', 'out', ?, ?, ?, ?, 'sent', ?)""",
            (
                m["company"],
                m["contact_name"],
                m["contact_phone"],
                m.get("chat_type", "group"),
                draft_reply,
                now,
            ),
        )
    c.commit()
    c.close()

    gw = _dispatch_via_telegram_bot(
        m.get("contact_phone") or "8897658040",
        draft_reply,
        contact_name=m.get("contact_name") or "",
    )
    return {
        "ok": True,
        "replied_to_id": int(message_id),
        "contact_name": m.get("contact_name"),
        "reply_text": draft_reply,
        "gateway": gw,
    }


def update_text_draft(message_id, new_draft_text):
    ensure_seeded()
    c = _db()
    c.execute(
        "UPDATE text_messages SET ai_draft_reply=?, status='drafted' WHERE id=?",
        (new_draft_text, int(message_id)),
    )
    c.commit()
    c.close()
    return {"ok": True, "id": int(message_id), "ai_draft_reply": new_draft_text}
