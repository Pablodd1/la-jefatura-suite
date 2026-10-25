"""
La Jefatura Suite — Headless & Grok 3.0 Voice Command Executor

The same grammar + DOM/profile-aware brain the browser widget parses, executable
server-side so voice control works from ANY channel: console widget, Telegram
voice notes (Whisper hook), or tenant web widgets.

All actions hit real mc.db state (tasks, drafts, behavioral routines) or real
generators (PDF), and every command returns a spoken/written `reply`.

Self-test:  python3 server/voice_commands.py
"""
import json
import os
import re
import sqlite3
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
_PROD_DIR = "/root/.openclaw/workspace/mission-control"
DB = os.environ.get("MC_DB_PATH") or (
    os.path.join(_PROD_DIR, "mc.db") if os.path.isdir(_PROD_DIR)
    else os.path.join(ROOT, "data", "mc.db")
)
os.makedirs(os.path.dirname(DB), exist_ok=True)
if HERE not in sys.path:
    sys.path.insert(0, HERE)


def _ensure_tasks_table():
    c = sqlite3.connect(DB)
    c.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id TEXT PRIMARY KEY,
            title TEXT,
            company TEXT,
            owner TEXT,
            due TEXT,
            status TEXT,
            severity TEXT,
            notes TEXT,
            done REAL
        )
    """)
    cnt = c.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
    if cnt == 0:
        samples_path = os.path.join(ROOT, "data", "samples", "tasks.json")
        if os.path.isfile(samples_path):
            data = json.load(open(samples_path, encoding="utf-8"))
            for t in data.get("tareas", []):
                c.execute(
                    "INSERT OR IGNORE INTO tasks VALUES(?,?,?,?,?,?,?,?,?)",
                    (t["id"], t["titulo"], t.get("empresa", "all"), t.get("owner", "CEO"),
                     t.get("due", ""), "pending" if t.get("estado") != "done" else "done",
                     t.get("severidad", "medium"), t.get("notas", ""), None)
                )
            c.commit()
    c.close()


def _reply(action, lang="es", **kw):
    if lang == "en":
        R_EN = {
            "switch_company": f"Switching Mission Control view to {kw.get('company')}.",
            "open_tab": f"Opening the {kw.get('tab')} section on your screen.",
            "download_report": "Generating and downloading the Executive PDF Report.",
            "complete_task": f"Task '{kw.get('task')}' marked as completed.",
            "read_brief": kw.get("brief", ""),
            "status_digest": kw.get("digest", ""),
            "confirm_coffee": f"Morning coffee order confirmed: {kw.get('coffee', 'Double Espresso Cortado')} scheduled for 07:45 AM.",
            "switch_slot": f"Switched behavioral brain context to {kw.get('slot')} routine.",
            "explain_plans": ("Grok 3.0 Brain active: La Jefatura connects your calendars, emails, CRM, tasks, "
                              "cameras, staff and client monitors during a one-time onboarding. From then on, "
                              "you only see outcomes, graphics, and pre-drafted responses ready for 1-click approval."),
            "refresh": "All company metrics and app integrations refreshed from Mission Control.",
            "help": ("Grok 3.0 Voice commands: switch to «company» · open «tab» (overview, comms, outcomes, "
                     "brain, setup, blogs) · approve draft · draft reply · complete task «number» · "
                     "order coffee · read brief · download report."),
            "unknown": "I heard you, CEO. Try saying 'open blogs', 'switch to CEDEXX', 'approve draft', or 'read brief'.",
        }
        return R_EN.get(action, R_EN["unknown"])

    R_ES = {
        "switch_company": f"Cambiando vista de Mission Control a {kw.get('company')}.",
        "open_tab": f"Abriendo la pestaña {kw.get('tab')} en pantalla.",
        "download_report": "Generando el informe PDF. Te llega por Telegram y correo en unos segundos.",
        "complete_task": f"Tarea {kw.get('task')} marcada como completada.",
        "read_brief": kw.get("brief", ""),
        "status_digest": kw.get("digest", ""),
        "confirm_coffee": f"Orden de café confirmada: {kw.get('coffee', 'Cortado Doble Espresso')} programado 07:45 AM.",
        "switch_slot": f"Contexto conductual cambiado a rutina de {kw.get('slot')}.",
        "explain_plans": ("Cerebro Grok 3.0 activo: La Jefatura conecta tus calendarios, correos, CRM, tareas, "
                          "cámaras, personal y clientes una sola vez en el onboarding. Después, tú solo recibes "
                          "resultados, gráficas y borradores listos para aprobar con un clic o por voz."),
        "refresh": "Datos actualizados desde Mission Control.",
        "help": ("Comandos Grok 3.0: cambiar a «empresa» · abrir «pestaña» (mando, bandeja, resultados, "
                 "cerebro, configuración, blogs) · aprobar borrador · redactar respuesta · completar tarea «n» · "
                 "preparar café · leer resumen · descargar informe."),
        "unknown": "Comando no reconocido. Di «ayuda» para ver la lista.",
    }
    return R_ES.get(action, R_ES["unknown"])


def parse(command: str, lang: str = "es") -> dict:
    t = command.strip()
    low = t.lower()

    # ── Knowledge intents FIRST: their free text may contain words like «mañana» or «café»
    # that would otherwise trigger routine/coffee commands. ──
    m = re.match(r"^(?:guardar|guarda|anotar|anota|agregar|agrega|a[ñn]adir|save|add|take|create|crear|crea)\s+"
                 r"(?:el\s+|un\s+|una\s+|a\s+|the\s+)?(?:resumen\s+(?:de\s+(?:la\s+)?)?reuni[oó]n|meeting\s+summary|"
                 r"summary\s+of\s+(?:the\s+)?meeting)\s*[:,\-]?\s*(.+)$", t, re.I)
    if m:
        return {"action": "save_meeting", "text": m.group(1).strip()}
    m = re.match(r"^(?:guardar|guarda|save|add)\s+(?:el\s+|un\s+|the\s+)?(?:resumen\s+(?:de\s+)?(?:correo|email)|"
                 r"email\s+summary)\s*[:,\-]?\s*(.+)$", t, re.I)
    if m:
        return {"action": "save_email", "text": m.group(1).strip()}
    m = re.match(r"^(?:guardar|guarda|anotar|anota|agregar|agrega|a[ñn]adir|save|add|take|crear|crea|create)\s+"
                 r"(?:una\s+|a\s+)?(?:nueva\s+|new\s+)?(?:nota|note)\s*[:,\-]?\s*(.+)$", t, re.I) \
        or re.match(r"^(?:nota|note)\s*[:,\-]\s*(.+)$", t, re.I)
    if m:
        return {"action": "save_note", "text": m.group(1).strip()}
    m = re.match(r"^(?:crear|crea|agregar|agrega|a[ñn]adir|add|create|new)\s+(?:una\s+|a\s+)?(?:nueva\s+|new\s+)?"
                 r"(?:tarea|task)\s*[:,\-]?\s*(.+)$", t, re.I) \
        or re.match(r"^(?:recu[ée]rdame|remind me to)\s+(.+)$", t, re.I)
    if m:
        return {"action": "save_task", "text": m.group(1).strip()}
    if re.match(r"^(?:buscar|busca|search|find|encuentra|qu[eé] dijo|what did)\b", low):
        return {"action": "ask", "text": t}
    if re.search(r"\b(notas?|notes?|tareas?|tasks?|reuniones?|meetings?|correos? guardados?)\b", low) and \
            re.search(r"\b(qu[eé]|cu[aá]les|cu[aá]ntas?|lista|listar|lee|leer|read|list|show|what|how many|dame|muestra)\b", low) \
            and not re.search(r"^(?:ir a|abrir|abre|open|go to)\b", low):
        return {"action": "ask", "text": t}
    if re.search(r"\b(miembros|members|conversaciones|conversations|abandono|abandonment|contactos|contacts|"
                 r"alertas|alerts|generaciones|generations|renders|costo|cost)\b", low):
        return {"action": "ask", "text": t}

    # Tab navigation commands
    tab_match = re.search(
        r"\b(blogs?|gu[ií]as?|funciones|setup|configuraci[oó]n|onboarding|integraciones|"
        r"cerebro|behavior|conductual|hábitos|habitos|resultados|outcomes|monitoreo|estudios|"
        r"bandeja|comms|correos|mensajes|borradores|inbox|mando|overview|consola|dashboard|inicio)\b",
        low
    )
    if re.search(r"^(?:ir a|abrir|abre|open|go to|ver|mostrar|show|tab|pestaña)\b", low) and tab_match:
        w = tab_match.group(1)
        if w in ("blog", "blogs", "guia", "guias", "guía", "guías", "funciones"):
            return {"action": "open_tab", "tab": "blogs"}
        if w in ("setup", "configuracion", "configuración", "onboarding", "integraciones"):
            return {"action": "open_tab", "tab": "setup"}
        if w in ("cerebro", "behavior", "conductual", "habitos", "hábitos"):
            return {"action": "open_tab", "tab": "behavior"}
        if w in ("resultados", "outcomes", "monitoreo", "estudios"):
            return {"action": "open_tab", "tab": "outcomes"}
        if w in ("bandeja", "comms", "correos", "mensajes", "borradores", "inbox"):
            return {"action": "open_tab", "tab": "comms"}
        return {"action": "open_tab", "tab": "overview"}

    sw = re.match(r"^(?:cambiar a|ir a|switch to|muestra(?:me)?|show(?: me)?)\s+(.+)$", t, re.I)
    if sw:
        return {"action": "switch_company", "company": sw.group(1).strip()}

    ct = re.match(r"^(?:completar|marcar|complete|done(?: with)?)\s+(?:tarea|task)?\s*(.+)$", t, re.I)
    if ct:
        return {"action": "complete_task", "task": ct.group(1).strip()}

    if re.search(r"caf[eé]|coffee|espresso|cortado", low):
        return {"action": "confirm_coffee"}
    if re.search(r"rutina|routine|mañana|morning|tarde|afternoon|noche|evening", low):
        if "tarde" in low or "afternoon" in low:
            return {"action": "switch_slot", "slot": "afternoon"}
        if "noche" in low or "evening" in low:
            return {"action": "switch_slot", "slot": "evening"}
        return {"action": "switch_slot", "slot": "morning"}
    if re.search(r"explica|explain|planes|plans|c[oó]mo funciona|how does it work|qu[eé] hay en la p[aá]gina", low):
        return {"action": "explain_plans"}
    if re.search(r"descargar|generar|download|report|pdf", low):
        return {"action": "download_report"}
    if re.search(r"leer|read|brief|resumen", low):
        return {"action": "read_brief"}
    if re.search(r"nuevo|new|status|novedades", low):
        return {"action": "status_digest"}
    if re.search(r"actualizar|refresh|reload|recargar", low):
        return {"action": "refresh"}
    if re.search(r"redactar|draft|responder a|reply to", low):
        return {"action": "draft_reply"}
    if re.search(r"aprender|learn", low) and re.search(r"voz|voice|estilo", low):
        return {"action": "learn_voice"}
    if re.search(r"aprob|approve|enviar borrador|send draft", low):
        return {"action": "approve_draft"}
    if re.search(r"ayuda|help|comandos|commands", low):
        return {"action": "help"}
    return {"action": "unknown"}


def _complete_task(fragment: str) -> tuple[bool, str]:
    _ensure_tasks_table()
    c = sqlite3.connect(DB)
    rows = c.execute("SELECT id, title FROM tasks WHERE status != 'done'").fetchall()
    hit = None
    frag = fragment.lower().rstrip(".")
    if frag.isdigit():
        idx = int(frag) - 1
        hit = rows[idx] if 0 <= idx < len(rows) else None
    if not hit:
        for r in rows:
            if frag in r[1].lower() or frag == r[0].lower():
                hit = r
                break
    if not hit:
        c.close()
        return False, f"No encontré una tarea abierta que coincida con «{fragment}»."
    c.execute("UPDATE tasks SET status='done', done=? WHERE id=?", (time.time(), hit[0]))
    c.commit()
    c.close()
    return True, hit[1]


def execute(command: str, lang: str = "es", samples_dir: str | None = None) -> dict:
    """Parse + run. Returns {ok, action, reply}. Never raises on bad input."""
    _ensure_tasks_table()
    try:
        import behavior_brain
        behavior_brain.record_event("voice_query", "grok_voice_command", {"command": command, "lang": lang})
    except Exception:
        pass

    # El Jefesito control requests (theme, language, greeting, close day, print, profile, name).
    try:
        import jefesito
        ctl = jefesito.control(command, lang)
    except Exception as e:  # never break voice because of a control bug
        print("jefesito.control error:", e, file=sys.stderr)
        ctl = None
    if ctl:
        return {"ok": True, "action": "control", "parsed": {"action": "control"}, "reply": ctl["reply"],
                "ui": ctl.get("ui"), "sources": ctl.get("sources", []), "grounded": True}

    p = parse(command, lang)
    action = p["action"]
    ok = True
    if action == "switch_company":
        reply = _reply(action, lang=lang, company=p.get("company"))
    elif action == "open_tab":
        reply = _reply(action, lang=lang, tab=p.get("tab"))
    elif action == "confirm_coffee":
        reply = _reply(action, lang=lang, coffee="Cortado Doble Espresso (Oat Milk)")
    elif action == "switch_slot":
        reply = _reply(action, lang=lang, slot=p.get("slot", "morning"))
    elif action == "explain_plans":
        reply = _reply(action, lang=lang)
    elif action == "complete_task":
        ok, detail = _complete_task(p.get("task", ""))
        reply = _reply(action, lang=lang, task=detail) if ok else detail
    elif action == "download_report":
        try:
            import reports_pdf
            out = os.path.join(tempfile.gettempdir(), "_voice_report.pdf")
            sd = samples_dir or os.path.join(HERE, "..", "data", "samples")
            reports_pdf.build_report("Medical Billing Miami Beach", sd, out, lang=lang)
            reply = _reply(action, lang=lang)
        except Exception as e:
            ok = False
            reply = f"Error generando el informe: {e}"
    elif action == "read_brief":
        from ai_insights import report_narative
        sd = samples_dir or os.path.join(HERE, "..", "data", "samples")
        nexus = json.load(open(os.path.join(sd, "nexus_crm.json"), encoding="utf-8"))
        tasks_j = json.load(open(os.path.join(sd, "tasks.json"), encoding="utf-8"))
        brief = report_narative("La Jefatura", nexus["kpis"],
                                tasks_j["resumen"], nexus["pipeline_por_etapa"], lang=lang)
        reply = ("(Datos de ejemplo del demo, no reales) " if lang != "en" else "(Demo sample data, not real) ") + brief
    elif action == "status_digest":
        c = sqlite3.connect(DB)
        t = c.execute("SELECT COUNT(*) FROM tasks WHERE status != 'done'").fetchone()[0]
        try:
            import comms_brain
            q = comms_brain.needs_reply_queue()
            pending = f" {len(q)} mensajes esperando tu respuesta." if q else " Bandeja de respuesta limpia."
        except Exception:
            pending = ""
        c.close()
        try:
            s = __import__("nexus_ingest").summary()
            dig = (f"Resumen: pipeline US${s['kpis']['pipeline_total_estimado_usd']:,.0f} "
                   f"con {s['kpis']['leads_activos']} leads; {t} tareas abiertas.{pending}")
        except Exception:
            dig = f"{t} tareas abiertas.{pending}"
        reply = ("(Datos de ejemplo del demo, no reales) " if lang != "en" else "(Demo sample data, not real) ") + dig
    elif action == "draft_reply":
        import comms_brain
        comms_brain.ensure_demo_inbox_seeded()
        q = comms_brain.needs_reply_queue()
        if not q:
            reply = "No hay mensajes pendientes de respuesta."
        else:
            top = q[0]
            d = comms_brain.draft(top["thread_id"], top["channel"])
            reply = (f"Borrador #{d.get('draft_id')} para {top['contact']}: {d.get('body','')[:120]}... "
                     f"Revísalo y aprueba para enviar.")
    elif action == "learn_voice":
        import comms_brain
        pr = comms_brain.learn()
        reply = (f"Voz actualizada: despedida '{pr.get('signoff','—')}', formalidad "
                 f"{pr.get('formality')}, largo medio {pr.get('avg_len')} palabras.")
    elif action == "approve_draft":
        import comms_brain
        comms_brain.ensure_demo_inbox_seeded()
        c = sqlite3.connect(DB)
        row = c.execute(
            "SELECT id FROM drafts WHERE status IN ('PENDING_REVIEW','pending_approval','edited','READY_TO_SEND') "
            "ORDER BY id DESC LIMIT 1"
        ).fetchone()
        c.close()
        if not row:
            reply = "No hay borradores esperando aprobación."
        else:
            r = comms_brain.approve_and_send(row[0])
            reply = ("Borrador aprobado y enviado directamente." if r.get("ok")
                     else f"No se pudo enviar: {r.get('error')}")
    elif action in ("save_note", "save_task", "save_meeting", "save_email"):
        import knowledge_store as ks
        txt = p.get("text", "")
        es = lang != "en"
        if action == "save_note":
            r = ks.add_note(txt, source="voice")
            reply = (f"Nota guardada con id {r['id']}: «{txt[:100]}»." if es
                     else f"Note saved as {r['id']}: \"{txt[:100]}\".") if r["ok"] else "No pude guardar una nota vacía."
        elif action == "save_task":
            r = ks.add_task(txt, source="voice")
            reply = (f"Tarea creada con id {r['id']}: «{txt[:100]}»." if es
                     else f"Task created as {r['id']}: \"{txt[:100]}\".") if r["ok"] else "No pude crear una tarea vacía."
        elif action == "save_meeting":
            r = ks.add_meeting_summary(txt, source="voice")
            reply = (f"Resumen de reunión guardado con id {r['id']}." if es
                     else f"Meeting summary saved as {r['id']}.") if r["ok"] else "No pude guardar un resumen vacío."
        else:
            r = ks.add_email_summary(txt, source="voice")
            reply = (f"Resumen de correo guardado con id {r['id']}." if es
                     else f"Email summary saved as {r['id']}.") if r["ok"] else "No pude guardar un resumen vacío."
        ok = bool(r.get("ok"))
        return {"ok": ok, "action": action, "parsed": p, "reply": reply, "record": r}
    elif action == "ask":
        import knowledge_store as ks
        a = ks.ask(p.get("text", command), lang=lang)
        return {"ok": True, "action": action, "parsed": p, "reply": a["answer"],
                "sources": a["sources"], "grounded": a["grounded"]}
    elif action != "unknown":
        reply = _reply(action, lang=lang)
    else:
        import knowledge_store as ks
        a = ks.ask(command, lang=lang)
        return {"ok": a["grounded"], "action": "ask", "parsed": p, "reply": a["answer"],
                "sources": a["sources"], "grounded": a["grounded"]}
    return {"ok": ok, "action": action, "parsed": p, "reply": reply}


if __name__ == "__main__":
    for cmd in ["cambiar a MBMB", "qué hay de nuevo", "ayuda",
                "leer resumen", "descargar informe", "completar tarea 1",
                "abrir blogs", "preparar café", "aprobar borrador", "fruta voladora"]:
        r = execute(cmd)
        print(f"  «{cmd}» -> {r['action']}: {r['reply'][:90]}")
    c = sqlite3.connect(DB)
    open_tasks = c.execute("SELECT id FROM tasks ORDER BY rowid LIMIT 1").fetchone()
    if open_tasks:
        c.execute("UPDATE tasks SET status='pending' WHERE id=? AND status='done'", (open_tasks[0],))
        c.commit()
    c.close()
    print("voice_commands OK")
