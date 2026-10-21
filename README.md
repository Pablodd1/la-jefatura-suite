# La Jefatura Suite

**White-label CEO command center for Jasmel Acosta's companies** — Nexus CRM
pipeline sync, camera AI digest, full per-company PDF reports, bilingual
(EN/ES) console. Built as a handoff package: docs first, code second.

> Built by Kimi Claw (OpenClaw agent) for Jasmel Acosta, Oct 21–22, 2026.
> Requested as a repo another developer can read, review and continue.

## What's here

| Path | What |
|---|---|
| `docs/JASMEL_REQUESTS.md` | **Start here** — the owner's asks, verbatim + decoded objectives |
| `docs/RESEARCH.md` | Real-world precedents every design decision was copied from (Frigate, n8n, Dexie patterns, etc.) |
| `docs/ARCHITECTURE.md` | System diagram + data contract + AI usage map + multi-tenancy plan |
| `docs/HANDOFF.md` | What's tested, what to wire next, open questions for Jasmel, landmines |
| `docs/CLA_LOGIC.md` | **Every automation the AI assistant runs in production** — crons, endpoints, auth, landmines log |
| `mock/demo.html` | The visual: CEO console + **voice widget layer** (bilingual voice commands control the whole site: switch company, complete tasks, download report, hear the brief) |
| `server/nexus_ingest.py` | Nexus CRM → SQLite sync (upsert + dashboard-shape aggregates) |
| `server/cameras.py` | Vendor-neutral camera layer (ONVIF + ffmpeg), event log, AI digest |
| `server/reports_pdf.py` | Real PDF generator (reportlab + matplotlib + Gemini narrative w/ fallback) |
| `server/voice_commands.py` | Headless executor of the same voice grammar (server-side, channel-agnostic) |
| `server/comms_brain.py` | **Spec-compliant comms core**: §7 draft lifecycle (immutable versions, approval invalidation), §8 learning from owner edits, §11 operating modes A–D (default B), §12 audit trail, memory layers (verified/stated/observed/ai) |
| `scripts/feasibility_audit.py` | Live-probes every provider; writes `docs/feasibility_results.json` |
| `docs/FEASIBILITY.md` | **What works / what's blocked / what's unsupported** — live-audited 2026-10-22 |
| `docs/ACCEPTANCE.md` | Spec §18 traceability matrix: PASS/PARTIAL/PENDING with proof for each |
| `docs/COMMS_BRAIN.md` | The comms loop: learning signals, model routing (owner's JMM rules), channel matrix, safety rails |
| `widgets/lajefatura-widget.js` | Embeddable white-label voice assistant — one `<script>` on any tenant site |
| `server/ai_insights.py` | Single Gemini integration point (temp 0, math-in-code rule) |
| `scripts/demo_server.py` | 4-endpoint demo server |
| `scripts/nexus_bridge_snippet.js` | Browser bridge: syncs Nexus IndexedDB → MC without repo access |
| `data/samples/` | Realistic datasets (12 leads / 8 visits across USA/Colombia/Mexico/Chile) |
| `assets/` | Sample generated PDF + verified screenshots |

## Run it (2 minutes)

```bash
pip install reportlab matplotlib   # PDF deps (only hard deps in the suite)
python3 scripts/demo_server.py 8931
# open http://localhost:8931        → console
# GET  /api/nexus/summary           → pipeline JSON
# GET  /api/report.pdf              → real generated PDF
```

Optional (when cameras exist): `pip install onvif-zeep wsdiscovery`, `apt install ffmpeg`.

## Status snapshot

- ✅ Nexus sync engine + read API (tested)
- ✅ Camera scaffold per Frigate/ONVIF research (loads w/o hardware)
- ✅ Full PDF report (tested, sample in `assets/`)
- ✅ Demo console EN/ES + client PDF (Playwright-verified)
- ✅ Demo console EN/ES + client PDF + **voice command layer** (Playwright-verified: company switch, task completion, digest, brief — `assets/demo-console-voice.png`)
- ✅ Voice grammar executable server-side (`voice_commands.py`, tested against live mc.db)
- ✅ **Comms brain** (owner request): monitors in/out texts, drafts replies in owner's voice, learns from owner-authored messages AND owner edits; approval-gated sending (Gmail/TG live, WhatsApp documented)
- ✅ **Master-spec compliance layer**: lifecycle states, approval-binds-to-version + invalidation on edit, modes A/B/C/D, provenance-tiered preferences, full audit trail — e2e-tested with a REAL Telegram send
- ✅ **Feasibility audit + acceptance traceability** (`docs/FEASIBILITY.md`, `docs/ACCEPTANCE.md`) — live-probed, nothing faked
- ✅ Escalation engine + daily Spanish voice brief (live in production Mission Control)
- ✅ **Full production automation inventory exported** (`docs/CLA_LOGIC.md`) — crons, endpoints, auth, landmines
- ⏳ Waiting on Jasmel: camera brands, fresh Gemini key, Nexus repo/bridge rollout, pilot tenants

## License / ownership

Code written for Jasmel Acosta. Sample company/person data is fictional.
