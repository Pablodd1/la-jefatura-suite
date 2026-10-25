"""Tests for El Jefesito: control by text/voice, themes, greeting, daily sheets, close-day, learning, PDF.

Run: python scripts/test_jefesito.py   (uses a throwaway DB)
"""
import datetime
import os
import sys
import tempfile

TMP = tempfile.mkdtemp()
os.environ["MC_DB_PATH"] = os.path.join(TMP, "test_mc.db")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "server"))

import daily_pdf  # noqa: E402
import jefesito as jf  # noqa: E402
import knowledge_store as ks  # noqa: E402
import voice_commands as vc  # noqa: E402

FAILS = []


def check(name, cond, detail=""):
    print(("PASS" if cond else "FAIL"), "|", name, "|", str(detail)[:170])
    if not cond:
        FAILS.append(name)


# 1. Defaults + 3 themes
p = jf.get_prefs()
check("defaults", p["theme"] == "graphite" and p["greeting_enabled"] is True and p["lang"] == "es", p)
check("exactly 3 themes, one yellow/black", len(jf.THEMES) == 3 and "yellow" in jf.THEMES, list(jf.THEMES))

# 2. Theme control by text/voice (persisted)
r = vc.execute("cambia el tema a amarillo")
check("theme yellow via command", r["action"] == "control" and r["ui"] == {"set_theme": "yellow"}, r["reply"])
check("theme persisted", jf.get_prefs()["theme"] == "yellow")
r = vc.execute("ponme el tema claro")
check("theme light", r["ui"] == {"set_theme": "light"} and jf.get_prefs()["theme"] == "light", r["reply"])
r = vc.execute("switch to the dark theme")
check("theme graphite (EN)", r["ui"] == {"set_theme": "graphite"}, r["reply"])
r = vc.execute("ofréceme temas")
check("offers the 3 themes, no change", all(n in r["reply"] for n in ("Claro", "Grafito", "Amarillo")) and not r.get("ui"), r["reply"])

# 3. Greeting control
r = vc.execute("detén el saludo")
check("stop greeting persisted", r["ui"] == {"set_greeting": False} and jf.get_prefs()["greeting_enabled"] is False, r["reply"])
r = vc.execute("activa el saludo")
check("enable greeting", r["ui"] == {"set_greeting": True} and jf.get_prefs()["greeting_enabled"] is True, r["reply"])

# 4. Language + name
r = vc.execute("habla en inglés")
check("language switch", r["ui"] == {"set_lang": "en"} and jf.get_prefs()["lang"] == "en", r["reply"])
vc.execute("speak Spanish")
r = vc.execute("llámame Juan")
check("name saved", jf.get_prefs()["ceo_name"] == "Juan" and r["ui"] == {"set_name": "Juan"}, r["reply"])

# 5. Notes that merely contain control words are NOT hijacked
r = vc.execute("guardar nota: cambiar el tema de la reunión y cerrar el día con Juan")
check("save_note not hijacked by control words", r["action"] == "save_note" and r["ok"], r["reply"])

# 6. Brief is grounded in connected data and never prints None
ks.add_task("Enviar propuesta a Doral", source="voice")
ks.ensure_demo_knowledge_seeded()
t0 = datetime.date(2026, 10, 26)
d = jf.get_day(t0, "es", today=t0)
facts = ks._facts()
bm = facts["building"][0]["members"]["total"]
check("brief cites BuildingApp member total from snapshot", f"{bm} miembros" in d["spoken"], d["spoken"][:200])
check("brief has no 'None'", "None" not in d["spoken"], "")
check("brief labels demo samples", "de ejemplo" in d["spoken"])
check("brief names the CEO", "Juan" in d["greeting"], d["greeting"])
check("brief lists the real open task", "Doral" in d["spoken"])
de = jf.get_day(t0, "en", today=t0)
check("english brief", "members" in de["spoken"] and "Summary for" in de["greeting"], de["greeting"])

# 7. Learning: honest when few interactions, real profile when enough
r = vc.execute("qué has aprendido de mí")
check("few interactions -> refuses to claim habits", "no voy a inventarlos" in r["reply"] or "too few" in r["reply"], r["reply"])
for txt, ch in [("abrir blogs", "voice"), ("abrir bandeja", "voice"), ("abrir resultados", "text"),
                ("preparar café", "voice"), ("leer resumen", "voice"), ("qué notas tengo", "text")]:
    jf.record(txt, ch, "open_tab", "es")
pr = jf.profile()
check("profile counts interactions", pr["interactions"] >= 6 and pr["enough"], pr["interactions"])
check("profile voice share is computed (4 of 6 recorded by hand)", pr["voice_pct"] > 0, pr["voice_pct"])
check("concise style detected from short commands", pr["style"] == "concise", pr["style"])
r = vc.execute("what have you learned about me", lang="en")
check("profile reply cites interaction count", "interactions" in r["reply"] and r["sources"], r["reply"][:140])
d2 = jf.get_day(t0, "es", today=t0)
check("brief now reports the learned profile", "he aprendido de ti" in " ".join(" ".join(s["lines"]) for s in d2["sections"]).lower(), "")

# 8. Sheets: open day first, day after second; closing starts a new sheet
pg = jf.pages("es", today=t0)
check("page 1 = today (text first page)", pg[0]["day"] == "2026-10-26" and pg[0]["kind"] == "day" and not pg[0]["closed"], pg[0]["label"])
check("page 2 = day after (preview)", pg[1]["day"] == "2026-10-27" and pg[1]["kind"] == "preview", pg[1]["label"])
check("preview never invents metrics", "no se estiman" in " ".join(" ".join(s["lines"]) for s in pg[1]["sections"]), "")
jf.close_day(today=t0)
pg = jf.pages("es", today=t0)
check("after close: new sheet = tomorrow", pg[0]["day"] == "2026-10-27" and pg[0]["kind"] == "preview", pg[0]["label"])
check("after close: second = day after tomorrow", pg[1]["day"] == "2026-10-28", pg[1]["label"])
check("closed day is archived", any(p_["day"] == "2026-10-26" and p_["closed"] for p_ in pg[2:]), [p_["day"] for p_ in pg])
frozen = jf.get_day(t0, "es", today=t0)["spoken"]
ks.add_note("nota posterior al cierre")
check("closed day is frozen (not rewritten)", jf.get_day(t0, "es", today=t0)["spoken"] == frozen)

# 9. Printable PDF
out = os.path.join(TMP, "daily.pdf")
built = daily_pdf.build(out, "es", today=t0)
raw = open(built, "rb").read()
npages = raw.count(b"/Type /Page") - raw.count(b"/Type /Pages")
check("PDF built", built.endswith(".pdf") and raw[:4] == b"%PDF", f"{len(raw)} bytes, {npages} pages")
check("PDF has one sheet per day (>=3)", npages >= 3, npages)

# 10. Existing commands still work
for cmd, act in [("ayuda", "help"), ("abrir blogs", "open_tab"), ("preparar café", "confirm_coffee")]:
    check(f"still works: {cmd}", vc.execute(cmd)["action"] == act)

print("\nFAILED:" if FAILS else "\nALL TESTS PASSED", FAILS or "")
sys.exit(1 if FAILS else 0)
