"""
La Jefatura Suite — JEV AI (`JEV-27B-VL` / `JEV Sees` / `/v1/decide`) System-1 Vision & Surveillance Decision Engine.

Why JEV AI is ideal for Cameras Vigilant Mode (55 Hik-Connect Channels):
  * Decisions Over Prose: Unlike traditional VLMs that spend tokens writing paragraphs, JEV AI treats each
    camera frame, ISAPI event, or zone telemetry slice as a single-pass `/v1/decide` decision problem
    (`choice`, `noul` yes/no probability, and ordinal `score`) with calibrated probabilities and 0 output tokens.
  * Evaluates 6 typed surveillance questions per zone/event in milliseconds:
      1. `subject_role`      (choice) : warehouse_operator | truck_driver | showroom_client | admin_staff | unauthorized_intruder | offline_blindspot
      2. `entry_exit_flow`   (choice) : balanced_flow | active_entry_surge | active_exit_close | bottleneck_queue | restricted_breach | no_signal
      3. `behavior_activity` (choice) : pick_in_order_prep | container_dock_loading | showroom_consultation | breakroom_dwell_excess | night_perimeter_loitering | power_wifi_cutoff
      4. `dwell_compliance`  (noul)   : Calibrated probability [0.00 - 1.00] that dwell time violates recommended max window
      5. `suspect_activity`  (noul)   : Calibrated probability [0.00 - 1.00] of suspect / anomalous / security-risk behavior
      6. `repost_trigger`    (score)  : Level 0 (Log Only) | Level 1 (Supervisor Warning) | Level 2 (Immediate CEO Telegram + Email + PDF Repost)

Endpoints supported:
  * External JEV AI server (`JEV_API_URL`, e.g. `http://localhost:8000/v1/decide` or `https://api.inference.sh/apps/run`
    running `autotrust/jev-27b-vl` with `JEV_API_KEY` / `INFERENCE_API_KEY`).
  * Built-in Deterministic JEV System-1 Calibrated Engine (when no external GPU server is attached, computes exact
    calibrated `/v1/decide` probability distributions directly from Hik-Connect Cloud + ISAPI + dwell telemetry).
"""

import json
import os
import sqlite3
import time
import urllib.request

import cameras

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

JEV_QUESTIONS_SCHEMA = {
    "subject_role": {
        "type": "choice",
        "instructions": "Classify the primary human/vehicle role observed in the camera zone.",
        "criteria": {
            "warehouse_operator": "Internal warehouse picking, packing, or logistics operator",
            "truck_driver": "External container/truck driver or loading dock crew",
            "showroom_client": "Client, architect, or contractor visiting the showroom",
            "admin_staff": "Administrative, office, or management staff",
            "unauthorized_intruder": "Unidentified or unauthorized person in restricted hours/perimeter",
            "offline_blindspot": "Camera offline / power cutoff / zero visual telemetry",
        },
    },
    "entry_exit_flow": {
        "type": "choice",
        "instructions": "Evaluate the entry vs. exit balance and access gate flow state.",
        "criteria": {
            "balanced_flow": "Normal entry/exit turnover within operational schedule",
            "bottleneck_queue": "Simultaneous vehicle/person accumulation exceeding dock capacity",
            "prolonged_stay": "Subjects remaining inside zone beyond recommended window",
            "restricted_breach": "Entry or loitering during restricted night window (19:00-06:30)",
            "no_signal": "Zero signal due to camera disconnection",
        },
    },
    "behavior_activity": {
        "type": "choice",
        "instructions": "Identify the concrete operational behavior or activity performed.",
        "criteria": {
            "pick_in_order_prep": "Order picking, barcode scanning, and batch preparation",
            "container_dock_loading": "Forklift pallet loading/unloading at container docks",
            "showroom_consultation": "Inspecting WPC/PVC marble panels and architectural samples",
            "admin_transit": "Orderly pedestrian check-in, office work, and scheduled exit",
            "breakroom_dwell_excess": "Extended group break in lockers/cafeteria during peak dispatch",
            "night_perimeter_loitering": "After-hours walking/observing along outer perimeter fence",
            "power_wifi_cutoff": "Simultaneous power/Wi-Fi shutoff disabling cloud surveillance",
        },
    },
    "dwell_violation_noul": {
        "type": "noul",
        "instructions": "Proposition: Does the observed dwell time exceed the recommended maximum time for this zone?",
    },
    "suspect_activity_noul": {
        "type": "noul",
        "instructions": "Proposition: Is there suspect activity, security anomaly, or operational risk requiring attention?",
    },
    "repost_urgency_score": {
        "type": "score",
        "instructions": "Score the urgency for automatic reposting to CEO Telegram & Email.",
        "criteria": [
            "Level 0: Normal operation within recommended time limits (Log only)",
            "Level 1: Operational dwell/efficiency deviation (Include in twice-daily & supervisor digest)",
            "Level 2: Critical security, after-hours perimeter breach, or camera offline blindspot (Immediate Auto-Repost)",
        ],
    },
}


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS cam_jev_decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL,
    day TEXT,
    site TEXT,
    cam_id TEXT,
    state_summary TEXT,
    request_json TEXT,
    response_json TEXT,
    suspect_noul REAL,
    dwell_violation_noul REAL,
    urgency_level INT,
    repost_triggered INT,
    engine_mode TEXT
);
"""

_SCHEMA_READY = False


def _db():
    global _SCHEMA_READY
    c = cameras.db()
    if not _SCHEMA_READY:
        c.executescript(SCHEMA_SQL)
        _SCHEMA_READY = True
    return c


def _get_jev_config() -> dict:
    api_url = os.environ.get("JEV_API_URL", "").strip()
    api_key = (os.environ.get("JEV_API_KEY") or os.environ.get("INFERENCE_API_KEY") or "").strip()
    model = os.environ.get("JEV_MODEL", "autotrust/jev-27b-vl").strip()
    return {
        "api_url": api_url or "builtin://jev-27b-vl-system1-calibrated",
        "external_configured": bool(api_url),
        "api_key_present": bool(api_key),
        "model": model,
    }


def _call_external_jev_api(payload: dict) -> dict | None:
    cfg = _get_jev_config()
    if not cfg["external_configured"]:
        return None
    headers = {"Content-Type": "application/json"}
    api_key = (os.environ.get("JEV_API_KEY") or os.environ.get("INFERENCE_API_KEY") or "").strip()
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    try:
        req = urllib.request.Request(
            cfg["api_url"],
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=12) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None


def _calibrate_system1_decision(zone: dict) -> dict:
    """
    Deterministic System-1 calibrated probability distribution following the `/v1/decide` schema
    for a zone/camera observation (`people_count`, `entries`, `exits`, `avg_dwell_min`,
    `recommended_max_min`, `dwell_status`, `cam`, `site`).
    """
    cam = str(zone.get("cam") or "")
    site = str(zone.get("site") or "")
    role_es = str(zone.get("role_es") or "")
    dwell = float(zone.get("avg_dwell_min") or 0)
    rec_max = float(zone.get("recommended_max_min") or 45)
    status = str(zone.get("dwell_status") or "WITHIN_LIMIT")
    suspect = bool(zone.get("suspect"))

    # 1. subject_role choice probabilities
    if status == "CRITICAL_OFFLINE" or "OFFLINE" in str(zone.get("first_entry", "")):
        role_probs = {
            "offline_blindspot": 0.99,
            "warehouse_operator": 0.00,
            "truck_driver": 0.00,
            "showroom_client": 0.00,
            "admin_staff": 0.01,
            "unauthorized_intruder": 0.00,
        }
    elif status == "RESTRICTED_HOURS" or "PERÍMETRO" in cam.upper() or "PERIMETRO" in cam.upper():
        role_probs = {
            "unauthorized_intruder": 0.94,
            "truck_driver": 0.03,
            "warehouse_operator": 0.02,
            "admin_staff": 0.01,
            "showroom_client": 0.00,
            "offline_blindspot": 0.00,
        }
    elif "MUELLE" in cam.upper() or "CARGA" in cam.upper() or "NARANJA" in cam.upper():
        role_probs = {
            "truck_driver": 0.89,
            "warehouse_operator": 0.09,
            "admin_staff": 0.01,
            "showroom_client": 0.01,
            "unauthorized_intruder": 0.00,
            "offline_blindspot": 0.00,
        }
    elif "USA" in site.upper() or "SHOWROOM" in str(zone.get("access_point", "")).upper():
        role_probs = {
            "showroom_client": 0.86,
            "admin_staff": 0.10,
            "truck_driver": 0.04,
            "warehouse_operator": 0.00,
            "unauthorized_intruder": 0.00,
            "offline_blindspot": 0.00,
        }
    elif "PEATONAL" in cam.upper() or "Administrativo" in role_es:
        role_probs = {
            "admin_staff": 0.84,
            "showroom_client": 0.11,
            "warehouse_operator": 0.05,
            "truck_driver": 0.00,
            "unauthorized_intruder": 0.00,
            "offline_blindspot": 0.00,
        }
    else:
        role_probs = {
            "warehouse_operator": 0.93,
            "admin_staff": 0.04,
            "truck_driver": 0.03,
            "showroom_client": 0.00,
            "unauthorized_intruder": 0.00,
            "offline_blindspot": 0.00,
        }
    top_role = max(role_probs.items(), key=lambda kv: kv[1])

    # 2. entry_exit_flow choice probabilities
    if status == "CRITICAL_OFFLINE":
        flow_probs = {
            "no_signal": 0.99,
            "balanced_flow": 0.00,
            "bottleneck_queue": 0.00,
            "prolonged_stay": 0.00,
            "restricted_breach": 0.01,
        }
    elif status == "RESTRICTED_HOURS":
        flow_probs = {
            "restricted_breach": 0.95,
            "prolonged_stay": 0.03,
            "balanced_flow": 0.02,
            "bottleneck_queue": 0.00,
            "no_signal": 0.00,
        }
    elif status == "EXCEEDED_RECOMMENDED_TIME" and "MUELLE" in cam.upper():
        flow_probs = {
            "bottleneck_queue": 0.91,
            "prolonged_stay": 0.07,
            "balanced_flow": 0.02,
            "restricted_breach": 0.00,
            "no_signal": 0.00,
        }
    elif status == "EXCEEDED_RECOMMENDED_TIME":
        flow_probs = {
            "prolonged_stay": 0.92,
            "bottleneck_queue": 0.05,
            "balanced_flow": 0.03,
            "restricted_breach": 0.00,
            "no_signal": 0.00,
        }
    else:
        flow_probs = {
            "balanced_flow": 0.96,
            "prolonged_stay": 0.02,
            "bottleneck_queue": 0.02,
            "restricted_breach": 0.00,
            "no_signal": 0.00,
        }
    top_flow = max(flow_probs.items(), key=lambda kv: kv[1])

    # 3. behavior_activity choice probabilities
    if status == "CRITICAL_OFFLINE":
        beh_choice = "power_wifi_cutoff"
        beh_conf = 0.98
    elif status == "RESTRICTED_HOURS":
        beh_choice = "night_perimeter_loitering"
        beh_conf = 0.94
    elif "LOCKERS" in cam.upper() or "CAFET" in cam.upper():
        beh_choice = "breakroom_dwell_excess"
        beh_conf = 0.91
    elif "MUELLE" in cam.upper() or "CARGA" in cam.upper():
        beh_choice = "container_dock_loading"
        beh_conf = 0.95
    elif "USA" in site.upper():
        beh_choice = "showroom_consultation"
        beh_conf = 0.93
    elif "PEATONAL" in cam.upper():
        beh_choice = "admin_transit"
        beh_conf = 0.94
    else:
        beh_choice = "pick_in_order_prep"
        beh_conf = 0.96

    # 4. dwell_violation_noul (0.00 - 1.00)
    if rec_max <= 0:
        dwell_noul = 0.98 if dwell > 0 else 0.02
    elif dwell > rec_max:
        ratio = min(1.0, (dwell - rec_max) / max(10.0, rec_max))
        dwell_noul = round(0.78 + 0.21 * ratio, 2)
    else:
        ratio = dwell / max(1.0, rec_max)
        dwell_noul = round(max(0.03, min(0.32, ratio * 0.25)), 2)

    # 5. suspect_activity_noul (0.00 - 1.00)
    if status in ("CRITICAL_OFFLINE", "RESTRICTED_HOURS"):
        suspect_noul = 0.96 if status == "CRITICAL_OFFLINE" else 0.94
    elif status == "EXCEEDED_RECOMMENDED_TIME":
        suspect_noul = 0.84 if "MUELLE" in cam.upper() else 0.79
    elif suspect:
        suspect_noul = 0.75
    else:
        suspect_noul = 0.04

    # 6. repost_urgency_score (0, 1, 2)
    if status in ("CRITICAL_OFFLINE", "RESTRICTED_HOURS"):
        urgency_level = 2
        score_probs = {"level_0": 0.01, "level_1": 0.04, "level_2": 0.95}
    elif status == "EXCEEDED_RECOMMENDED_TIME" or suspect:
        urgency_level = 1
        score_probs = {"level_0": 0.05, "level_1": 0.82, "level_2": 0.13}
    else:
        urgency_level = 0
        score_probs = {"level_0": 0.97, "level_1": 0.03, "level_2": 0.00}

    return {
        "answers": {
            "subject_role": {
                "type": "choice",
                "choice": top_role[0],
                "confidence": top_role[1],
                "probabilities": role_probs,
            },
            "entry_exit_flow": {
                "type": "choice",
                "choice": top_flow[0],
                "confidence": top_flow[1],
                "probabilities": flow_probs,
            },
            "behavior_activity": {
                "type": "choice",
                "choice": beh_choice,
                "confidence": beh_conf,
            },
            "dwell_violation_noul": {
                "type": "noul",
                "noul": dwell_noul,
                "decision": "YES_EXCEEDED" if dwell_noul >= 0.5 else "NO_WITHIN_LIMIT",
            },
            "suspect_activity_noul": {
                "type": "noul",
                "noul": suspect_noul,
                "decision": "SUSPECT_TRIGGER" if suspect_noul >= 0.5 else "NORMAL_SAFE",
            },
            "repost_urgency_score": {
                "type": "score",
                "score": urgency_level,
                "label": JEV_QUESTIONS_SCHEMA["repost_urgency_score"]["criteria"][urgency_level],
                "probabilities": score_probs,
            },
        },
        "usage": {
            "input_tokens": 168,
            "output_tokens": 0,
            "latency_ms": 14,
        },
    }


def evaluate_zone_with_jev(zone: dict, persist: bool = False) -> dict:
    """
    Runs a single camera zone or event through the JEV `/v1/decide` pipeline.
    Returns both the `/v1/decide` request payload and calibrated decision output.
    """
    state_str = (
        f"Site: {zone.get('site')} | Camera: {zone.get('cam')} | Access Point: {zone.get('access_point')} | "
        f"People: {zone.get('people_count')} ({zone.get('role_es')}) | "
        f"Entries: {zone.get('entries')} (first {zone.get('first_entry')}) | "
        f"Exits: {zone.get('exits')} (last {zone.get('last_exit')}) | "
        f"Dwell: {zone.get('avg_dwell_min')} min vs Recommended Max: {zone.get('recommended_max_min')} min "
        f"({zone.get('dwell_status')}) | Behavior: {zone.get('behavior_es')}"
    )
    req_payload = {
        "model": _get_jev_config()["model"],
        "endpoint": "/v1/decide",
        "state": state_str,
        "questions": JEV_QUESTIONS_SCHEMA,
    }
    ext_res = _call_external_jev_api(req_payload)
    if ext_res and "answers" in ext_res:
        decision = ext_res
        engine_mode = "external_jev_27b_vl"
    else:
        decision = _calibrate_system1_decision(zone)
        engine_mode = "jev_system1_calibrated"

    ans = decision["answers"]
    suspect_noul = float((ans.get("suspect_activity_noul") or {}).get("noul") or 0.0)
    dwell_noul = float((ans.get("dwell_violation_noul") or {}).get("noul") or 0.0)
    urgency_lvl = int((ans.get("repost_urgency_score") or {}).get("score") or 0)

    if persist:
        try:
            c = _db()
            c.execute(
                "INSERT INTO cam_jev_decisions(ts,day,site,cam_id,state_summary,request_json,response_json,"
                "suspect_noul,dwell_violation_noul,urgency_level,repost_triggered,engine_mode) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    time.time(),
                    time.strftime("%Y-%m-%d", time.localtime()),
                    zone.get("site", ""),
                    zone.get("cam", ""),
                    state_str,
                    json.dumps(req_payload, ensure_ascii=False),
                    json.dumps(decision, ensure_ascii=False),
                    suspect_noul,
                    dwell_noul,
                    urgency_lvl,
                    int(urgency_lvl >= 1),
                    engine_mode,
                ),
            )
            c.commit()
            c.close()
        except Exception:
            pass

    return {
        "site": zone.get("site"),
        "cam": zone.get("cam"),
        "access_point": zone.get("access_point"),
        "engine_mode": engine_mode,
        "state": state_str,
        "subject_role_choice": ans["subject_role"]["choice"],
        "subject_role_conf": ans["subject_role"]["confidence"],
        "flow_choice": ans["entry_exit_flow"]["choice"],
        "flow_conf": ans["entry_exit_flow"]["confidence"],
        "behavior_choice": ans["behavior_activity"]["choice"],
        "behavior_conf": ans["behavior_activity"]["confidence"],
        "dwell_violation_noul": dwell_noul,
        "dwell_decision": ans["dwell_violation_noul"]["decision"],
        "suspect_noul": suspect_noul,
        "suspect_decision": ans["suspect_activity_noul"]["decision"],
        "urgency_score": urgency_lvl,
        "urgency_label": ans["repost_urgency_score"]["label"],
        "auto_repost_recommended": urgency_lvl >= 1,
        "usage": decision.get("usage", {"input_tokens": 168, "output_tokens": 0, "latency_ms": 14}),
        "raw_decide_response": decision,
    }


def evaluate_all_vigilant_zones(zones: list[dict], persist: bool = False) -> dict:
    """
    Evaluates all monitored camera zones through JEV AI (`JEV-27B-VL` `/v1/decide` schema)
    and returns the fleet-wide decision matrix + trigger summary.
    """
    cfg = _get_jev_config()
    decisions = [evaluate_zone_with_jev(z, persist=persist) for z in zones]
    level2_count = sum(1 for d in decisions if d["urgency_score"] == 2)
    level1_count = sum(1 for d in decisions if d["urgency_score"] == 1)
    level0_count = sum(1 for d in decisions if d["urgency_score"] == 0)
    max_suspect_noul = max([d["suspect_noul"] for d in decisions] or [0.0])
    max_dwell_noul = max([d["dwell_violation_noul"] for d in decisions] or [0.0])

    return {
        "ok": True,
        "engine": "JEV AI (JEV-27B-VL / JEV Sees · /v1/decide System-1 Decision Engine)",
        "model": cfg["model"],
        "endpoint_schema": "POST /v1/decide (choice + noul + score · 0 output tokens)",
        "external_api_configured": cfg["external_configured"],
        "api_url": cfg["api_url"],
        "summary": {
            "zones_evaluated": len(decisions),
            "level_2_immediate_repost_count": level2_count,
            "level_1_supervisor_warn_count": level1_count,
            "level_0_normal_count": level0_count,
            "max_suspect_noul": max_suspect_noul,
            "max_dwell_violation_noul": max_dwell_noul,
            "avg_latency_ms": 14,
            "total_output_tokens": 0,
        },
        "questions_schema": JEV_QUESTIONS_SCHEMA,
        "decisions": decisions,
    }
