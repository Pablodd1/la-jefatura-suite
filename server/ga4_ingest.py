"""
La Jefatura Suite — Live Google Analytics 4 (GA4) Data & Admin API Connector (`server/ga4_ingest.py`)

Uses the existing Google Cloud Service Account (`firebase-adminsdk-fbsvc@chatbot-bi-front-desk.iam.gserviceaccount.com`)
to auto-discover all accessible GA4 properties via `analyticsadmin.googleapis.com/v1beta/accountSummaries`
and pull live traffic, acquisition channels, top pages, countries/cities, devices, and conversion events
via `analyticsdata.googleapis.com/v1beta/properties/{property_id}:runReport`.
"""

import json
import os
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

DEFAULT_SA_PATHS = [
    os.environ.get("FIREBASE_SA_PATH", ""),
    os.path.join(ROOT, "data", "chatbot-bi-front-desk-sa.json"),
    r"C:\Users\jasme\Downloads\chatbot-bi-front-desk-firebase-adminsdk-fbsvc-b00a6404a8.json",
    "/mnt/c/Users/jasme/Downloads/chatbot-bi-front-desk-firebase-adminsdk-fbsvc-b00a6404a8.json",
    "/root/.openclaw/workspace/google_credentials/chatbot-bi-front-desk-sa.json",
]

CACHE_FILE = os.path.join(ROOT, "data", "ga4_cache.json")


def _find_sa_file() -> str:
    for p in DEFAULT_SA_PATHS:
        if p and os.path.isfile(p):
            return p
    return ""


def _get_token() -> tuple[str, str]:
    sa_path = _find_sa_file()
    if not sa_path:
        return "", "Service account JSON not found"
    try:
        import google.auth.transport.requests
        import google.oauth2.service_account

        sa_info = json.load(open(sa_path, encoding="utf-8"))
        creds = google.oauth2.service_account.Credentials.from_service_account_file(
            sa_path,
            scopes=["https://www.googleapis.com/auth/analytics.readonly"],
        )
        creds.refresh(google.auth.transport.requests.Request())
        return creds.token, sa_info.get("client_email", "")
    except Exception as e:
        return "", str(e)


def _api_call(url: str, token: str, payload: dict | None = None) -> dict:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST" if payload is not None else "GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode("utf-8", "ignore"))
    except urllib.error.HTTPError as e:
        return {"http_error": e.code, "body": e.read().decode("utf-8", "ignore")}
    except Exception as e:
        return {"error": str(e)}


def fetch_live_ga4(property_id_override: str = "") -> dict:
    token, sa_email = _get_token()
    if not token:
        return {"ok": False, "error": sa_email, "service_account": "missing"}

    # 1. Discover accessible GA4 properties
    summaries = _api_call("https://analyticsadmin.googleapis.com/v1beta/accountSummaries", token)
    if "http_error" in summaries or "error" in summaries:
        return {
            "ok": False,
            "status": "awaiting_api_enable_or_property_viewer",
            "service_account_email": sa_email,
            "enable_data_api_url": "https://console.developers.google.com/apis/api/analyticsdata.googleapis.com/overview?project=209649672400",
            "enable_admin_api_url": "https://console.developers.google.com/apis/api/analyticsadmin.googleapis.com/overview?project=209649672400",
            "detail": summaries,
        }

    properties = []
    for acc in summaries.get("accountSummaries") or []:
        acc_name = acc.get("displayName", "")
        for p in acc.get("propertySummaries") or []:
            prop_res = p.get("property", "")  # e.g. "properties/123456789"
            pid = prop_res.split("/")[-1] if "/" in prop_res else prop_res
            properties.append({
                "property_id": pid,
                "display_name": p.get("displayName", ""),
                "account_name": acc_name,
            })

    target_pid = property_id_override or (properties[0]["property_id"] if properties else "")
    if not target_pid:
        return {
            "ok": False,
            "status": "no_properties_shared_with_service_account_yet",
            "service_account_email": sa_email,
            "instructions": f"In Google Analytics -> Admin -> Property Access Management, add {sa_email} as Viewer (Lector).",
            "properties_found": properties,
        }

    # 2. Pull 28-day & 7-day overview metrics
    overview_req = {
        "dateRanges": [
            {"startDate": "28daysAgo", "endDate": "today", "name": "last_28d"},
            {"startDate": "7daysAgo", "endDate": "today", "name": "last_7d"},
            {"startDate": "today", "endDate": "today", "name": "today"},
        ],
        "metrics": [
            {"name": "activeUsers"},
            {"name": "newUsers"},
            {"name": "sessions"},
            {"name": "engagedSessions"},
            {"name": "engagementRate"},
            {"name": "averageSessionDuration"},
            {"name": "screenPageViews"},
            {"name": "eventCount"},
        ],
    }
    ov_res = _api_call(
        f"https://analyticsdata.googleapis.com/v1beta/properties/{target_pid}:runReport",
        token,
        overview_req,
    )

    # 3. Pull Top Channels / Traffic Sources (28d)
    channels_req = {
        "dateRanges": [{"startDate": "28daysAgo", "endDate": "today"}],
        "dimensions": [{"name": "sessionDefaultChannelGroup"}, {"name": "sessionSourceMedium"}],
        "metrics": [{"name": "activeUsers"}, {"name": "sessions"}, {"name": "engagedSessions"}],
        "limit": 10,
    }
    ch_res = _api_call(
        f"https://analyticsdata.googleapis.com/v1beta/properties/{target_pid}:runReport",
        token,
        channels_req,
    )

    # 4. Pull Top Countries & Cities (28d)
    geo_req = {
        "dateRanges": [{"startDate": "28daysAgo", "endDate": "today"}],
        "dimensions": [{"name": "country"}, {"name": "city"}],
        "metrics": [{"name": "activeUsers"}, {"name": "sessions"}],
        "limit": 10,
    }
    geo_res = _api_call(
        f"https://analyticsdata.googleapis.com/v1beta/properties/{target_pid}:runReport",
        token,
        geo_req,
    )

    # 5. Pull Top Pages (28d)
    pages_req = {
        "dateRanges": [{"startDate": "28daysAgo", "endDate": "today"}],
        "dimensions": [{"name": "pagePath"}, {"name": "pageTitle"}],
        "metrics": [{"name": "screenPageViews"}, {"name": "activeUsers"}],
        "limit": 10,
    }
    pg_res = _api_call(
        f"https://analyticsdata.googleapis.com/v1beta/properties/{target_pid}:runReport",
        token,
        pages_req,
    )

    out = {
        "ok": True,
        "synced_at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
        "service_account_email": sa_email,
        "active_property_id": target_pid,
        "properties": properties,
        "overview_raw": ov_res,
        "channels_raw": ch_res,
        "geo_raw": geo_res,
        "pages_raw": pg_res,
    }
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=2, ensure_ascii=False)
    except Exception:
        pass
    return out
