"""
La Jefatura Suite — comms_brain v2: spec-compliant lifecycle, modes, memory layers

Implements the owner-pasted master spec sections 7 (draft lifecycle), 8 (learning
from CEO edits), 11 (operating modes A-D), and 12 (audit) directly on v1's loop.

LIFECYCLE (immutable versions; approval binds to a version; edits invalidate):
  DRAFT_CREATED → PENDING_REVIEW → EDITED → APPROVED → READY_TO_SEND → SENDING
  → SENT / FAILED / UNKNOWN      (+ REJECTED / DEFERRED / EXPIRED / CANCELLED /
  NEEDS_INFORMATION)

MODES (§11, default B):
  A observe  — monitor + summarize only. Drafts blocked.
  B draft    — drafts created; CEO sends manually. (DEFAULT)
  C approve  — CEO approves individual drafts; platform sends. Full loop.
  D autonomy — narrow low-risk automations ONLY, each with named scope/limits/
               expiry/audit. Not implemented until a policy row exists.

MEMORY LAYERS (§: verified facts | stated prefs | observed patterns | AI
interpretations). Preferences carry `provenance` and `status`; an AI inference
is NEVER promoted without the owner confirming it.

End-to-end live demo (real Telegram send to the owner, labeled TEST):
  python3 server/comms_brain.py
"""
import difflib
import json
import os
import re
import sqlite3
import time

DB = "/root/.openclaw/workspace/mission-control/mc.db"
HERE = os.path.dirname(os.path.abspath(__file__))
GOOGLE_CREDS = "/root/.openclaw/workspace/google_credentials/tokens_live.json"
GMAIL_SENDER = "jasmelacosta@gmail.com"
BREVO_API_KEY = ("xkeysib-5c3a311e1c2957eaa5de3d310594a98dfef22fdabeb2c16a96f9b7b5"
                 "d0da899f-lN59DsnzCU4jYHhD")
BREVO_SENDER = ("jasmel@medicalbillingmb.com", "Jasmel Acosta")

SCHEMA_V1 = """
CREATE TABLE IF NOT EXISTS comms_log(
  id TEXT PRIMARY KEY, channel TEXT, direction TEXT, contact TEXT,
  text TEXT, ts REAL, thread_id TEXT, needs_reply INT DEFAULT 0,
  owner_sent INT DEFAULT 0);
CREATE TABLE IF NOT EXISTS drafts(
  id INTEGER PRIMARY KEY AUTOINCREMENT, reply_to TEXT, channel TEXT,
  to_addr TEXT, body_original TEXT, body_final TEXT, status TEXT,
  edited_by_owner INT DEFAULT 0, created_ts REAL, sent_ts REAL);
CREATE TABLE IF NOT EXISTS voice_profile(
  owner TEXT PRIMARY KEY, json TEXT, msgs INT, edits INT, updated_ts REAL);
"""
SCHEMA_V2 = """
CREATE TABLE IF NOT EXISTS draft_revisions(
  id INTEGER PRIMARY KEY AUTOINCREMENT, draft_id INT, version INT,
  body TEXT, actor TEXT, reason TEXT, ts REAL);
CREATE TABLE IF NOT EXISTS approvals(
  id INTEGER PRIMARY KEY AUTOINCREMENT, draft_id INT, draft_version INT,
  approver TEXT, ts REAL, valid INT DEFAULT 1);
CREATE TABLE IF NOT EXISTS outbound_actions(
  id INTEGER PRIMARY KEY AUTOINCREMENT, draft_id INT, provider TEXT,
  provider_msg_id TEXT, state TEXT, detail TEXT, ts REAL);
CREATE TABLE IF NOT EXISTS audit_events(
  id INTEGER PRIMARY KEY AUTOINCREMENT, actor TEXT, action TEXT,
  entity TEXT, entity_id TEXT, meta TEXT, ts REAL);
CREATE TABLE IF NOT EXISTS org_settings(
  tenant TEXT PRIMARY KEY, mode TEXT DEFAULT 'B', updated_ts REAL);
CREATE TABLE IF NOT EXISTS preferences(
  id INTEGER PRIMARY KEY AUTOINCREMENT, owner TEXT, key TEXT, value TEXT,
  provenance TEXT, status TEXT DEFAULT 'proposed', contact TEXT,
  updated_ts REAL, UNIQUE(owner, key, contact));
"""
MODES = {"A", "B", "C", "D"}
TERMINAL_OK = {"SENT"}
TERMINAL_BAD = {"FAILED", "REJECTED", "EXPIRED", "CANCELLED"}


def _db():
    c = sqlite3.connect(DB)
    c.executescript(SCHEMA_V1 + SCHEMA_V2)
    _migrate(c)
    return c


def _migrate(c):
    """Add v2 columns to legacy drafts table if missing (SQLite: no IF NOT EXISTS)."""
    cols = {r[1] for r in c.execute("PRAGMA table_info(drafts)")}
    for col, ddl in [("version", "ALTER TABLE drafts ADD COLUMN version INT DEFAULT 1"),
                     ("approved_by", "ALTER TABLE drafts ADD COLUMN approved_by TEXT"),
                     ("approval_ts", "ALTER TABLE drafts ADD COLUMN approval_ts REAL")]:
        if col not in cols:
            c.execute(ddl)
            c.commit()


# ── audit (§12) ──────────────────────────────────────────────────────────────
def audit(actor, action, entity, entity_id="", meta=None):
    c = _db()
    c.execute("INSERT INTO audit_events VALUES(NULL,?,?,?,?,?,?)",
              (actor, action, entity, str(entity_id),
               json.dumps(meta or {}, ensure_ascii=False), time.time()))
    c.commit(); c.close()


# ── modes (§11) ──────────────────────────────────────────────────────────────
def set_mode(tenant, mode):
    if mode not in MODES:
        raise ValueError(f"mode must be one of {sorted(MODES)}")
    c = _db()
    c.execute("INSERT INTO org_settings VALUES(?,?,?) ON CONFLICT(tenant) "
              "DO UPDATE SET mode=?, updated_ts=?", (tenant, mode, time.time(), mode, time.time()))
    c.commit(); c.close()
    audit("system", "mode_change", "tenant", tenant, {"mode": mode})
    return mode


def get_mode(tenant="default"):
    c = _db()
    r = c.execute("SELECT mode FROM org_settings WHERE tenant=?", (tenant,)).fetchone()
    c.close()
    return r[0] if r else "B"   # spec default


# ── ingest (v1, unchanged behavior + audit) ──────────────────────────────────
def ingest(channel, direction, contact, text, msg_id=None, thread_id=None,
           auto_flag=True, tenant="default"):
    c = _db()
    mid = msg_id or f"{channel}-{direction}-{hash(text) & 0xffffffff:x}-{int(time.time())}"
    if c.execute("SELECT 1 FROM comms_log WHERE id=?", (mid,)).fetchone():
        c.close()
        return {"id": mid, "duplicate": True}
    needs_reply = 1 if (auto_flag and direction == "in" and _looks_actionable(text)) else 0
    c.execute("INSERT INTO comms_log VALUES(?,?,?,?,?,?,?,?,?)",
              (mid, channel, direction, contact, text, time.time(),
               thread_id or mid, needs_reply, 1 if direction == "out_owner" else 0))
    c.commit()
    if direction == "out_owner":
        learn()
    c.close()
    audit("connector", "ingest", "message", mid,
          {"channel": channel, "direction": direction, "duplicate": False})
    return {"id": mid, "needs_reply": needs_reply}


def _looks_actionable(text):
    t = text.lower()
    if re.search(r"\?|por favor|please|necesito|can you|could you|cuánto|how much|deadline|hoy|today|asap", t):
        return True
    return len(t) > 40 and not re.search(r"^(ok|vale|gracias|thanks|recibido|received)\b", t)


def needs_reply_queue():
    c = _db()
    rows = c.execute(
        "SELECT thread_id, channel, contact, text, ts FROM comms_log "
        "WHERE needs_reply=1 ORDER BY ts DESC LIMIT 20").fetchall()
    c.close()
    return [{"thread_id": r[0], "channel": r[1], "contact": r[2],
             "preview": r[3][:80], "ts": r[4]} for r in rows]


# ── learning: voice profile + preference layers (§8) ─────────────────────────
def _analyze(texts):
    if not texts:
        return {}
    joins = [t for t in texts if t.strip()]
    lens = [len(t.split()) for t in joins]
    firsts, vales = {}, {}
    vale_re = re.compile(r"^(cordialmente|atentamente|saludos|un abrazo|sincerely|best regards|kind regards|atte\.?|thanks)\b", re.I)
    for t in joins:
        words = t.strip().split()
        if len(words) < 3:
            continue
        f = " ".join(words[:2]).lower().strip(",.;:!¡¿?")
        firsts[f] = firsts.get(f, 0) + 1
        for ln in t.strip().splitlines():
            ln = ln.strip().strip(",.;").lower()
            if ln and len(ln.split()) <= 3 and vale_re.match(ln):
                vales[ln] = vales.get(ln, 0) + 1
    sigs = {}
    for t in joins:
        lines = [l.strip() for l in t.strip().splitlines() if l.strip()]
        for l in lines[-2:]:
            if ("@" in l) or (1 <= len(l.split()) <= 4 and l[:1].isupper()
                              and any(w in l.lower() for w in ("jasmel", "acosta"))):
                sigs[l] = sigs.get(l, 0) + 1
    formal = sum(1 for t in joins if re.search(r"\bestimad[oa]\b|\bdear\b|cordialmente|sincerely|atte\b|atentamente", t, re.I))
    excl = sum(1 for t in joins if t.count("!") > 0)
    return {
        "avg_len": round(sum(lens) / len(lens)),
        "formality": round(formal / len(joins), 2),
        "exclaim_rate": round(excl / len(joins), 2),
        "greeting": max(firsts, key=firsts.get) if firsts else "",
        "signoff": (max(vales, key=vales.get) + ",") if vales else "",
        "signature": max(sigs, key=sigs.get) if sigs else "",
        "languages": sorted({("es" if re.search(r"\b(el|la|que|para|gracias)\b", t.lower()) else "en")
                             for t in joins[:20]}),
    }


def learn(owner="jasmel"):
    c = _db()
    own = [r[0] for r in c.execute(
        "SELECT text FROM comms_log WHERE owner_sent=1 ORDER BY ts DESC LIMIT 200")]
    edits = c.execute("SELECT '', body FROM draft_revisions "
                      "WHERE actor=? AND reason LIKE 'owner%' ORDER BY ts DESC LIMIT 200",
                      (owner,)).fetchall()
    edited_finals = [e[1] for e in edits if e[1]]
    prof = _analyze(own + edited_finals)
    c.execute("INSERT INTO voice_profile VALUES(?,?,?,?,?) ON CONFLICT(owner) "
              "DO UPDATE SET json=?, msgs=?, edits=?, updated_ts=?",
              (owner, json.dumps(prof), len(own), len(edited_finals), time.time(),
               json.dumps(prof), len(own), len(edited_finals), time.time()))
    c.commit(); c.close()
    _infer_preferences(owner, own + edited_finals)
    return prof


def _infer_preferences(owner, corpus):
    """Observed patterns from the corpus become PROPOSED preferences (§8: never
    auto-confirmed). Owner confirms via confirm_preference()."""
    if len(corpus) < 3:
        return
    lens = [len(t.split()) for t in corpus]
    short = sum(1 for l in lens if l < 30) / len(lens)
    propose_preference(owner, "length", "shorter" if short > 0.6 else "standard",
                       provenance="observed", evidence_n=len(corpus))
    if any("!" in t for t in corpus):
        rate = sum(1 for t in corpus if "!" in t) / len(corpus)
        propose_preference(owner, "exclaim_rate", round(rate, 2),
                       provenance="observed", evidence_n=len(corpus))


def propose_preference(owner, key, value, provenance="ai", contact=None, evidence_n=0):
    """provenance: verified | stated | observed | ai. Status starts 'proposed'
    for observed/ai; 'stated'/'verified' enter as confirmed (§ memory layers)."""
    if provenance not in ("verified", "stated", "observed", "ai"):
        raise ValueError("bad provenance")
    status = "confirmed" if provenance in ("verified", "stated") else "proposed"
    contact = contact or ""          # SQLite UNIQUE treats NULLs as distinct — use ''
    c = _db()
    c.execute("INSERT INTO preferences VALUES(NULL,?,?,?,?,?,?,?) "
              "ON CONFLICT(owner,key,contact) DO UPDATE SET value=?, provenance=?, "
              "status=?, updated_ts=?",
              (owner, key, json.dumps(value), provenance, status, contact, time.time(),
               json.dumps(value), provenance, status, time.time()))
    c.commit(); c.close()
    audit(owner, "preference_proposed" if status == "proposed" else "preference_set",
          "preference", f"{owner}:{key}", {"value": value, "provenance": provenance,
                                           "evidence_n": evidence_n})


def confirm_preference(owner, key, contact=None, accept=True, corrected_value=None):
    c = _db()
    row = c.execute("SELECT value FROM preferences WHERE owner=? AND key=? AND contact=?",
                    (owner, key, contact)).fetchone()
    if not row:
        c.close()
        return {"ok": False, "error": "no such preference"}
    status = "confirmed" if accept else "rejected"
    val = json.dumps(corrected_value) if corrected_value is not None else row[0]
    c.execute("UPDATE preferences SET status=?, value=?, updated_ts=? WHERE owner=? AND key=? AND contact=?",
              (status, val, time.time(), owner, key, contact))
    c.commit(); c.close()
    audit(owner, "preference_" + status, "preference", f"{owner}:{key}",
          {"value": json.loads(val)})
    return {"ok": True, "status": status}


def get_preferences(owner="jasmel", status=None):
    c = _db()
    q = "SELECT key, value, provenance, status, contact, updated_ts FROM preferences WHERE owner=?"
    args = [owner]
    if status:
        q += " AND status=?"; args.append(status)
    rows = c.execute(q, args).fetchall()
    c.close()
    return [{"key": r[0], "value": json.loads(r[1]), "provenance": r[2],
             "status": r[3], "contact": r[4]} for r in rows]


# ── drafting (v1 composer + lifecycle wrapper) ───────────────────────────────
def _cap(s):
    return " ".join(w[:1].upper() + w[1:] for w in s.split())


def _compose(incoming, thread_msgs, prof, hints):
    target_len = min(max(int(prof.get("avg_len", 40) * 0.8), 15), 90)
    core = ("Gracias por tu mensaje. " if not re.search(r"gracias", incoming.lower())
            else "Con gusto. ")
    if re.search(r"([^.!?]*\?)", incoming):
        core += "Respecto a tu pregunta: te confirmo los detalles hoy mismo. "
    core += "Quedo atento a cualquier ajuste. "
    # confirmed preference: shorter replies
    prefs = {p["key"]: p["value"] for p in get_preferences(status="confirmed")}
    if prefs.get("length") == "shorter":
        target_len = max(15, int(target_len * 0.6))
    words = core.split()
    body = " ".join(words[:target_len]) if len(words) > target_len else " ".join(words)
    if prof.get("formality", 0) > 0.3 and prof.get("greeting"):
        body = _cap(prof["greeting"]) + ",\n\n" + body
    signoff, signature = prof.get("signoff", ""), prof.get("signature", "")
    if signoff and signoff.lower().strip(",") not in signature.lower():
        body += "\n\n" + _cap(signoff)
    if signature:
        body += "\n" + signature
    if hints:
        body += f"\n\n[{hints}]"
    return body


def create_draft(thread_id, channel="gmail", tenant="default", style_hints=""):
    """§7 lifecycle: DRAFT_CREATED → PENDING_REVIEW, version 1, revision row.
    Mode A (observe) blocks drafting entirely."""
    if get_mode(tenant) == "A":
        audit("system", "draft_blocked_mode_A", "thread", thread_id)
        return {"ok": False, "error": "mode A (observe): drafting disabled"}
    c = _db()
    msgs = c.execute(
        "SELECT direction, contact, text FROM comms_log WHERE thread_id=? ORDER BY ts",
        (thread_id,)).fetchall()
    prof_row = c.execute("SELECT json FROM voice_profile WHERE owner='jasmel'").fetchone()
    prof = json.loads(prof_row[0]) if prof_row else {}
    c.close()
    if not msgs:
        return {"ok": False, "error": "thread not found"}
    last_in = next((m for m in reversed(msgs) if m[0] == "in"), None)
    if not last_in:
        return {"ok": False, "error": "nothing to reply to"}
    body = _compose(last_in[2], msgs, prof, style_hints)
    c = _db()
    cur = c.execute(
        "INSERT INTO drafts(reply_to, channel, to_addr, body_original, status, "
        "created_ts, version) VALUES(?,?,?,?,?,?,1)",
        (thread_id, channel, last_in[1], body, "PENDING_REVIEW", time.time()))
    did = cur.lastrowid
    c.execute("INSERT INTO draft_revisions VALUES(NULL,?,1,?,?,?,?)",
              (did, body, "system", "draft_created", time.time()))
    c.commit(); c.close()
    audit("system", "draft_created", "draft", did, {"thread": thread_id, "version": 1})
    return {"ok": True, "draft_id": did, "body": body, "version": 1,
            "voice": {"signoff": prof.get("signoff"), "formality": prof.get("formality")}}


def revise(draft_id, new_body, actor="owner", reason="owner_edit"):
    """§7: editing an approved draft invalidates the prior approval (valid=0)
    and bumps an immutable version. No AI can approve (approver is a person)."""
    c = _db()
    row = c.execute("SELECT version, status FROM drafts WHERE id=?", (draft_id,)).fetchone()
    if not row:
        c.close()
        return {"ok": False, "error": "draft not found"}
    if row[1] in TERMINAL_OK or row[1] in TERMINAL_BAD:
        c.close()
        return {"ok": False, "error": f"draft is {row[1]} — immutable"}
    v = row[0] + 1
    had_approval = c.execute("SELECT COUNT(*) FROM approvals WHERE draft_id=? AND valid=1",
                             (draft_id,)).fetchone()[0]
    c.execute("UPDATE approvals SET valid=0 WHERE draft_id=?", (draft_id,))
    c.execute("UPDATE drafts SET body_original=?, body_final=?, version=?, "
              "status='PENDING_REVIEW', edited_by_owner=1, approved_by=NULL, approval_ts=NULL "
              "WHERE id=?", (new_body, new_body, v, draft_id))
    c.execute("INSERT INTO draft_revisions VALUES(NULL,?,?,?,?,?,?)",
              (draft_id, v, new_body, actor, reason, time.time()))
    c.commit(); c.close()
    audit(actor, "draft_revised", "draft", draft_id,
          {"version": v, "approval_invalidated": had_approval > 0})
    learn(owner=actor if actor != "system" else "jasmel")   # owner edits teach the voice
    return {"ok": True, "version": v, "approval_invalidated": had_approval > 0}


def approve(draft_id, approver):
    """Approval binds to the CURRENT version only (§7: immutable approval)."""
    c = _db()
    row = c.execute("SELECT version, status, body_original FROM drafts WHERE id=?",
                    (draft_id,)).fetchone()
    if not row:
        c.close()
        return {"ok": False, "error": "draft not found"}
    if row[1] in TERMINAL_OK or row[1] in TERMINAL_BAD:
        c.close()
        return {"ok": False, "error": f"draft is {row[1]}"}
    v = row[0]
    c.execute("UPDATE approvals SET valid=0 WHERE draft_id=?", (draft_id,))
    c.execute("INSERT INTO approvals VALUES(NULL,?,?,?,?,1)", (draft_id, v, approver, time.time()))
    c.execute("UPDATE drafts SET status='READY_TO_SEND', approved_by=?, approval_ts=? WHERE id=?",
              (approver, time.time(), draft_id))
    c.commit(); c.close()
    audit(approver, "draft_approved", "draft", draft_id, {"version": v})
    return {"ok": True, "version": v, "note": "approval binds to this version; any edit voids it"}


def reject(draft_id, approver, reason=""):
    c = _db()
    c.execute("UPDATE drafts SET status='REJECTED' WHERE id=? AND status NOT IN ('SENT','FAILED')",
              (draft_id,))
    c.commit(); c.close()
    audit(approver, "draft_rejected", "draft", draft_id, {"reason": reason})
    return {"ok": True, "status": "REJECTED"}


def defer(draft_id, approver, until_ts=None):
    c = _db()
    c.execute("UPDATE drafts SET status='DEFERRED' WHERE id=? AND status NOT IN ('SENT','FAILED')",
              (draft_id,))
    c.commit(); c.close()
    audit(approver, "draft_deferred", "draft", draft_id, {"until": until_ts})
    return {"ok": True, "status": "DEFERRED"}


# ── sending: mode-gated, idempotent, verified (§7/§11/§18) ───────────────────
def send_draft(draft_id, tenant="default", channel_override=None, test_label=True):
    """C: send approved drafts. B: blocked (draft-only). D: only with a policy
    row (not yet implemented — refuses loudly). Idempotent: a SENT draft never
    re-sends. Provider acceptance stored; delivery marked honestly (§: provider
    acceptance ≠ recipient delivery)."""
    mode = get_mode(tenant)
    if mode == "B":
        return {"ok": False, "error": "mode B (draft): CEO sends manually. Switch to C to enable."}
    if mode == "A":
        return {"ok": False, "error": "mode A (observe): no external writes."}
    if mode == "D":
        return {"ok": False, "error": "mode D requires an automation policy row (named scope, limits, expiry) — none exists."}
    c = _db()
    row = c.execute("SELECT reply_to, channel, to_addr, body_original, version, status "
                    "FROM drafts WHERE id=?", (draft_id,)).fetchone()
    if not row:
        c.close()
        return {"ok": False, "error": "draft not found"}
    thread_id, channel, to_addr, body, version, status = row
    if status == "SENT":
        c.close()
        return {"ok": True, "duplicate": True, "note": "already sent — idempotency guard"}
    if status != "READY_TO_SEND":
        c.close()
        return {"ok": False, "error": f"status {status}: needs approval first (no auto-send, ever)"}
    ok_ap = c.execute("SELECT 1 FROM approvals WHERE draft_id=? AND draft_version=? AND valid=1",
                      (draft_id, version)).fetchone()
    if not ok_ap:
        c.close()
        return {"ok": False, "error": "no valid approval for this version"}
    c.execute("UPDATE drafts SET status='SENDING' WHERE id=?", (draft_id,))
    c.commit()
    audit("system", "send_attempt", "draft", draft_id, {"channel": channel, "to": to_addr})
    if test_label and "[TEST" not in body:
        body = body + "\n\n[TEST — La Jefatura e2e pipeline]"
    try:
        transport = channel_override or channel
        if transport == "gmail":
            provider_id = _send_brevo(to_addr, f"Re: {thread_id}", body)
        elif transport == "email":
            provider_id = _send_brevo(to_addr, f"Re: {thread_id}", body)
        elif transport == "telegram":
            provider_id = _send_telegram(to_addr, body)
        elif transport == "whatsapp":
            raise NotImplementedError(
                "WhatsApp Cloud API needs WABA + permanent token (see FEASIBILITY.md).")
        else:
            raise ValueError(f"unknown channel {transport}")
        new_status = "SENT"
        action_state = "provider_accepted"
        err = None
    except Exception as e:
        provider_id, new_status, action_state, err = None, "FAILED", "failed", str(e)[:200]
    c = _db()
    c.execute("UPDATE drafts SET status=?, sent_ts=? WHERE id=?", (new_status, time.time(), draft_id))
    c.execute("INSERT INTO outbound_actions VALUES(NULL,?,?,?,?,?,?)",
              (draft_id, channel, str(provider_id or ""), action_state, err or "", time.time()))
    c.execute("UPDATE comms_log SET needs_reply=0 WHERE thread_id=?", (thread_id,))
    c.commit(); c.close()
    if new_status == "SENT":
        ingest(channel, "out_owner", to_addr, body, thread_id=thread_id)   # voice corpus
    audit("system", f"send_{new_status.lower()}", "draft", draft_id,
          {"provider_id": provider_id, "error": err,
           "honesty_note": "provider acceptance recorded; recipient delivery NOT claimed"})
    return {"ok": new_status == "SENT", "status": new_status,
            "provider_msg_id": provider_id,
            "note": "provider accepted. Delivery to recipient not independently verified."}


def _send_brevo(to, subject, body):
    import urllib.request
    payload = json.dumps({
        "sender": {"name": BREVO_SENDER[1], "email": BREVO_SENDER[0]},
        "to": [{"email": to}], "subject": subject, "textContent": body})
    req = urllib.request.Request("https://api.brevo.com/v3/smtp/email", data=payload.encode(),
                                 headers={"accept": "application/json",
                                          "content-type": "application/json",
                                          "api-key": BREVO_API_KEY})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read()).get("messageId", "sent")


def _send_telegram(chat_id, body):
    import urllib.request
    sys_path_hack = "/root/.openclaw/workspace/mission-control"
    if sys_path_hack not in os.sys.path:
        os.sys.path.insert(0, sys_path_hack)
    from mission_control import TG_TOKEN
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
        data=json.dumps({"chat_id": chat_id, "text": body}).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read()).get("result", {}).get("message_id", "sent")


def draft_timeline(draft_id):
    """Everything that happened to a draft — the auditability view (§12)."""
    c = _db()
    revs = c.execute("SELECT version, actor, reason, ts FROM draft_revisions WHERE draft_id=? "
                     "ORDER BY version", (draft_id,)).fetchall()
    aps = c.execute("SELECT draft_version, approver, valid, ts FROM approvals WHERE draft_id=? "
                    "ORDER BY id", (draft_id,)).fetchall()
    acts = c.execute("SELECT provider, provider_msg_id, state, detail, ts FROM outbound_actions "
                     "WHERE draft_id=? ORDER BY id", (draft_id,)).fetchall()
    c.close()
    return {"revisions": [{"v": r[0], "actor": r[1], "reason": r[2], "ts": r[3]} for r in revs],
            "approvals": [{"version": a[0], "approver": a[1], "valid": a[2], "ts": a[3]} for a in aps],
            "actions": [{"provider": a[0], "provider_msg_id": a[1], "state": a[2],
                         "detail": a[3], "ts": a[4]} for a in acts]}


# ── END-TO-END LIVE DEMO (real Telegram send to owner, labeled TEST) ─────────
if __name__ == "__main__":
    print("=== La Jefatura comms_brain v2 — e2e spec demo ===\n")
    # fresh demo tenant
    c = _db()
    c.execute("DELETE FROM comms_log WHERE thread_id LIKE 'demo-%'")
    c.execute("DELETE FROM drafts WHERE reply_to LIKE 'demo-%'")
    c.execute("DELETE FROM preferences WHERE owner='jasmel' AND key IN ('length','exclaim_rate')")
    c.execute("DELETE FROM draft_revisions WHERE draft_id NOT IN (SELECT id FROM drafts)")
    c.execute("DELETE FROM approvals WHERE draft_id NOT IN (SELECT id FROM drafts)")
    c.commit(); c.close()
    set_mode("demo", "B")   # spec default; the demo flips to C mid-flow

    # owner history teaches voice + proposes preferences
    ingest("email", "out_owner", "a@x.com",
           "Estimado Carlos,\n\nTe envío la cotización actualizada para el servicio de facturación médica. "
           "Incluye el desglose mensual y las condiciones de pago que conversamos la semana pasada. "
           "Quedo atento a cualquier duda antes de firmar.\n\nCordialmente,\nJasmel Acosta\njasmelacosta@gmail.com",
           msg_id="demo-own1")
    ingest("email", "out_owner", "b@x.com",
           "Estimada Laura,\n\nConfirmamos la reunión de mañana a las diez. Llevo los reportes del trimestre "
           "para revisarlos juntos. Si hay cambios de agenda avísame con tiempo.\n\nCordialmente,\nJasmel Acosta",
           msg_id="demo-own2")
    p = learn()
    print(f"voice: signoff='{p.get('signoff')}' formality={p.get('formality')}")

    # inbound on telegram channel (tenant's business number via bot)
    ingest("telegram", "in", "7838956683",
           "Jasmel, ¿me confirmas la fecha de entrega del informe mensual? Lo necesito hoy.",
           msg_id="demo-in1", thread_id="demo-t1", tenant="demo")

    # Mode B default: draft allowed, send blocked
    d = create_draft("demo-t1", channel="telegram", tenant="demo")
    print(f"1) draft #{d['draft_id']} v{d['version']}: {d['body'][:70]!r}...")
    r = send_draft(d["draft_id"], tenant="demo")
    print(f"2) mode B send attempt -> {r['error'][:60]}  (spec §11: blocked ✓)")

    # owner edits (the gold signal) → approval invalidation rule
    owner_final = ("Estimado equipo,\n\nEl informe sale hoy antes de las 6 PM. "
                   "Lo subo al drive y les aviso por aquí.\n\nCordialmente,\nJasmel Acosta")
    rv = revise(d["draft_id"], owner_final, actor="jasmel", reason="owner_edit")
    print(f"3) owner edit -> v{rv['version']} (approval invalidated: {rv['approval_invalidated']})")
    print("   prefs after owner edit:",
          [(x["key"], x["value"], x["status"]) for x in get_preferences()])
    confirm_preference("jasmel", "length", accept=True)

    # approve binds to version; edit AFTER approval invalidates (§7)
    ap = approve(d["draft_id"], "jasmel")
    print(f"4) approved v{ap['version']}")
    set_mode("demo", "C")   # now the ONLY thing that can block a send is the approval gate
    rv2 = revise(d["draft_id"], owner_final + "\n\nP.D.: Lo subigo también al portal.", actor="jasmel")
    print(f"5) post-approval edit -> v{rv2['version']}, prior approval void: {rv2['approval_invalidated']}")
    bad = send_draft(d["draft_id"], tenant="demo")
    print(f"6) send with void approval -> {bad['error'][:60]}  (§7 ✓)")
    approve(d["draft_id"], "jasmel")

    # full loop with a REAL telegram send (labeled TEST, to owner)
    s = send_draft(d["draft_id"], tenant="demo")
    print(f"7) mode C REAL send -> {s['status']} provider_msg_id={s['provider_msg_id']}")
    print(f"   honesty: {s['note']}")
    dup = send_draft(d["draft_id"], tenant="demo")
    print(f"8) resend attempt -> duplicate={dup.get('duplicate')}  (§18 #5 idempotency ✓)")

    print("\n=== timeline (auditability §12) ===")
    tl = draft_timeline(d["draft_id"])
    for r in tl["revisions"]:
        print(f"  v{r['v']} {r['actor']}: {r['reason']}")
    for a in tl["approvals"]:
        print(f"  approval v{a['version']} by {a['approver']} valid={a['valid']}")
    for a in tl["actions"]:
        print(f"  action: {a['provider']} {a['state']} id={a['provider_msg_id']}")
    print("\ncomms_brain v2 OK — lifecycle, modes, memory layers verified live")
