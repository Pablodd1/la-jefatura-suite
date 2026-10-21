# COMMS_BRAIN — monitor → draft → owner-edit → learn → send

Owner's request, verbatim: *"monitoring, responding with draft and learn from
each text incoming and outgoing also edited and made by the owner of the
account profile."*

This document is the map for `server/comms_brain.py` — tested end-to-end
(self-test in `__main__`), no sends performed, approval gate intact.

## The loop

```
 INGEST (every msg, in + out)            DRAFT (owner's voice)
 ┌────────────────────────────┐          ┌──────────────────────────────┐
 │ comms_log                  │  needs_  │ drafts.body_original         │
 │ id, channel, direction,    │  reply=1 │ composed from:               │
 │ contact, text, ts,         │ ───────► │  · thread context (last in)  │
 │ thread_id, needs_reply,    │          │  · voice_profile JSON        │
 │ owner_sent                 │          │  · style hints               │
 └─────────┬──────────────────┘          └──────────┬───────────────────┘
           │ owner text (out_owner)                │
           ▼                                       ▼
 ┌─────────────────────────────────┐    ┌───────────────────────────┐
 │ LEARN                           │    │ APPROVAL GATE (hard rule) │
 │ voice_profile: greeting,        │    │ owner edits / okays draft │
 │ signoff, signature, formality,  │◄───┤ record_edit() stores the  │
 │ avg_len, exclaim_rate, langs    │    │ final text + retunes voice│
 │ rebuilt from 200 latest owner   │    └───────────┬───────────────┘
 │ msgs + every owner edit         │                │ approve_and_send()
 └─────────────────────────────────┘                ▼
                                        SEND via channel transport →
                                        log out_owner (feeds LEARN)
```

## Why the owner edit is the gold signal

Anyone can prompt-engineer a style. Only the owner's *edits to our drafts*
reveal what they actually wanted to say: which words they swap, what they
delete, how they open. `record_edit()` stores `body_final` and a similarity
score; `learn()` folds edited finals into the profile corpus with the same
weight as owner-authored messages. After a few dozen edits the draft stops
needing them.

## Voice profile (pure code, no LLM in the metric path)

`comms_brain._analyze()` computes every fingerprint in Python — the LLM may
*compose* with them, never *count* them (owner's standing rule). Signatures
detected line-wise (short closing line w/ valediction regex; name/email as
signature). Profile lives in mc.db `voice_profile`, one row per owner.

## Model routing (from the owner's JMM analysis, applied here)

| Task | Model class | Where |
|---|---|---|
| `needs_reply` classification, daily drafts | flash-class (cheap, fast) | fallback heuristic today; gemini flash when keyed |
| Complex threads (contradictory, multi-party, high stakes) | reasoning model | escalation hook in `draft(style_hints="complex")` |
| Voice/dictation | live-class realtime model | future |

Rule carried over from the JMM writeup: **no model swap without a blinded
eval on ≥100 real cases** (accuracy, unsupported claims, fact use, latency
p50/p95, cost). The heuristic fallback stays regardless — the loop must never
stall on an API key.

## Channels

| Channel | Ingest | Send | Status |
|---|---|---|---|
| Gmail | Gmail API history list → `ingest()` | `approve_and_send` → Gmail send (urllib, token from `google_credentials/tokens_live.json`) | LIVE on host |
| Telegram | webhook/poll → `ingest()` | TG bot sendMessage (token from MC `.env`) | LIVE on host |
| WhatsApp | Meta Cloud API webhook → `ingest()` (shape already matches) | needs WABA id + permanent token — **the one unwired transport, by design** until Jasmel provisions it | documented |

## Voice commands (wired in `voice_commands.py`)

- "redactar respuesta" / "draft reply" → drafts a reply to the top pending thread, reports draft id
- "aprender voz" / "learn voice" → rebuilds voice profile, speaks what it learned
- "aprobar borrador" / "approve draft" → sends the newest pending draft (approval = the owner's explicit act)
- "qué hay de nuevo" → digest now includes pending-reply count

## Safety rails

1. **Nothing sends without `approve_and_send`** — there is no auto-send path in code.
2. `needs_reply` heuristic errs toward flagging (owner reviews queue, low cost).
3. Drafts carry `status` (`pending_approval` → `edited` → `sent`); every state change timestamped.
4. Secrets never in repo: Gmail token file path + TG token env are host-side.
5. Outgoing messages are logged `out_owner` so the owner's real voice keeps teaching the profile — including messages they wrote entirely by hand.
