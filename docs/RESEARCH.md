# Research — real-world precedents (no guessing)

Every design decision in this suite was copied/mimicked/improved from a
verified existing implementation. Sources fetched and read Oct 21–22, 2026.

---

## 1. Executive dashboards / "AI CEO command centers"

**EzInsights AI — CEO Command Center** (YouTube product demo)
`https://www.youtube.com/watch?v=rphe-bIC250`
- What it confirmed: the category is real — KPI tiles at top, agenda, alerts.
  Ours keeps that spine but adds *action* layer (escalations, tick-to-complete).

**"Your Next Hire Should Be an AI — Here's How a Nonprofit Did It in Two
Weeks"** — fabswill.com (Mar 17, 2026)
`https://fabswill.com/blog/your-next-hire-should-be-an-ai/`
- "Mimi, the AI employee": scoped role, 2-week build, supervises repeatable
  ops tasks. **Mimicked**: our product is not a chatbot bolt-on — it's a
  scoped operational role (morning brief, escalation watcher, report writer).
  **Improved**: ours is multi-tenant from day one (the white-label ask).

**Bond / `alfred_` EA skill patterns** (agent skills ecosystem)
- Sleep/wake windows and "CEO office-hours" routines: batch interruptions
  into a morning digest instead of pinging all day. **Mimicked**: Informe del
  Jefe is exactly this — one consolidated 8:17am brief, not 40 notifications.

## 2. Camera integration — the vendor-neutral model

This is where "dont guess" mattered most. Four independent projects converge
on the same architecture; we copied it:

**Frigate NVR** (`https://frigate.video`, blakeblackshear/frigate, 28k+ stars)
- Dual path: *native camera events when available* (ONVIF), *software CV as
  fallback* (detectors). ffmpeg does ALL video handling.
- **Mimicked in `server/cameras.py`**: ffmpeg one-frame snapshots, ffmpeg
  `scene` score for motion (zero OpenCV dependency), lazy optional ONVIF.

**KeepPeek #96 — "Add generic ONVIF PullPoint and RTSP metadata motion/AI
events"** (GitHub issue, Aug 2026)
`https://github.com/xnorpx/keeppeek/issues/96`
- Priority order adopted verbatim: 1) ONVIF Event Service PullPoint for
  motion/tamper/analytics → 2) ONVIF metadata over RTSP (Profile T/M) →
  3) software decode fallback.
- **Lesson that shaped our scaffold**: implement the *interface* now
  (`log_event`, `snapshot`, `motion_poll`), fill hardware specifics after
  Jasmel names his camera brands. Standard RTSP URL patterns per brand
  (Hikvision `/Streaming/Channels/101`, Dahua `/cam/realmonitor?channel=1&subtype=0`,
  Amcrest/Tapo/Reolink variants) are documented in `data/samples/cameras.json`
  for the next dev.

**ZoneMinder / Agent DVR** (long-running open NVRs)
- Confirmed: ffmpeg + event log + snapshot storage is the entire durable
  core; everything else is UI. Our `cam_events` SQLite table = their event
  tables, minimal version.

**AI summary pattern**: send event list + newest snapshot to Gemini vision;
  digest only what needs a human ("out-of-hours", "unknown person").
  Temperature 0, facts pre-computed in code — never let the LLM do math.

## 3. Automated PDF report pipelines

**n8n template — "Automated Report Generation with AI"**
- Standard 5-stage pipeline, copied as our architecture:
  `collect → aggregate (deterministic) → AI narrative → PDF → distribute`.
- Key rule adopted: **all calculations in code before the LLM call**; the LLM
  narrates pre-computed numbers (LLMs are unreliable at arithmetic; a weekly
  CEO report with a wrong sum is worse than no report).

**StackOverflow — "Generate PDF report from SQL database"**
`https://stackoverflow.com/questions/15086552`
- HTML/flow first, then render. We render directly with reportlab
  (battle-tested, no headless browser needed on the server).

**Tooling choices (not guessed — standard)**:
- `reportlab` + `matplotlib`: the canonical Python PDF/chart pair.
- Client-side twin: jsPDF + jspdf-autotable in `mock/demo.html` so the demo
  generates a real PDF from `file://` with zero backend.

## 4. CRM data sync without a server DB

**Dexie.js / IndexedDB-backed SPAs** (the pattern Nexus follows)
- Web apps persisting to IndexedDB expose no remote API. Two proven bridges:
  **A. source-level**: replace the persistence layer with HTTP calls (best,
  needs repo access); **B. in-page bridge**: userscript reads IndexedDB and
  POSTs deltas (works with zero cooperation from the CRM vendor).
- We ship both: schema contract in `server/nexus_ingest.py` (PATH A) and
  `scripts/nexus_bridge_snippet.js` (PATH B, 5-min interval userscript).

---

### What we deliberately did NOT copy

- Heavy NVR stacks (Frigate full install, Shinobi) — premature for 4 cameras
  with unknown brands; our scaffold upgrades into them if needed.
- LLM-in-the-loop for every event (cost + hallucination risk on a security
  surface) — AI digest is once per cycle, over pre-filtered events.
