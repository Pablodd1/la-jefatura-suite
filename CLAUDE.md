# CLAUDE.md — Guide for Claude Code & Collaborators (`la-jefatura-suite`)

This file provides context and strict guardrails for **Claude Code (`claude`)** and human collaborators working on **La Jefatura Suite** (`https://github.com/Pablodd1/la-jefatura-suite`), the Executive Operating System & CTO/CFO Mission Control for **Juan David García Montoya** (`BUILDING INNOVATION`, `UNITEC USA`, `ESPACIOS IMPORTADOS`, `Planta Pick-In`, `IDEO`).

---

## 1. Quick Start (Run Locally)

```bash
# 1. Clone the repository
git clone https://github.com/Pablodd1/la-jefatura-suite.git
cd la-jefatura-suite

# 2. Install Python dependencies
pip install edge-tts matplotlib reportlab google-auth requests

# 3. Start the server on port 8931
python scripts/demo_server.py 8931
```

Then open:
- **Spanish UI (Default):** `http://localhost:8931/?lang=es`
- **English UI:** `http://localhost:8931/?lang=en`

---

## 2. Core Architecture & Key Files

- **`scripts/demo_server.py`**:
  - Zero-dependency `ThreadingHTTPServer` serving both the static UI (`mock/demo.html`) and all `/api/*` REST endpoints on port `8931`.
- **`mock/demo.html`**:
  - Single-page Executive UI containing:
    - `#pane-assistant`: **Super Asistente (El Jefesito)** with 3-in-1 Multi-Intent Compound Command execution, inline Mode C 1-Click Approval Cards, and Executive Watchdog Alerts.
    - `#pane-outcomes`: **Entregables & Reportes Diarios CTO/CFO** (individual daily HTML + PDF reports for Building Innovation and UNITEC USA).
    - `#pane-cameras`: **55 Hik-Connect Cloud Cameras** live status (`USA`, `Planta Pick-In`, `ESPACIOS IMPORTADOS`, `SALON IDEO`, `OFICINA IDEO`).
    - `#pane-buildingapp`, `#pane-unitec`, `#pane-nexus`, `#pane-agenda`, `#pane-comms`.
- **`server/daily_company_reports.py`**:
  - Generates and dispatches **2 individual CTO + CFO Daily Reports** (`building` and `unitec`) with embedded `matplotlib` PNG charts and PDF attachments via Gmail SMTP / Resend API and Telegram (`@ceojefesitobot` & `@Pegantebot`).
- **`server/ceo_action_brain.py`**:
  - 8-domain executive decision engine (Calendar, Email Drafts, WhatsApp/SMS Drafts, Alarms, Notes, Ideas, Follow-ups, 4-Phase Brainstorming) + `execute_compound_request()` for multi-intent commands + `watchdog_digest()`.
- **`server/cameras.py` & `server/camera_report.py`**:
  - Polls Hik-Connect cloud (`apiisa.hik-connect.com`) every 5 minutes for all 5 recorders / 55 camera channels and logs historical state transitions into `data/mc.db` (`cam_device_log`, `cam_status_log`).
- **`server/buildingapp_ingest.py` & `server/unitec_ingest.py` & `server/ga4_ingest.py`**:
  - Live Firestore & Google Analytics 4 (`543661675` Building Innovation & `533522460` Unitec USA Design) connectors.
- **`server/google_workspace.py`**:
  - Connects CEO Gmail (IMAP/SMTP via 16-char App Password or OAuth2) and Google Calendar (`.ics` / CalDAV).

---

## 3. Strict Guardrails for Collaborators & AI Agents

1. **Zero Hallucination / Deterministic Data Only**:
   - Never hardcode fake numbers as live metrics. Always distinguish between 100% live-measured telemetry (Firestore, GA4, Hik-Connect API, `mc.db`) and simulated demo examples (`mode="example"`).
2. **Never Commit Secrets or `.env` Files**:
   - Keep `.env`, `data/*.secret.json`, `data/*service-account*.json`, and `data/daily_report_recipients.json` out of git commits (already enforced in `.gitignore`).
3. **Sync Both Branches When Pushing**:
   - Always pull before making changes and push to both `main` and `master`:
     ```bash
     git pull origin main --rebase
     git push origin HEAD:main
     git push origin HEAD:master
     ```
4. **Smoke Test Before Pushing**:
   - Verify `/api/health`, `/api/ceo/watchdog`, `/api/reports/company_daily`, and `/api/cameras/status` return `HTTP 200 OK`.
