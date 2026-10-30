"""
La Jefatura Suite — Nexus CRM ingestion + read API

PROBLEM THIS SOLVES (read docs/JASMEL_REQUESTS.md first):
  Nexus CRM (https://nexus-crm-global.ai.studio/) stores ALL its data in the
  browser's IndexedDB. There is no server database — Juan's data on his laptop
  never reaches Jasmel, and vice versa. Nothing to extract remotely.

  This module gives Nexus a shared brain: Mission Control becomes the sync
  target. Two integration paths (pick one):

  PATH A — "Wire the repo" (best): the next developer gets the Nexus source,
           replaces its IndexedDB persistence layer with POST calls to
           POST /api/nexus/push (schema below matches the Nexus UI exactly:
           leads have empresa/contacto/pais/etapa/valor_usd, visits have
           cliente/objetivo/resultado/nota).

  PATH B — "Browser bridge" (no repo needed): ship sellers a tiny userscript/
           bookmarklet that reads IndexedDB (Dexie table names are visible in
           the app bundle) and POSTs deltas to /api/nexus/push every N minutes.
           See scripts/nexus_bridge_snippet.js.

Storage: SQLite (same mc.db as Mission Control) — tables nexus_leads,
nexus_visits, nexus_sync_log.
"""

import json
import sqlite3
import time

import os; _PROD_DIR = "/root/.openclaw/workspace/mission-control"; DB = os.environ.get("MC_DB_PATH") or (os.path.join(_PROD_DIR, "mc.db") if os.path.isdir(_PROD_DIR) else os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "mc.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS nexus_leads (
    id TEXT PRIMARY KEY,
    empresa TEXT, contacto TEXT, pais TEXT,
    etapa TEXT, valor_usd REAL, probabilidad_pct INTEGER,
    dias INTEGER, vendedor TEXT, ultima_nota TEXT,
    updated_at REAL
);
CREATE TABLE IF NOT EXISTS nexus_visits (
    id TEXT PRIMARY KEY,
    cliente TEXT, pais TEXT, vendedor TEXT, fecha TEXT,
    objetivo TEXT, resultado TEXT, nota TEXT,
    updated_at REAL
);
CREATE TABLE IF NOT EXISTS nexus_sync_log (
    ts REAL, source TEXT, leads INT, visits INT, status TEXT
);
"""


def db():
    c = sqlite3.connect(DB, timeout=30.0)
    c.executescript(SCHEMA)
    return c


# ── Write ────────────────────────────────────────────────────────────────────

def push(payload: dict, source: str = "nexus") -> dict:
    """Bulk upsert from a Nexus client/bridge.

    payload = {"leads": [...], "visits": [...]}
    Records carry their natural key (id or empresa+contacto). Upsert semantics:
    last write wins per id — the bridge sends the browser's current state.
    """
    now = time.time()
    leads = payload.get("leads") or []
    visits = payload.get("visits") or []
    c = db()
    for L in leads:
        lid = str(L.get("id") or f"{L.get('empresa','?')}|{L.get('contacto','?')}")
        c.execute(
            "INSERT INTO nexus_leads VALUES(?,?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET empresa=excluded.empresa, "
            "contacto=excluded.contacto, pais=excluded.pais, etapa=excluded.etapa, "
            "valor_usd=excluded.valor_usd, probabilidad_pct=excluded.probabilidad_pct, "
            "dias=excluded.dias, vendedor=excluded.vendedor, "
            "ultima_nota=excluded.ultima_nota, updated_at=excluded.updated_at",
            (lid, L.get("empresa"), L.get("contacto"), L.get("pais"),
             L.get("etapa"), L.get("valor_usd"), L.get("probabilidad_pct"),
             L.get("dias"), L.get("vendedor"), L.get("ultima_nota"), now))
    for V in visits:
        vid = str(V.get("id") or f"{V.get('cliente','?')}|{V.get('fecha','?')}")
        c.execute(
            "INSERT INTO nexus_visits VALUES(?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET cliente=excluded.cliente, "
            "pais=excluded.pais, vendedor=excluded.vendedor, fecha=excluded.fecha, "
            "objetivo=excluded.objetivo, resultado=excluded.resultado, "
            "nota=excluded.nota, updated_at=excluded.updated_at",
            (vid, V.get("cliente"), V.get("pais"), V.get("vendedor"),
             V.get("fecha"), V.get("objetivo"), V.get("resultado"),
             V.get("nota"), now))
    c.execute("INSERT INTO nexus_sync_log VALUES(?,?,?,?,?)",
              (now, source, len(leads), len(visits), "ok"))
    c.commit(); c.close()
    return {"ok": True, "leads": len(leads), "visits": len(visits)}


# ── Read ─────────────────────────────────────────────────────────────────────

def summary() -> dict:
    """Aggregates in the exact shape the Nexus dashboard shows (so the MC
    console and the PDF report render identically to the CRM the sellers use)."""
    c = db()
    stages = c.execute(
        "SELECT etapa, COUNT(*), COALESCE(SUM(valor_usd),0) "
        "FROM nexus_leads GROUP BY etapa").fetchall()
    countries = c.execute(
        "SELECT pais, COUNT(*), COALESCE(SUM(valor_usd),0) "
        "FROM nexus_leads GROUP BY pais ORDER BY 3 DESC").fetchall()
    sellers = c.execute(
        "SELECT vendedor, SUM(CASE WHEN etapa='cerrado' THEN 1 ELSE 0 END), "
        "COALESCE(SUM(valor_usd),0), "
        "ROUND(100.0*SUM(CASE WHEN etapa='cerrado' THEN 1 ELSE 0 END)/COUNT(*),1) "
        "FROM nexus_leads GROUP BY vendedor ORDER BY 3 DESC").fetchall()
    totals = c.execute(
        "SELECT COUNT(*), COALESCE(SUM(valor_usd),0), "
        "COALESCE(SUM(CASE WHEN etapa='cerrado' THEN valor_usd ELSE 0 END),0) "
        "FROM nexus_leads").fetchone()
    visits = c.execute("SELECT COUNT(*) FROM nexus_visits").fetchone()[0]
    recent_visits = [dict(zip(("id", "cliente", "pais", "vendedor", "fecha",
                               "objetivo", "resultado", "nota", "updated_at"), r))
                     for r in c.execute(
        "SELECT * FROM nexus_visits ORDER BY fecha DESC LIMIT 8")]
    top_leads = [dict(zip(("id", "empresa", "contacto", "pais", "etapa",
                           "valor_usd", "probabilidad_pct", "dias", "vendedor",
                           "ultima_nota", "updated_at"), r))
                 for r in c.execute(
        "SELECT * FROM nexus_leads ORDER BY valor_usd DESC LIMIT 10")]
    c.close()
    return {
        "kpis": {
            "leads_activos": totals[0],
            "pipeline_total_estimado_usd": totals[1],
            "ventas_cerradas_total_usd": totals[2],
            "visitas_registradas": visits,
        },
        "pipeline_por_etapa": [
            {"etapa": s, "count": n, "valor_usd": v} for s, n, v in stages],
        "pipeline_por_pais": [
            {"pais": p, "leads": n, "valor_usd": v} for p, n, v in countries],
        "top_vendedores": [
            {"nombre": n, "cerrados": w, "pipeline_usd": v, "conversion_pct": r}
            for n, w, v, r in sellers],
        "visitas_recientes": recent_visits,
        "top_leads": top_leads,
    }


def load_sample(path: str) -> dict:
    """One-shot: seed mc.db from data/samples/nexus_crm.json so the demo and
    the PDF work before any real Nexus client is wired."""
    data = json.load(open(path, encoding="utf-8"))
    return push({"leads": data["leads"], "visits": data["visitas"]},
                source="sample-seed")


# ── Mission Control route table ──────────────────────────────────────────────
# Integrate by adding to mission_control.py's do_POST/do_GET dispatch:
#   from server.nexus_ingest import push, summary   (path adjusted)
#   POST /api/nexus/push    -> push(json_body, source=headers.get('X-Bridge','nexus'))
#   GET  /api/nexus/summary -> summary()
ROUTES = {
    ("POST", "/api/nexus/push"): push,
    ("GET", "/api/nexus/summary"): summary,
}

if __name__ == "__main__":
    # Self-test: seed from sample, read back.
    r = load_sample("../data/samples/nexus_crm.json")
    s = summary()
    print("push:", r)
    print("leads_activos:", s["kpis"]["leads_activos"],
          "| pipeline: $", s["kpis"]["pipeline_total_estimado_usd"],
          "| visitas:", s["kpis"]["visitas_registradas"])
    assert s["kpis"]["leads_activos"] == 12, "sample has 12 leads"
    assert s["kpis"]["visitas_registradas"] == 8, "sample has 8 visits"
    print("nexus_ingest OK")
