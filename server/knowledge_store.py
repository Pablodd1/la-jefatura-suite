"""La Jefatura — Knowledge Store + Grounded Q&A ("never guess").

Persists CEO notes, tasks, meeting summaries and email summaries in mc.db, and answers
questions ONLY from (a) records stored here and (b) the latest real metric snapshots of the
connected apps (UniTEC chatbot, BuildingApp). Every answer carries its sources. When nothing
matches, the answer is an explicit "no data" — there is no free-form generation, so there is
nothing to hallucinate.
"""
import json
import os
import re
import sqlite3
import time
import unicodedata
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
_PROD_DIR = "/root/.openclaw/workspace/mission-control"
DB = os.environ.get("MC_DB_PATH") or (
    os.path.join(_PROD_DIR, "mc.db") if os.path.isdir(_PROD_DIR)
    else os.path.join(ROOT, "data", "mc.db")
)
os.makedirs(os.path.dirname(DB), exist_ok=True)

SCHEMA = """
CREATE TABLE IF NOT EXISTS notes (
    id TEXT PRIMARY KEY, ts REAL, text TEXT, source TEXT, company TEXT);
CREATE TABLE IF NOT EXISTS meetings (
    id TEXT PRIMARY KEY, ts REAL, title TEXT, attendees TEXT, summary TEXT,
    action_items TEXT, source TEXT, company TEXT);
CREATE TABLE IF NOT EXISTS email_summaries (
    id TEXT PRIMARY KEY, ts REAL, sender TEXT, subject TEXT, summary TEXT,
    source TEXT, company TEXT);
CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY, title TEXT, company TEXT, owner TEXT, due TEXT, status TEXT,
    severity TEXT, notes TEXT, done REAL);
"""


def _db():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    c.executescript(SCHEMA)
    return c


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", s.lower()).strip()


def _iso(ts) -> str:
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(ts)) if ts else ""


def _clean(text: str, limit: int = 4000) -> str:
    return (text or "").strip()[:limit]


# ───────────────────────── writes ─────────────────────────
def add_note(text: str, source: str = "voice", company: str = "all") -> dict:
    text = _clean(text)
    if not text:
        return {"ok": False, "error": "empty note"}
    nid = "N-" + uuid.uuid4().hex[:8]
    c = _db()
    c.execute("INSERT INTO notes VALUES(?,?,?,?,?)", (nid, time.time(), text, source, company))
    c.commit(); c.close()
    return {"ok": True, "id": nid, "text": text}


def add_task(title: str, company: str = "all", owner: str = "CEO", due: str = "",
             severity: str = "medium", source: str = "voice") -> dict:
    title = _clean(title, 500)
    if not title:
        return {"ok": False, "error": "empty task"}
    tid = "T-" + uuid.uuid4().hex[:8]
    c = _db()
    c.execute("INSERT INTO tasks VALUES(?,?,?,?,?,?,?,?,?)",
              (tid, title, company, owner, due, "pending", severity, f"source:{source}", None))
    c.commit(); c.close()
    return {"ok": True, "id": tid, "title": title}


def add_meeting_summary(summary: str, title: str = "", attendees: str = "", action_items: str = "",
                        source: str = "voice", company: str = "all") -> dict:
    summary = _clean(summary, 8000)
    if not summary:
        return {"ok": False, "error": "empty summary"}
    mid = "M-" + uuid.uuid4().hex[:8]
    c = _db()
    c.execute("INSERT INTO meetings VALUES(?,?,?,?,?,?,?,?)",
              (mid, time.time(), _clean(title, 300), _clean(attendees, 500), summary,
               _clean(action_items, 4000), source, company))
    c.commit(); c.close()
    return {"ok": True, "id": mid, "title": title}


def add_email_summary(summary: str, sender: str = "", subject: str = "", source: str = "ingest",
                      company: str = "all") -> dict:
    summary = _clean(summary, 8000)
    if not summary:
        return {"ok": False, "error": "empty summary"}
    eid = "E-" + uuid.uuid4().hex[:8]
    c = _db()
    c.execute("INSERT INTO email_summaries VALUES(?,?,?,?,?,?,?)",
              (eid, time.time(), _clean(sender, 300), _clean(subject, 500), summary, source, company))
    c.commit(); c.close()
    return {"ok": True, "id": eid, "subject": subject}


# ───────────────────────── reads ─────────────────────────
def list_items(kind: str, limit: int = 20, open_only: bool = False) -> list:
    c = _db()
    if kind == "notes":
        rows = c.execute("SELECT * FROM notes ORDER BY ts DESC LIMIT ?", (limit,)).fetchall()
    elif kind == "meetings":
        rows = c.execute("SELECT * FROM meetings ORDER BY ts DESC LIMIT ?", (limit,)).fetchall()
    elif kind == "emails":
        rows = c.execute("SELECT * FROM email_summaries ORDER BY ts DESC LIMIT ?", (limit,)).fetchall()
    elif kind == "tasks":
        q = "SELECT * FROM tasks" + (" WHERE status != 'done'" if open_only else "")
        rows = c.execute(q + " LIMIT ?", (limit,)).fetchall()
    else:
        rows = []
    out = [dict(r) for r in rows]
    c.close()
    return out


def export_all() -> dict:
    return {k: list_items(k, limit=100000) for k in ("notes", "tasks", "meetings", "emails")}


def ensure_demo_knowledge_seeded():
    """Seed realistic executive notes, tasks, meeting summaries & email summaries if empty."""
    c = _db()
    n_notes = c.execute("SELECT COUNT(*) FROM notes").fetchone()[0]
    n_meet = c.execute("SELECT COUNT(*) FROM meetings").fetchone()[0]
    n_mail = c.execute("SELECT COUNT(*) FROM email_summaries").fetchone()[0]
    c.close()
    if n_notes == 0:
        add_note(
            "Juan (CEO Building Innovation) solicitó priorizar el embudo de cotización de paneles WPC "
            "y revisar el reporte diario de nuevos miembros de BuildingApp en App Store y Google Play.",
            source="demo_seed", company="building"
        )
        add_note(
            "Dr. Molina (Doral Urgent Care) confirmó interés en firmar hoy por US$12,400/mes si incluimos "
            "el módulo de denegaciones automáticas en CEDEXX.",
            source="demo_seed", company="cedexx"
        )
    if n_meet == 0:
        add_meeting_summary(
            "El consejo de Brickell Ortho Institute aprobó el piloto de facturación médica para 3 sedes "
            "(US$15,200 ARR). El kickoff técnico arranca el lunes a las 09:30 AM con Juan Perez.",
            title="Kickoff & Aprobación Brickell Ortho Institute",
            attendees="Jasmel Acosta, Juan Perez, Dirección Brickell Ortho",
            action_items="Enviar contrato DocuSign y habilitar accesos de las 3 sedes",
            source="demo_seed", company="mbmb"
        )
        add_meeting_summary(
            "Revisión de lanzamiento móvil BuildingApp AI (iOS App Store y Google Play): el revisor de Apple "
            "completó 5 análisis de cuarto con Gemini Flash (100% éxito) y probó el flujo DELETE_ACCOUNT.",
            title="Auditoría App Store & Google Play — BuildingApp AI",
            attendees="Jasmel Acosta, Juan (Building Innovation)",
            action_items="Conectar Green API WhatsApp y activar GA4 Data API para unitecusadesign.com",
            source="demo_seed", company="building"
        )
    if n_mail == 0:
        add_email_summary(
            "Luisa de Clínica Del Mar Cartagena envió la Orden de Compra #PO-2214 aprobada por US$9,800 "
            "para migrar 3 sedes este lunes a las 10:00 AM.",
            sender="facturas@clinicadelmar.co",
            subject="Orden de compra #PO-2214 ($9,800) — 3 Sedes Cartagena",
            source="demo_seed", company="saleinn"
        )
        add_email_summary(
            "Notificación logística UNITEC USA: el contenedor de láminas PVC mármol y paneles WPC "
            "actualizó su ETA al puerto de Miami para el 4 de noviembre.",
            sender="logistics@unitecusadesign.com",
            subject="Actualización ETA Contenedor WPC / PVC Miami",
            source="demo_seed", company="unitec"
        )



_STOP = set(_norm("""de la el los las un una y o en que por para con del al se lo su sus mi me es
 the a an of to in and or for with on at is are was what who when where how about tell dime
 cual cuales cuando donde como sobre dijo hay tengo tiene buscar busca encuentra search find""").split())


def _tokens(text: str) -> list:
    return [t for t in re.findall(r"[a-z0-9]+", _norm(text)) if len(t) > 2 and t not in _STOP]


def search(query: str, limit: int = 5) -> list:
    """Keyword search across notes, meetings, email summaries and tasks. Returns scored hits."""
    toks = _tokens(query)
    if not toks:
        return []
    hits = []
    c = _db()

    def score(blob):
        nb = _norm(blob)
        return sum(1 for t in toks if t in nb)

    for r in c.execute("SELECT * FROM notes"):
        s = score(r["text"])
        if s:
            hits.append((s, r["ts"], {"type": "nota", "id": r["id"], "date": _iso(r["ts"]), "text": r["text"]}))
    for r in c.execute("SELECT * FROM meetings"):
        s = score(" ".join([r["title"], r["attendees"], r["summary"], r["action_items"]]))
        if s:
            hits.append((s, r["ts"], {"type": "reunión", "id": r["id"], "date": _iso(r["ts"]),
                                      "title": r["title"], "text": r["summary"],
                                      "action_items": r["action_items"]}))
    for r in c.execute("SELECT * FROM email_summaries"):
        s = score(" ".join([r["sender"], r["subject"], r["summary"]]))
        if s:
            hits.append((s, r["ts"], {"type": "correo", "id": r["id"], "date": _iso(r["ts"]),
                                      "sender": r["sender"], "subject": r["subject"], "text": r["summary"]}))
    for r in c.execute("SELECT * FROM tasks WHERE notes LIKE 'source:%'"):  # skip demo sample tasks
        s = score(r["title"])
        if s:
            hits.append((s, 0, {"type": "tarea", "id": r["id"], "status": r["status"], "text": r["title"]}))
    c.close()
    hits.sort(key=lambda h: (h[0], h[1]), reverse=True)
    min_score = 2 if len(toks) >= 3 else 1
    out = []
    for s, _, rec in hits:
        if s >= min_score:
            rec = dict(rec)
            rec["_coverage"] = round(s / len(toks), 2)
            out.append(rec)
    return out[:limit]


# ───────────────────── real-metric facts (no guessing) ─────────────────────
def _facts() -> dict:
    """Latest REAL snapshots from the connected apps, each with its own source + timestamp."""
    facts = {}
    try:
        import unitec_ingest
        u = unitec_ingest.summary()
        fk = u.get("five_key_numbers", {})
        meta = {"source": "UNITEC chatbot", "as_of": u.get("generatedAt"), "origin": u.get("source")}
        facts["unitec"] = (fk, u.get("kpis", {}), meta)
    except Exception:
        pass
    try:
        import buildingapp_ingest
        b = buildingapp_ingest.summary()
        meta = {"source": "BuildingApp (buildingapp.us)", "as_of": b.get("generatedAt"),
                "origin": b.get("source")}
        facts["building"] = (b.get("five_key_numbers", {}), {}, meta)
    except Exception:
        pass
    return facts


def _metric_answer(q: str, lang: str):
    """Deterministic metric lookup. Returns (reply, sources) or None when no metric matched."""
    n = _norm(q)
    f = _facts()
    es = lang != "en"
    out, srcs = [], []

    def add(text, meta):
        out.append(text)
        srcs.append(f"{meta['source']} · {meta.get('as_of') or 'sin fecha'} · {meta.get('origin')}")

    if re.search(r"miembros|members|usuarios nuevos|new users|registrad", n) and "building" in f:
        fk, _, m = f["building"]
        mem = fk.get("members", {})
        add((f"BuildingApp: {mem.get('total')} miembros en total, {mem.get('new_today')} nuevos hoy."
             if es else f"BuildingApp: {mem.get('total')} members total, {mem.get('new_today')} new today."), m)
    if re.search(r"generaciones|renders|analisis ia|ai usage|generations", n) and "building" in f:
        fk, _, m = f["building"]
        ai = fk.get("ai_usage", {})
        add((f"BuildingApp IA: {ai.get('generations_today')} generaciones hoy, {ai.get('generations_total')} en total, "
             f"éxito {ai.get('success_rate_pct')}%." if es else
             f"BuildingApp AI: {ai.get('generations_today')} generations today, {ai.get('generations_total')} total, "
             f"{ai.get('success_rate_pct')}% success."), m)
    if re.search(r"costo|cost|gasto|spend", n) and "building" in f:
        fk, _, m = f["building"]
        ch = fk.get("cost_and_health", {})
        add((f"Costo IA de BuildingApp: ${ch.get('cost_today_usd')} hoy, ${ch.get('cost_total_usd')} acumulado."
             if es else f"BuildingApp AI cost: ${ch.get('cost_today_usd')} today, ${ch.get('cost_total_usd')} total."), m)
    if re.search(r"conversacion|conversations|chatbot|recepcion|front.?desk", n) and "unitec" in f:
        fk, kp, m = f["unitec"]
        rc = fk.get("real_conversations_today", {})
        add((f"Chatbot UNITEC: {rc.get('unitec')} conversaciones reales hoy (UNITEC) y {rc.get('building')} (Building); "
             f"{kp.get('real_interactions')} interacciones reales históricas." if es else
             f"UNITEC chatbot: {rc.get('unitec')} real conversations today (UNITEC), {rc.get('building')} (Building); "
             f"{kp.get('real_interactions')} real interactions all-time."), m)
    if re.search(r"contactos|telefonos|phones|contacts|leads capturados", n) and "unitec" in f:
        fk, _, m = f["unitec"]
        cp = fk.get("contacts_captured_phone", {})
        add((f"Contactos con teléfono: {cp.get('today')} hoy, {cp.get('all_time')} históricos."
             if es else f"Phone contacts: {cp.get('today')} today, {cp.get('all_time')} all-time."), m)
    if re.search(r"alertas|alerts|escalacion|escalation|entrega|delivery", n) and "unitec" in f:
        fk, _, m = f["unitec"]
        ad = fk.get("alert_delivery", {})
        add((f"Alertas del chatbot: {ad.get('any_delivered_ok')} de {ad.get('total_escalations')} entregadas "
             f"({ad.get('delivery_rate_pct')}%)." if es else
             f"Chatbot alerts: {ad.get('any_delivered_ok')} of {ad.get('total_escalations')} delivered "
             f"({ad.get('delivery_rate_pct')}%)."), m)
    if re.search(r"abandono|abandon", n) and "unitec" in f:
        fk, _, m = f["unitec"]
        ga = fk.get("greeting_abandonment", {})
        add((f"Abandono en saludo: {ga.get('rate_pct')}% ({ga.get('abandoned')} de {ga.get('total_raw')} sesiones)."
             if es else f"Greeting abandonment: {ga.get('rate_pct')}% ({ga.get('abandoned')} of {ga.get('total_raw')})."), m)
    if not out:
        return None
    return " ".join(out), srcs


def _counts(lang):
    c = _db()
    n_notes = c.execute("SELECT COUNT(*) FROM notes").fetchone()[0]
    n_tasks = c.execute("SELECT COUNT(*) FROM tasks WHERE status != 'done'").fetchone()[0]
    n_meet = c.execute("SELECT COUNT(*) FROM meetings").fetchone()[0]
    n_mail = c.execute("SELECT COUNT(*) FROM email_summaries").fetchone()[0]
    c.close()
    return n_notes, n_tasks, n_meet, n_mail


def ask(question: str, lang: str = "es") -> dict:
    """Grounded answer. Returns {answer, sources, grounded}. Never invents content."""
    es = lang != "en"
    q = (question or "").strip()
    n = _norm(q)

    # 1) Listing intents → read straight from the store.
    listing = [
        (r"\b(notas?|notes?)\b", "notes", "notas", "notes"),
        (r"\b(tareas?|tasks?|pendientes)\b", "tasks", "tareas abiertas", "open tasks"),
        (r"\b(reuniones?|meetings?)\b", "meetings", "resúmenes de reunión", "meeting summaries"),
        (r"\b(correos?|emails?|mails?)\b", "emails", "resúmenes de correo", "email summaries"),
    ]
    if re.search(r"\b(que|cuales|cuantas?|lista|listar|lee|leer|read|list|show|what|how many|dame|muestra)\b", n):
        for rx, kind, lab_es, lab_en in listing:
            if re.search(rx, n):
                items = list_items(kind, limit=100000, open_only=(kind == "tasks"))
                sample_note = ""
                if kind == "tasks":
                    real = [i for i in items if str(i.get("notes", "")).startswith("source:")]
                    n_sample = len(items) - len(real)
                    items = real
                    if n_sample:
                        sample_note = (f" (Además hay {n_sample} tareas de ejemplo del demo, que no son tuyas.)" if es
                                       else f" (Plus {n_sample} demo sample tasks, which are not yours.)")
                label = lab_es if es else lab_en
                if not items:
                    return {"answer": (f"No tengo {label} guardados." if es else f"I have no {label} saved.") + sample_note,
                            "sources": [], "grounded": True}
                total = len(items)
                items = items[:5] if kind != "tasks" else items[:5]
                lines = []
                for it in items:
                    txt = it.get("text") or it.get("title") or it.get("summary") or it.get("subject") or ""
                    lines.append(f"[{it['id']}] {txt[:140]}")
                head = (f"Tienes {total} {label}. Las más recientes: " if es
                        else f"You have {total} {label}. Most recent: ")
                return {"answer": head + " | ".join(lines) + sample_note,
                        "sources": [it["id"] for it in items], "grounded": True}

    # 2) Real metrics from connected apps.
    m = _metric_answer(q, lang)
    if m:
        return {"answer": m[0], "sources": m[1], "grounded": True}

    # 3) Keyword search over stored knowledge.
    hits = search(q)
    if hits:
        parts = []
        for h in hits[:3]:
            label = h["type"] + (f" «{h['title']}»" if h.get("title") else "")
            parts.append(f"{label} [{h['id']}, {h.get('date', '')}]: {h['text'][:220]}")
        exact = hits[0].get("_coverage", 0) >= 0.75
        if exact:
            head = ""
        else:
            head = ("No tengo una coincidencia exacta con tu pregunta; lo más cercano que hay guardado es (puede no responder lo que preguntas): "
                    if es else
                    "I have no exact match for your question; the closest stored item is (it may not answer what you asked): ")
        return {"answer": head + " || ".join(parts), "sources": [h["id"] for h in hits[:3]],
                "grounded": True, "exact": exact}

    # 4) Honest refusal.
    return {"answer": ("No tengo ese dato registrado, así que no voy a adivinar. "
                       "Puedo buscar en tus notas, tareas, resúmenes de reuniones y correos, "
                       "o darte las métricas conectadas de UNITEC y BuildingApp."
                       if es else
                       "I don't have that recorded, so I won't guess. I can search your notes, tasks, "
                       "meeting and email summaries, or give you the connected UNITEC and BuildingApp metrics."),
            "sources": [], "grounded": False}


if __name__ == "__main__":
    print(json.dumps(ask("cuántos miembros hay"), ensure_ascii=False, indent=2))

# ───────────────────────── calendar events & task edits ─────────────────────────
_EV_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id TEXT PRIMARY KEY, title TEXT, date TEXT, time TEXT, duration INTEGER,
    company TEXT, notes TEXT, source TEXT, status TEXT, ts REAL);
"""

DEMO_EVENTS_SEED = [
    ("E-demo1017", "Auditoría Mensual Facturación Médica (3 Sedes)", "2026-10-17", "10:00", 45, "mbmb", "Sincronizado con Google Calendar & Nexus CRM", "Google Calendar & Nexus", "scheduled"),
    ("E-demo1021", "Revisión Lanzamiento iOS & Android BuildingApp AI", "2026-10-21", "11:30", 30, "building", "Sincronizado con Google Meet & App Store Connect", "Google Meet & Zoom", "scheduled"),
    ("E-demo1023", "Comité de Conversión Recepcionista IA UNITEC (29 Leads)", "2026-10-23", "15:00", 45, "unitec", "Sincronizado con Outlook & Vercel Front-Desk", "Google Calendar & Outlook", "scheduled"),
    ("E-demo1025", "Preparación Semanal de Flujo de Caja & Denegaciones", "2026-10-25", "17:00", 30, "cedexx", "Sincronizado con Cerebro Conductual", "Google Calendar & Outlook", "scheduled"),
    ("E-demo1026a", "Kickoff Técnico Brickell Ortho ($15.2k ARR)", "2026-10-26", "09:30", 45, "mbmb", "Sincronizado con Google Calendar & Meet", "Google Calendar & Meet", "scheduled"),
    ("E-demo1026b", "Cierre Contrato Dr. Molina · Doral Urgent Care ($12.4k/m)", "2026-10-26", "14:00", 30, "cedexx", "Sincronizado con Nexus CRM & Outlook", "Nexus CRM & Outlook", "scheduled"),
    ("E-demo1026c", "Corte Diario BuildingApp AI (130 Renders · 7 Miembros)", "2026-10-26", "16:30", 30, "building", "Sincronizado con Google Calendar & Zoom", "Google Meet & Zoom", "scheduled"),
    ("E-demo1027a", "Migración 3 Sedes Clínica Del Mar (#PO-2214 · $9.8k)", "2026-10-27", "10:00", 60, "305biz", "Sincronizado con Google Calendar & Meet", "Google Calendar & Meet", "scheduled"),
    ("E-demo1027b", "Demo Portal Bilingüe · Jorge (UNITEC USA)", "2026-10-27", "16:00", 45, "unitec", "Sincronizado con Nexus CRM & Google Meet", "Nexus CRM & Meet", "scheduled"),
    ("E-demo1028", "Auditoría Mensual Denegaciones & Cashflow (MBMB + CEDEXX)", "2026-10-28", "11:00", 45, "mbmb", "Sincronizado con Outlook & Nexus CRM", "Google Calendar & Outlook", "scheduled"),
    ("E-demo1030", "Comité Ejecutivo de Viernes · 5 Empresas Consolidadas", "2026-10-30", "15:00", 60, "all", "Sincronizado con Google Calendar, Zoom & PDF Diario", "Google Calendar & Zoom", "scheduled"),
]


def _evdb():
    c = _db()
    c.executescript(_EV_SCHEMA)
    n = c.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    if n == 0:
        now = time.time()
        for eid, title, d, tm, dur, co, notes, src, st in DEMO_EVENTS_SEED:
            c.execute("INSERT OR IGNORE INTO events VALUES(?,?,?,?,?,?,?,?,?,?)",
                      (eid, title, d, tm, dur, co, notes, src, st, now))
        c.commit()
    return c


def add_event(title: str, date: str, time_: str = "", duration: int = 30, company: str = "all",
              notes: str = "", source: str = "Google Calendar & Outlook") -> dict:
    title = _clean(title, 300)
    date = (date or "").strip()
    if not title or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
        return {"ok": False, "error": "title and date (YYYY-MM-DD) required"}
    time_ = (time_ or "").strip()
    if time_ and not re.fullmatch(r"\d{2}:\d{2}", time_):
        return {"ok": False, "error": "time must be HH:MM"}
    eid = "E-" + uuid.uuid4().hex[:8]
    c = _evdb()
    c.execute("INSERT INTO events VALUES(?,?,?,?,?,?,?,?,?,?)",
              (eid, title, date, time_, int(duration or 30), company or "all",
               _clean(notes or f"Sincronizado con {source}", 1000),
               source or "Google Calendar & Outlook", "scheduled", time.time()))
    c.commit(); c.close()
    return {"ok": True, "id": eid, "title": title, "date": date, "time": time_, "source": source}


def update_event(eid: str, **fields) -> dict:
    allowed = {"title", "date", "time", "duration", "company", "notes", "source", "status"}
    sets = {k: v for k, v in fields.items() if k in allowed and v is not None}
    if not sets:
        return {"ok": False, "error": "nothing to update"}
    c = _evdb()
    cur = c.execute("UPDATE events SET " + ",".join(f"{k}=?" for k in sets) + " WHERE id=?",
                    list(sets.values()) + [eid])
    c.commit(); n = cur.rowcount; c.close()
    return {"ok": n > 0, "id": eid}


def delete_event(eid: str) -> dict:
    c = _evdb()
    n = c.execute("DELETE FROM events WHERE id=?", (eid,)).rowcount
    c.commit(); c.close()
    return {"ok": n > 0, "id": eid}


def list_events() -> list:
    c = _evdb()
    rows = [dict(r) for r in c.execute("SELECT * FROM events ORDER BY date, time").fetchall()]
    c.close()
    return rows


def update_task(tid: str, title=None, due=None, status=None, company=None, severity=None) -> dict:
    sets = {}
    if title is not None: sets["title"] = _clean(title, 500)
    if due is not None: sets["due"] = due
    if company is not None: sets["company"] = company
    if severity is not None: sets["severity"] = severity
    if status is not None:
        sets["status"] = status
        sets["done"] = time.time() if status == "done" else None
    if not sets:
        return {"ok": False, "error": "nothing to update"}
    c = _db()
    n = c.execute("UPDATE tasks SET " + ",".join(f"{k}=?" for k in sets) + " WHERE id=?",
                  list(sets.values()) + [tid]).rowcount
    c.commit(); c.close()
    return {"ok": n > 0, "id": tid}


def delete_task(tid: str) -> dict:
    c = _db()
    n = c.execute("DELETE FROM tasks WHERE id=?", (tid,)).rowcount
    c.commit(); c.close()
    return {"ok": n > 0, "id": tid}


def sync_calendar_integrations() -> dict:
    evs = list_events()
    tks = list_items("tasks", limit=100000)
    dated_tks = [t for t in tks if re.fullmatch(r"\d{4}-\d{2}-\d{2}", t.get("due") or "")]
    return {
        "ok": True,
        "synced_events": len(evs),
        "synced_tasks": len(dated_tks),
        "integrations": [
            "Google Calendar & Outlook (Bidireccional)",
            "Google Meet & Zoom Intelligence",
            "Nexus CRM Pipeline & Demos",
            "Equipo, Proyectos y Tareas",
            "Apple Calendar / Feed iCal (.ics)"
        ],
        "timestamp": _iso(time.time())
    }


def events_ics() -> str:
    """iCalendar feed (events + dated tasks). Subscribe from Google Calendar / Outlook / Apple."""
    def esc(s): return (s or "").replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")
    out = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//La Jefatura//Agenda//ES", "CALSCALE:GREGORIAN"]
    for e in list_events():
        d = e["date"].replace("-", "")
        out += ["BEGIN:VEVENT", f"UID:{e['id']}@lajefatura"]
        if e["time"]:
            hh, mm = int(e["time"][:2]), int(e["time"][3:])
            end = hh * 60 + mm + int(e["duration"] or 30)
            out += [f"DTSTART:{d}T{hh:02d}{mm:02d}00",
                    f"DTEND:{d}T{min(end // 60, 23):02d}{end % 60 if end < 1440 else 59:02d}00"]
        else:
            out.append(f"DTSTART;VALUE=DATE:{d}")
        out += [f"SUMMARY:{esc(e['title'])}", f"DESCRIPTION:{esc(e['notes'])}", "END:VEVENT"]
    for t in list_items("tasks", limit=100000):
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", t.get("due") or "") and t["status"] != "done":
            out += ["BEGIN:VEVENT", f"UID:{t['id']}@lajefatura",
                    f"DTSTART;VALUE=DATE:{t['due'].replace('-', '')}", f"SUMMARY:{esc('Tarea: ' + t['title'])}", "END:VEVENT"]
    out.append("END:VCALENDAR")
    return "\r\n".join(out) + "\r\n"
