# La Jefatura Suite — White-Label CEO Mission Control

**White-label CEO Master Command Center for Jasmel Acosta's companies** — Zero-touch CEO onboarding, Nexus CRM pipeline sync, unified multi-channel AI Comms Brain (pre-drafted replies in the CEO's voice + 1-click Approve & Send), People/Clients/Meetings/Apps outcome studies, AI security camera digest, Behavioral & Time-of-Day Learning Engine (Morning / Afternoon / Evening habits, coffee & report format foresight, UI interaction telemetry), Grok 3.0 Voice & Website DOM Brain layer, per-company board-ready PDF reports, and an interactive Step-by-Step Function Blogs tab.

---

## What's Here

| Path | What |
|---|---|
| `docs/JASMEL_REQUESTS.md` | **Start here** — the owner's asks, verbatim + decoded objectives |
| `docs/RESEARCH.md` | Real-world precedents every design decision was modeled on (Frigate, n8n, Dexie patterns, etc.) |
| `docs/ARCHITECTURE.md` | System diagram + data contract + AI usage map + multi-tenancy plan |
| `docs/HANDOFF.md` | What's tested, what to wire next, open questions for Jasmel, landmines |
| `docs/CLA_LOGIC.md` | **Every automation the AI assistant runs in production** — crons, endpoints, auth, landmines log |
| `mock/demo.html` | **6-Tab White-Label CEO Console**: Command Center, AI Inbox (1-Click Approve & Send), Outcomes & Monitoring (Staff, Clients, Meetings, Apps), Behavioral Brain (Morning/Afternoon/Evening routines + Coffee/Report foresight + Live Telemetry), 1-Time CEO Setup, and Step-by-Step Function Blogs |
| `widgets/lajefatura-widget.js` | **Grok 3.0 Voice & DOM Brain Layer** — bilingual speech recognition & synthesis, live website DOM awareness, touches/clicks any button or tab by voice, and feeds the Behavioral Brain |
| `server/behavior_brain.py` | **Behavioral & Temporal Learning Engine** — learns from the CEO's profile, mouse movements/focus, clicks, typing cadence, voice queries, and Morning / Afternoon / Evening habits |
| `server/comms_brain.py` | **Spec-compliant Comms Core**: §7 draft lifecycle (immutable versions, approval invalidation), §8 learning from owner edits, §11 operating modes A–D, §12 audit trail, 1-click approve & send |
| `server/nexus_ingest.py` | Nexus CRM → SQLite sync (upsert + dashboard-shape aggregates) |
| `server/cameras.py` | Vendor-neutral camera layer (ONVIF + ffmpeg), event log, AI digest |
| `server/reports_pdf.py` | Real PDF generator (`reportlab` + `matplotlib` + Gemini narrative w/ fallback) |
| `server/voice_commands.py` | Headless & Grok 3.0 executor of the voice grammar (server-side, channel-agnostic) |
| `server/ai_insights.py` | Single Gemini integration point (temp 0, math-in-code rule) |
| `scripts/demo_server.py` | Full Mission Control HTTP & API server (port 8931) |
| `scripts/verify_e2e_browser.js` | Automated 16-check real Chromium E2E browser verification suite |
| `scripts/feasibility_audit.py` | Live-probes external providers; writes `docs/feasibility_results.json` |
| `docs/FEASIBILITY.md` | **What works / what's blocked / what's unsupported** |
| `docs/ACCEPTANCE.md` | Spec §18 traceability matrix: PASS/PARTIAL/PENDING with proof for each |
| `docs/COMMS_BRAIN.md` | The comms loop: learning signals, model routing, channel matrix, safety rails |

---

## Run It (1 Minute)

```bash
pip install reportlab matplotlib
python scripts/demo_server.py 8931
# Open http://localhost:8931        → 6-Tab CEO Mission Control Console + Grok 3.0 Voice
# GET  /api/nexus/summary           → Pipeline JSON
# GET  /api/comms/inbox             → Unified Inbox + AI Pre-Drafts + Voice Profile
# GET  /api/behavior/state          → Behavioral Brain + Morning/Afternoon/Evening Foresight
# GET  /api/onboarding/state        → White-Label Setup & 9 Connected Ecosystems
# GET  /api/report.pdf              → Real generated Board PDF Report
```

### Run Automated Browser Verification
```bash
node scripts/verify_e2e_browser.js
```
