"""
La Jefatura Suite — Comms Brain (monitor → draft → owner-edit → learn → send)

The owner asked (verbatim): "monitoring, responding with draft and learn from
each text incoming and outgoing also edited and made by the owner of the
account profile."

THE LOOP
  1. INGEST   every message (in + out) across channels into comms_log.
  2. DRAFT    when a message needs_reply, build a reply in the OWNER'S voice:
              greeting, sign-off, formality, length, signature — all learned.
  3. APPROVE  owner edits the draft. NOTHING sends without approval. The edit
              is the strongest training signal that exists.
  4. LEARN    every owner-authored text AND every owner-edit tightens the
              voice_profile. The next draft is measurably more "them".
  5. SEND     only after approval, via the channel's real transport.

CHANNELS
  gmail     LIVE (OAuth tokens on host; REST send via urllib, no SDK needed)
  telegram  LIVE (bot token in MC .env)
  whatsapp  DOCUMENTED — Meta Cloud API webhook shape matches ingest(); the
            transport is the only missing piece (needs WABA + permanent token)

MODEL ROUTING (owner's JMM analysis, applied here — docs/COMMS_BRAIN.md)
  daily drafts/fast classification -> flash-class model
  complex threads -> escalate to reasoning model
  switching models without a blinded eval = malpractice (owner's rule)

Self-test:  python3 server/comms_brain.py
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

SCHEMA = """
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


def _db():
    c = sqlite3.connect(DB)
    c.executescript(SCHEMA)
    return c


# ── 1. INGEST ────────────────────────────────────────────────────────────────
def ingest(channel, direction, contact, text, msg_id=None, thread_id=None,
           auto_flag=True):
    """Record any message. Idempotent on msg_id. Returns the row id."""
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
    if direction == "out_owner":           # owner's own words teach the voice
        learn()
    c.close()
    return {"id": mid, "needs_reply": needs_reply}


def _looks_actionable(text):
    """Cheap heuristic — a question, request, or deadline usually needs a reply.
    (A flash-class classifier replaces this when a key exists; keep heuristic
    as fallback so the loop never stalls on an API.)"""
    t = text.lower()
    if re.search(r"\?|por favor|please|necesito|can you|could you|cuánto|how much|deadline|hoy|today|asap", t):
        return True
    return len(t) > 40 and not re.search(r"^(ok|vale|gracias|thanks|recibido|received)\b", t)


# ── 4. LEARN (voice profile from owner texts + owner edits) ─────────────────
_PROFILE_KEYS = ["greeting", "signoff", "signature", "formality", "avg_len",
                 "avg_sentences", "exclaim_rate", "common_openers", "languages"]


def _analyze(texts):
    """Extract style fingerprints from a corpus. Pure code — the LLM never
    computes metrics (owner's rule: never let the LLM do math)."""
    if not texts:
        return {}
    joins = [t for t in texts if t.strip()]
    lens = [len(t.split()) for t in joins]
    firsts, lasts = {}, {}
    for t in joins:
        words = t.strip().split()
        if len(words) < 3:
            continue
        f = " ".join(words[:2]).lower().strip(",.;:!¡¿?")
        firsts[f] = firsts.get(f, 0) + 1
    formal = sum(1 for t in joins if re.search(r"\bestimad[oa]\b|\bdear\b|cordialmente|sincerely|atte\b|atentamente", t, re.I))
    excl = sum(1 for t in joins if t.count("!") > 0)
    # valediction: short closing LINE (cordialmente, / atentamente, / saludos,)
    vale_re = re.compile(r"^(cordialmente|atentamente|saludos|un abrazo|sincerely|best regards|kind regards|atte\.?|thanks)\b", re.I)
    vales = {}
    for t in joins:
        for ln in t.strip().splitlines():
            ln = ln.strip().strip(",.;").lower()
            if ln and len(ln.split()) <= 3 and vale_re.match(ln):
                vales[ln] = vales.get(ln, 0) + 1
    # signature: last short line that looks like a name/address (has @ or 2-3 titlecase words)
    sigs = {}
    for t in joins:
        lines = [l.strip() for l in t.strip().splitlines() if l.strip()]
        for l in lines[-2:]:
            if ("@" in l) or (1 <= len(l.split()) <= 4 and l[:1].isupper() and any(
                    w in l.lower() for w in ("jasmel", "acosta"))):
                sigs[l] = sigs.get(l, 0) + 1
    return {
        "avg_len": round(sum(lens) / len(lens)),
        "avg_sentences": round(sum(t.count(".") + t.count("!") + t.count("?") for t in joins) / len(joins), 1),
        "formality": round(formal / len(joins), 2),
        "exclaim_rate": round(excl / len(joins), 2),
        "greeting": max(firsts, key=firsts.get) if firsts else "",
        "signoff": (max(vales, key=vales.get) + ",") if vales else "",
        "signature": max(sigs, key=sigs.get) if sigs else "",
        "languages": sorted({("es" if re.search(r"\b(el|la|que|para|gracias)\b", t.lower()) else "en")
                             for t in joins[:20]}),
    }


def learn(owner="jasmel"):
    """Rebuild voice_profile from ALL owner-authored text (sent messages) +
    every recorded owner edit. Call after ingest(out_owner) and record_edit."""
    c = _db()
    own = [r[0] for r in c.execute(
        "SELECT text FROM comms_log WHERE owner_sent=1 ORDER BY ts DESC LIMIT 200")]
    edits = c.execute(
        "SELECT body_original, body_final FROM drafts WHERE edited_by_owner=1").fetchall()
    edited_finals = [e[1] for e in edits if e[1]]
    prof = _analyze(own + edited_finals)
    for k, v in _analyze(edited_finals).items() if edited_finals else []:
        pass  # edits already folded into corpus; per-edit deltas live in drafts
    c.execute("INSERT INTO voice_profile VALUES(?,?,?,?,?) "
              "ON CONFLICT(owner) DO UPDATE SET json=?, msgs=?, edits=?, updated_ts=?",
              (owner, json.dumps(prof), len(own), len(edited_finals), time.time(),
               json.dumps(prof), len(own), len(edited_finals), time.time()))
    c.commit(); c.close()
    return prof


def record_edit(draft_id, final_text):
    """THE learning moment: owner rewrote our draft. Store final + diff stats,
    retune the profile from the edit corpus."""
    c = _db()
    row = c.execute("SELECT body_original FROM drafts WHERE id=?", (draft_id,)).fetchone()
    if not row:
        c.close()
        return {"ok": False, "error": "draft not found"}
    orig = row[0]
    sim = difflib.SequenceMatcher(None, orig, final_text).ratio()
    c.execute("UPDATE drafts SET body_final=?, status='edited', edited_by_owner=1 "
              "WHERE id=?", (final_text, draft_id))
    c.commit()
    prof = learn()
    c.close()
    return {"ok": True, "similarity": round(sim, 2),
            "learned": {"signoff": prof.get("signoff"), "formality": prof.get("formality"),
                        "avg_len": prof.get("avg_len")}}


# ── 2. DRAFT ─────────────────────────────────────────────────────────────────
def draft(thread_id, channel="gmail", style_hints=""):
    """Compose a reply to a thread in the owner's voice.

    AI model (when a key exists): gemini flash-class writes the body from
    thread context + voice profile JSON + style hints (temp 0.3).
    Fallback (now): template assembler that applies profile greeting/signoff/
    length — deliberately 'dumb' so the owner-edit loop is the teacher.
    """
    c = _db()
    msgs = c.execute(
        "SELECT direction, contact, text FROM comms_log WHERE thread_id=? "
        "ORDER BY ts", (thread_id,)).fetchall()
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
        "INSERT INTO drafts(reply_to, channel, to_addr, body_original, status, created_ts) "
        "VALUES(?,?,?,?,?,?)",
        (thread_id, channel, last_in[1], body, "pending_approval", time.time()))
    c.commit()
    did = cur.lastrowid
    c.close()
    return {"ok": True, "draft_id": did, "body": body,
            "voice": {"signoff": prof.get("signoff"), "formality": prof.get("formality")}}


def _cap(s):   # "estimada laura" -> "Estimada Laura" (capitalize() would butcher names)
    return " ".join(w[:1].upper() + w[1:] for w in s.split())


def _compose(incoming, thread_msgs, prof, hints):
    """Template fallback composer. Mirrors the learned style:
    greeting if formal, mirrored length (capped), learned sign-off + signature."""
    target_len = min(max(int(prof.get("avg_len", 40) * 0.8), 15), 90)
    core = ("Gracias por tu mensaje. " if not re.search(r"gracias", incoming.lower())
            else "Con gusto. ")
    # address the ask crudely: first question/verb phrase
    m = re.search(r"([^.!?]*\?)", incoming)
    if m:
        core += "Respecto a tu pregunta: te confirmo los detalles hoy mismo. "
    core += "Quedo atento a cualquier ajuste. "
    words = core.split()
    if len(words) > target_len:                     # cut on a word boundary
        body = " ".join(words[:target_len])
    else:
        body = " ".join(words)
    if prof.get("formality", 0) > 0.3 and prof.get("greeting"):
        body = _cap(prof["greeting"]) + ",\n\n" + body
    signoff = prof.get("signoff", "")
    signature = prof.get("signature", "")
    if signoff and signoff.lower().strip(",") not in signature.lower():  # don't double the name
        body += "\n\n" + _cap(signoff)
    elif not signoff and signature:            # no valediction learned yet: keep name only
        pass
    if signature:
        body += "\n" + signature
    if hints:
        body += f"\n\n[{hints}]"
    return body


# ── 3/5. APPROVE + SEND ─────────────────────────────────────────────────────
def approve_and_send(draft_id, edited_body=None, channel_override=None):
    """Owner approved (possibly after editing in their client). Sends via the
    channel transport. Gmail + Telegram are live paths; whatsapp raises a
    clear NotImplemented with the Meta Cloud API steps."""
    c = _db()
    row = c.execute("SELECT reply_to, channel, to_addr, body_original FROM drafts "
                    "WHERE id=? AND status IN ('pending_approval','edited')",
                    (draft_id,)).fetchone()
    if not row:
        c.close()
        return {"ok": False, "error": "draft not found or already handled"}
    thread_id, channel, to_addr, orig = row
    body = edited_body or orig
    if edited_body:                        # approval-with-edits also teaches
        c.execute("UPDATE drafts SET body_final=?, edited_by_owner=1 WHERE id=?",
                  (edited_body, draft_id))
    transport = channel_override or channel
    try:
        if transport == "gmail":
            result = _send_gmail(to_addr, f"Re: {thread_id}", body)
        elif transport == "telegram":
            result = _send_telegram(to_addr, body)
        elif transport == "whatsapp":
            raise NotImplementedError(
                "WhatsApp needs Meta Cloud API: WABA id + permanent token, "
                "POST https://graph.facebook.com/v21.0/{WABA}/messages with "
                "messaging_product=whatsapp. Webhook shape matches ingest() — "
                "this is the only unwired piece, by design, until Jasmel provisions it.")
        else:
            raise ValueError(f"unknown channel {transport}")
    except Exception as e:
        c.close()
        return {"ok": False, "error": str(e)}
    c.execute("UPDATE drafts SET status='sent', sent_ts=? WHERE id=?", (time.time(), draft_id))
    c.execute("UPDATE comms_log SET needs_reply=0 WHERE thread_id=?", (thread_id,))
    ingest(transport, "out_owner", to_addr, body, thread_id=thread_id)   # owner's voice corpus
    c.close()
    return {"ok": True, "sent_via": transport, "result": result}


def _send_gmail(to, subject, body):
    import urllib.request
    creds = json.load(open(GOOGLE_CREDS))
    tok = creds.get("token")
    if not tok:
        raise RuntimeError("gmail token missing — run the OAuth flow in workspace/google_credentials")
    raw = (f"To: {to}\r\nSubject: {subject}\r\nContent-Type: text/plain; charset=utf-8"
           f"\r\n\r\n{body}")
    import base64
    payload = base64.urlsafe_b64encode(raw.encode()).decode()
    req = urllib.request.Request(
        "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
        data=json.dumps({"raw": payload}).encode(),
        headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read()).get("id", "sent")


def _send_telegram(chat_id, body):
    import urllib.request
    token = os.environ.get("TG_BOT_TOKEN")
    if not token:
        env = os.path.join(os.path.dirname(DB), ".env")
        if os.path.exists(env):
            for line in open(env):
                if line.startswith("TG_BOT_TOKEN="):
                    token = line.split("=", 1)[1].strip()
    if not token:
        raise RuntimeError("TG_BOT_TOKEN not found")
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=json.dumps({"chat_id": chat_id, "text": body}).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read()).get("result", {}).get("message_id", "sent")


def needs_reply_queue():
    c = _db()
    rows = c.execute(
        "SELECT thread_id, channel, contact, text, ts FROM comms_log "
        "WHERE needs_reply=1 ORDER BY ts DESC LIMIT 20").fetchall()
    c.close()
    return [{"thread_id": r[0], "channel": r[1], "contact": r[2],
             "preview": r[3][:80], "ts": r[4]} for r in rows]


# ── SELF-TEST: full loop with a simulated owner edit ────────────────────────
if __name__ == "__main__":
    # clean previous self-test rows so the demo is deterministic
    c = _db()
    c.execute("DELETE FROM comms_log WHERE thread_id LIKE 'demo-%'")
    c.execute("DELETE FROM drafts WHERE reply_to LIKE 'demo-%'")
    c.commit(); c.close()

    # owner history teaches the voice
    ingest("gmail", "out_owner", "a@x.com",
           "Estimado Carlos,\n\nTe envío la cotización actualizada para el servicio de facturación médica. "
           "Incluye el desglose mensual y las condiciones de pago que conversamos la semana pasada en la llamada. "
           "Quedo atento a cualquier duda o ajuste que necesites revisar antes de firmar.\n\nCordialmente,\nJasmel Acosta\njasmelacosta@gmail.com",
           msg_id="demo-own1")
    ingest("gmail", "out_owner", "b@x.com",
           "Estimada Laura,\n\nPerfecto, confirmamos la reunión de mañana a las diez en la oficina. "
           "Llevo impresos los reportes del último trimestre para que los revisemos juntos punto por punto. "
           "Si surge cualquier cambio de agenda avísame con tiempo.\n\nCordialmente,\nJasmel Acosta",
           msg_id="demo-own2")
    p = learn()
    print(f"  learned voice: signoff='{p.get('signoff')}' formality={p.get('formality')} avg_len={p.get('avg_len')}")

    # incoming that needs a reply
    ingest("gmail", "in", "dr.molina@doralurgent.com",
           "Jasmel, ¿cuál es el precio mensual del servicio para dos médicos? Necesito la cifra hoy.",
           msg_id="demo-in1", thread_id="demo-t1")
    q = needs_reply_queue()
    print(f"  queue: {len(q)} need reply -> {q[0]['contact']}")

    d = draft("demo-t1")
    print(f"  draft #{d['draft_id']} (voice signoff='{d['voice']['signoff']}'):\n    {d['body'][:120]!r}")

    # owner edits the draft — the strongest training signal
    owner_final = ("Estimado Dr. Molina,\n\nPara dos médicos la tarifa es 6.5% de lo cobrado, "
                   "sin costo fijo. Le envío el contrato hoy mismo.\n\nCordialmente,\nJasmel Acosta")
    e = record_edit(d["draft_id"], owner_final)
    print(f"  owner edit: similarity={e['similarity']} -> learned signoff='{e['learned']['signoff']}'")

    # second draft must now wear the owner's voice
    ingest("gmail", "in", "clinica@delmar.com", "¿Me confirman la fecha de corte para nómina?",
           msg_id="demo-in2", thread_id="demo-t2")
    d2 = draft("demo-t2")
    print(f"  draft #2 (after learning): {d2['body'][:140]!r}")

    for row in needs_reply_queue():
        print(f"  still pending: {row['contact']} — {row['preview']!r}")
    print("comms_brain OK — no sends performed (approval gate intact)")
