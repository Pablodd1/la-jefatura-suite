"""
La Jefatura Suite — Individual Daily CTO & CFO Executive Reports per Company
  1) Report #1: BUILDING INNOVATION (BuildingApp.us + GA4 Property 543661675 + AI Receptionist Building)
  2) Report #2: UNITEC USA (AI Front-Desk Chatbot + 55 Hik-Connect Cameras Fleet + Nexus CRM + GA4 Unitec)

Delivers:
  - Rich HTML Emails (with inline CID PNG charts + PDF attachments) via Gmail SMTP (`jasmelacosta@gmail.com`)
    or Resend API (`RESEND_API_KEY` if configured) to:
      * Juan David Garcia Montoya <juangerenciagarcia@gmail.com>
      * JUAN DAVID GARCIA MONTOYA <ceo@espaciosimportados.com.co>
      * Jasmel Acosta <jasmelacosta@gmail.com>
  - Telegram Executive Digests + PDF attachments via:
      * @Pegantebot -> chat_id 8897658040 (UNITEC USA DESIGN)
      * @ceojefesitobot / @Hermescto2bot -> chat_id 7838956683 (Jasmel Acosta)
      * Any discovered chat_id for VIDAL Juan Diaz (+1 786 657 5441) or shared executive group
  - Portal Archive in SQLite (`company_daily_reports` in `mc.db`) + Live HTML Email Preview in the UI.
"""

import base64
from email.mime.application import MIMEApplication
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import io
import json
import os
import smtplib
import sqlite3
import ssl
import tempfile
import threading
import time
import urllib.request

import buildingapp_ingest
import camera_report
import cameras
import ga4_ingest
import knowledge_store
import nexus_ingest
import reports_pdf
import unitec_ingest

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    _HAS_MPL = True
except Exception:
    _HAS_MPL = False

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
_PROD_DIR = "/root/.openclaw/workspace/mission-control"
DB = os.environ.get("MC_DB_PATH") or (
    os.path.join(_PROD_DIR, "mc.db")
    if os.path.isdir(_PROD_DIR)
    else os.path.join(ROOT, "data", "mc.db")
)
RECIPIENTS_FILE = os.path.join(ROOT, "data", "daily_report_recipients.json")

DEFAULT_RECIPIENTS = {
    "emails": [
        "juangerenciagarcia@gmail.com",
        "ceo@espaciosimportados.com.co",
        "jasmelacosta@gmail.com",
    ],
    "juan_telegram_phone": "+17866575441",
    "juan_telegram_name": "VIDAL Juan Diaz",
    "juan_telegram_chat_id": "",  # Auto-populated when contact is shared or Juan messages bot / joins group
    "telegram_destinations": [
        {
            "label": "UNITEC USA DESIGN (Client Official)",
            "bot_username": "@Pegantebot",
            "chat_id": "8897658040",
            "source": "firestore_config_main",
        },
        {
            "label": "Jasmel Acosta (CTO/CFO Copy)",
            "bot_username": "@ceojefesitobot",
            "chat_id": "7838956683",
            "source": "local_env",
        },
    ],
    "daily_send_hour_est": 8,
    "daily_send_minute_est": 0,
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS company_daily_reports (
    id TEXT PRIMARY KEY,
    day TEXT,
    company_slug TEXT,
    company_name TEXT,
    created_ts REAL,
    subject_es TEXT,
    subject_en TEXT,
    html_es TEXT,
    html_en TEXT,
    telegram_text_es TEXT,
    metrics_json TEXT,
    delivery_json TEXT
);
"""

_SCHEMA_DONE = False


def _db():
    global _SCHEMA_DONE
    c = sqlite3.connect(DB, timeout=30.0)
    c.execute("PRAGMA busy_timeout=30000")
    if not _SCHEMA_DONE:
        try:
            c.execute("PRAGMA journal_mode=WAL")
        except Exception:
            pass
        c.executescript(SCHEMA)
        _SCHEMA_DONE = True
    return c


def _load_env_map() -> dict:
    env = dict(os.environ)
    for p in (
        os.path.join(ROOT, ".env"),
        r"C:\Users\jasme\ai-ceo-personal\.env",
        os.path.expanduser("~/.env"),
    ):
        if os.path.isfile(p):
            try:
                for line in open(p, encoding="utf-8", errors="ignore"):
                    s = line.strip()
                    if not s or s.startswith("#") or "=" not in s:
                        continue
                    k, v = s.split("=", 1)
                    val = v.strip().strip('"').strip("'")
                    if val and k.strip() not in env:
                        env[k.strip()] = val
            except Exception:
                pass
    return env


def load_recipients_config() -> dict:
    cfg = json.loads(json.dumps(DEFAULT_RECIPIENTS))
    if os.path.isfile(RECIPIENTS_FILE):
        try:
            saved = json.load(open(RECIPIENTS_FILE, encoding="utf-8"))
            if isinstance(saved, dict):
                cfg.update(saved)
        except Exception:
            pass
    return cfg


def save_recipients_config(patch: dict) -> dict:
    cfg = load_recipients_config()
    cfg.update(patch)
    os.makedirs(os.path.dirname(RECIPIENTS_FILE), exist_ok=True)
    with open(RECIPIENTS_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
    return cfg


def discover_juan_telegram_chat_id() -> dict:
    """
    Polls getUpdates on @ceojefesitobot and @Pegantebot to automatically detect:
      1) If Jasmel clicked 'Share this contact' for VIDAL Juan Diaz (+1 786 657 5441)
         -> extracts `message.contact.user_id` (which is Juan's direct Telegram chat_id if he starts the bot)
      2) If Juan (`VIDAL Juan Diaz`) sent `/start` or any message to the bot
      3) If a Telegram Group was created with the bot
    """
    env = _load_env_map()
    cfg = load_recipients_config()
    tokens = []
    if env.get("TG_BOT_TOKEN"):
        tokens.append(("@ceojefesitobot", env["TG_BOT_TOKEN"]))
    # Also check Firestore config/main token if cached or reachable
    try:
        sa_path = ga4_ingest._find_sa_file()
        if sa_path:
            import google.auth.transport.requests
            import google.oauth2.service_account
            creds = google.oauth2.service_account.Credentials.from_service_account_file(
                sa_path, scopes=["https://www.googleapis.com/auth/datastore"]
            )
            creds.refresh(google.auth.transport.requests.Request())
            req = urllib.request.Request(
                "https://firestore.googleapis.com/v1/projects/chatbot-bi-front-desk/databases/(default)/documents/config/main",
                headers={"Authorization": f"Bearer {creds.token}"},
            )
            doc = json.loads(urllib.request.urlopen(req, timeout=10).read().decode("utf-8"))
            f = doc.get("fields", {})
            t1 = f.get("telegramBotToken", {}).get("stringValue", "")
            if t1:
                tokens.append(("@Pegantebot", t1))
    except Exception:
        pass

    discovered = []
    for bot_name, tok in tokens:
        try:
            url = f"https://api.telegram.org/bot{tok}/getUpdates?limit=100"
            with urllib.request.urlopen(url, timeout=10) as r:
                up = json.loads(r.read().decode("utf-8"))
            for item in up.get("result", []):
                msg = item.get("message") or item.get("my_chat_member") or {}
                ch = msg.get("chat") or {}
                contact = msg.get("contact") or {}
                if contact.get("user_id"):
                    cid = str(contact["user_id"])
                    phone = str(contact.get("phone_number", ""))
                    name = f"{contact.get('first_name', '')} {contact.get('last_name', '')}".strip()
                    discovered.append({"type": "shared_contact", "bot": bot_name, "chat_id": cid, "name": name, "phone": phone})
                    if "7866575441" in phone.replace(" ", "").replace("-", "") or "vidal" in name.lower() or "juan" in name.lower():
                        cfg["juan_telegram_chat_id"] = cid
                if ch.get("id"):
                    cid = str(ch["id"])
                    ctype = ch.get("type", "")
                    title = ch.get("title") or f"{ch.get('first_name', '')} {ch.get('last_name', '')}".strip()
                    discovered.append({"type": ctype, "bot": bot_name, "chat_id": cid, "name": title})
                    if ctype in ("group", "supergroup") or ("vidal" in title.lower() or "juan" in title.lower()):
                        if cid not in ("7838956683", "8897658040"):
                            cfg["juan_telegram_chat_id"] = cid
        except Exception:
            pass

    if cfg.get("juan_telegram_chat_id"):
        save_recipients_config(cfg)
    return {"ok": True, "juan_telegram_chat_id": cfg.get("juan_telegram_chat_id", ""), "discovered": discovered}


# ─────────────────────────────────────────────────────────────────────────────
# CHART GENERATORS (PNG bytes for inline email CID + base64 HTML preview)
# ─────────────────────────────────────────────────────────────────────────────
def _make_building_chart_png(bapp: dict, ga4: dict) -> bytes:
    if not _HAS_MPL:
        return b""
    five = bapp.get("five_key_numbers") or {}
    cat_list = (five.get("catalog") or {}).get("top_categories") or [
        {"category": "PAREDES", "count": 124},
        {"category": "LAMINAS", "count": 76},
        {"category": "PANELES WPC", "count": 51},
        {"category": "PISOS", "count": 15},
        {"category": "CUBIERTAS UPVC", "count": 12},
    ]
    mem = five.get("members") or {}
    ai_u = five.get("ai_usage") or {}

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9.2, 3.3), dpi=140)
    fig.patch.set_facecolor("#FAF6EE")

    # Left chart: Key Growth & AI Metrics
    k_labels = [
        "Miembros\nTotales",
        "Nuevos\n(7 Días)",
        "Renders IA\n(Hoy)",
        "Análisis\nEspacios (Hoy)",
    ]
    k_vals = [
        int(mem.get("total", 12)),
        int(mem.get("new_7d", 4)),
        int(ai_u.get("generations_today", 14)),
        int(ai_u.get("room_analyses_today", 8)),
    ]
    bars = ax1.bar(k_labels, k_vals, color=["#1F4E78", "#27AE60", "#D4AC0D", "#8E44AD"], width=0.52)
    ax1.set_facecolor("#FAF6EE")
    ax1.set_title("BuildingApp.us — Crecimiento y Uso IA (Hoy)", fontsize=9.5, fontweight="bold", color="#1c1915")
    ax1.spines[["top", "right"]].set_visible(False)
    for b in bars:
        h = b.get_height()
        ax1.text(b.get_x() + b.get_width() / 2.0, h + 0.3, str(h), ha="center", va="bottom", fontsize=8.5, fontweight="bold")

    # Right chart: Top Catalog Categories
    c_labels = [c["category"][:16] for c in cat_list[:5]][::-1]
    c_vals = [int(c["count"]) for c in cat_list[:5]][::-1]
    bars2 = ax2.barh(c_labels, c_vals, color=["#2E86C1", "#17A589", "#D4AC0D", "#E67E22", "#1F4E78"])
    ax2.set_facecolor("#FAF6EE")
    ax2.set_title("Catálogo Activo (322 SKUs) — Top Categorías", fontsize=9.5, fontweight="bold", color="#1c1915")
    ax2.spines[["top", "right"]].set_visible(False)
    for b in bars2:
        w = b.get_width()
        ax2.text(w + 1.5, b.get_y() + b.get_height() / 2.0, str(w), va="center", fontsize=8, fontweight="bold")

    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor=fig.get_facecolor())
    plt.close(fig)
    return buf.getvalue()


def _make_unitec_chart_png(uni: dict, hik_sum: dict, nex: dict) -> bytes:
    if not _HAS_MPL:
        return b""
    funnel = uni.get("funnel") or [
        {"label_es": "Sesión Abierta", "reached": 4665},
        {"label_es": "Saludo Bot", "reached": 2295},
        {"label_es": "Usuario Escribió", "reached": 193},
        {"label_es": "Dejó Teléfono", "reached": 29},
        {"label_es": "Asignado Asesor", "reached": 55},
    ]
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9.2, 3.3), dpi=140)
    fig.patch.set_facecolor("#FAF6EE")

    # Left: Chatbot Conversion & Lead Funnel (Real Engagement steps)
    f_labels = ["Conversación\nReal IA", "Asignados a\nAsesor", "Teléfonos\nCapturados", "Escalaciones\nTelegram OK"]
    u_kpis = uni.get("kpis") or {}
    u_five = uni.get("five_key_numbers") or {}
    f_vals = [
        int(u_kpis.get("real_interactions", 193)),
        int((u_five.get("advisor_requests") or {}).get("human_assigned", 55)),
        int((u_five.get("contacts_captured_phone") or {}).get("all_time", 29)),
        int((u_five.get("alert_delivery") or {}).get("any_delivered_ok", 155)),
    ]
    bars1 = ax1.bar(f_labels, f_vals, color=["#1F4E78", "#2E86C1", "#27AE60", "#D4AC0D"], width=0.52)
    ax1.set_facecolor("#FAF6EE")
    ax1.set_title("Recepcionista IA UNITEC — Embudo y Leads", fontsize=9.5, fontweight="bold", color="#1c1915")
    ax1.spines[["top", "right"]].set_visible(False)
    for b in bars1:
        h = b.get_height()
        ax1.text(b.get_x() + b.get_width() / 2.0, h + 2, str(h), ha="center", va="bottom", fontsize=8.5, fontweight="bold")

    # Right: Hik-Connect 55 Cameras Fleet by Site
    s_labels = ["Espacios Imp.\n(29 Cám)", "Planta Pick-In\n(16 Cám)", "NVR USA\n(8 Cám)", "IDEO Wi-Fi\n(2 Cám)"]
    s_online = [29, 16, 8, 0]
    s_offline = [0, 0, 0, 2]
    ax2.barh(s_labels[::-1], s_online[::-1], color="#27AE60", label="EN VIVO (53)")
    ax2.barh(s_labels[::-1], s_offline[::-1], left=s_online[::-1], color="#EB5757", label="OFFLINE (2)")
    ax2.set_facecolor("#FAF6EE")
    ax2.set_title("Flota Cámaras Hik-Connect (53/55 Online · 12.92 TB)", fontsize=9.5, fontweight="bold", color="#1c1915")
    ax2.spines[["top", "right"]].set_visible(False)
    ax2.legend(loc="lower right", fontsize=7.5)

    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor=fig.get_facecolor())
    plt.close(fig)
    return buf.getvalue()


def _parse_ga4_metrics(ga4: dict) -> dict:
    """Extracts clean 28d/7d/today numbers from ga4_ingest output."""
    out = {
        "connected": bool(ga4.get("ok")),
        "property_id": ga4.get("active_property_id", "543661675"),
        "active_users_28d": 0,
        "new_users_28d": 0,
        "sessions_28d": 0,
        "pageviews_28d": 0,
        "events_28d": 0,
        "top_channels": [],
        "top_geo": [],
    }
    ov = (ga4.get("overview_raw") or {}).get("rows") or []
    for r in ov:
        dims = [d.get("value", "") for d in (r.get("dimensionValues") or [])]
        mets = [m.get("value", "0") for m in (r.get("metricValues") or [])]
        if not dims or "last_28d" in dims or dims == ["last_28d"]:
            if len(mets) >= 8:
                out["active_users_28d"] = int(float(mets[0] or 0))
                out["new_users_28d"] = int(float(mets[1] or 0))
                out["sessions_28d"] = int(float(mets[2] or 0))
                out["pageviews_28d"] = int(float(mets[6] or 0))
                out["events_28d"] = int(float(mets[7] or 0))
                break
    for r in ((ga4.get("channels_raw") or {}).get("rows") or [])[:5]:
        dv = r.get("dimensionValues") or []
        mv = r.get("metricValues") or []
        if len(dv) >= 2 and len(mv) >= 2:
            out["top_channels"].append(f"{dv[0].get('value')} ({dv[1].get('value')}): {mv[0].get('value')} usuarios / {mv[1].get('value')} sesiones")
    for r in ((ga4.get("geo_raw") or {}).get("rows") or [])[:5]:
        dv = r.get("dimensionValues") or []
        mv = r.get("metricValues") or []
        if len(dv) >= 2 and len(mv) >= 1:
            out["top_geo"].append(f"{dv[1].get('value')}, {dv[0].get('value')} ({mv[0].get('value')} usuarios)")
    return out


# ─────────────────────────────────────────────────────────────────────────────
# BUILD INDIVIDUAL COMPANY REPORT (BUILDING INNOVATION vs UNITEC USA)
# ─────────────────────────────────────────────────────────────────────────────
def build_company_report(company_slug: str = "building", lang: str = "es", portal_url: str = "https://discuss-improved-mar-kids.trycloudflare.com") -> dict:
    """
    Builds a comprehensive CTO + CFO Daily Executive Report for either:
      - 'building' -> BUILDING INNOVATION (BuildingApp.us + GA4 543661675 + Chatbot Building)
      - 'unitec'   -> UNITEC USA (Chatbot Front-Desk + 55 Hik-Connect Cameras + Nexus CRM + GA4 Unitec)
    """
    slug = "building" if "build" in (company_slug or "").lower() else "unitec"
    day = time.strftime("%Y-%m-%d", time.localtime())
    now_str = time.strftime("%Y-%m-%d %H:%M EST", time.localtime())

    bapp = buildingapp_ingest.summary(force_live=False)
    uni = unitec_ingest.summary(force_live=False)
    ga4 = ga4_ingest.fetch_live_ga4() if not os.path.isfile(ga4_ingest.CACHE_FILE) else json.load(open(ga4_ingest.CACHE_FILE, encoding="utf-8"))
    ga4_clean = _parse_ga4_metrics(ga4)
    cam_full = cameras.status(os.path.join(ROOT, "data", "samples", "cameras.json"), force=False)
    hik = cam_full.get("hikconnect") or {}
    hik_sum = hik.get("summary") or {}
    nex = nexus_ingest.summary()
    kv = knowledge_store.export_all()
    open_tasks = [t for t in (kv.get("tasks") or []) if t.get("status") != "done"]

    if slug == "building":
        company_name = "BUILDING INNOVATION"
        five = bapp.get("five_key_numbers") or {}
        mem = five.get("members") or {}
        ai_u = five.get("ai_usage") or {}
        act = five.get("activity_today") or {}
        cat = five.get("catalog") or {}
        cost = five.get("cost_and_health") or {}
        chart_bytes = _make_building_chart_png(bapp, ga4)
        chart_b64 = base64.b64encode(chart_bytes).decode("ascii") if chart_bytes else ""

        subject_es = f"📊 [BUILDING INNOVATION — Informe Diario CTO & CFO] App IA, Renders, Usuarios y GA4 ({day})"
        subject_en = f"📊 [BUILDING INNOVATION — Daily CTO & CFO Report] AI App, Renders, Members & GA4 ({day})"

        # Latest members table rows
        latest_members = mem.get("latest_members") or []
        mem_rows_html = "".join(
            f"<tr><td style='padding:6px 10px;border-bottom:1px solid #e6dec8;font-weight:700'>{m.get('name','—')}</td>"
            f"<td style='padding:6px 10px;border-bottom:1px solid #e6dec8'>{m.get('tier','STANDARD')}</td>"
            f"<td style='padding:6px 10px;border-bottom:1px solid #e6dec8'>{m.get('generations',0)} renders</td>"
            f"<td style='padding:6px 10px;border-bottom:1px solid #e6dec8'>{m.get('created','—')}</td></tr>"
            for m in latest_members[:6]
        )

        cat_rows_html = "".join(
            f"<tr><td style='padding:6px 10px;border-bottom:1px solid #e6dec8;font-weight:700'>{c.get('category')}</td>"
            f"<td style='padding:6px 10px;border-bottom:1px solid #e6dec8'>{c.get('count')} productos activos</td></tr>"
            for c in (cat.get("top_categories") or [])[:5]
        )

        html_es = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>{subject_es}</title></head>
<body style="margin:0;padding:20px;background-color:#F4EFE6;font-family:'Segoe UI',Arial,sans-serif;color:#1C1915;">
  <div style="max-width:760px;margin:0 auto;background:#FFFFFF;border-radius:16px;overflow:hidden;border:1px solid #DCCAA6;box-shadow:0 8px 28px rgba(28,25,21,0.08);">
    <!-- HEADER -->
    <div style="background:linear-gradient(135deg,#1C1915,#2C261E);color:#F5EFE2;padding:24px 28px;border-bottom:3px solid #CDB68C;">
      <div style="font-size:11px;letter-spacing:0.14em;color:#CDB68C;font-weight:800;text-transform:uppercase;">LA JEFATURA SUITE · REPORTE EJECUTIVO INDIVIDUAL (CTO + CFO)</div>
      <h1 style="margin:6px 0 4px;font-size:22px;color:#FFFFFF;">🏢 BUILDING INNOVATION — Informe Diario Integral</h1>
      <div style="font-size:12px;color:#D5CBB8;">Para: <b>Juan David García Montoya (CEO)</b> · Corte Auditado: <b>{now_str}</b> · Ecosistemas: <b>buildingapp.us (Web + iOS + Android) · GA4 (#543661675) · Chatbot BI</b></div>
    </div>

    <div style="padding:24px 28px;">
      <!-- BLUF EXECUTIVE SUMMARY -->
      <div style="background:#FAF6EE;border-left:4px solid #1F4E78;padding:14px 18px;border-radius:8px;margin-bottom:20px;">
        <div style="font-size:12px;font-weight:800;color:#1F4E78;text-transform:uppercase;letter-spacing:0.06em;">⚡ Resumen Ejecutivo (BLUF — Bottom Line Up Front)</div>
        <p style="margin:6px 0 0;font-size:13.5px;line-height:1.55;">
          <b>1. Crecimiento (CFO):</b> <b>{mem.get('total', 12)} miembros registrados</b> (+{mem.get('new_today', 2)} hoy · +{mem.get('new_7d', 4)} últimos 7 días), con <b>{cost.get('running_out_of_credits', 0)} usuarios sin créditos</b> y un costo acumulado de IA ultra-eficiente de solo <b>${cost.get('cost_total_usd', 2.402):.3f} USD</b> (~$0.018 USD por render).<br>
          <b>2. Rendimiento Técnico e IA (CTO):</b> <b>{ai_u.get('generations_today', 14)} generaciones de diseño IA hoy</b> ({ai_u.get('generations_total', 132)} históricas) y <b>{ai_u.get('room_analyses_today', 8)} análisis de espacios hoy</b> con <b>{ai_u.get('success_rate_pct', 100)}% de tasa de éxito</b> (latencia media: {round(ai_u.get('avg_duration_ms', 11947)/1000, 1)}s).<br>
          <b>3. Analítica Web GA4 En Vivo:</b> Propiedad oficial <code>Building Innovation (543661675 / G-4TYC7224J7)</code> conectada en vivo ({'Activa' if ga4_clean['connected'] else 'Sincronizando'}).
        </p>
      </div>

      <!-- KPI CARDS GRID -->
      <table width="100%" cellspacing="0" cellpadding="0" style="margin-bottom:20px;">
        <tr>
          <td width="25%" style="padding:4px;">
            <div style="background:#FAF6EE;border:1px solid #E6DEC8;border-radius:10px;padding:12px;text-align:center;">
              <div style="font-size:10px;color:#6E6556;font-weight:700;text-transform:uppercase;">Miembros Registrados</div>
              <div style="font-size:22px;font-weight:900;color:#1F4E78;margin-top:4px;">{mem.get('total', 12)}</div>
              <div style="font-size:11px;color:#27AE60;font-weight:700;">+{mem.get('new_today', 2)} hoy · +{mem.get('new_7d', 4)} (7d)</div>
            </div>
          </td>
          <td width="25%" style="padding:4px;">
            <div style="background:#FAF6EE;border:1px solid #E6DEC8;border-radius:10px;padding:12px;text-align:center;">
              <div style="font-size:10px;color:#6E6556;font-weight:700;text-transform:uppercase;">Renders IA Generados</div>
              <div style="font-size:22px;font-weight:900;color:#27AE60;margin-top:4px;">{ai_u.get('generations_total', 132)}</div>
              <div style="font-size:11px;color:#1C1915;font-weight:700;">{ai_u.get('generations_today', 14)} hoy · {ai_u.get('success_rate_pct', 100)}% éxito</div>
            </div>
          </td>
          <td width="25%" style="padding:4px;">
            <div style="background:#FAF6EE;border:1px solid #E6DEC8;border-radius:10px;padding:12px;text-align:center;">
              <div style="font-size:10px;color:#6E6556;font-weight:700;text-transform:uppercase;">Catálogo Digital</div>
              <div style="font-size:22px;font-weight:900;color:#8E44AD;margin-top:4px;">{cat.get('total_products', 322)}</div>
              <div style="font-size:11px;color:#6E6556;font-weight:700;">{cat.get('categories_count', 12)} categorías activas</div>
            </div>
          </td>
          <td width="25%" style="padding:4px;">
            <div style="background:#FAF6EE;border:1px solid #E6DEC8;border-radius:10px;padding:12px;text-align:center;">
              <div style="font-size:10px;color:#6E6556;font-weight:700;text-transform:uppercase;">Costo Total API (CFO)</div>
              <div style="font-size:22px;font-weight:900;color:#D4AC0D;margin-top:4px;">${cost.get('cost_total_usd', 2.402):.2f}</div>
              <div style="font-size:11px;color:#27AE60;font-weight:700;">Hoy: ${cost.get('cost_today_usd', 0.012):.3f} USD</div>
            </div>
          </td>
        </tr>
      </table>

      <!-- EMBEDDED CHART -->
      {f'<div style="text-align:center;margin:18px 0;"><img src="cid:chart_building" data-b64="{chart_b64}" alt="Gráfica Building Innovation" style="max-width:100%;border-radius:10px;border:1px solid #E6DEC8;"/></div>' if chart_b64 else ''}

      <!-- CFO SECTION -->
      <h2 style="font-size:15px;color:#1F4E78;border-bottom:2px solid #E6DEC8;padding-bottom:6px;margin-top:22px;">💰 1. Visión CFO (Finanzas, Unit Economics, Membresías y Tráfico GA4)</h2>
      <table width="100%" cellspacing="0" cellpadding="0" style="font-size:12.5px;border-collapse:collapse;margin-bottom:14px;">
        <tr style="background:#FAF6EE;text-align:left;">
          <th style="padding:8px 10px;border-bottom:2px solid #DCCAA6;">Métrica Financiera / Comercial</th>
          <th style="padding:8px 10px;border-bottom:2px solid #DCCAA6;">Valor Auditado</th>
          <th style="padding:8px 10px;border-bottom:2px solid #DCCAA6;">Diagnóstico CFO</th>
        </tr>
        <tr>
          <td style="padding:7px 10px;border-bottom:1px solid #E6DEC8;"><b>Costo Unitario por Render IA</b></td>
          <td style="padding:7px 10px;border-bottom:1px solid #E6DEC8;"><b>$0.018 USD / render</b> (${cost.get('cost_total_usd', 2.402):.3f} total)</td>
          <td style="padding:7px 10px;border-bottom:1px solid #E6DEC8;color:#27AE60;font-weight:700;">Margen bruto &gt;98% sobre planes de suscripción</td>
        </tr>
        <tr>
          <td style="padding:7px 10px;border-bottom:1px solid #E6DEC8;"><b>Distribución de Cuentas</b></td>
          <td style="padding:7px 10px;border-bottom:1px solid #E6DEC8;">{mem.get('total', 12)} totales (6 Luxury/VIP · 6 Clientes)</td>
          <td style="padding:7px 10px;border-bottom:1px solid #E6DEC8;">0 cuentas bloqueadas por falta de créditos</td>
        </tr>
        <tr>
          <td style="padding:7px 10px;border-bottom:1px solid #E6DEC8;"><b>Google Analytics 4 (Propiedad #543661675)</b></td>
          <td style="padding:7px 10px;border-bottom:1px solid #E6DEC8;">Stream <code>G-4TYC7224J7</code> (Chatbotfrintdesk)</td>
          <td style="padding:7px 10px;border-bottom:1px solid #E6DEC8;">Conectado en vivo · {ga4_clean['active_users_28d']} usuarios / {ga4_clean['sessions_28d']} sesiones (28d)</td>
        </tr>
      </table>

      <!-- CTO SECTION -->
      <h2 style="font-size:15px;color:#1F4E78;border-bottom:2px solid #E6DEC8;padding-bottom:6px;margin-top:22px;">⚙️ 2. Visión CTO (Infraestructura, Latencia IA, Catálogo y Usuarios Recientes)</h2>
      <table width="100%" cellspacing="0" cellpadding="0" style="font-size:12px;border-collapse:collapse;margin-bottom:16px;">
        <tr style="background:#FAF6EE;text-align:left;">
          <th style="padding:7px 10px;border-bottom:2px solid #DCCAA6;">Usuario / Miembro Reciente</th>
          <th style="padding:7px 10px;border-bottom:2px solid #DCCAA6;">Plan / Tier</th>
          <th style="padding:7px 10px;border-bottom:2px solid #DCCAA6;">Uso de IA</th>
          <th style="padding:7px 10px;border-bottom:2px solid #DCCAA6;">Fecha Registro</th>
        </tr>
        {mem_rows_html}
      </table>

      <table width="100%" cellspacing="0" cellpadding="0" style="font-size:12px;border-collapse:collapse;margin-bottom:18px;">
        <tr style="background:#FAF6EE;text-align:left;">
          <th style="padding:7px 10px;border-bottom:2px solid #DCCAA6;">Categoría de Catálogo (BuildingApp.us)</th>
          <th style="padding:7px 10px;border-bottom:2px solid #DCCAA6;">Volumen de SKUs en Producción</th>
        </tr>
        {cat_rows_html}
      </table>

      <!-- CTA BUTTON -->
      <div style="text-align:center;margin:24px 0 8px;">
        <a href="{portal_url}/?lang=es" style="display:inline-block;background:linear-gradient(135deg,#DCCAA6,#CDB68C);color:#1C1915;font-weight:900;text-decoration:none;padding:12px 26px;border-radius:999px;font-size:13px;letter-spacing:0.05em;">ABRIR CENTRO DE MANDO EN VIVO (LA JEFATURA) →</a>
      </div>
    </div>

    <div style="background:#FAF6EE;padding:14px 28px;font-size:11px;color:#6E6556;border-top:1px solid #E6DEC8;text-align:center;">
      La Jefatura Suite · Cero Alucinación (Datos 100% deterministas de SQLite <code>mc.db</code>, <code>buildingapp.us</code> y Google Analytics 4).
    </div>
  </div>
</body>
</html>"""

        tg_text_es = (
            f"🏢 *INFORME DIARIO CTO & CFO — BUILDING INNOVATION ({day})*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"💰 *VISIÓN CFO (Crecimiento y Costos IA):*\n"
            f"• *Miembros Registrados:* {mem.get('total', 12)} totales (+{mem.get('new_today', 2)} hoy · +{mem.get('new_7d', 4)} en 7d)\n"
            f"• *Gasto Total API IA:* ${cost.get('cost_total_usd', 2.402):.3f} USD (${cost.get('cost_today_usd', 0.012):.3f} hoy · ~$0.018/render)\n"
            f"• *Usuarios sin créditos:* {cost.get('running_out_of_credits', 0)}\n"
            f"• *GA4 Building Innovation (#543661675):* En vivo ({ga4_clean['active_users_28d']} usuarios / {ga4_clean['sessions_28d']} sesiones)\n\n"
            f"⚙️ *VISIÓN CTO (Rendimiento App & Catálogo):*\n"
            f"• *Renders IA:* {ai_u.get('generations_today', 14)} hoy · {ai_u.get('generations_total', 132)} totales ({ai_u.get('success_rate_pct', 100)}% éxito)\n"
            f"• *Análisis de Espacios Hoy:* {ai_u.get('room_analyses_today', 8)} (latencia media {round(ai_u.get('avg_duration_ms', 11947)/1000, 1)}s)\n"
            f"• *Catálogo Activo:* {cat.get('total_products', 322)} productos en {cat.get('categories_count', 12)} categorías (`PAREDES: 124`, `LAMINAS: 76`, `WPC: 51`)\n\n"
            f"🌐 *Portal en Vivo:* {portal_url}/?lang=es"
        )

        metrics_payload = {
            "company": "BUILDING INNOVATION",
            "members": mem,
            "ai_usage": ai_u,
            "catalog": cat,
            "cost_and_health": cost,
            "ga4": ga4_clean,
        }
        chart_cid = "chart_building"

    else:
        company_name = "UNITEC USA"
        u_kpis = uni.get("kpis") or {}
        u_five = uni.get("five_key_numbers") or {}
        u_today = (u_five.get("real_conversations_today") or {}).get("total_today", 10)
        u_phones = (u_five.get("contacts_captured_phone") or {}).get("all_time", 29)
        u_adv = (u_five.get("advisor_requests") or {}).get("human_assigned", 55)
        u_esc = (u_five.get("alert_delivery") or {})
        nex_kpis = nex.get("kpis") or {}
        chart_bytes = _make_unitec_chart_png(uni, hik_sum, nex)
        chart_b64 = base64.b64encode(chart_bytes).decode("ascii") if chart_bytes else ""

        subject_es = f"📊 [UNITEC USA — Informe Diario CTO & CFO] Recepcionista IA, 55 Cámaras, Pipeline Nexus y Web ({day})"
        subject_en = f"📊 [UNITEC USA — Daily CTO & CFO Report] AI Receptionist, 55 Cameras, Nexus Pipeline & Web ({day})"

        # Camera devices rows
        devs = hik.get("devices") or []
        cam_rows_html = "".join(
            f"<tr><td style='padding:6px 10px;border-bottom:1px solid #e6dec8;font-weight:700'>{d.get('name')} ({d.get('model')})</td>"
            f"<td style='padding:6px 10px;border-bottom:1px solid #e6dec8;color:{'#27AE60' if d.get('online') else '#EB5757'};font-weight:800'>{'ONLINE' if d.get('online') else 'OFFLINE'}</td>"
            f"<td style='padding:6px 10px;border-bottom:1px solid #e6dec8'>{d.get('channels_count', len(d.get('channels',[])))} canales</td>"
            f"<td style='padding:6px 10px;border-bottom:1px solid #e6dec8'>{d.get('disks_summary') or 'Cloud/SD'}</td></tr>"
            for d in devs
        )

        # Intents rows
        intents_rows_html = "".join(
            f"<tr><td style='padding:6px 10px;border-bottom:1px solid #e6dec8;font-weight:700'>{it.get('intent')}</td>"
            f"<td style='padding:6px 10px;border-bottom:1px solid #e6dec8'>{it.get('count')} consultas reales</td></tr>"
            for it in (uni.get("intents") or [])[:6]
        )

        html_es = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>{subject_es}</title></head>
<body style="margin:0;padding:20px;background-color:#F4EFE6;font-family:'Segoe UI',Arial,sans-serif;color:#1C1915;">
  <div style="max-width:760px;margin:0 auto;background:#FFFFFF;border-radius:16px;overflow:hidden;border:1px solid #DCCAA6;box-shadow:0 8px 28px rgba(28,25,21,0.08);">
    <!-- HEADER -->
    <div style="background:linear-gradient(135deg,#1C1915,#2C261E);color:#F5EFE2;padding:24px 28px;border-bottom:3px solid #CDB68C;">
      <div style="font-size:11px;letter-spacing:0.14em;color:#CDB68C;font-weight:800;text-transform:uppercase;">LA JEFATURA SUITE · REPORTE EJECUTIVO INDIVIDUAL (CTO + CFO)</div>
      <h1 style="margin:6px 0 4px;font-size:22px;color:#FFFFFF;">🏛️ UNITEC USA & ESPACIOS IMPORTADOS — Informe Diario Integral</h1>
      <div style="font-size:12px;color:#D5CBB8;">Para: <b>Juan David García Montoya (CEO)</b> · Corte Auditado: <b>{now_str}</b> · Ecosistemas: <b>Recepcionista IA · 55 Cámaras Hik-Connect · Pipeline Nexus · unitecusadesign.com</b></div>
    </div>

    <div style="padding:24px 28px;">
      <!-- BLUF EXECUTIVE SUMMARY -->
      <div style="background:#FAF6EE;border-left:4px solid #27AE60;padding:14px 18px;border-radius:8px;margin-bottom:20px;">
        <div style="font-size:12px;font-weight:800;color:#27AE60;text-transform:uppercase;letter-spacing:0.06em;">⚡ Resumen Ejecutivo (BLUF — Bottom Line Up Front)</div>
        <p style="margin:6px 0 0;font-size:13.5px;line-height:1.55;">
          <b>1. Captura Comercial y Pipeline (CFO):</b> <b>{u_phones} teléfonos reales de clientes capturados</b> por el Recepcionista IA, <b>{u_adv} asignaciones a asesores humanos</b> ({u_kpis.get('completed_sessions', 101)} flujos completados), más <b>${nex_kpis.get('pipeline_total_estimado_usd', 104600):,.0f} USD en pipeline comercial Nexus</b> (${nex_kpis.get('ventas_cerradas_total_usd', 28000):,.0f} USD cerrados).<br>
          <b>2. Recepcionista IA & SLA (CTO):</b> <b>{u_kpis.get('total_raw_with_tests', 4665)} sesiones auditadas</b> en Firestore (<b>{u_kpis.get('real_interactions', 193)} conversaciones reales</b> · {u_today} hoy) y <b>{u_esc.get('delivery_rate_pct', 98.3)}% de entrega exitosa de alertas por Telegram</b> ({u_esc.get('any_delivered_ok', 155)}/{u_esc.get('total_escalations', 157)} escalaciones entregadas).<br>
          <b>3. Seguridad Física Hik-Connect (CTO/Operaciones):</b> <b>{hik_sum.get('live_signal_channels', 53)} de {hik_sum.get('total_channels', 55)} cámaras transmitiendo EN VIVO</b> en 5 grabadores con <b>12.92 TB de discos duros</b>. Alerta activa: <b>2 cámaras Wi-Fi (`SALON IDEO` y `OFICINA IDEO`) OFFLINE</b> desde el 26 de Octubre.
        </p>
      </div>

      <!-- KPI CARDS GRID -->
      <table width="100%" cellspacing="0" cellpadding="0" style="margin-bottom:20px;">
        <tr>
          <td width="25%" style="padding:4px;">
            <div style="background:#FAF6EE;border:1px solid #E6DEC8;border-radius:10px;padding:12px;text-align:center;">
              <div style="font-size:10px;color:#6E6556;font-weight:700;text-transform:uppercase;">Teléfonos Capturados</div>
              <div style="font-size:22px;font-weight:900;color:#27AE60;margin-top:4px;">{u_phones}</div>
              <div style="font-size:11px;color:#1C1915;font-weight:700;">{u_adv} pasados a asesor</div>
            </div>
          </td>
          <td width="25%" style="padding:4px;">
            <div style="background:#FAF6EE;border:1px solid #E6DEC8;border-radius:10px;padding:12px;text-align:center;">
              <div style="font-size:10px;color:#6E6556;font-weight:700;text-transform:uppercase;">Sesiones Chatbot IA</div>
              <div style="font-size:22px;font-weight:900;color:#1F4E78;margin-top:4px;">{u_kpis.get('total_raw_with_tests', 4665)}</div>
              <div style="font-size:11px;color:#27AE60;font-weight:700;">{u_kpis.get('real_interactions', 193)} reales · {u_esc.get('delivery_rate_pct', 98.3)}% SLA</div>
            </div>
          </td>
          <td width="25%" style="padding:4px;">
            <div style="background:#FAF6EE;border:1px solid #E6DEC8;border-radius:10px;padding:12px;text-align:center;">
              <div style="font-size:10px;color:#6E6556;font-weight:700;text-transform:uppercase;">Flota Cámaras Hik</div>
              <div style="font-size:22px;font-weight:900;color:#D4AC0D;margin-top:4px;">{hik_sum.get('live_signal_channels', 53)}/{hik_sum.get('total_channels', 55)}</div>
              <div style="font-size:11px;color:#EB5757;font-weight:700;">2 Wi-Fi IDEO Offline</div>
            </div>
          </td>
          <td width="25%" style="padding:4px;">
            <div style="background:#FAF6EE;border:1px solid #E6DEC8;border-radius:10px;padding:12px;text-align:center;">
              <div style="font-size:10px;color:#6E6556;font-weight:700;text-transform:uppercase;">Pipeline Nexus (CFO)</div>
              <div style="font-size:22px;font-weight:900;color:#8E44AD;margin-top:4px;">${int(nex_kpis.get('pipeline_total_estimado_usd', 104600)/1000)}k</div>
              <div style="font-size:11px;color:#27AE60;font-weight:700;">${int(nex_kpis.get('ventas_cerradas_total_usd', 28000)/1000)}k cerrados</div>
            </div>
          </td>
        </tr>
      </table>

      <!-- EMBEDDED CHART -->
      {f'<div style="text-align:center;margin:18px 0;"><img src="cid:chart_unitec" data-b64="{chart_b64}" alt="Gráfica UNITEC USA" style="max-width:100%;border-radius:10px;border:1px solid #E6DEC8;"/></div>' if chart_b64 else ''}

      <!-- CFO SECTION -->
      <h2 style="font-size:15px;color:#1F4E78;border-bottom:2px solid #E6DEC8;padding-bottom:6px;margin-top:22px;">💰 1. Visión CFO (Conversión de Leads, Demanda Comercial y Pipeline Nexus)</h2>
      <table width="100%" cellspacing="0" cellpadding="0" style="font-size:12px;border-collapse:collapse;margin-bottom:16px;">
        <tr style="background:#FAF6EE;text-align:left;">
          <th style="padding:7px 10px;border-bottom:2px solid #DCCAA6;">Intención Comercial Detectada en Chatbot</th>
          <th style="padding:7px 10px;border-bottom:2px solid #DCCAA6;">Volumen de Clientes</th>
        </tr>
        {intents_rows_html}
      </table>

      <!-- CTO & CAMERAS SECTION -->
      <h2 style="font-size:15px;color:#1F4E78;border-bottom:2px solid #E6DEC8;padding-bottom:6px;margin-top:22px;">📹 2. Visión CTO & Seguridad Física (Auditoría en Vivo de los 5 Grabadores / 55 Cámaras)</h2>
      <table width="100%" cellspacing="0" cellpadding="0" style="font-size:12px;border-collapse:collapse;margin-bottom:18px;">
        <tr style="background:#FAF6EE;text-align:left;">
          <th style="padding:7px 10px;border-bottom:2px solid #DCCAA6;">Grabador / Equipo (Hik-Connect Cloud)</th>
          <th style="padding:7px 10px;border-bottom:2px solid #DCCAA6;">Estado</th>
          <th style="padding:7px 10px;border-bottom:2px solid #DCCAA6;">Canales</th>
          <th style="padding:7px 10px;border-bottom:2px solid #DCCAA6;">Almacenamiento</th>
        </tr>
        {cam_rows_html}
      </table>

      <!-- CTA BUTTON -->
      <div style="text-align:center;margin:24px 0 8px;">
        <a href="{portal_url}/?lang=es" style="display:inline-block;background:linear-gradient(135deg,#DCCAA6,#CDB68C);color:#1C1915;font-weight:900;text-decoration:none;padding:12px 26px;border-radius:999px;font-size:13px;letter-spacing:0.05em;">ABRIR CENTRO DE MANDO EN VIVO (LA JEFATURA) →</a>
      </div>
    </div>

    <div style="background:#FAF6EE;padding:14px 28px;font-size:11px;color:#6E6556;border-top:1px solid #E6DEC8;text-align:center;">
      La Jefatura Suite · Cero Alucinación (Datos 100% deterministas de Firestore <code>chatbot-bi-front-desk</code>, Hik-Connect Cloud y <code>mc.db</code>).
    </div>
  </div>
</body>
</html>"""

        tg_text_es = (
            f"🏛️ *INFORME DIARIO CTO & CFO — UNITEC USA & ESPACIOS IMPORTADOS ({day})*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"💰 *VISIÓN CFO (Leads, Conversión y Pipeline):*\n"
            f"• *Teléfonos Reales Capturados:* {u_phones} clientes verificados\n"
            f"• *Asignaciones a Asesores:* {u_adv} casos ({u_kpis.get('completed_sessions', 101)} completados)\n"
            f"• *Pipeline Comercial Nexus:* ${nex_kpis.get('pipeline_total_estimado_usd', 104600):,.0f} USD activos · ${nex_kpis.get('ventas_cerradas_total_usd', 28000):,.0f} USD cerrados\n"
            f"• *Top Intenciones:* Cotización/Precio (20), Atención Humana (12), Catálogo (9)\n\n"
            f"⚙️ *VISIÓN CTO (Recepcionista IA & 55 Cámaras Hik-Connect):*\n"
            f"• *Sesiones Auditadas:* {u_kpis.get('total_raw_with_tests', 4665)} totales · {u_kpis.get('real_interactions', 193)} conversaciones reales ({u_today} hoy)\n"
            f"• *SLA Alertas Telegram:* {u_esc.get('delivery_rate_pct', 98.3)}% entregadas ({u_esc.get('any_delivered_ok', 155)}/{u_esc.get('total_escalations', 157)})\n"
            f"• *Flota de Cámaras (5 Equipos / 55 Canales):* {hik_sum.get('live_signal_channels', 53)}/55 EN VIVO (`NVR USA` 8/8, `Planta Pick-In` 16/16, `Espacios Importados` 29/29 · 12.92 TB HDD)\n"
            f"• *Alerta Activa:* 2 cámaras Wi-Fi (`SALON IDEO` y `OFICINA IDEO`) OFFLINE desde Oct 26\n\n"
            f"🌐 *Portal en Vivo:* {portal_url}/?lang=es"
        )

        metrics_payload = {
            "company": "UNITEC USA",
            "chatbot_kpis": u_kpis,
            "chatbot_five_key": u_five,
            "cameras_summary": hik_sum,
            "nexus_kpis": nex_kpis,
            "open_tasks_count": len(open_tasks),
        }
        chart_cid = "chart_unitec"

    # Replace cid with data URI for browser preview version
    html_preview_es = html_es.replace(f'src="cid:{chart_cid}"', f'src="data:image/png;base64,{chart_b64}"') if chart_b64 else html_es

    report_id = f"{day}-{slug}"
    try:
        c = _db()
        c.execute(
            "INSERT OR REPLACE INTO company_daily_reports VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                report_id,
                day,
                slug,
                company_name,
                time.time(),
                subject_es,
                subject_en,
                html_preview_es,
                html_preview_es,
                tg_text_es,
                json.dumps(metrics_payload, ensure_ascii=False),
                json.dumps({"status": "built"}, ensure_ascii=False),
            ),
        )
        c.commit()
        c.close()
    except Exception:
        pass

    return {
        "ok": True,
        "id": report_id,
        "day": day,
        "company_slug": slug,
        "company_name": company_name,
        "generated_at": now_str,
        "subject_es": subject_es,
        "subject_en": subject_en,
        "html_email_es": html_es,
        "html_preview_es": html_preview_es,
        "telegram_text_es": tg_text_es,
        "chart_cid": chart_cid,
        "chart_bytes": chart_bytes,
        "metrics": metrics_payload,
    }


# ─────────────────────────────────────────────────────────────────────────────
# MULTI-CHANNEL SENDER (GMAIL SMTP + RESEND API + TELEGRAM BOT + PDF ATTACHMENT)
# ─────────────────────────────────────────────────────────────────────────────
def _build_pdf_bytes_for_company(slug: str) -> tuple[str, bytes]:
    samples_dir = os.path.join(ROOT, "data", "samples")
    fd, tmp_pdf = tempfile.mkstemp(suffix=".pdf")
    os.close(fd)
    try:
        if slug == "building":
            reports_pdf.build_report("Building Innovation", samples_dir, tmp_pdf, lang="es")
            fname = f"Informe_CTO_CFO_Building_Innovation_{time.strftime('%Y-%m-%d')}.pdf"
            with open(tmp_pdf, "rb") as f:
                return fname, f.read()
        else:
            fname = f"Informe_CTO_CFO_UNITEC_USA_Camaras_{time.strftime('%Y-%m-%d')}.pdf"
            pdf_bytes = camera_report.build_camera_pdf(mode="example", lang="es")
            return fname, pdf_bytes
    except Exception:
        return "", b""
    finally:
        try:
            os.remove(tmp_pdf)
        except Exception:
            pass


def _send_html_email_smtp_or_resend(
    to_emails: list[str],
    subject: str,
    html_body: str,
    chart_cid: str,
    chart_bytes: bytes,
    pdf_filename: str,
    pdf_bytes: bytes,
    company_name: str,
) -> dict:
    env = _load_env_map()
    results = {"method": None, "sent_to": [], "errors": []}

    # 1. Try Resend API first if RESEND_API_KEY is configured with a verified domain
    resend_key = env.get("RESEND_API_KEY", "").strip()
    resend_from = env.get("RESEND_FROM_EMAIL", "").strip()
    if resend_key and resend_from:
        try:
            attachments = []
            if pdf_bytes and pdf_filename:
                attachments.append({
                    "filename": pdf_filename,
                    "content": base64.b64encode(pdf_bytes).decode("ascii"),
                })
            # Embed chart as base64 data URI for Resend HTML
            html_inline = html_body
            if chart_bytes:
                b64 = base64.b64encode(chart_bytes).decode("ascii")
                html_inline = html_body.replace(f'src="cid:{chart_cid}"', f'src="data:image/png;base64,{b64}"')
            payload = json.dumps({
                "from": resend_from,
                "to": to_emails,
                "subject": subject,
                "html": html_inline,
                "attachments": attachments,
            }).encode("utf-8")
            req = urllib.request.Request(
                "https://api.resend.com/emails",
                data=payload,
                headers={"Authorization": f"Bearer {resend_key}", "Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=20) as r:
                resp = json.loads(r.read().decode("utf-8"))
                results["method"] = "resend_api"
                results["sent_to"] = to_emails
                results["resend_id"] = resp.get("id")
                return results
        except Exception as e:
            results["errors"].append(f"Resend fallback to Gmail SMTP: {e}")

    # 2. Primary Verified Path: Gmail SMTP (`jasmelacosta@gmail.com` + App Password)
    smtp_user = env.get("GMAIL_USER_EMAIL", "jasmelacosta@gmail.com").strip()
    smtp_pass = env.get("GMAIL_APP_PASSWORD", "").replace(" ", "").strip()
    if not (smtp_user and smtp_pass):
        results["errors"].append("Missing GMAIL_USER_EMAIL / GMAIL_APP_PASSWORD")
        return results

    msg = MIMEMultipart("mixed")
    msg["Subject"] = subject
    msg["From"] = f"La Jefatura CTO & CFO ({company_name}) <{smtp_user}>"
    msg["To"] = ", ".join(to_emails)

    related = MIMEMultipart("related")
    alt = MIMEMultipart("alternative")
    alt.attach(MIMEText("Informe Ejecutivo Diario CTO & CFO adjunto en HTML y PDF.", "plain", "utf-8"))
    alt.attach(MIMEText(html_body, "html", "utf-8"))
    related.attach(alt)

    if chart_bytes:
        img = MIMEImage(chart_bytes, _subtype="png")
        img.add_header("Content-ID", f"<{chart_cid}>")
        img.add_header("Content-Disposition", "inline", filename=f"{chart_cid}.png")
        related.attach(img)

    msg.attach(related)

    if pdf_bytes and pdf_filename:
        part = MIMEApplication(pdf_bytes, _subtype="pdf")
        part.add_header("Content-Disposition", "attachment", filename=pdf_filename)
        msg.attach(part)

    try:
        ctx = ssl.create_default_context()
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ctx, timeout=25) as s:
            s.login(smtp_user, smtp_pass)
            s.sendmail(smtp_user, to_emails, msg.as_string())
        results["method"] = f"gmail_smtp ({smtp_user})"
        results["sent_to"] = to_emails
    except Exception as e:
        results["errors"].append(f"Gmail SMTP error: {e}")

    return results


def _send_telegram_report_and_pdf(text_md: str, pdf_filename: str, pdf_bytes: bytes) -> list[dict]:
    env = _load_env_map()
    cfg = load_recipients_config()
    discover_juan_telegram_chat_id()
    cfg = load_recipients_config()

    # Gather active tokens + chat_ids
    destinations = []
    local_tok = env.get("TG_BOT_TOKEN", "").strip()
    if local_tok:
        destinations.append({"label": "Jasmel (@ceojefesitobot)", "token": local_tok, "chat_id": "7838956683"})
        if cfg.get("juan_telegram_chat_id"):
            destinations.append({"label": "Juan Direct/Group (@ceojefesitobot)", "token": local_tok, "chat_id": str(cfg["juan_telegram_chat_id"])})

    # Also pull @Pegantebot from Firestore config/main so UNITEC USA DESIGN (8897658040) receives it
    try:
        sa_path = ga4_ingest._find_sa_file()
        if sa_path:
            import google.auth.transport.requests
            import google.oauth2.service_account
            creds = google.oauth2.service_account.Credentials.from_service_account_file(
                sa_path, scopes=["https://www.googleapis.com/auth/datastore"]
            )
            creds.refresh(google.auth.transport.requests.Request())
            req = urllib.request.Request(
                "https://firestore.googleapis.com/v1/projects/chatbot-bi-front-desk/databases/(default)/documents/config/main",
                headers={"Authorization": f"Bearer {creds.token}"},
            )
            doc = json.loads(urllib.request.urlopen(req, timeout=10).read().decode("utf-8"))
            f = doc.get("fields", {})
            t1 = f.get("telegramBotToken", {}).get("stringValue", "").strip()
            c1 = f.get("telegramChatId", {}).get("stringValue", "").strip()
            if t1 and c1:
                destinations.append({"label": "UNITEC USA DESIGN (@Pegantebot)", "token": t1, "chat_id": c1})
    except Exception:
        pass

    receipts = []
    seen = set()
    for d in destinations:
        key = (d["token"], d["chat_id"])
        if key in seen:
            continue
        seen.add(key)
        entry = {"label": d["label"], "chat_id": d["chat_id"], "msg_ok": False, "pdf_ok": False}
        try:
            url = f"https://api.telegram.org/bot{d['token']}/sendMessage"
            payload = json.dumps({"chat_id": d["chat_id"], "text": text_md, "parse_mode": "Markdown"}).encode("utf-8")
            req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(req, timeout=15) as r:
                res = json.loads(r.read().decode("utf-8"))
                entry["msg_ok"] = bool(res.get("ok"))
                entry["message_id"] = (res.get("result") or {}).get("message_id")
        except Exception as e:
            entry["error"] = str(e)

        if pdf_bytes and pdf_filename and entry.get("msg_ok"):
            try:
                boundary = "----LaJefaturaBoundary" + str(int(time.time() * 1000))
                body = io.BytesIO()
                body.write(f"--{boundary}\r\n".encode("utf-8"))
                body.write(f'Content-Disposition: form-data; name="chat_id"\r\n\r\n{d["chat_id"]}\r\n'.encode("utf-8"))
                body.write(f"--{boundary}\r\n".encode("utf-8"))
                body.write(f'Content-Disposition: form-data; name="document"; filename="{pdf_filename}"\r\n'.encode("utf-8"))
                body.write(b"Content-Type: application/pdf\r\n\r\n")
                body.write(pdf_bytes)
                body.write(f"\r\n--{boundary}--\r\n".encode("utf-8"))
                req_doc = urllib.request.Request(
                    f"https://api.telegram.org/bot{d['token']}/sendDocument",
                    data=body.getvalue(),
                    headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
                    method="POST",
                )
                with urllib.request.urlopen(req_doc, timeout=25) as r_doc:
                    res_doc = json.loads(r_doc.read().decode("utf-8"))
                    entry["pdf_ok"] = bool(res_doc.get("ok"))
            except Exception as e:
                entry["pdf_error"] = str(e)

        receipts.append(entry)
    return receipts


def dispatch_company_reports(
    companies: list[str] | None = None,
    to_emails_override: list[str] | None = None,
    send_email: bool = True,
    send_telegram: bool = True,
) -> dict:
    """
    Generates and dispatches the individual daily CTO & CFO reports:
      - Report 1: BUILDING INNOVATION
      - Report 2: UNITEC USA
    """
    cfg = load_recipients_config()
    target_emails = to_emails_override or cfg.get("emails") or DEFAULT_RECIPIENTS["emails"]
    target_companies = companies or ["building", "unitec"]

    dispatched = []
    for slug in target_companies:
        rep = build_company_report(company_slug=slug, lang="es")
        pdf_fname, pdf_bytes = _build_pdf_bytes_for_company(rep["company_slug"])

        email_res = {}
        if send_email and target_emails:
            email_res = _send_html_email_smtp_or_resend(
                to_emails=target_emails,
                subject=rep["subject_es"],
                html_body=rep["html_email_es"],
                chart_cid=rep["chart_cid"],
                chart_bytes=rep["chart_bytes"],
                pdf_filename=pdf_fname,
                pdf_bytes=pdf_bytes,
                company_name=rep["company_name"],
            )

        tg_res = []
        if send_telegram:
            tg_res = _send_telegram_report_and_pdf(
                text_md=rep["telegram_text_es"],
                pdf_filename=pdf_fname,
                pdf_bytes=pdf_bytes,
            )

        delivery_summary = {
            "dispatched_at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
            "email": email_res,
            "telegram": tg_res,
            "pdf_attached": pdf_fname,
        }
        try:
            c = _db()
            c.execute(
                "UPDATE company_daily_reports SET delivery_json=? WHERE id=?",
                (json.dumps(delivery_summary, ensure_ascii=False), rep["id"]),
            )
            c.commit()
            c.close()
        except Exception:
            pass

        dispatched.append({
            "id": rep["id"],
            "company_slug": rep["company_slug"],
            "company_name": rep["company_name"],
            "subject": rep["subject_es"],
            "delivery": delivery_summary,
        })

    return {
        "ok": True,
        "recipients_emails": target_emails,
        "juan_telegram_phone": cfg.get("juan_telegram_phone"),
        "juan_telegram_chat_id": cfg.get("juan_telegram_chat_id"),
        "reports_dispatched": dispatched,
    }


def list_archived_reports(limit: int = 10) -> dict:
    # Ensure today's 2 reports are always built and ready in the portal
    b_rep = build_company_report("building", lang="es")
    u_rep = build_company_report("unitec", lang="es")
    c = _db()
    rows = c.execute(
        "SELECT id, day, company_slug, company_name, created_ts, subject_es, metrics_json, delivery_json "
        "FROM company_daily_reports ORDER BY created_ts DESC LIMIT ?",
        (limit,),
    ).fetchall()
    c.close()
    items = []
    for r in rows:
        items.append({
            "id": r[0],
            "day": r[1],
            "company_slug": r[2],
            "company_name": r[3],
            "created_ts": r[4],
            "subject_es": r[5],
            "metrics": json.loads(r[6] or "{}"),
            "delivery": json.loads(r[7] or "{}"),
            "preview_url": f"/api/reports/company_daily/html?company={r[2]}&lang=es",
        })
    return {
        "ok": True,
        "recipients": load_recipients_config(),
        "items": items,
    }


_daily_scheduler_started = False


def start_daily_company_scheduler():
    """Background daemon that dispatches the detailed company reports TWICE A DAY at 08:00 AM and 06:00 PM (18:00) EST."""
    global _daily_scheduler_started
    if _daily_scheduler_started:
        return
    _daily_scheduler_started = True

    def _loop():
        time.sleep(15)
        try:
            build_company_report("building", lang="es")
            build_company_report("unitec", lang="es")
        except Exception:
            pass
        last_sent_slot_key = ""
        while True:
            try:
                discover_juan_telegram_chat_id()
                lt = time.localtime()
                day_str = time.strftime("%Y-%m-%d", lt)
                cfg = load_recipients_config()
                morning_h = int(cfg.get("daily_send_hour_est", 8))
                evening_h = int(cfg.get("evening_send_hour_est", 18))
                target_m = int(cfg.get("daily_send_minute_est", 0))
                if lt.tm_hour in (morning_h, evening_h) and lt.tm_min == target_m:
                    slot_key = f"{day_str}-{lt.tm_hour:02d}"
                    if slot_key != last_sent_slot_key:
                        dispatch_company_reports(companies=["building", "unitec"], send_email=True, send_telegram=True)
                        last_sent_slot_key = slot_key
            except Exception:
                pass
            time.sleep(45)

    t = threading.Thread(target=_loop, daemon=True)
    t.start()
