# HANDOFF — where to start, what to do next

Read order: `JASMEL_REQUESTS.md` → `RESEARCH.md` → this file → code.

## Verified working (tested Oct 22, 2026, this host)

- `python3 server/nexus_ingest.py` → seeds 12 leads/8 visits into mc.db,
  aggregates correct. Self-asserting.
- `python3 server/cameras.py` → loads with zero optional deps, returns digest.
- `python3 server/reports_pdf.py "Medical Billing Miami Beach" data/samples \
  /tmp/out.pdf` → real 24KB PDF (cover, narrative, KPI table, funnel chart,
  leads, tasks, agenda, camera digest).
- `python3 scripts/demo_server.py 8931` → all 4 endpoints verified by curl:
  `/` (HTML), `/api/nexus/summary` (JSON), `/api/report.pdf` (binary),
  `POST /api/nexus/push` (upsert round-trip).
- `mock/demo.html` → Playwright-verified desktop + mobile screenshots in
  `assets/`. Client-side jsPDF button generates a real PDF from file://.

## To wire into production Mission Control (small, explicit)

1. In `mission_control.py` add the route dispatch documented in
   `server/nexus_ingest.py` (`ROUTES` table) and `server/cameras.py` comments.
2. Copy `scripts/nexus_bridge_snippet.js` to Juan/Maria/Carlos machines with
   the tunnel URL filled in (or get the Nexus repo and do PATH A — better).
3. Point the PDF cron at live mc.db instead of samples (change `SAMPLES` arg
   in the cron line to a live-collection function — the shapes already match).

## Open questions for Jasmel (do not guess these)

| # | Question | Blocks |
|---|---|---|
| 1 | Camera brands/models + LAN reachability (same network as MC host? VPN?) | cameras module activation |
| 2 | Fresh `GEMINI_API_KEY` (aistudio.google.com, free tier is enough) | AI narrative quality |
| 3 | Nexus repo access, or OK to roll out the browser bridge to sellers? | pipeline sync PATH A vs B |
| 4 | Which 10 companies first for white-label pilots + price points | tenant onboarding |
| 5 | Report cadence per company (daily 8am? weekly Monday?) + delivery channel (email/TG/WhatsApp) | cron design |

## Known landmines (learned the hard way, write them down so you don't relearn)

- **Never trust text extraction for PDF layout checks** — use `pdftoppm -png`
  and look at the render. The pipeline chart was present but invisible to
  text-only review.
- **sqlite INSERT placeholder counts**: schema drift errors only surface on
  first write — always run the module self-test after touching DDL.
- **LLMs don't do math**: every number in the AI narrative is computed in SQL
  first. A wrong sum in a CEO report is a fired-customer bug.
- All credentials rotate (we lost Gemini, Brevo SMTP, Supabase GoTrue within
  one week). Centralize key loading behind one env read (`ai_insights._load_key`
  pattern) so rotation is a one-line fix.
