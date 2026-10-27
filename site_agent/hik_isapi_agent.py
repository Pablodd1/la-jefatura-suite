#!/usr/bin/env python3
"""
La Jefatura — Site Agent for Hikvision NVR/DVR/IPC (runs on ANY PC on the same LAN as the recorder).

Why it exists: Hik-Connect cloud only exposes health + alarms when "Notify Surveillance Center" is ON.
The recorder itself, via ISAPI, streams EVERY smart event locally. This agent reads that stream and
forwards compact JSON to La Jefatura. It never uploads video, only event metadata (+ optional snapshot).

Protocol (official Hikvision ISAPI, same one used by open-source pyHik / hikvisionapi / HA integrations):
  GET /ISAPI/Event/notification/alertStream      (multipart/mixed, HTTP Digest auth)
  GET /ISAPI/System/deviceInfo                    (identity check)
  GET /ISAPI/ContentMgmt/InputProxy/channels      (channel names on an NVR)

Usage:
  pip install requests
  python hik_isapi_agent.py --host 192.168.12.213 --user lajefatura_ai --password XXXX \
      --serial GC5348382 --server https://YOUR-TUNNEL.trycloudflare.com --token MC_TOKEN

STATUS: written to the published ISAPI spec; NOT yet run against a real recorder (this build machine
cannot reach the LAN). First run on site should use --dry-run to print events without sending.
"""
import argparse
import json
import re
import sys
import time
import xml.etree.ElementTree as ET

import requests
from requests.auth import HTTPDigestAuth

NS = re.compile(r"\{[^}]*\}")


def strip(tag):
    return NS.sub("", tag)


def parse_event(xml_text):
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return None
    d = {strip(e.tag): (e.text or "").strip() for e in root.iter()}
    if "eventType" not in d:
        return None
    return {"kind": d.get("eventType", "").lower(), "state": d.get("eventState", ""),
            "channel": d.get("channelID") or d.get("dynChannelID") or "", "time": d.get("dateTime", ""),
            "desc": d.get("eventDescription", ""), "region": d.get("regionID", "")}


def stream(args):
    auth = HTTPDigestAuth(args.user, args.password)
    base = f"http://{args.host}:{args.port}"
    r = requests.get(base + "/ISAPI/System/deviceInfo", auth=auth, timeout=10)
    r.raise_for_status()
    print("connected:", re.sub(r"\s+", " ", r.text)[:160])
    buf = ""
    with requests.get(base + "/ISAPI/Event/notification/alertStream", auth=auth, stream=True, timeout=(10, 90)) as s:
        s.raise_for_status()
        for chunk in s.iter_content(chunk_size=1024, decode_unicode=False):
            buf += chunk.decode("utf-8", errors="ignore")
            while "</EventNotificationAlert>" in buf:
                end = buf.index("</EventNotificationAlert>") + len("</EventNotificationAlert>")
                start = buf.rfind("<EventNotificationAlert", 0, end)
                xml_text, buf = buf[start:end], buf[end:]
                ev = parse_event(xml_text)
                # "videoloss/ VMD heartbeat" noise: keep only active state changes
                if ev and ev["kind"] != "videoloss" or (ev and ev["state"] == "active"):
                    yield ev


def push(args, ev):
    payload = {"events": [{"cam": f"{args.serial}-CH{int(ev['channel'] or 0):02d}", "kind": ev["kind"],
                           "zona": ev["desc"] or ev["kind"], "conf": 1.0,
                           "nota": f"{ev['state']} {ev['time']} region={ev['region']}"}]}
    if args.dry_run:
        print("DRY", json.dumps(payload, ensure_ascii=False))
        return
    requests.post(args.server.rstrip("/") + "/api/cameras/events", json=payload,
                  headers={"X-MC-Token": args.token}, timeout=15)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--host", required=True)
    p.add_argument("--port", type=int, default=80)
    p.add_argument("--user", required=True)
    p.add_argument("--password", required=True)
    p.add_argument("--serial", required=True)
    p.add_argument("--server", default="http://127.0.0.1:8931")
    p.add_argument("--token", default="")
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args()
    while True:
        try:
            for ev in stream(a):
                if ev["state"] in ("active", ""):
                    push(a, ev)
        except KeyboardInterrupt:
            sys.exit(0)
        except Exception as e:
            print("stream error, retry in 15s:", e)
            time.sleep(15)


if __name__ == "__main__":
    main()
