# Camera reporting — research, what was copied, what is real

## Open-source references checked
| Project | Idea reused | Where in our code |
|---|---|---|
| Frigate (blakeblackshear/frigate) | Events + periodic review summaries; GenAI only *describes* what a detector already found; never detects | `camera_report.build_report` (deterministic totals) ; AI only narrates later |
| pyHik (mezz64/pyHik), hikvisionapi, HA Hikvision integrations | Hikvision ISAPI `GET /ISAPI/Event/notification/alertStream` (multipart, Digest auth) streams motion, line crossing, intrusion, tamper, video loss, HDD error | `site_agent/hik_isapi_agent.py` |
| peku33/HikVision-EventReceiver | Receive + log events in SQLite, no video analysis | `cam_events` table + `/api/cameras/events` |
| Hikvision ISAPI `/ISAPI/Smart/...`, `/ISAPI/VCA/...` | People counting / heatmap are *queried* statistics, need a camera that supports them | NOT implemented: needs model check on site (DS-7608NI / iDS-7216 depend on attached camera) |

## What is measured today (no extra hardware)
Every 5 min via Hik-Connect cloud: device online, per-channel signal, HDD capacity, WAN/LAN IP, firmware.
Derived: availability %, downtime, state changes (offline/online, signal lost/restored, IP, firmware, disk change).

## What needs one change on site
1. "Notify Surveillance Center" ON in recorder motion/AcuSense rules -> cloud alarm feed fills (`ingest_cloud_alarms`).
2. Site agent on a PC in the recorder LAN -> every smart event, with channel + time.
Until then the report says "no activity events" and why. It never invents activity.

## Known limits
* This build machine cannot reach 192.168.12.213 (ports 80/554/8000 closed from here), so the agent and RTSP snapshots are untested.
* Alarm JSON field names from Hik-Connect are parsed defensively; confirm with the first real alarm.
* Single-sample downtime is estimated as one poll interval (5 min).
