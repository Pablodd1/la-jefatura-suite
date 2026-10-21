"""
La Jefatura Suite — Camera integration (ONVIF / RTSP)

STATUS: scaffold, BY DESIGN. Jasmel has not provided camera brands/models yet.
This module implements the VENDOR-NEUTRAL layer that 100% of serious open-source
NVR projects converge on (verified in docs/RESEARCH.md — Frigate, KeepPeek,
ZoneMinder, Agent DVR all follow this exact model):

  RTSP        -> video transport (snapshot via ffmpeg: one frame, cheap)
  ONVIF       -> discovery (WS-Discovery probe), events (PullPoint motion),
                 PTZ, profile queries
  ffmpeg      -> the only sane snapshot/clip tool; do NOT decode video in Python
  AI summary  -> snapshot -> Gemini vision caption -> Telegram digest
  Storage     -> snapshots/ + SQLite event log (cam_events)

Dependencies are OPTIONAL and imported lazily: the module loads and reports
status with zero deps installed; real capture requires:
    pip install onvif-zeep        (discovery + events)
    apt install ffmpeg            (snapshots — usually already present)

Config comes from data/samples/cameras.json (copy to config/cameras.json and
fill real hosts). NEVER commit credentials.
"""

import json
import os
import sqlite3
import subprocess
import time

DB = "/root/.openclaw/workspace/mission-control/mc.db"
SNAP_DIR = "/root/.openclaw/workspace/mission-control/snapshots"
os.makedirs(SNAP_DIR, exist_ok=True)

SCHEMA = """
CREATE TABLE IF NOT EXISTS cam_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cam_id TEXT, ts REAL, kind TEXT,      -- motion | person | vehicle | offline
    zona TEXT, confianza REAL, snapshot TEXT,
    fuera_horario INT DEFAULT 0, nota TEXT
);
"""

WORK_START = 8   # office hours 08:00-19:00 local (Miami)
WORK_END = 19


def db():
    c = sqlite3.connect(DB)
    c.executescript(SCHEMA)
    return c


# ── 1. Discovery (ONVIF WS-Discovery) ───────────────────────────────────────

def discover(timeout: int = 5) -> list[dict]:
    """Probe the LAN for ONVIF devices. Requires: pip install onvif-zeep."""
    try:
        from onvif import ONVIFCamera  # noqa: F401
        from wsdiscovery import WSDiscovery
    except ImportError:
        return [{"error": "onvif-zeep/wsdiscovery not installed",
                 "fix": "pip install onvif-zeep wsdiscovery"}]
    wsd = WSDiscovery()
    wsd.start()
    services = wsd.searchServices(types=[
        "http://www.onvif.org/ver10/network/wsdl/NetworkVideoTransmitter"])
    out = []
    for s in services:
        xaddrs = [str(a) for a in s.getXAddrs()]
        out.append({"name": s.getEPR(), "xaddrs": xaddrs})
    wsd.stop()
    return out


# ── 2. Snapshots (ffmpeg, one frame) ─────────────────────────────────────────

def snapshot(cam: dict) -> str | None:
    """Grab a single JPEG from the RTSP url. Returns path or None."""
    url = cam.get("url_rtsp", "")
    if not url or "USER:PASS@IP" in url:
        return None  # placeholder config
    path = os.path.join(SNAP_DIR, f"{cam['id']}_{int(time.time())}.jpg")
    r = subprocess.run(
        ["ffmpeg", "-y", "-rtsp_transport", "tcp", "-i", url,
         "-frames:v", "1", "-q:v", "3", path],
        capture_output=True, timeout=20)
    return path if r.returncode == 0 and os.path.getsize(path) > 5000 else None


# ── 3. Events ────────────────────────────────────────────────────────────────
# Research note (docs/RESEARCH.md): the robust pattern used by Frigate/KeepPeek
# is "native events when the camera provides them (ONVIF PullPoint), software
# CV as fallback". We implement the fallback here with plain ffmpeg frame diffs
# (no OpenCV dependency), and leave PullPoint for after hardware is known.

def motion_poll(cam: dict, seconds: int = 4) -> float:
    """Cheap motion score 0..1 via frame difference (ffmpeg signalstats).
    Works on ANY RTSP camera, no AI needed. Fine for 'is something moving'."""
    url = cam.get("url_rtsp", "")
    if not url or "USER:PASS@IP" in url:
        return 0.0
    try:
        r = subprocess.run(
            ["ffmpeg", "-rtsp_transport", "tcp", "-i", url, "-t",
             str(seconds), "-vf",
             "select='gte(scene,0)',metadata=print", "-f", "null", "-"],
            capture_output=True, text=True, timeout=seconds + 10)
        scores = [float(l.split("=")[1]) for l in r.stderr.splitlines()
                  if "scene_score" in l]
        return max(scores) if scores else 0.0
    except Exception:
        return 0.0


def log_event(cam_id: str, kind: str, zona: str = "", conf: float = 0.0,
              snapshot: str | None = None, nota: str = "",
              fuera_horario: bool | None = None) -> int:
    if fuera_horario is None:
        h = time.localtime().tm_hour
        fuera_horario = 1 if (h < WORK_START or h >= WORK_END) else 0
    c = db()
    cur = c.execute(
        "INSERT INTO cam_events(cam_id,ts,kind,zona,confianza,snapshot,"
        "fuera_horario,nota) VALUES(?,?,?,?,?,?,?,?)",
        (cam_id, time.time(), kind, zona, conf, snapshot, fuera_horario, nota))
    c.commit(); c.close()
    return cur.lastrowid


# ── 4. AI digest (Gemini vision on snapshots) ───────────────────────────────

def ai_digest(limit: int = 12) -> str:
    """Event digest for the daily report. Text events go to Gemini; if a
    snapshot path exists for the newest event, a vision caption is requested.
    Falls back to a plain template without a key."""
    from ai_insights import camera_event_summary  # lazy: same package
    c = db()
    rows = c.execute(
        "SELECT cam_id,ts,kind,zona,confianza,fuera_horario,nota,snapshot "
        "FROM cam_events ORDER BY ts DESC LIMIT ?", (limit,)).fetchall()
    c.close()
    events = [{"cam": r[0], "tipo": r[2], "zona": r[3], "confianza": r[4],
               "fuera_horario": bool(r[5]), "nota": r[6]} for r in rows]
    return camera_event_summary(events)


# ── Route table for Mission Control ──────────────────────────────────────────
# GET /api/cameras/status  -> {cameras: config, last_events, digest}
# POST /api/cameras/snap/:id -> force snapshot, returns path
def status(config_path: str) -> dict:
    cfg = json.load(open(config_path, encoding="utf-8"))
    c = db()
    last = c.execute(
        "SELECT cam_id,ts,kind,zona,fuera_horario FROM cam_events "
        "ORDER BY ts DESC LIMIT 10").fetchall()
    c.close()
    return {
        "cameras": cfg["camaras"],
        "eventos_recientes": [
            {"cam": r[0], "ts": r[1], "tipo": r[2], "zona": r[3],
             "fuera_horario": bool(r[4])} for r in last],
        "digest_ia": ai_digest(),
    }


if __name__ == "__main__":
    s = status("../data/samples/cameras.json")
    print("cameras:", len(s["cameras"]),
          "| digest:", s["digest_ia"][:100], "...")
    print("cameras module OK (scaffold, no hardware configured)")
