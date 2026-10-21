# JASMEL'S REQUESTS — verbatim, with objectives

> This file preserves exactly what Jasmel Acosta (owner) asked for, in his
> words, so the next developer understands the *intent*, not just the code.
> Source: Telegram conversation, Oct 21–22, 2026 (Asia/Shanghai timestamps).
> Kimi Claw (the AI assistant who built v1/v2) compiled this handoff.

---

## Request 1 — "follow up to the pdf capability" (Oct 21, 15:26 Miami)

> "follow up to the pdf capability. if i were to use this as a white label
> service for 10 compoanies id likje each company to have a full report
> including their dailey sales their staffs task and whatever elase
> [LINK: https://latitude-here-windsor-radical.trycloudflare.com/]"
> (link = La Jefatura v2 CEO dashboard, Mission Control on port 8090)

**Decoded objectives:**
- **White-label product**: sell "La Jefatura" to ~10 companies as a service.
- **Per-company full PDF report**: daily sales, staff tasks, "whatever else" —
  i.e. everything the CEO console already shows (agenda, emails, alerts).
- This is the wedge for a real SaaS: each tenant pays for their own branded
  morning report.

## Request 2 — "how does nexus work" (Oct 21, 15:40 Miami)

> "how does nexus work? can it be automated? or extract the results at least?"

**Context given**: Nexus CRM = https://nexus-crm-global.ai.studio/ — a custom
CRM built by Carlos/Saleinnovation. Dashboard shows:
- `LEADS ACTIVOS: 23`, `TIEMPO PROM CONVERSION: 11 días`,
  `INGRESO MENSUAL PROYECTADO: $48,200`, `VENTAS CERRADAS TOTALES: $96,400`,
  `TASA CONVERSION GLOBAL: 31%`
- Sellers: Juan Perez (top seller), Maria Gomez, Carlos Ruiz
- Fields per lead: `EMPRESA, CONTACTO, PAIS (USA/Colombia/Mexico/Chile),
  ETAPA (No Contactado/Contactado/Cotizacion/Cerrado), VALOR USD,
  PROBABILIDAD %, DIAS, VENDEDOR, ULTIMA NOTA`
- Visits table: `ID VISITA, CLIENTE, PAIS, VENDEDOR, FECHA, OBJETIVO,
  RESULTADO, NOTA`
- Jasmel's exact words: **"i know nexus pulls form some kind of db can u check
  its its remote so that way anyone using it gets same results"**

**Decoded objectives:**
- Get Nexus's shared database remote so every seller sees the same pipeline.
- Automate or extract results (pipeline numbers) into the CEO console + PDF.
- Jasmel *believes* Nexus has a server DB ("pulls from some kind of db").
- **Verified reality**: Nexus is a hosted web app whose data lives in the
  browser (IndexedDB / Dexie). No shared server store is visible. That fact
  changes the design — see ARCHITECTURE.md.

## Request 3 — cameras (Oct 21, 15:49 Miami)

> "do u know how to check cameras? i got few cameras id like a summary of
> things and also they can be seen in the dashboard"

**Decoded objectives:**
- Jasmel owns several security cameras (brands/models NOT yet provided).
- Wants: (a) camera views embedded in the CEO dashboard, (b) an AI *summary*
  of camera events (not raw footage review) — "a summary of things".

## Request 4 — the build order (Oct 21, 15:53 Miami)

> "lets do it in this order: 1.nexus 2.cameras 3.full company report for pdf
> 4. also make it pretty and change language based on page settings"

**Objectives:**
1. Nexus integration first (pipeline data).
2. Cameras second.
3. Full per-company PDF report third.
4. Polish the UI ("make it pretty") and make it **bilingual — follow the
   page's language setting** (EN/ES).

## Request 5 — the handoff directive (Oct 22, 03:54 GMT+8)

> "when done, place in a repo, leave all the detail about my request and the
> objectives for another developer to read, review and continue the work,
> dont be lazy, also check online for other similar use cases, dont guess.
> copy, mimic and improve add all ai when is required"

**Objectives:**
- Public repo with THIS documentation set (README + JASMEL_REQUESTS +
  RESEARCH + ARCHITECTURE + HANDOFF).
- Ground every design decision in researched, real-world precedents —
  "dont guess. copy, mimic and improve".
- Add AI wherever it genuinely adds value ("add all ai when is required").
- And separately: **"send the repo to my email when done"** → deliver repo
  URL + summary to jasmelacosta@gmail.com.

---

## What the previous AI (Kimi Claw) already delivered before this handoff

| Item | State | Location |
|---|---|---|
| CEO console v2 (Apple-minimal dashboard) | LIVE | `/root/.openclaw/workspace/mission-control/mission_control.py` + `shots/ceo.html` |
| Escalation engine (24h nudge / 48h critical to Telegram) | LIVE, tested | `mission-control/escalate.py` (cron hourly) |
| "Informe del Jefe" (daily TG text + Spanish voice brief) | LIVE, delivered daily 8:17am Miami | `mission-control/informe.py` (cron 20:17 CST) |
| 305business backend rewire (MC-native auth + Supabase swap) | LIVE, E2E verified | `305business-llc/` repo |
| La Jefatura Suite (this repo) | THIS DELIVERABLE | Nexus ingest, cameras scaffold, real PDF generator, demo console, AI layer |

## Known credential issues the next dev must know

- **CEDEXX-era Gemini key is DEAD** (403, service account deleted — confirmed
  Oct 22, 2026). AI narrative falls back to templates until Jasmel provides a
  fresh `GEMINI_API_KEY` (free at aistudio.google.com).
- Supabase CEDEXX project works for data, but **GoTrue auth is broken
  project-wide** (all emails 400). MC-native auth is the workaround.
- Brevo API works (verified Oct 21); SMTP path is flaky — use the REST API.
