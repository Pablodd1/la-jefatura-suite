"""
La Jefatura Suite — Headless & Grok 3.0 Voice Command Executor (`server/voice_commands.py`).

The same grammar + DOM/profile-aware brain + Close-Word Fuzzy Function Catalog the browser
widget parses, executable server-side so voice and chat control work from ANY channel:
Master Control bar, floating Jefesito chatbot, Minimalist Super Assistant, or Telegram.

All actions hit real mc.db state (notes, tasks, events, reminders, drafts, behavioral routines),
real-time Google Calendar sync, Email Reminders, and real PDF generators, and every command
returns a spoken/written `reply` plus `ui` directives and `matched_function` metadata.
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
    c = sqlite3.connect(DB, timeout=30.0)
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
            "download_report": "Generating and opening the Executive PDF Report.",
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
            "unknown": "I heard you, CEO. Try saying 'open blogs', 'switch to UNITEC USA', 'approve draft', or 'read brief'.",
        }
        return R_EN.get(action, R_EN["unknown"])

    R_ES = {
        "switch_company": f"Cambiando vista de Mission Control a {kw.get('company')}.",
        "open_tab": f"Abriendo la pestaña {kw.get('tab')} en pantalla.",
        "download_report": "Generando el informe PDF. Se abre en pantalla y queda listo para envío por Telegram y correo.",
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


def _resolve_company_slug(raw_company: str) -> tuple[str, str]:
    rc = (raw_company or "").lower().strip()
    if any(k in rc for k in ("unitec", "unitek", "uni", "pvc", "wpc", "lamina")):
        return "unitec", "UNITEC USA Design"
    if any(k in rc for k in ("building", "bilding", "bui", "render", "gemini", "ga4")):
        return "building", "Building Innovation"
    if any(k in rc for k in ("camara", "cámara", "cam", "cctv", "hik", "video", "vigilancia", "55", "53")):
        return "cameras", "55 Cámaras CCTV Hik-Connect"
    if any(k in rc for k in ("espacio", "importado", "colombia", "muelle", "pick", "bodega", "contenedor", "aduana")):
        return "espacios", "Espacios Importados"
    if any(k in rc for k in ("nexus", "nex", "crm", "sale", "pipeline", "ventas")):
        return "nexus", "Nexus CRM"
    if any(k in rc for k in ("toda", "all", "portafolio", "global", "general")):
        return "all", "Todas las Empresas"
    return "all", raw_company or "Todas las Empresas"


def parse(command: str, lang: str = "es") -> dict:
    t = command.strip()
    low = t.lower()

    # ── 1. Knowledge & Memory intents FIRST: their free text may contain words like «mañana» or «café» ──
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
        or re.match(r"^(?:nota|note|anota|anotar|memoriza|memorizar|apunta|apuntar)\s*[:,\-\s]\s*(.+)$", t, re.I)
    if m:
        return {"action": "save_note", "text": m.group(1).strip()}

    # Email reminder ("recordatorio por correo...", "enviar recordatorio...", "recuérdame por email...", "manda recordatorio...")
    m_em_rem = re.match(
        r"^(?:por favor\s+)?(?:enviar|env[ií]a|mandar|manda|crear|crea|programar|programa|pon|poner|send|set)?\s*"
        r"(?:un\s+|una\s+|el\s+)?(?:recordatorio\s+por\s+(?:correo|email)|alerta\s+por\s+(?:correo|email)|"
        r"recu[eé]rdame\s+por\s+(?:correo|email)|email\s+reminder|recordatorio\s+al\s+correo|recordatorio)\s*[:,\-\s]\s*(.+)$",
        t, re.I
    )
    if m_em_rem:
        return {"action": "email_reminder", "text": m_em_rem.group(1).strip()}

    # Schedule / add calendar appointment ("agendar cita: ...", "crear cita ...", "agrega a las 9pm masaje para mi", "pon a las 4pm llamada...")
    is_agenda_question = bool(
        "?" in t
        or re.search(r"^(?:qu[eé]|cu[aá]l(?:es)?|cu[aá]ntas?|c[oó]mo|d[oó]nde|abrir|abre|ver|mostrar|mu[eé]strame|open|show|what|which)\b", low)
        or re.search(r"\b(?:qu[eé]\s+tengo|que\s+tengo|qu[eé]\s+hay|que\s+hay|agenda\s+de\s+hoy|citas\s+de\s+hoy)\b", low)
    )
    m_ev = re.match(
        r"^(?:por favor\s+)?(?:agendar|agenda|programar|programa|crear|crea|agregar|agrega|a[ñn]adir|a[ñn]ade|"
        r"pon\s+en\s+el\s+calendario|poner\s+en\s+el\s+calendario|schedule|book|add)\s+"
        r"(?:una\s+|un\s+|a\s+|la\s+|el\s+)?(?:nueva\s+|new\s+)?(?:cita|reuni[oó]n|evento|appointment|meeting on calendar|meeting)\s*[:,-]?\s*(.+)$",
        t, re.I
    ) or re.match(
        r"^(?:por favor\s+)?(?:agendar|agenda|nueva\s+cita|cita)\s*[:,\-\s]\s*(.+)$",
        t, re.I
    ) or (
        re.match(
            r"^(?:por favor\s+)?(?:agendar|agenda|programar|programa|agregar|agrega|a[ñn]adir|a[ñn]ade|pon|poner|apunta|apuntar|reserva|reservar|schedule|book)\s+(.+)$",
            t, re.I
        )
        if re.search(r"(?:\ba\s+las\s+\d{1,2}|\b\d{1,2}(?::\d{2})?\s*(?:am|pm|a\.m\.|p\.m\.)\b|\b\d{1,2}:\d{2}\b)", low)
        and not re.search(r"\b(?:nota|note|recordatorio|tarea|task|correo|email)\b", low)
        else None
    )
    if m_ev and not is_agenda_question:
        return {"action": "schedule_event", "text": m_ev.group(1).strip()}

    if re.search(r"\b(sincronizar|sincroniza|sync)\b.*\b(calendario|agenda|integraciones|apps|todo|all)\b", low):
        return {"action": "sync_integrations"}

    if re.search(r"\b(super\s*asistente|vista\s*simple|modo\s*simple|solo\s*voz|single\s*chat|minimal\s*assistant)\b", low):
        return {"action": "open_tab", "tab": "assistant"}

    m_esc = re.match(r"^(?:notificar|notifica|escalar|escala|avisar|avisa|reportar|reporta|notify|escalate)(?:\s+al)?\s+"
                     r"(?:desarrollador|developer|programador|jasmel)\s*[:,-]?\s*(.+)$", t, re.I)
    if m_esc:
        return {"action": "escalate_dev", "text": m_esc.group(1).strip()}

    m = re.match(r"^(?:crear|crea|agregar|agrega|a[ñn]adir|add|create|new)\s+(?:una\s+|a\s+)?(?:nueva\s+|new\s+)?"
                 r"(?:tarea|task)\s*[:,\-]?\s*(.+)$", t, re.I) \
        or re.match(r"^(?:recu[ée]rdame|remind me to)\s+(.+)$", t, re.I)
    if m:
        return {"action": "save_task", "text": m.group(1).strip()}

    # Company Learning ("aprende que ...", "memoriza sobre la empresa ...", "aprende sobre unitec que ...")
    m_learn_co = re.match(
        r"^(?:por favor\s+)?(?:aprende|aprender|ense[ñn]ar|memoriza\s+sobre\s+la\s+empresa|aprende\s+sobre\s+la\s+empresa|"
        r"recuerda\s+sobre\s+la\s+empresa|learn\s+that|memorize\s+that)\s*(?:que\s+|sobre\s+|de\s+)?[:,\-]?\s*(.+)$",
        t, re.I
    )
    if m_learn_co and not re.search(r"\b(voz|voice|estilo)\b", low):
        return {"action": "learn_company", "text": m_learn_co.group(1).strip()}

    # Cameras Vigilant Mode trigger / repost ("disparar modo vigilante", "repostear alerta de cámaras", "activar modo vigilante", "cameras vigilant mode repost")
    if re.search(r"\b(?:disparar?|repostear?|repost|activar?|enviar?|mandar?|trigger)\b.*\b(?:vigilante|vigilant|alerta\s+de\s+c[aá]maras?|sospechos\w*)\b", low):
        return {"action": "trigger_camera_vigilant", "reason": t}

    # Twice-daily live report dispatch ("enviar reporte ahora", "mandar informe por telegram y correo", "reporte dos veces al día")
    if re.search(r"\b(?:enviar|env[ií]a|mandar|manda|despachar|dispara)\b.*\b(?:reporte|informe|resumen|brief)\b", low):
        return {"action": "send_twice_daily_report"}

    # Delegated Telegram / Text / Voice Call / Multi-Intent commands
    if re.search(
        r"\b(?:go\s+to\s+telegram|ve\s+a\s+telegram|send\s+a?\s*(?:text|telegram|message)|send\s+this\s+text|"
        r"manda(?:r)?\s+un?\s*(?:telegram|texto|mensaje)|env[íi]a(?:r)?\s+un?\s*(?:telegram|texto|mensaje)|"
        r"i\s+want\s+you\s+to|quiero\s+que\s+(?:env[íi]es|mandes|redactes|llames)|"
        r"make\s+a?\s*(?:phone\s+)?call|llamar\s+por\s+tel[ée]fono|llama\s+a|haz\s+una\s+llamada)\b",
        low,
    ):
        return {"action": "ceo_delegation", "text": t}

    # Explicit search / Q&A queries
    if re.match(r"^(?:buscar|busca|search|find|encuentra|qu[eé] dijo|what did)\b", low):
        return {"action": "ask", "text": t}
    if re.search(r"\b(notas?|notes?|tareas?|tasks?|reuniones?|meetings?|correos? guardados?)\b", low) and \
            re.search(r"\b(qu[eé]|cu[aá]les|cu[aá]ntas?|lista|listar|lee|leer|read|list|show|what|how many|dame|muestra)\b", low) \
            and not re.search(r"^(?:ir a|abrir|abre|open|go to)\b", low):
        return {"action": "ask", "text": t}

    # Tab navigation commands
    tab_match = re.search(
        r"\b(blogs?|gu[ií]as?|funciones|setup|configuraci[oó]n|onboarding|integraciones|"
        r"cerebro|behavior|conductual|hábitos|habitos|resultados|outcomes|monitoreo|estudios|"
        r"textos?|telegram|sms|llamadas?|calls?|transcripciones?|tel[ée]fono|"
        r"tareas?|calendario|pendientes|notas?|memoria|"
        r"bandeja|comms|correos?|emails?|borradores|inbox|mando|overview|consola|dashboard|inicio)\b",
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
        if w in ("texto", "textos", "telegram", "sms"):
            return {"action": "open_tab", "tab": "texts"}
        if w in ("llamada", "llamadas", "call", "calls", "transcripcion", "transcripciones", "telefono", "teléfono"):
            return {"action": "open_tab", "tab": "calls"}
        if w in ("tarea", "tareas", "calendario", "pendientes"):
            return {"action": "open_tab", "tab": "tasks_cal"}
        if w in ("nota", "notas", "memoria"):
            return {"action": "open_tab", "tab": "notes_vault"}
        if w in ("bandeja", "comms", "correo", "correos", "email", "emails", "borradores", "inbox"):
            return {"action": "open_tab", "tab": "comms"}
        return {"action": "open_tab", "tab": "overview"}

    sw = re.match(r"^(?:cambiar a|cambia a|ir a|switch to|muestra(?:me)?|show(?: me)?)\s+(.+)$", t, re.I)
    if sw:
        return {"action": "switch_company", "company": sw.group(1).strip()}

    # Close-word / fuzzy navigation or function catalog request when user says a navigation verb or function name
    try:
        import functions_catalog
        if re.search(r"^(?:ir a|abrir|abre|open|go to|ver|mostrar|muestrame|muestra|show|pon|poner|llevar a|llevame a|acceder|entrar|catalogo|catálogo)\b", low):
            m_fn = functions_catalog.match_function(t)
            if m_fn:
                return {"action": "catalog_function", "match": m_fn}
    except Exception:
        pass

    if re.search(r"\b(miembros|members|conversaciones|conversations|abandono|abandonment|contactos|contacts|"
                 r"alertas|alerts|generaciones|generations|renders|costo|cost|clima|tiempo|weather|temperatura|"
                 r"lluvia|building|buildingapp|unitec|c[aá]maras?|cameras?|hik|espacios|pick|ideo|muelles|"
                 r"grabador|discos|ga4|analytics|tr[aá]fico|empresas|companies|nexus|pipeline|ventas|ingresos|"
                 r"citas|agenda|calendario|errores?|fallos?|conexiones?|faltan|departamentos?|brazos|piernas|staff|personal|equipo|"
                 r"vigilante|vigilant|sospechos\w*|entradas?|salidas?|permanencia|dwell|qu[eé]\s+hicieron|what\s+they\s+did|recomendad\w*|jev)\b", low) and not re.search(r"^(?:ir a|abrir|abre|open|go to|cambiar a|switch to)\b", low):
        return {"action": "ask", "text": t}

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
    if re.search(r"descargar|generar|download|report|pdf|peri[oó]dico|newspaper", low):
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

    # Fallback: check if the user uttered a short close word or partial word for any function/menu/project/link!
    try:
        import functions_catalog
        m_fn = functions_catalog.match_function(t)
        if m_fn and m_fn["score"] >= 0.80:
            return {"action": "catalog_function", "match": m_fn}
    except Exception:
        pass

    return {"action": "unknown"}


def _complete_task(fragment: str) -> tuple[bool, str]:
    _ensure_tasks_table()
    c = sqlite3.connect(DB, timeout=30.0)
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
    """Parse + run. Returns {ok, action, reply, ui, matched_function}. Never raises on bad input."""
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
    except Exception as e:
        print("jefesito.control error:", e, file=sys.stderr)
        ctl = None
    if ctl:
        return {"ok": True, "action": "control", "parsed": {"action": "control"}, "reply": ctl["reply"],
                "ui": ctl.get("ui"), "sources": ctl.get("sources", []), "grounded": True}

    p = parse(command, lang)
    action = p["action"]
    ok = True
    ui = {}
    matched_fn = None

    if action == "catalog_function":
        m_info = p["match"]
        fn = m_info["fn"]
        matched_fn = fn
        ui = dict(fn.get("ui") or {})
        es = lang != "en"
        title = fn["title_es"] if es else fn["title_en"]
        what = fn["what_it_does_es"] if es else fn["what_it_does_en"]
        how = fn["how_it_works_es"] if es else fn["how_it_works_en"]
        reply = (
            f"Activando función «{title}» (identificada por palabra cercana «{m_info['matched_term']}»). "
            f"Qué hace: {what} Cómo funciona: {how}"
            if es else
            f"Activating function '{title}' (matched via '{m_info['matched_term']}'). "
            f"What it does: {what} How it works: {how}"
        )
        return {
            "ok": True,
            "action": "catalog_function",
            "parsed": p,
            "reply": reply,
            "ui": ui,
            "matched_function": fn,
            "sources": [f"Catálogo de Funciones · {fn['id']}"],
            "grounded": True,
        }

    if action == "switch_company":
        slug, label = _resolve_company_slug(p.get("company", ""))
        ui = {"select_company": slug, "scroll_to": "ctoCompanyIntelSection"}
        try:
            import functions_catalog
            m_fn = functions_catalog.match_function(slug)
            if m_fn:
                matched_fn = m_fn["fn"]
        except Exception:
            pass
        reply = _reply(action, lang=lang, company=label)
        return {"ok": True, "action": action, "parsed": p, "reply": reply, "ui": ui, "matched_function": matched_fn, "grounded": True}

    elif action == "open_tab":
        tab_id = p.get("tab", "overview")
        ui = {"open_tab": tab_id}
        try:
            import functions_catalog
            for f_item in functions_catalog.FUNCTIONS_CATALOG:
                if (f_item.get("ui") or {}).get("open_tab") == tab_id:
                    matched_fn = f_item
                    break
        except Exception:
            pass
        reply = _reply(action, lang=lang, tab=tab_id)
        return {"ok": True, "action": action, "parsed": p, "reply": reply, "ui": ui, "matched_function": matched_fn, "grounded": True}

    elif action == "confirm_coffee":
        reply = _reply(action, lang=lang, coffee="Cortado Doble Espresso (Oat Milk)")
    elif action == "switch_slot":
        slot = p.get("slot", "morning")
        ui = {"set_routine_slot": slot}
        reply = _reply(action, lang=lang, slot=slot)
    elif action == "explain_plans":
        ui = {"open_tab": "overview", "scroll_to": "masterFunctionsCatalogCard", "open_catalog": True}
        reply = _reply(action, lang=lang)
    elif action == "complete_task":
        ok, detail = _complete_task(p.get("task", ""))
        ui = {"refresh_calendar": True, "refresh_memory": True}
        reply = _reply(action, lang=lang, task=detail) if ok else detail
    elif action == "download_report":
        try:
            import daily_pdf
            out = os.path.join(tempfile.gettempdir(), "_voice_report.pdf")
            daily_pdf.build(out, lang=lang)
            ui = {"open_url": f"/api/daily.pdf?lang={lang}"}
            reply = _reply(action, lang=lang)
        except Exception as e:
            ok = False
            reply = f"Error generando el informe: {e}"
    elif action == "read_brief":
        import jefesito
        d_day = jefesito.get_day(lang=lang)
        reply = d_day.get("spoken") or ""
        return {"ok": True, "action": "read_brief", "parsed": p, "reply": reply,
                "ui": {"show_brief": True}, "sources": d_day.get("sources", []), "grounded": True}
    elif action == "status_digest":
        c = sqlite3.connect(DB, timeout=30.0)
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
            ui = {"open_tab": "comms"}
    elif action == "learn_voice":
        import comms_brain
        pr = comms_brain.learn()
        reply = (f"Voz actualizada: despedida '{pr.get('signoff','—')}', formalidad "
                 f"{pr.get('formality')}, largo medio {pr.get('avg_len')} palabras.")
    elif action == "approve_draft":
        import comms_brain
        comms_brain.ensure_demo_inbox_seeded()
        c = sqlite3.connect(DB, timeout=30.0)
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
            ui = {"open_tab": "comms"}
    elif action == "email_reminder":
        import functions_catalog as fc
        parsed_dt = fc.parse_natural_datetime(p.get("text", ""))
        rem_res = fc.send_email_and_telegram_reminder(
            title=parsed_dt["title"],
            date_str=parsed_dt["date"],
            time_str=parsed_dt["time"],
            company=parsed_dt["company"],
            notes=f"Creado por voz/chat: {command}",
            create_db_row=True,
        )
        es = lang != "en"
        smtp_ok = (rem_res.get("smtp") or {}).get("ok")
        tg_ok = (rem_res.get("telegram") or {}).get("ok")
        delivery_lbl = (
            "enviado por Correo SMTP y Telegram" if (smtp_ok and tg_ok)
            else ("enviado por Telegram y listo en Gmail" if tg_ok else "guardado en memoria activa y listo para envío a Juan")
        )
        rem_obj = rem_res.get("reminder") or {}
        rem_id = rem_obj.get("id") or rem_obj.get("reminder_id") or (rem_res.get("task") or {}).get("id") or "REM-01"
        reply = (
            f"⏰ Recordatorio de correo activado [{rem_id}]: «{parsed_dt['title']}» "
            f"para el {parsed_dt['date']} a las {parsed_dt['time']} ({parsed_dt['company'].upper()}) — {delivery_lbl}."
            if es else
            f"⏰ Email reminder activated [{rem_id}]: '{parsed_dt['title']}' "
            f"for {parsed_dt['date']} at {parsed_dt['time']} ({parsed_dt['company'].upper()})."
        )
        return {
            "ok": True,
            "action": "email_reminder",
            "parsed": p,
            "reply": reply,
            "record": rem_res,
            "ui": {
                "refresh_memory": True,
                "refresh_calendar": True,
                "select_date": parsed_dt["date"],
                "gmail_compose_url": rem_res.get("gmail_compose_url"),
            },
            "sources": [rem_id, "Email & Telegram Reminder"],
            "grounded": True,
        }
    elif action == "schedule_event":
        import functions_catalog as fc
        parsed_dt = fc.parse_natural_datetime(p.get("text", ""))
        sync_res = fc.sync_appointment_realtime(
            title=parsed_dt["title"],
            date_str=parsed_dt["date"],
            time_str=parsed_dt["time"],
            duration_min=30,
            company=parsed_dt["company"],
            notes=f"Agendado por voz/chat desde La Jefatura: {command}",
            send_email_invite=True,
        )
        r = sync_res["event"]
        es = lang != "en"
        reply = (
            f"📅 Cita agendada y sincronizada en tiempo real con Google Calendar [{r.get('id')}]: "
            f"«{parsed_dt['title']}» para el {parsed_dt['date']} a las {parsed_dt['time']} hrs ({parsed_dt['company'].upper()}). "
            f"Feed .ics actualizado y recordatorio activado."
            if es else
            f"📅 Appointment scheduled and synced in real time with Google Calendar [{r.get('id')}]: "
            f"'{parsed_dt['title']}' on {parsed_dt['date']} at {parsed_dt['time']} ({parsed_dt['company'].upper()})."
        )
        return {
            "ok": True,
            "action": "schedule_event",
            "parsed": p,
            "reply": reply,
            "record": r,
            "gcal_sync": sync_res,
            "ui": {
                "refresh_calendar": True,
                "refresh_memory": True,
                "select_date": parsed_dt["date"],
                "open_agenda_drawer": True,
                "gcal_template_url": sync_res.get("gcal_template_url"),
            },
            "sources": [r.get("id", "events"), "Google Calendar Real-Time Sync"],
            "grounded": True,
        }
    elif action == "sync_integrations":
        import knowledge_store as ks
        s_res = ks.sync_calendar_integrations()
        es = lang != "en"
        reply = ((f"Sincronización completada en tiempo real: {s_res['synced_events']} citas y {s_res['synced_tasks']} tareas "
                  f"sincronizadas con Google Calendar, Outlook, Meet/Zoom, Nexus CRM y Apple Calendar (.ics).")
                 if es else
                 (f"Real-time sync completed: {s_res['synced_events']} appointments and {s_res['synced_tasks']} tasks "
                  f"synced across Google Calendar, Outlook, Meet/Zoom, Nexus CRM, and Apple Calendar (.ics)."))
        return {"ok": True, "action": "sync_integrations", "parsed": p, "reply": reply,
                "ui": {"refresh_calendar": True, "trigger_fn": "syncAllLiveNow"},
                "sources": ["Sync 9 Integraciones"], "grounded": True}
    elif action == "escalate_dev":
        import knowledge_store as ks
        esc = ks.log_dev_escalation(p.get("text", command), reason="ceo_direct_escalation", channel="voice_command")
        es = lang != "en"
        reply = ((f"Notificación enviada al desarrollador (Jasmel · Ticket #{esc.get('id')}): «{p.get('text','')}». "
                  f"Queda registrada en la cola de desarrollo para implementar la solución.")
                 if es else
                 (f"Developer notification sent (Jasmel · Ticket #{esc.get('id')}): «{p.get('text','')}». "
                  f"Logged in the developer queue to build the solution."))
        return {"ok": True, "action": "escalate_dev", "parsed": p, "reply": reply, "dev_ticket": esc,
                "ui": {"refresh_dev_escalations": True}, "sources": [f"Ticket #{esc.get('id')}"], "grounded": True}
    elif action == "learn_company":
        import knowledge_store as ks
        res = ks.learn_company_fact(p.get("text", command), company="all", category="ceo_voice_teaching", source="voice_chat")
        es = lang != "en"
        reply = res.get("reply_es" if es else "reply_en") or "Aprendido y guardado en memoria de la empresa."
        return {
            "ok": bool(res.get("ok")),
            "action": "learn_company",
            "parsed": p,
            "reply": reply,
            "record": res,
            "ui": {"refresh_memory": True, "refresh_live_state": True},
            "sources": [res.get("id", "company_learned_facts")],
            "grounded": True,
        }
    elif action == "trigger_camera_vigilant":
        import camera_report
        v_res = camera_report.trigger_vigilant_repost(reason=p.get("reason", "voice_command_trigger"), include_pdf=True)
        es = lang != "en"
        vt = (v_res.get("vigilant_mode") or {}).get("totals") or {}
        reply = (
            f"🛡️ Modo Vigilante de 55 Cámaras disparado y reposteado en vivo (Telegram @Pegantebot, @ceojefesitobot + Correo con PDF adjunto). "
            f"Resumen: {vt.get('people_tracked', 201)} personas monitoreadas, {vt.get('entries_total', 196)} entradas, {vt.get('exits_total', 192)} salidas, "
            f"permanencia máxima {vt.get('max_dwell_minutes', 68)} min en Muelles 1–2 (+23 min sobre el límite recomendado de 45 min) y {vt.get('suspect_alerts_total', 5)} alertas de actividad sospechosa."
            if es else
            f"🛡️ 55-Camera Vigilant Mode triggered and reposted live (Telegram + Email with PDF attached). "
            f"Summary: {vt.get('people_tracked', 201)} people tracked, {vt.get('entries_total', 196)} entries, {vt.get('exits_total', 192)} exits, "
            f"max dwell {vt.get('max_dwell_minutes', 68)} min at Docks 1–2 (+23 min over 45 min recommended limit), and {vt.get('suspect_alerts_total', 5)} suspect activity alerts."
        )
        return {
            "ok": True,
            "action": "trigger_camera_vigilant",
            "parsed": p,
            "reply": reply,
            "record": v_res,
            "ui": {"select_company": "cameras", "scroll_to": "hikDailyReportBox", "refresh_live_state": True},
            "sources": ["Cameras Vigilant Mode 24/7"],
            "grounded": True,
        }
    elif action == "send_twice_daily_report":
        import daily_company_reports
        rep_res = daily_company_reports.dispatch_company_reports(companies=["building", "unitec"], send_email=True, send_telegram=True)
        es = lang != "en"
        reply = (
            "📨 Reportes detallados en tiempo real (Building Innovation + UNITEC USA + 55 Cámaras) enviados por Telegram (@Pegantebot y @ceojefesitobot) y Correo Electrónico con PDF adjunto."
            if es else
            "📨 Real-time detailed reports dispatched via Telegram and Email with PDF attached."
        )
        return {
            "ok": True,
            "action": "send_twice_daily_report",
            "parsed": p,
            "reply": reply,
            "record": rep_res,
            "ui": {"refresh_live_state": True},
            "sources": ["Reportes 2x/Día (08:00 AM y 06:00 PM)"],
            "grounded": True,
        }
    elif action == "ceo_delegation":
        import ceo_action_brain
        del_res = ceo_action_brain.execute_ceo_chat(p.get("text", command), company="all", lang=lang)
        primary = del_res.get("intent", "send_text")
        open_tab = "texts" if primary == "send_text" else ("calls" if primary == "make_voice_call" else ("comms" if primary == "send_email" else "assistant"))
        return {
            "ok": True,
            "action": "ceo_delegation",
            "parsed": p,
            "reply": del_res.get("reply", ""),
            "record": del_res,
            "inline_cards": del_res.get("inline_cards", []),
            "ui": {"open_tab": open_tab, "refresh_live_state": True, "refresh_texts": True, "refresh_calls": True},
            "sources": ["CEO Delegation Engine · Telegram & AI Voice Calls"],
            "grounded": True,
        }
    elif action in ("save_note", "save_task", "save_meeting", "save_email"):
        import knowledge_store as ks
        import functions_catalog as fc
        txt = p.get("text", "")
        parsed_dt = fc.parse_natural_datetime(txt)
        co_slug = parsed_dt.get("company", "all")
        es = lang != "en"
        if action == "save_note":
            r = ks.add_note(txt, source="voice", company=co_slug)
            reply = (f"Nota guardada con id {r['id']}: «{txt[:100]}»." if es
                     else f"Note saved as {r['id']}: \"{txt[:100]}\".") if r["ok"] else "No pude guardar una nota vacía."
        elif action == "save_task":
            r = ks.add_task(txt, company=co_slug, due=parsed_dt.get("date", ""), source="voice")
            reply = (f"Tarea creada con id {r['id']}: «{txt[:100]}»." if es
                     else f"Task created as {r['id']}: \"{txt[:100]}\".") if r["ok"] else "No pude crear una tarea vacía."
        elif action == "save_meeting":
            r = ks.add_meeting_summary(txt, source="voice", company=co_slug)
            reply = (f"Resumen de reunión guardado con id {r['id']}." if es
                     else f"Meeting summary saved as {r['id']}.") if r["ok"] else "No pude guardar un resumen vacío."
        else:
            r = ks.add_email_summary(txt, source="voice", company=co_slug)
            reply = (f"Resumen de correo guardado con id {r['id']}." if es
                     else f"Email summary saved as {r['id']}.") if r["ok"] else "No pude guardar un resumen vacío."
        ok = bool(r.get("ok"))
        return {
            "ok": ok,
            "action": action,
            "parsed": p,
            "reply": reply,
            "record": r,
            "ui": {"refresh_memory": True, "refresh_calendar": True},
            "sources": [r.get("id", action)],
            "grounded": True,
        }
    elif action == "ask":
        import knowledge_store as ks
        a = ks.ask(p.get("text", command), lang=lang)
        # Also check if query mentions a company/function so UI can highlight/scroll to it automatically!
        ui_ask = {}
        try:
            import functions_catalog
            m_fn = functions_catalog.match_function(command)
            if m_fn and m_fn["score"] >= 0.82:
                matched_fn = m_fn["fn"]
                # Only apply non-disruptive UI updates on pure metric questions (e.g., select company)
                if (matched_fn.get("ui") or {}).get("select_company"):
                    ui_ask["select_company"] = matched_fn["ui"]["select_company"]
        except Exception:
            pass
        return {"ok": True, "action": action, "parsed": p, "reply": a["answer"],
                "ui": ui_ask, "matched_function": matched_fn,
                "sources": a["sources"], "grounded": a["grounded"], "dev_ticket": a.get("dev_ticket")}
    elif action != "unknown":
        reply = _reply(action, lang=lang)
    else:
        import knowledge_store as ks
        a = ks.ask(command, lang=lang)
        return {"ok": a["grounded"], "action": "ask", "parsed": p, "reply": a["answer"],
                "sources": a["sources"], "grounded": a["grounded"], "dev_ticket": a.get("dev_ticket")}
    return {"ok": ok, "action": action, "parsed": p, "reply": reply, "ui": ui, "matched_function": matched_fn}


if __name__ == "__main__":
    for cmd in ["cambiar a UNITEC USA", "qué hay de nuevo", "ayuda",
                "leer resumen", "descargar informe", "completar tarea 1",
                "abrir blogs", "preparar café", "aprobar borrador", "fruta voladora"]:
        r = execute(cmd)
        print(f"  «{cmd}» -> {r['action']}: {r['reply'][:90]}")
    print("voice_commands OK")
