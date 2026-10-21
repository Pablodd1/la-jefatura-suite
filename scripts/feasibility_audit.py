#!/usr/bin/env python3
"""Feasibility audit v2 — refresh OAuth first, import real TG token.
Every claim in docs/FEASIBILITY.md must pass here first."""
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

R = {}

def probe(name, fn):
    try:
        R[name] = fn()
    except Exception as e:
        R[name] = {"status": "FAIL", "error": str(e)[:160]}
    d = R[name]
    print(f"{name:14s} -> {d.get('status')}: {str(d.get('detail', d.get('error','')))[:120]}")

TOKENS_PATH = "/root/.openclaw/workspace/google_credentials/tokens_live.json"

def refresh_google():
    """Rotate the expired access token via refresh_token. Persists on success."""
    c = json.load(open(TOKENS_PATH))
    body = urllib.parse.urlencode({
        "client_id": c["client_id"], "client_secret": c["client_secret"],
        "refresh_token": c["refresh_token"], "grant_type": "refresh_token"}).encode()
    req = urllib.request.Request("https://oauth2.googleapis.com/token", data=body,
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=25) as r:
        d = json.loads(r.read())
    c["token"] = c["access_token"] = d["access_token"]
    c["refreshed_at"] = __import__("datetime").datetime.now().isoformat()
    json.dump(c, open(TOKENS_PATH, "w"), indent=1)
    return d["access_token"]

def google_token():
    tok = json.load(open(TOKENS_PATH)).get("token", "")
    def alive(t):
        req = urllib.request.Request("https://gmail.googleapis.com/gmail/v1/users/me/profile",
                                     headers={"Authorization": f"Bearer {t}"})
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read())
    try:
        d = alive(tok)
        return tok, d, "cached"
    except urllib.error.HTTPError as e:
        if e.code != 401:
            raise
    tok = refresh_google()
    d = alive(tok)
    return tok, d, "refreshed"

def gmail():
    tok, d, how = google_token()
    return {"status": "LIVE", "detail": f"{how}: historyId {d.get('historyId')}, {d.get('messagesTotal')} msgs"}
probe("gmail.read", gmail)

def gcal():
    tok = json.load(open(TOKENS_PATH))["token"]
    req = urllib.request.Request("https://www.googleapis.com/calendar/v3/users/me/calendarList",
                                 headers={"Authorization": f"Bearer {tok}"})
    with urllib.request.urlopen(req, timeout=20) as r:
        d = json.loads(r.read())
        return {"status": "LIVE", "detail": f"{len(d.get('items', []))} calendars"}
probe("gcal", gcal)

def gmail_send_scope():
    """Verify gmail.send scope is actually authorized (spec: narrowest scopes)."""
    tok = json.load(open(TOKENS_PATH))["token"]
    req = urllib.request.Request(
        "https://gmail.googleapis.com/gmail/v1/users/me/settings/sendAs",
        headers={"Authorization": f"Bearer {tok}"})
    with urllib.request.urlopen(req, timeout=20) as r:
        d = json.loads(r.read())
        return {"status": "LIVE", "detail": f"{len(d.get('sendAs', []))} send-as identities"}
probe("gmail.send", gmail_send_scope)

def telegram():
    sys.path.insert(0, "/root/.openclaw/workspace/mission-control")
    from mission_control import TG_TOKEN
    with urllib.request.urlopen(f"https://api.telegram.org/bot{TG_TOKEN}/getMe", timeout=20) as r:
        d = json.loads(r.read())
        return {"status": "LIVE", "detail": f"bot @{d['result']['username']}"}
probe("telegram", telegram)

probe("whatsapp.cloud", lambda: {"status": "DOCUMENTED",
    "detail": "Meta Cloud API code-ready; needs WABA id + permanent token + webhook verify. NOT provisioned."})

probe("whatsapp.personal", lambda: {"status": "ASSESSED", "detail":
    "OpenClaw WhatsApp adapter not configured on this host — method: unofficial WhatsApp Web protocol "
    "(Baileys-class). Risks: account restriction, QR re-pairing. Policy: read-and-draft only, never "
    "auto-send, immediate disconnect. Product stays functional without it (spec section 4)."})

def gemini():
    sys.path.insert(0, "/root/.openclaw/workspace/la-jefatura-suite/server")
    from ai_insights import _load_key
    k = _load_key()
    if not k:
        return {"status": "DEAD", "detail": "no key configured"}
    req = urllib.request.Request(
        f"https://generativelanguage.googleapis.com/v1beta/models?key={k}")
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return {"status": "LIVE", "detail": f"{len(json.loads(r.read()).get('models', []))} models"}
    except urllib.error.HTTPError as e:
        return {"status": "DEAD", "error": f"HTTP {e.code}: {e.read()[:90]}"}
probe("gemini", gemini)

json.dump(R, open("/root/.openclaw/workspace/la-jefatura-suite/docs/feasibility_results.json", "w"), indent=1)
print("\nsaved -> docs/feasibility_results.json")
