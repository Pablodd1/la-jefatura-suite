"""
La Jefatura Suite — AI insights layer (Gemini)

Single responsibility: turn raw metrics/events into executive-ready text.
Used by: nexus_ingest (lead insights), cameras (event summaries), reports_pdf (narrative).

Key rules (from industry research — docs/RESEARCH.md):
  - All CALCULATIONS happen in SQL/code before calling the LLM. The LLM
    only narrates pre-computed numbers (LLMs are bad at math, great at prose).
  - temperature=0 for consistent, professional tone on every run.
  - Graceful fallback: if no GEMINI_API_KEY, return a template narrative so
    the pipeline never breaks.

Env: GEMINI_API_KEY (or falls back to the CEDEXX backend .env on this host —
     that path is dev-machine specific and harmless if absent).
"""

import json
import os
import urllib.request

_MODEL = "gemini-2.5-flash"


def _load_key():
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if key:
        return key
    # Dev convenience: reuse the CEDEXX backend key if it exists on this host.
    # NEVER committed; the .env is gitignored on the CEDEXX repo.
    for path in (
        "/root/.openclaw/workspace/cedexx-repo/backend/.env",
        os.path.join(os.path.dirname(__file__), "..", "..", "cedexx-repo/backend/.env"),
    ):
        try:
            for line in open(path, encoding="utf-8"):
                if line.startswith("GEMINI_API_KEY="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
        except OSError:
            continue
    return ""


def gemini(prompt: str, max_tokens: int = 1024) -> str | None:
    """One-shot Gemini call. Returns None on any failure (caller falls back)."""
    key = _load_key()
    if not key:
        return None
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{_MODEL}:generateContent?key={key}"
    )
    body = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0, "maxOutputTokens": max_tokens},
    }).encode()
    req = urllib.request.Request(url, data=body,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read().decode())
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Pre-built prompts — one function per surface. Data in, narrative out.
# ─────────────────────────────────────────────────────────────────────────────

def report_narative(company: str, kpis: dict, tasks_summary: dict,
                    pipeline: list[dict], lang: str = "es") -> str:
    """Executive narrative for the company PDF report (temperature 0)."""
    lang_note = "Write in Spanish (LatAm business register)." if lang == "es" \
        else "Write in English (executive register)."
    prompt = f"""You are a senior operations analyst writing the executive summary
for the weekly CEO report of '{company}'. {lang_note}

RULES:
- Exactly 3 short paragraphs: (1) performance vs targets, (2) pipeline/risk,
  (3) recommended focus for next week.
- Use ONLY the numbers provided. Never invent figures. Never speculate about
  causes the data does not show.
- Plain prose, no bullet points, no headers, confident but factual tone.

DATA (all pre-calculated):
KPIs: {json.dumps(kpis, ensure_ascii=False)}
Tasks: {json.dumps(tasks_summary, ensure_ascii=False)}
Pipeline by stage: {json.dumps(pipeline, ensure_ascii=False)}

Write only the 3 paragraphs, nothing else."""
    out = gemini(prompt, max_tokens=600)
    if out:
        return out
    # Fallback narrative — pipeline must never break without the key.
    k = kpis
    return (
        f"Resumen ejecutivo ({company}): ingreso mensual proyectado US$"
        f"{k.get('ingreso_mensual_proyectado_usd', 0):,}; pipeline total US$"
        f"{k.get('pipeline_total_estimado_usd', 0):,} con tasa de conversion del "
        f"{k.get('tasa_conversion_global_pct', 0)}%. {tasks_summary.get('overdue', 0)} "
        f"tarea(s) vencida(s) requieren accion inmediata del CEO; "
        f"{tasks_summary.get('due_hoy', 0)} vencen hoy. Enfoque recomendado: "
        f"desbloquear tareas vencidas de alto valor y mantener ritmo de "
        f"cotizaciones en etapa final."
    )


def lead_insight(lead: dict, lang: str = "es") -> str:
    """One-liner 'why this lead matters' for the CRM panel."""
    prompt = f"""In one sentence ({'Spanish' if lang == 'es' else 'English'}), explain
why this sales lead deserves attention NOW. Be concrete, mention value and next action.
Lead: {json.dumps(lead, ensure_ascii=False)}
One sentence only."""
    out = gemini(prompt, max_tokens=120)
    return out or f"Valor US${lead.get('valor_usd', 0):,} — etapa {lead.get('etapa', '?')}."


def camera_event_summary(events: list[dict], lang: str = "es") -> str:
    """Narrative digest of camera events for the daily report."""
    prompt = f"""You are a security digest writer for a CEO morning brief.
{'Spanish' if lang == 'es' else 'English'}. 2-3 sentences max.
Summarize these camera AI events, flag ONLY what needs human attention
(out-of-hours, unknown person, repeated zones). If nothing notable, say so.
Events: {json.dumps(events, ensure_ascii=False)}"""
    out = gemini(prompt, max_tokens=200)
    if out:
        return out
    notable = [e for e in events if e.get("fuera_horario")]
    if notable:
        return (f"{len(notable)} evento(s) fuera de horario detectado(s); "
                f"el mas reciente en {notable[-1].get('zona', 'zona desconocida')}. "
                f"Revisar snapshot en el panel.")
    return "Sin eventos fuera de horario en las ultimas 12 horas."
