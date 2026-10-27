"""
La Jefatura Suite — Camera Daily Report Engine (CEO text summaries, totals, history)

Design (verified against open-source practice, see docs/CAMERAS_REPORT_RESEARCH.md):
  * Frigate / HA-Hikvision pattern  -> events + periodic state, summarised per period.
  * Everything below is DETERMINISTIC (SQL/arithmetic). No AI invents numbers; the
    report only states what was measured. Missing data is reported as "sin dato".

Data sources (each labelled in the report so the CEO knows what is measured):
  CLOUD  Hik-Connect poll every 5 min : device/channel online, disk, WAN/LAN IP, firmware
  CLOUD  Hik-Connect alarm feed       : push events (only if "Notify Surveillance Center" is ON)
  SITE   site_agent/hik_isapi_agent.py: local ISAPI alertStream events (motion, line crossing,
                                        intrusion, tamper, video loss, HDD error) POSTed to
                                        /api/cameras/events  (needs a PC on the site LAN)
"""

import json
import os
import sqlite3
import threading
import time

import cameras

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPORT_DIR = os.path.join(ROOT, "data", "camera_reports")
os.makedirs(REPORT_DIR, exist_ok=True)

POLL_SECONDS = 300
REPORT_HOUR, REPORT_MIN = 7, 30   # daily report is built at 07:30 local for the previous day

SCHEMA = """
CREATE TABLE IF NOT EXISTS cam_status_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, day TEXT,
    serial TEXT, channel INT, name TEXT, device_online INT, signal_ok INT
);
CREATE INDEX IF NOT EXISTS ix_csl_day ON cam_status_log(day, serial);
CREATE TABLE IF NOT EXISTS cam_device_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, day TEXT, serial TEXT, name TEXT,
    online INT, wan_ip TEXT, lan_ip TEXT, firmware TEXT, disks TEXT, encrypted INT
);
CREATE INDEX IF NOT EXISTS ix_cdl_day ON cam_device_log(day, serial);
CREATE TABLE IF NOT EXISTS cam_reports (
    day TEXT PRIMARY KEY, built_at REAL, text_es TEXT, text_en TEXT, data_json TEXT
);
CREATE TABLE IF NOT EXISTS cam_event_dedupe (k TEXT PRIMARY KEY);
"""

_lock = threading.Lock()


def _db():
    c = cameras.db()
    c.executescript(SCHEMA)
    return c


def _day(ts=None):
    return time.strftime("%Y-%m-%d", time.localtime(ts or time.time()))


# ───────────────────────────── polling ─────────────────────────────

def poll() -> dict:
    """Take one measurement of every device/channel and log state transitions as events."""
    with _lock:
        hik = cameras.sync_hikconnect(force=True)
        if not hik.get("ok") or hik.get("cached_fallback"):
            return {"ok": False, "error": hik.get("error") or hik.get("last_sync_error")}
        now = time.time()
        day = _day(now)
        c = _db()
        transitions = 0
        for d in hik["devices"]:
            prev = c.execute(
                "SELECT online,wan_ip,lan_ip,firmware,disks FROM cam_device_log "
                "WHERE serial=? ORDER BY ts DESC LIMIT 1", (d["serial"],)).fetchone()
            disks = d.get("disks_summary", "")
            c.execute("INSERT INTO cam_device_log(ts,day,serial,name,online,wan_ip,lan_ip,firmware,disks,encrypted) "
                      "VALUES(?,?,?,?,?,?,?,?,?,?)",
                      (now, day, d["serial"], d["name"], int(d["online"]), d.get("wan_ip", ""),
                       d.get("lan_ip", ""), d.get("firmware", ""), disks, int(d.get("is_encrypted", False))))
            if prev is not None:
                if prev[0] != int(d["online"]):
                    cameras.log_event(d["serial"], "online" if d["online"] else "offline", d["name"], 1.0,
                                      None, f"{d['name']} ({d['model']}) pasó a {'ONLINE' if d['online'] else 'OFFLINE'}")
                    transitions += 1
                if prev[1] and prev[1] != d.get("wan_ip"):
                    cameras.log_event(d["serial"], "wan_change", d["name"], 1.0, None,
                                      f"IP pública cambió {prev[1]} -> {d.get('wan_ip')}")
                if prev[3] and prev[3] != d.get("firmware"):
                    cameras.log_event(d["serial"], "firmware", d["name"], 1.0, None,
                                      f"Firmware {prev[3]} -> {d.get('firmware')}")
                if prev[4] and prev[4] != disks:
                    cameras.log_event(d["serial"], "disk_change", d["name"], 1.0, None,
                                      f"Discos {prev[4]} -> {disks}")
            for ch in d["channels"]:
                p = c.execute("SELECT signal_ok FROM cam_status_log WHERE serial=? AND channel=? "
                              "ORDER BY ts DESC LIMIT 1", (d["serial"], ch["channel_no"])).fetchone()
                ok = int(ch["signal_status"] == "OK" and d["online"])
                c.execute("INSERT INTO cam_status_log(ts,day,serial,channel,name,device_online,signal_ok) "
                          "VALUES(?,?,?,?,?,?,?)",
                          (now, day, d["serial"], ch["channel_no"], ch["name"], int(d["online"]), ok))
                if p is not None and p[0] != ok and d["online"]:
                    cameras.log_event(f"{d['serial']}-CH{ch['channel_no']:02d}",
                                      "signal_restored" if ok else "signal_lost", ch["name"], 1.0, None,
                                      f"Canal {ch['channel_no']} «{ch['name']}» {'recuperó' if ok else 'perdió'} señal")
                    transitions += 1
        c.commit()
        c.close()
    alarms = ingest_cloud_alarms(hik)
    return {"ok": True, "devices": len(hik["devices"]), "channels": len(hik["channels"]),
            "transitions": transitions, "cloud_alarms_new": alarms, "ts": now}


def ingest_cloud_alarms(hik: dict) -> int:
    """Pull Hik-Connect alarm feed. Empty unless 'Notify Surveillance Center' is enabled on the recorder."""
    sid = cameras._HIK_CACHE.get("session_id")
    base = cameras._HIK_CACHE.get("base_url")
    if not sid or not base:
        return 0
    new = 0
    c = _db()
    for d in hik.get("devices", []):
        try:
            res = cameras._http_req(
                f"{base}/v3/alarms/v2/advanced?deviceSerials={d['serial']}&queryType=-1&limit=50&stype=-1",
                headers={"sessionId": sid})
        except Exception:
            continue
        for a in res.get("alarms") or []:
            key = d["serial"] + "|" + json.dumps(a, sort_keys=True)[:300]
            if c.execute("SELECT 1 FROM cam_event_dedupe WHERE k=?", (key,)).fetchone():
                continue
            c.execute("INSERT INTO cam_event_dedupe(k) VALUES(?)", (key,))
            ts = None
            for k in ("alarmStartTime", "alarmTime", "time", "startTime"):
                v = a.get(k)
                if v:
                    try:
                        ts = float(v) / (1000.0 if float(v) > 1e11 else 1.0)
                    except (TypeError, ValueError):
                        try:
                            ts = time.mktime(time.strptime(str(v)[:19], "%Y-%m-%d %H:%M:%S"))
                        except Exception:
                            pass
                    break
            ch = a.get("channelNo") or a.get("channel") or ""
            cameras.log_event(f"{d['serial']}-CH{int(ch):02d}" if str(ch).isdigit() else d["serial"],
                              "cloud_alarm", str(a.get("alarmType", a.get("type", ""))), 1.0,
                              a.get("alarmPicUrl") or a.get("picUrl"), json.dumps(a, ensure_ascii=False)[:500])
            if ts:
                c.execute("UPDATE cam_events SET ts=? WHERE id=(SELECT MAX(id) FROM cam_events)", (ts,))
            new += 1
    c.commit()
    c.close()
    return new


# ───────────────────────────── report ─────────────────────────────

def _fmt_min(m):
    m = int(round(m))
    return f"{m // 60} h {m % 60:02d} min" if m >= 60 else f"{m} min"


def build_report(day: str | None = None, save: bool = True) -> dict:
    day = day or _day()
    c = _db()
    t0 = time.mktime(time.strptime(day, "%Y-%m-%d"))
    t1 = t0 + 86400

    devs = c.execute("SELECT serial, MAX(name) FROM cam_device_log WHERE day=? GROUP BY serial", (day,)).fetchall()
    out_devices = []
    tot_samples = tot_ok = 0
    for serial, name in devs:
        rows = c.execute("SELECT ts,online,wan_ip,lan_ip,firmware,disks FROM cam_device_log "
                         "WHERE day=? AND serial=? ORDER BY ts", (day, serial)).fetchall()
        n = len(rows)
        up = sum(r[1] for r in rows)
        # downtime estimated from consecutive samples (each offline sample covers its interval)
        down_min = 0.0
        for i, r in enumerate(rows):
            nxt = rows[i + 1][0] if i + 1 < n else min(r[0] + POLL_SECONDS, t1)
            if not r[1]:
                down_min += max(0.0, (nxt - r[0]) / 60.0)
        ch_rows = c.execute("SELECT channel,MAX(name),COUNT(*),SUM(signal_ok) FROM cam_status_log "
                            "WHERE day=? AND serial=? GROUP BY channel ORDER BY channel", (day, serial)).fetchall()
        chans = [{"channel": r[0], "name": r[1], "samples": r[2],
                  "availability_pct": round(100.0 * (r[3] or 0) / r[2], 1) if r[2] else None} for r in ch_rows]
        weak = [x for x in chans if x["availability_pct"] is not None and x["availability_pct"] < 99.0]
        tot_samples += n
        tot_ok += up
        last = rows[-1] if rows else None
        out_devices.append({
            "serial": serial, "name": name, "samples": n,
            "availability_pct": round(100.0 * up / n, 1) if n else None,
            "downtime_min": round(down_min, 1),
            "channels_total": len(chans), "channels_weak": weak,
            "wan_ip": last[2] if last else "", "lan_ip": last[3] if last else "",
            "firmware": last[4] if last else "", "disks": last[5] if last else "",
            "first_sample": time.strftime("%H:%M", time.localtime(rows[0][0])) if rows else None,
            "last_sample": time.strftime("%H:%M", time.localtime(rows[-1][0])) if rows else None,
        })

    ev = c.execute("SELECT cam_id,ts,kind,zona,fuera_horario,nota FROM cam_events WHERE ts>=? AND ts<? ORDER BY ts",
                   (t0, t1)).fetchall()
    by_kind, by_cam, by_hour = {}, {}, {h: 0 for h in range(24)}
    activity_kinds = ("motion", "person", "vehicle", "linecrossing", "intrusion", "cloud_alarm", "regionEntrance",
                      "regionExiting", "fielddetection", "facedetection", "tamper")
    first_act, last_act, after_hours = {}, {}, []
    for cam_id, ts, kind, zona, fh, nota in ev:
        by_kind[kind] = by_kind.get(kind, 0) + 1
        if kind in activity_kinds:
            by_cam[cam_id] = by_cam.get(cam_id, 0) + 1
            by_hour[int(time.strftime("%H", time.localtime(ts)))] += 1
            first_act.setdefault(cam_id, ts)
            last_act[cam_id] = ts
            if fh:
                after_hours.append({"cam": cam_id, "time": time.strftime("%H:%M", time.localtime(ts)),
                                    "kind": kind, "zona": zona})
    top_cams = sorted(by_cam.items(), key=lambda x: -x[1])[:5]
    health_events = [{"time": time.strftime("%H:%M", time.localtime(e[1])), "kind": e[2], "nota": e[5]}
                     for e in ev if e[2] in ("offline", "online", "signal_lost", "signal_restored",
                                             "wan_change", "firmware", "disk_change", "videoloss", "hdd_error")]
    sources = {"cloud_polls": max([d["samples"] for d in out_devices] or [0]),
               "activity_events": sum(by_cam.values()),
               "site_agent_events": sum(1 for e in ev if (e[5] or "").startswith("[isapi]"))}
    c.close()

    data = {
        "day": day, "devices": out_devices, "totals": {
            "devices": len(out_devices),
            "channels": sum(d["channels_total"] for d in out_devices),
            "fleet_availability_pct": round(100.0 * tot_ok / tot_samples, 1) if tot_samples else None,
            "downtime_min": round(sum(d["downtime_min"] for d in out_devices), 1),
            "activity_events": sources["activity_events"], "after_hours_events": len(after_hours),
            "health_events": len(health_events)},
        "events_by_kind": by_kind, "events_by_hour": by_hour,
        "top_cameras": [{"cam": k, "events": v,
                         "first": time.strftime("%H:%M", time.localtime(first_act[k])),
                         "last": time.strftime("%H:%M", time.localtime(last_act[k]))} for k, v in top_cams],
        "after_hours": after_hours[:20], "health_events": health_events[:40], "sources": sources,
    }
    data["text_es"] = _text(data, "es")
    data["text_en"] = _text(data, "en")
    if save:
        c = _db()
        c.execute("INSERT OR REPLACE INTO cam_reports(day,built_at,text_es,text_en,data_json) VALUES(?,?,?,?,?)",
                  (day, time.time(), data["text_es"], data["text_en"], json.dumps(data, ensure_ascii=False)))
        c.commit()
        c.close()
        with open(os.path.join(REPORT_DIR, f"camaras_{day}.md"), "w", encoding="utf-8") as f:
            f.write(data["text_es"] + "\n\n---\n\n" + data["text_en"])
    return data


def _text(d: dict, lang: str) -> str:
    es = lang == "es"
    T = d["totals"]
    L = []
    if not d["devices"]:
        return ("Informe de cámaras " + d["day"] + ": sin datos medidos ese día (el monitoreo aún no había corrido)."
                if es else f"Camera report {d['day']}: no measured data that day (monitoring had not run yet).")
    L.append((f"INFORME DE CÁMARAS — {d['day']}" if es else f"CAMERA REPORT — {d['day']}"))
    L.append((f"Resumen: {T['devices']} equipos, {T['channels']} canales. Disponibilidad de la flota {T['fleet_availability_pct']}%. "
              f"Tiempo total fuera de línea de equipos: {_fmt_min(T['downtime_min'])}. "
              f"Actividad detectada: {T['activity_events']} eventos ({T['after_hours_events']} fuera de horario). "
              f"Eventos de salud/red: {T['health_events']}.") if es else
             (f"Summary: {T['devices']} devices, {T['channels']} channels. Fleet availability {T['fleet_availability_pct']}%. "
              f"Total device offline time: {_fmt_min(T['downtime_min'])}. "
              f"Activity detected: {T['activity_events']} events ({T['after_hours_events']} after hours). "
              f"Health/network events: {T['health_events']}."))
    L.append("")
    L.append("POR EQUIPO:" if es else "PER DEVICE:")
    for x in d["devices"]:
        weak = ", ".join(f"CH{w['channel']} {w['name']} ({w['availability_pct']}%)" for w in x["channels_weak"][:6])
        L.append(f"- {x['name']} [{x['serial']}] · {x['availability_pct']}% " +
                 (f"disponible, caído {_fmt_min(x['downtime_min'])}" if es else f"available, down {_fmt_min(x['downtime_min'])}") +
                 f" · {x['channels_total']} " + ("canales" if es else "channels") + f" · HDD {x['disks'] or 'n/d'}" +
                 (f" · {'canales con falla' if es else 'weak channels'}: {weak}" if weak else ""))
    L.append("")
    if d["health_events"]:
        L.append("CAMBIOS DE ESTADO:" if es else "STATE CHANGES:")
        for e in d["health_events"][:15]:
            L.append(f"- {e['time']} · {e['nota']}")
        L.append("")
    if d["top_cameras"]:
        L.append("ZONAS MÁS ACTIVAS:" if es else "MOST ACTIVE ZONES:")
        for t in d["top_cameras"]:
            L.append(f"- {t['cam']}: {t['events']} " + ("eventos" if es else "events") +
                     f" ({t['first']}–{t['last']})")
        peak = max(d["events_by_hour"].items(), key=lambda kv: kv[1])
        L.append((f"Hora pico de actividad: {peak[0]:02d}:00 ({peak[1]} eventos)." if es else
                  f"Peak activity hour: {peak[0]:02d}:00 ({peak[1]} events)."))
        L.append("")
    else:
        L.append(("ACTIVIDAD: sin eventos de movimiento/personas recibidos. Causa conocida: la notificación al centro de "
                  "vigilancia está apagada en las grabadoras y no hay agente local instalado; no se inventa actividad.")
                 if es else
                 ("ACTIVITY: no motion/person events received. Known cause: 'Notify Surveillance Center' is OFF on the "
                  "recorders and no site agent is installed; no activity is invented."))
        L.append("")
    if d["after_hours"]:
        L.append("FUERA DE HORARIO:" if es else "AFTER HOURS:")
        for a in d["after_hours"][:10]:
            L.append(f"- {a['time']} · {a['cam']} · {a['kind']}")
        L.append("")
    s = d["sources"]
    L.append((f"Fuentes: {s['cloud_polls']} mediciones de nube Hik-Connect, {s['activity_events']} eventos de actividad, "
              f"{s['site_agent_events']} eventos de agente local.") if es else
             (f"Sources: {s['cloud_polls']} Hik-Connect cloud measurements, {s['activity_events']} activity events, "
              f"{s['site_agent_events']} site-agent events."))
    return "\n".join(L)


def get_report(day: str | None = None) -> dict:
    day = day or _day()
    c = _db()
    r = c.execute("SELECT data_json FROM cam_reports WHERE day=?", (day,)).fetchone()
    c.close()
    if r and day != _day():
        return json.loads(r[0])
    return build_report(day)  # today is always rebuilt live


def add_agent_events(events: list) -> int:
    """Events pushed by the site agent (ISAPI alertStream). Stored as kind=<eventType>."""
    n = 0
    for e in events:
        cameras.log_event(str(e.get("cam", "")), str(e.get("kind", "motion")).lower(), str(e.get("zona", "")),
                          float(e.get("conf", 1.0)), e.get("snapshot"), "[isapi] " + str(e.get("nota", ""))[:300])
        n += 1
    return n


# ───────────────────────────── scheduler ─────────────────────────────

def _loop():
    last_report_day = None
    while True:
        try:
            poll()
            lt = time.localtime()
            yday = _day(time.time() - 86400)
            due = (lt.tm_hour, lt.tm_min) >= (REPORT_HOUR, REPORT_MIN)
            if due and last_report_day != _day():
                build_report(yday)
                last_report_day = _day()
        except Exception:
            pass
        time.sleep(POLL_SECONDS)


def start_scheduler():
    t = threading.Thread(target=_loop, name="camera-report-scheduler", daemon=True)
    t.start()
    return t


if __name__ == "__main__":
    print(json.dumps(poll(), ensure_ascii=False))
    print(build_report()["text_es"])
