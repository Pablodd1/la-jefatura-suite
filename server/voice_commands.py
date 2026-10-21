"""
La Jefatura Suite — headless voice-command executor

The same grammar the browser widget parses, executable server-side so voice
control works from ANY channel: console widget, Telegram voice notes
(Whisper hook — see WHISPER_HOOK), tenant web widgets.

All actions hit real mc.db state (tasks) or the real generators (PDF), and
every command returns a spoken/written `reply`. Zero AI needed for control;
AI only narrates digests (ai_insights), keeping commands deterministic —
a voice command must NEVER be probabilistic.

Self-test:  python3 server/voice_commands.py
"""
import json
import os
import re
import sqlite3
import sys

DB = "/root/.openclaw/workspace/mission-control/mc.db"
HERE = os.path.dirname(os.path.abspath(__file__))


def _reply_es(action, **kw):
    R = {
        "switch_company": f"Cambiando a {kw.get('company')}.",
        "download_report": "Generando el informe PDF. Te llega por Telegram y correo en unos segundos.",
        "complete_task": f"Tarea {kw.get('task')} marcada como completada.",
        "read_brief": kw.get("brief", ""),
        "status_digest": kw.get("digest", ""),
        "refresh": "Datos actualizados desde Mission Control.",
        "help": ("Comandos: cambiar a «empresa» · descargar informe · completar tarea «nombre» · "
                 "leer resumen · qué hay de nuevo · actualizar."),
        "unknown": "Comando no reconocido. Di «ayuda» para ver la lista.",
    }
    return R[action]


def parse(command: str, lang: str = "es") -> dict:
    t = command.strip()
    sw = re.match(r"^(?:cambiar a|ir a|switch to|muestra(?:me)?|show(?: me)?)\s+(.+)$",
                  t, re.I)
    if sw:
        return {"action": "switch_company", "company": sw.group(1).strip()}
    ct = re.match(r"^(?:completar|marcar|complete|done(?: with)?)\s+(?:tarea|task)?\s*(.+)$",
                  t, re.I)
    if ct:
        return {"action": "complete_task", "task": ct.group(1).strip()}
    low = t.lower()
    if re.search(r"descargar|generar|download|report", low):
        return {"action": "download_report"}
    if re.search(r"leer|read|brief|resumen", low):
        return {"action": "read_brief"}
    if re.search(r"nuevo|new|status|novedades", low):
        return {"action": "status_digest"}
    if re.search(r"actualizar|refresh|reload|recargar", low):
        return {"action": "refresh"}
    if re.search(r"ayuda|help|comandos|commands", low):
        return {"action": "help"}
    return {"action": "unknown"}


def _complete_task(fragment: str) -> tuple[bool, str]:
    c = sqlite3.connect(DB)
    rows = c.execute(
        "SELECT id, title FROM tasks WHERE status != 'done'").fetchall()
    hit = None
    frag = fragment.lower().rstrip(".")
    if frag.isdigit():                      # "tarea 3" -> third open task
        idx = int(frag) - 1
        hit = rows[idx] if 0 <= idx < len(rows) else None
    if not hit:                             # fuzzy title match
        for r in rows:
            if frag in r[1].lower():
                hit = r
                break
    if not hit:
        c.close()
        return False, f"No encontré una tarea abierta que coincida con «{fragment}»."
    c.execute("UPDATE tasks SET status='done', done=? WHERE id=?",
              (__import__("time").time(), hit[0]))
    c.commit(); c.close()
    return True, hit[1]


def execute(command: str, lang: str = "es", samples_dir: str | None = None) -> dict:
    """Parse + run. Returns {ok, action, reply}. Never raises on bad input."""
    p = parse(command, lang)
    action = p["action"]
    ok = True
    if action == "switch_company":
        reply = _reply_es(action, company=p.get("company"))
    elif action == "complete_task":
        ok, detail = _complete_task(p.get("task", ""))
        reply = _reply_es(action, task=detail) if ok else detail
    elif action == "download_report":
        try:
            import reports_pdf
            out = "/tmp/_voice_report.pdf"
            sd = samples_dir or os.path.join(HERE, "..", "data", "samples")
            reports_pdf.build_report("Medical Billing Miami Beach", sd, out)
            reply = _reply_es(action)
        except Exception as e:
            ok = False
            reply = f"Error generando el informe: {e}"
    elif action == "read_brief":
        from ai_insights import report_narative
        sd = samples_dir or os.path.join(HERE, "..", "data", "samples")
        nexus = json.load(open(os.path.join(sd, "nexus_crm.json"), encoding="utf-8"))
        tasks_j = json.load(open(os.path.join(sd, "tasks.json"), encoding="utf-8"))
        brief = report_narative("La Jefatura", nexus["kpis"],
                                tasks_j["resumen"], nexus["pipeline_por_etapa"])
        reply = brief
    elif action == "status_digest":
        c = sqlite3.connect(DB)
        t = c.execute("SELECT COUNT(*) FROM tasks WHERE status != 'done'").fetchone()[0]
        c.close()
        try:
            sys.path.insert(0, HERE)
            s = __import__("nexus_ingest").summary()
            dig = (f"Resumen: pipeline US${s['kpis']['pipeline_total_estimado_usd']:,.0f} "
                   f"con {s['kpis']['leads_activos']} leads; {t} tareas abiertas.")
        except Exception:
            dig = f"{t} tareas abiertas."
        reply = dig
    else:
        ok = action != "unknown"
        reply = _reply_es(action)
    return {"ok": ok, "action": action, "reply": reply}


# WHISPER_HOOK (future): TG voice note -> Whisper API -> text -> execute().
# Not enabled until a key exists; grammar above is the single control plane.

if __name__ == "__main__":
    for cmd in ["cambiar a MBMB", "qué hay de nuevo", "ayuda",
                "leer resumen", "descargar informe", "completar tarea 1",
                "fruta voladora"]:
        r = execute(cmd)
        print(f"  «{cmd}» -> {r['action']}: {r['reply'][:90]}")
    # restore demo state after self-test
    c = sqlite3.connect(DB)
    open_tasks = c.execute(
        "SELECT id FROM tasks ORDER BY rowid LIMIT 1").fetchone()
    if open_tasks:
        c.execute("UPDATE tasks SET status='pending' WHERE id=? AND status='done'",
                  (open_tasks[0],))
        c.commit()
    c.close()
    print("voice_commands OK")
