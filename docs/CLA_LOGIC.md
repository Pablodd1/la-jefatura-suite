# CLA_LOGIC — every automation Kimi Claw runs in production

> This file exports the assistant's brain: the workflows, crons, integrations and
> landmines that currently live ONLY in the workspace. The next developer should
> be able to keep the lights on from this document alone.
> Host: Alibaba Cloud VPS, Ubuntu, Python 3.12, node v24. Owner: Jasmel Acosta.
> All secrets live in host env / `.env` files — NEVER in this repo.

---

## 1. Mission Control (the spine) — `/root/.openclaw/workspace/mission-control/`

| File | Role | Schedule |
|---|---|---|
| `mission_control.py` | HTTP server, port 8090. SQLite `mc.db`. Serves CEO console + APIs | always-on (systemd `mc-server`) |
| `escalate.py` | Task escalation engine: overdue >24h → staff nudge (once, `nudge_ts`); >48h → CRITICAL alert to CEO Telegram (once, `escalated`) | cron `23 * * * *` |
| `informe.py` | "El Informe del Jefe": pulls /api/ceo + /api/weather → composes 60-sec Spanish brief → Telegram text + voice (edge-tts `es-US-AlonsoNeural` → /tmp/informe.mp3 → sendVoice) | cron `17 20 * * *` = 8:17 AM Miami |
| `ceo.html` | Apple-minimal console: company switcher, pendientes board (tick-to-complete → POST /api/task/done), auto-refresh 30s | served at `/` |
| `check_apps.sh` | Smoke-test all deployed apps, alerts on 404/down | daily cron |
| cloudflared tunnel | exposes MC to internet (URL is ephemeral; watchdog cron restarts tunnel if down) | always-on |

Key MC endpoints: `GET /api/ceo?company=`, `GET /api/weather` (open-meteo),
`POST /api/task/done`, `POST /api/lead` (→ Telegram notify), `/api/b305/*` (deal
flow), `/api/305/auth/*` (email-code auth, see §4), `/api/nexus/*` (from this suite).

## 2. Telegram (the owner's interface)

- Bot posts to chat 7838956683 (Jasmel). Creds: TG_BOT_TOKEN + TG_CHAT_ID in MC `.env`.
- Live message types: escalations, Informe del Jefe (text+voice), new-lead
  notifications, smoke-test failures. All tested live.

## 3. Crons (as of Oct 2026)

| Time (server CST) | Miami time | Job |
|---|---|---|
| `17 20 * * *` | 8:17 AM | Informe del Jefe (text + voice) |
| `23 * * * *` | hourly :23 | Escalation sweep |
| `45 17 * * *` | 5:45 AM | Daily status report |
| `0 8 * * *`… | 8:00 AM | Gmail monitor (unread from justmail@michaelbuildingmb.com) |
| `52 19 * * *` | 7:52 AM | AI Dynamics content reminder (flag file /tmp/aidynamic_reminder_flag) |
| watch | — | cloudflared tunnel watchdog |

Cron style note: on-the-hour jobs collide and fail more; off-peak minutes were
chosen deliberately (the "lucky number" rule from the owner).

## 4. 305business (`/root/.openclaw/workspace/305business-llc/` → repo Pablodd1/305business-llc)

- **Auth is MC-native, NOT Supabase GoTrue** (GoTrue broken project-wide on the
  CEDEXX Supabase — every email 400s). `/api/305/auth/{code,verify,me,profile,logout}`:
  6-digit code emailed via Brevo, sha256-hashed, 10-min TTL, 5-attempt lockout,
  60s resend limit, 30-day session tokens (hashed). jasmelacosta@gmail.com = admin.
- Data: Supabase CEDEXX project `fjeubuopladzxxswomko` (URL+anon key in repo files).
- Listings rendered from `js/businesses-data.js` with live-DB fallback;
  inquiries dual-written to MC `/api/lead`.
- Deploy: GitHub master → Vercel project `305business-llc`. Vercel SSO protection
  ON (previews redirect to login) — review via tunnel or turn Deployment Protection off.

## 5. MBMB stack

- **Booking server** `mbmb_booking_server.py` (port 8085): website form → Google
  Calendar event (+Meet link) → Brevo confirmation email → Telegram queue.
  Manager CLI: `mbmb_manager.py {update,serve,test,status}`.
- **Brevo**: REST API works from this host (SMTP is flaky — use REST). Sender
  jasmel@medicalbillingmb.com. List "MBMB MIAMI" ~1,618 subs, 20k credits/cycle.
- **Buffer MCP**: LinkedIn (auto) + Instagram (manual) posting for MBMB. Posting
  standards (CTA, phone, booking link, hashtags) live in TOOLS.md.
- Google Gmail/Calendar/Sheets via OAuth tokens (gmail send/read verified).

## 6. GitHub

- Classic PAT (write-verified on 305business-llc) — used for repo writes.
  Fine-grained PAT is read-only for that repo; don't swap them blindly.
- Repos owned: `Pablodd1/305business-llc`, `Pablodd1/aidynamics-site`, `Pablodd1/la-jefatura-suite`.

## 7. Voice/AI layers

- `widgets/lajefatura-widget.js` (this repo): embeddable voice assistant —
  Web Speech recognition + speechSynthesis, bilingual grammar, action registry
  (`window.LJ.register`), server fallback via `POST /api/voice/command`.
- `server/voice_commands.py` (this repo): headless executor of the SAME grammar —
  voice notes from Telegram/WhatsApp can flow through it later (Whisper hook
  documented in-file). Commands mutate real state (tasks, PDF). Deterministic by
  design: control plane never probabilistic, AI only narrates.
- Older proven pattern: 305biz KB voice widget (Gemini TTS / OpenAI Realtime).

## 8. Landmines (rotation log)

| Date lost | Credential | Symptom | Workaround |
|---|---|---|---|
| Oct 2026 | CEDEXX GEMINI_API_KEY | 403, service account deleted | template fallbacks; need fresh key |
| Oct 2026 | Supabase GoTrue (CEDEXX proj) | all auth emails 400 | MC-native auth |
| Oct 2026 | Brevo SMTP | flaky | REST API |
| Sep 2026 | old Supabase projects (yzakbld…, uakiregr…) | NXDOMAIN | CEDEXX project |

Rule: centralize key loading (see `ai_insights._load_key`) so rotation = 1 line.
