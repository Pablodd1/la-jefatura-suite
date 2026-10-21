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
| `mock/demo.html` | The visual: CEO console with realistic sample data, EN/ES toggle, working client-side PDF |
| `server/nexus_ingest.py` | Nexus CRM → SQLite sync (upsert + dashboard-shape aggregates) |
| `server/cameras.py` | Vendor-neutral camera layer (ONVIF + ffmpeg), event log, AI digest |
| `server/reports_pdf.py` | Real PDF generator (reportlab + matplotlib + Gemini narrative w/ fallback) |
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
- ✅ Escalation engine + daily Spanish voice brief (live in production Mission Control)
- ⏳ Waiting on Jasmel: camera brands, fresh Gemini key, Nexus repo/bridge rollout, pilot tenants

## License / ownership

Code written for Jasmel Acosta. Sample company/person data is fictional.
