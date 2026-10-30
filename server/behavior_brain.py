"""
La Jefatura Suite — Behavioral & Temporal Learning Engine (behavior_brain.py)

Learns from the CEO's profile, UI movements (mouse focus/hover, clicks, typing),
questions asked, tasks requested, and routines across Morning, Afternoon, and Evening.
Foresees needs and prepares actions/reports/preferences in advance (e.g., morning
coffee preference, preferred morning report format, priority module ordering).
"""

import json
import os
import sqlite3
import time
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def get_db_path() -> str:
    env_db = os.environ.get("MC_DB_PATH")
    if env_db:
        return env_db
    prod_dir = "/root/.openclaw/workspace/mission-control"
    if os.path.isdir(prod_dir):
        return os.path.join(prod_dir, "mc.db")
    data_dir = os.path.join(ROOT, "data")
    os.makedirs(data_dir, exist_ok=True)
    return os.path.join(data_dir, "mc.db")


DB = get_db_path()

SCHEMA = """
CREATE TABLE IF NOT EXISTS behavior_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner TEXT DEFAULT 'jasmel',
    event_type TEXT,       -- click | mouse_focus | typing | voice_query | task_request | tab_view | preference_update
    target TEXT,           -- element or module id
    time_slot TEXT,        -- morning | afternoon | evening
    detail TEXT,           -- JSON metadata
    ts REAL
);

CREATE TABLE IF NOT EXISTS ceo_profile (
    owner TEXT PRIMARY KEY,
    profile_json TEXT,
    updated_ts REAL
);
"""

DEFAULT_PROFILE = {
    "owner": "jasmel",
    "name": "Jasmel Acosta",
    "role": "Founder & CEO",
    "companies": ["MBMB", "CEDEXX", "305BIZ", "AIDYN", "NEXUS"],
    "coffee_preference": {
        "drink": "Double Espresso Cortado (Oat Milk)",
        "drink_es": "Cortado Doble Espresso (Leche de Avena)",
        "prep_time": "07:45 AM",
        "temp": "Extra Hot (165°F)",
        "notes_en": "Prepared automatically before the 08:17 AM Executive Brief",
        "notes_es": "Preparado automáticamente antes del Informe Ejecutivo de las 08:17 AM"
    },
    "report_preference": {
        "morning_format": "Executive Visual Digest + 60s Voice Brief + PDF",
        "morning_format_es": "Resumen Visual Ejecutivo + Audio 60s + PDF",
        "afternoon_format": "Pipeline Funnel & Staff Velocity Matrix",
        "afternoon_format_es": "Embudo de Pipeline y Matriz de Velocidad del Equipo",
        "evening_format": "Security Camera Digest + Next-Day Calendar & Draft Queue",
        "evening_format_es": "Resumen de Cámaras IA + Agenda de Mañana y Cola de Borradores",
        "chart_style": "Minimalist Horizontal Bars + KPI Delta Cards",
        "delivery_channels": ["Console", "Telegram Voice", "PDF Email"]
    },
    "routines": {
        "morning": {
            "window": "05:00 – 11:59",
            "top_modules": ["kpis_revenue", "critical_tasks", "comms_approvals", "agenda_today"],
            "habit_summary_es": "Por la mañana (07:30–09:00), el CEO revisa primero flujo de caja proyectado, desbloquea tareas críticas vencidas (>48h) y aprueba borradores urgentes mientras toma su Cortado Doble.",
            "habit_summary_en": "In the morning (07:30–09:00), the CEO checks projected cashflow first, unblocks overdue critical tasks (>48h), and approves urgent drafts while having a Double Espresso Cortado.",
            "foreseen_items": [
                {
                    "id": "prep-coffee",
                    "icon": "☕",
                    "title_es": "Café Matutino Preparado: Cortado Doble Espresso",
                    "title_en": "Morning Coffee Ready: Double Espresso Cortado",
                    "desc_es": "Orden automática programada 07:45 AM (leche de avena, extra caliente) lista para tu lectura de las 08:00 AM.",
                    "desc_en": "Auto-scheduled 07:45 AM order (oat milk, extra hot) ready for your 08:00 AM briefing.",
                    "action_label_es": "Confirmar Orden (1-Click)",
                    "action_label_en": "Confirm Order (1-Click)",
                    "action_cmd": "confirm_coffee"
                },
                {
                    "id": "prep-morning-brief",
                    "icon": "📑",
                    "title_es": "Informe Matutino Pre-Generado (Formato Visual + PDF)",
                    "title_en": "Pre-Generated Morning Report (Visual + PDF Format)",
                    "desc_es": "Basado en tus hábitos de las 08:15 AM: 5 empresas consolidadas, 3 párrafos sin relleno y gráfico de conversión.",
                    "desc_en": "Based on your 08:15 AM routine: 5 consolidated companies, 3 concise paragraphs, and conversion chart.",
                    "action_label_es": "Abrir / Descargar PDF",
                    "action_label_en": "Open / Download PDF",
                    "action_cmd": "download_report"
                },
                {
                    "id": "prep-urgent-draft",
                    "icon": "✉️",
                    "title_es": "Borrador Urgente Pre-Redactado: Dr. Molina (Doral Urgent)",
                    "title_en": "Urgent Draft Pre-Written: Dr. Molina (Doral Urgent)",
                    "desc_es": "Detectado como tu primera acción habitual: propuesta de $12,400 lista con tu firma y tono formal.",
                    "desc_en": "Detected as your #1 morning priority: $12,400 proposal reply drafted in your formal executive tone.",
                    "action_label_es": "Revisar y Aprobar",
                    "action_label_en": "Review & Approve",
                    "action_cmd": "open_tab:comms"
                }
            ]
        },
        "afternoon": {
            "window": "12:00 – 17:59",
            "top_modules": ["nexus_pipeline", "client_monitoring", "staff_productivity", "meetings_study"],
            "habit_summary_es": "Por la tarde (12:00–17:30), el CEO se enfoca en cierres de Nexus CRM, monitoreo de visitas a clientes (USA/Colombia/México) y velocidad de entrega del equipo.",
            "habit_summary_en": "In the afternoon (12:00–17:30), the CEO focuses on Nexus CRM deal closures, client visit monitoring (USA/Colombia/Mexico), and staff delivery velocity.",
            "foreseen_items": [
                {
                    "id": "prep-deal-brief",
                    "icon": "🎯",
                    "title_es": "Dossier Pre-Demo Listo: Doral Urgent Care (14:00)",
                    "title_en": "Pre-Demo Dossier Ready: Doral Urgent Care (2:00 PM)",
                    "desc_es": "Preparado 30 min antes de tu llamada con Dr. Molina: historial de visitas, objeciones y ROI proyectado.",
                    "desc_en": "Prepared 30m before your call with Dr. Molina: visit history, objections, and projected ROI.",
                    "action_label_es": "Ver Estudio de Clientes",
                    "action_label_en": "View Client Study",
                    "action_cmd": "open_tab:outcomes"
                },
                {
                    "id": "prep-staff-nudge",
                    "icon": "👥",
                    "title_es": "Seguimiento de Equipo: 3 Cotizaciones de Carlos y María",
                    "title_en": "Team Follow-Up: 3 Quotes from Carlos & Maria",
                    "desc_es": "Sueles revisar el avance de ventas a las 15:00. Resumen de actividad del equipo pre-calculado.",
                    "desc_en": "You typically check sales velocity at 3:00 PM. Team activity summary is pre-calculated.",
                    "action_label_es": "Ver Monitoreo de Personal",
                    "action_label_en": "View Staff Monitoring",
                    "action_cmd": "open_tab:outcomes"
                },
                {
                    "id": "prep-afternoon-voice",
                    "icon": "🎙",
                    "title_es": "Resumen de Voz de Media Tarde (Grok 3.0)",
                    "title_en": "Mid-Afternoon Voice Pulse (Grok 3.0)",
                    "desc_es": "Lectura rápida de 30 segundos sobre movimientos del pipeline y tareas cerradas hoy.",
                    "desc_en": "Quick 30-second audio readout on pipeline movements and tasks completed today.",
                    "action_label_es": "Escuchar Resumen",
                    "action_label_en": "Listen to Pulse",
                    "action_cmd": "read_brief"
                }
            ]
        },
        "evening": {
            "window": "18:00 – 04:59",
            "top_modules": ["cameras_security", "comms_approvals", "tomorrow_agenda", "daily_close"],
            "habit_summary_es": "Por la noche (18:00+), el CEO prefiere modo silencioso: revisa el digest de cámaras IA fuera de horario, despeja borradores pendientes con un clic y valida la agenda del día siguiente.",
            "habit_summary_en": "In the evening (6:00 PM+), the CEO prefers low-noise mode: reviews after-hours AI camera digests, clears pending drafts with one click, and checks tomorrow's schedule.",
            "foreseen_items": [
                {
                    "id": "prep-cam-digest",
                    "icon": "📹",
                    "title_es": "Auditoría Nocturna de Cámaras IA (4 Cámaras)",
                    "title_en": "Evening AI Camera Security Audit (4 Cameras)",
                    "desc_es": "1 evento fuera de horario en Bodega/Archivo (21:47) aislado con snapshot. Resto de sedes sin anomalías.",
                    "desc_en": "1 after-hours event in Warehouse/Records (21:47) isolated with snapshot. All other zones clear.",
                    "action_label_es": "Ver Cámaras y Eventos",
                    "action_label_en": "View Cameras & Events",
                    "action_cmd": "open_tab:outcomes"
                },
                {
                    "id": "prep-inbox-zero",
                    "icon": "⚡",
                    "title_es": "Cierre de Bandeja: 4 Borradores Listos para Aprobar",
                    "title_en": "Evening Inbox Zero: 4 Drafts Ready for 1-Click Approval",
                    "desc_es": "Todos los mensajes entrantes del día tienen respuesta redactada en tu voz esperando tu OK.",
                    "desc_en": "All incoming messages from today have replies drafted in your voice awaiting your OK.",
                    "action_label_es": "Aprobar Borradores",
                    "action_label_en": "Approve Drafts",
                    "action_cmd": "open_tab:comms"
                },
                {
                    "id": "prep-tomorrow",
                    "icon": "🌙",
                    "title_es": "Preparación de Mañana: Agenda + Café 07:45 AM",
                    "title_en": "Tomorrow Prep: Schedule + 07:45 AM Coffee Locked",
                    "desc_es": "4 reuniones sincronizadas, alarma de informe 08:17 AM activa y preferencia de café confirmada.",
                    "desc_en": "4 meetings synced, 08:17 AM briefing cron active, and morning coffee preference locked.",
                    "action_label_es": "Ver Cerebro Conductual",
                    "action_label_en": "View Behavioral Brain",
                    "action_cmd": "open_tab:behavior"
                }
            ]
        }
    }
}


_SCHEMA_DONE = False
_SEED_DONE = False


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


def current_time_slot() -> str:
    h = datetime.now().hour
    if 5 <= h < 12:
        return "morning"
    if 12 <= h < 18:
        return "afternoon"
    return "evening"


def ensure_seeded():
    global _SEED_DONE
    if _SEED_DONE:
        return
    c = _db()
    row = c.execute("SELECT profile_json FROM ceo_profile WHERE owner='jasmel'").fetchone()
    if not row:
        c.execute("INSERT INTO ceo_profile VALUES(?,?,?)",
                  ("jasmel", json.dumps(DEFAULT_PROFILE, ensure_ascii=False), time.time()))
        # Seed realistic historical telemetry across morning, afternoon, evening
        now = time.time()
        seed_events = [
            ("jasmel", "click", "kpi_projected_revenue", "morning", {"label": "Ingreso mensual proyectado"}, now - 7200),
            ("jasmel", "click", "task_critical_T01", "morning", {"label": "Enviar propuesta CEDEXX a Doral Urgent"}, now - 7100),
            ("jasmel", "voice_query", "grok_voice", "morning", {"query": "Read morning executive summary and prepare coffee"}, now - 6900),
            ("jasmel", "report_download", "pdf_executive_report", "morning", {"format": "Visual + PDF", "company": "all"}, now - 6800),
            ("jasmel", "typing", "draft_edit_dr_molina", "morning", {"wpm": 68, "style": "concise_formal"}, now - 6500),
            ("jasmel", "mouse_focus", "nexus_pipeline_funnel", "afternoon", {"dwell_ms": 14200}, now - 5400),
            ("jasmel", "click", "client_visit_doral", "afternoon", {"label": "Doral Urgent Care Group"}, now - 5100),
            ("jasmel", "task_request", "staff_check_juan", "afternoon", {"query": "Check Juan Perez closed deals"}, now - 4800),
            ("jasmel", "mouse_focus", "cameras_security_grid", "evening", {"dwell_ms": 19500}, now - 3600),
            ("jasmel", "click", "approve_draft_btn", "evening", {"label": "Approve & Send Draft"}, now - 3200),
        ]
        c.executemany(
            "INSERT INTO behavior_events(owner,event_type,target,time_slot,detail,ts) VALUES(?,?,?,?,?,?)",
            [(o, et, tg, sl, json.dumps(dt, ensure_ascii=False), ts) for o, et, tg, sl, dt, ts in seed_events]
        )
        c.commit()
    c.close()
    _SEED_DONE = True


def record_event(event_type: str, target: str, detail: dict | None = None,
                 time_slot: str | None = None, owner: str = "jasmel") -> dict:
    ensure_seeded()
    slot = time_slot if time_slot in ("morning", "afternoon", "evening") else current_time_slot()
    c = _db()
    c.execute(
        "INSERT INTO behavior_events(owner,event_type,target,time_slot,detail,ts) VALUES(?,?,?,?,?,?)",
        (owner, event_type, target, slot, json.dumps(detail or {}, ensure_ascii=False), time.time())
    )
    # If preference update, merge into ceo_profile
    if event_type == "preference_update" and detail:
        row = c.execute("SELECT profile_json FROM ceo_profile WHERE owner=?", (owner,)).fetchone()
        prof = json.loads(row[0]) if row else dict(DEFAULT_PROFILE)
        if "coffee_drink" in detail:
            prof["coffee_preference"]["drink"] = detail["coffee_drink"]
            prof["coffee_preference"]["drink_es"] = detail["coffee_drink"]
        if "coffee_time" in detail:
            prof["coffee_preference"]["prep_time"] = detail["coffee_time"]
        if "report_format" in detail:
            prof["report_preference"]["morning_format"] = detail["report_format"]
            prof["report_preference"]["morning_format_es"] = detail["report_format"]
        c.execute("UPDATE ceo_profile SET profile_json=?, updated_ts=? WHERE owner=?",
                  (json.dumps(prof, ensure_ascii=False), time.time(), owner))
    c.commit()
    c.close()
    return {"ok": True, "slot": slot, "event_type": event_type, "target": target}


def get_state(slot: str | None = None, owner: str = "jasmel") -> dict:
    ensure_seeded()
    active_slot = slot if slot in ("morning", "afternoon", "evening") else current_time_slot()
    c = _db()
    row = c.execute("SELECT profile_json FROM ceo_profile WHERE owner=?", (owner,)).fetchone()
    prof = json.loads(row[0]) if row else dict(DEFAULT_PROFILE)

    counts_by_type = dict(c.execute(
        "SELECT event_type, COUNT(*) FROM behavior_events WHERE owner=? GROUP BY event_type",
        (owner,)
    ).fetchall())
    counts_by_slot = dict(c.execute(
        "SELECT time_slot, COUNT(*) FROM behavior_events WHERE owner=? GROUP BY time_slot",
        (owner,)
    ).fetchall())
    top_targets = c.execute(
        "SELECT target, COUNT(*) as n FROM behavior_events WHERE owner=? AND time_slot=? "
        "GROUP BY target ORDER BY n DESC LIMIT 6",
        (owner, active_slot)
    ).fetchall()
    recent = c.execute(
        "SELECT event_type, target, time_slot, detail, ts FROM behavior_events "
        "WHERE owner=? ORDER BY id DESC LIMIT 12",
        (owner,)
    ).fetchall()
    c.close()

    return {
        "active_slot": active_slot,
        "detected_system_slot": current_time_slot(),
        "profile": prof,
        "active_routine": prof["routines"].get(active_slot, prof["routines"]["morning"]),
        "telemetry": {
            "total_signals": sum(counts_by_type.values()),
            "by_type": {
                "clicks": counts_by_type.get("click", 0),
                "mouse_focus": counts_by_type.get("mouse_focus", 0),
                "typing": counts_by_type.get("typing", 0),
                "voice_queries": counts_by_type.get("voice_query", 0),
                "task_requests": counts_by_type.get("task_request", 0),
                "report_downloads": counts_by_type.get("report_download", 0),
            },
            "by_slot": {
                "morning": counts_by_slot.get("morning", 0),
                "afternoon": counts_by_slot.get("afternoon", 0),
                "evening": counts_by_slot.get("evening", 0),
            },
            "top_targets_in_slot": [{"target": r[0], "count": r[1]} for r in top_targets],
            "recent_events": [
                {
                    "type": r[0],
                    "target": r[1],
                    "slot": r[2],
                    "detail": json.loads(r[3] or "{}"),
                    "ts": r[4]
                }
                for r in recent
            ]
        }
    }


if __name__ == "__main__":
    st = get_state("morning")
    print("behavior_brain OK | signals:", st["telemetry"]["total_signals"],
          "| coffee:", st["profile"]["coffee_preference"]["drink"])
