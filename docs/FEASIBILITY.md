# FEASIBILITY AUDIT — what works, what's verified, what's unsupported

Per the master spec's final rule: *"Begin by performing the feasibility audit…
Report what works, what has been verified, and what remains unsupported."*

Audited live from the production host on **2026-10-22** by
`scripts/feasibility_audit.py` (re-run anytime; raw results in
`docs/feasibility_results.json`). Nothing below is assumed.

## Verified LIVE today

| Capability | Status | Evidence |
|---|---|---|
| Telegram bot (send/receive) | ✅ LIVE | `@Miamijassbot` getMe OK; real message delivered in e2e demo (provider msg 13147) |
| Email send via Brevo REST | ✅ LIVE | Handoff email delivered 2026-10-21 (Brevo msgId `202610212022…`); used as the email transport in comms_brain |
| Draft lifecycle (§7) | ✅ TESTED | e2e demo: DRAFT_CREATED→PENDING_REVIEW→EDITED→APPROVED→READY_TO_SEND→SENDING→SENT, plus REJECTED/DEFERRED paths implemented |
| Approval invalidation (§7) | ✅ TESTED | edit after approval → prior approval `valid=0`, send blocked until re-approval |
| Mode gating A/B/C (§11) | ✅ TESTED | A blocks drafts; B blocks sends; C full loop; D refuses without policy row |
| Idempotent send (§18 #5) | ✅ TESTED | re-send attempt returns `duplicate=True`, no double-send |
| Owner-edit learning (§8) | ✅ TESTED | revise() retrains voice profile; prefs proposed with provenance, confirmed only by owner |
| Audit trail (§12) | ✅ TESTED | every lifecycle event in `audit_events`; `draft_timeline()` renders it |
| Voice command plane | ✅ TESTED | console widget + headless executor, bilingual grammar |
| PDF reports / Nexus sync / cameras scaffold | ✅ TESTED | earlier phases (see HANDOFF.md) |

## BLOCKED on owner action (nothing to code — creds are dead)

| Capability | Blocker | Owner action (minutes) |
|---|---|---|
| Gmail read/threads/labels | refresh token `invalid_grant` (died ~June 2026; Google testing-mode tokens expire) | Open this URL, authorize, paste the redirect code to me: `https://accounts.google.com/o/oauth2/v2/auth?client_id=825632849625-7hrh43h4qph4ud966ku07v69ragg2a9d.apps.googleusercontent.com&redirect_uri=http://localhost&response_type=code&access_type=offline&prompt=consent&scope=https://www.googleapis.com/auth/gmail.modify%20https://www.googleapis.com/auth/calendar%20https://www.googleapis.com/auth/drive.readonly` (helper: `google_credentials/exchange_code.py`) |
| Google Calendar | same dead token | same re-auth |
| AI narrative (Gemini) | API key 403 — bound service account deleted | New key at https://aistudio.google.com (free) → give it to me |
| WhatsApp Business (§3) | needs WABA id + permanent token + webhook verify | Create at Meta Business → add number → give me the token; webhook verification code is already spec'd |
| WhatsApp personal (§4) | no adapter on host | **Risk-assessed, not recommended as a dependency** — see below |

## UNSUPPORTED by providers (spec says expose, not fake)

- **Personal WhatsApp has NO official full-access API** (§4, engineering rule).
  Any connector (OpenClaw adapter, GREEN-API, Baileys-class) = unofficial
  WhatsApp Web protocol → account-restriction risk, QR re-pairing, no history
  guarantees. Policy: read-and-draft only, never auto-send, honest UI if
  unavailable. **The product does not depend on it** — email, Telegram,
  calendar (post-reauth), CRM and summaries all work without it.
- Meta Cloud API cannot read messages older than the webhook subscription
  window → historical backfill claims are capped honestly (§5).

## Pilot selection (spec Phase 1 decision)

**Pilots (live today):** Telegram (business messaging) + Brevo email + the
draft/approve/learn loop. Calendar joins the moment the Google token is
re-authorized. WhatsApp Business joins when the WABA token lands.

**Deliberately deferred:** personal WhatsApp (risk), Outlook/365 (no tenant
uses it yet), Mode D autonomy (needs policy framework + pilot data).
