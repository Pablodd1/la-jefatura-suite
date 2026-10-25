"""Tests for notes/tasks/meetings/emails + grounded Q&A. Uses a throwaway DB.

Run: python scripts/test_knowledge.py
"""
import os
import sys
import tempfile

TMP = tempfile.mkdtemp()
os.environ["MC_DB_PATH"] = os.path.join(TMP, "test_mc.db")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "server"))

import knowledge_store as ks  # noqa: E402
import voice_commands as vc  # noqa: E402

FAILS = []


def check(name, cond, detail=""):
    print(("PASS" if cond else "FAIL"), "|", name, "|", str(detail)[:160])
    if not cond:
        FAILS.append(name)


# 1. Empty store: never guess
r = vc.execute("qué notas tengo")
check("empty notes -> explicit none", "No tengo" in r["reply"] and r["action"] == "ask", r["reply"])
r = vc.execute("qué dijo Juan sobre el contrato de Tampa")
check("unknown fact on empty store -> refuses to guess", r["grounded"] is False and "no voy a adivinar" in r["reply"], r["reply"])

# 2. Saving by voice. Words like «mañana» / «café» must NOT trigger routine/coffee commands.
r = vc.execute("guardar nota: llamar mañana a Juan por el contrato de Tampa y confirmar café con el cliente")
check("save_note routed (not switch_slot/coffee)", r["action"] == "save_note" and r["ok"], r["reply"])
r = vc.execute("crear tarea enviar propuesta a Doral Urgent Care antes del viernes")
check("save_task", r["action"] == "save_task" and r["ok"], r["reply"])
r = vc.execute("guardar resumen de reunión: Brickell Ortho aprobó el piloto de 3 sedes, arranca el lunes, pendiente enviar contrato")
check("save_meeting", r["action"] == "save_meeting" and r["ok"], r["reply"])
r = vc.execute("save email summary: Supplier says container ETA moved to November 4")
check("save_email", r["action"] == "save_email" and r["ok"], r["reply"])
r = vc.execute("nota: revisar precios de PVC")
check("short 'nota:' form", r["action"] == "save_note", r["reply"])

# 3. Retrieval returns ONLY what was stored, with ids
r = vc.execute("qué dijo Brickell sobre el piloto")
check("meeting recalled verbatim w/ id", "3 sedes" in r["reply"] and r["grounded"] and r["sources"], r["reply"])
r = vc.execute("buscar container November")
check("email recalled", "November 4" in r["reply"], r["reply"])
r = vc.execute("buscar contenedor noviembre")
check("cross-language query is NOT silently translated/guessed", r["grounded"] is False, r["reply"])
r = vc.execute("cuántas notas tengo")
check("count from DB", "Tienes 2" in r["reply"], r["reply"])
r = vc.execute("qué tareas tengo")
check("only MY task counted, demo samples flagged", "Tienes 1 tareas" in r["reply"] and "Doral" in r["reply"]
      and "de ejemplo" in r["reply"], r["reply"])

# 4. Hallucination traps: facts that were NOT stored
r = vc.execute("qué dijo Brickell sobre el precio del contrato de Miami")
check("partial match is disclosed as NOT exact", "no exacta" in r["reply"].lower() or "coincidencia exacta" in r["reply"]
      and r.get("grounded") is True, r["reply"])
for q in ["cuál es el teléfono del doctor Khalil",
          "what did Maria say about the warehouse inventory"]:
    r = vc.execute(q)
    check(f"trap refuses: {q[:45]}", r["grounded"] is False and
          ("No tengo" in r["reply"] or "don't have" in r["reply"]), r["reply"])

# 5. English
r = ks.ask("what notes do I have", lang="en")
check("english list", "You have 2" in r["answer"], r["answer"])

# 6. Export has everything saved
ex = ks.export_all()
check("export contains all", len(ex["notes"]) == 2 and len(ex["meetings"]) == 1 and len(ex["emails"]) == 1
      and any("Doral" in t["title"] for t in ex["tasks"]), {k: len(v) for k, v in ex.items()})

# 7. Existing commands still work
r = vc.execute("ayuda")
check("help still works", r["action"] == "help", r["reply"])
r = vc.execute("abrir blogs")
check("open_tab still works", r["action"] == "open_tab", r["reply"])
r = vc.execute("preparar café")
check("coffee still works", r["action"] == "confirm_coffee", r["reply"])

# 8. Metric answers carry a source
r = vc.execute("cuántos miembros nuevos hay en BuildingApp")
check("metric answer cites source", r["grounded"] and r["sources"] and "BuildingApp" in r["sources"][0], r["reply"] + " || " + str(r["sources"]))

print("\nFAILED:" if FAILS else "\nALL TESTS PASSED", FAILS or "")
sys.exit(1 if FAILS else 0)
