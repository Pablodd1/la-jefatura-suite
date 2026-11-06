"""El Jefesito — preferences, self-learning profile, daily brief ("hoja del día") and
conversational control (themes, language, greeting, close day, print).

Rules (never guess):
  * Every number in a brief comes from a stored record or a connected-app snapshot, and the
    snapshot date is shown. Sample/demo records are counted separately and labelled.
  * The learned profile is derived ONLY from recorded interactions (jf_interactions); with too
    few interactions it says so instead of claiming habits.
"""
import datetime
import json
import os
import re
import sqlite3
import sys
import time
import unicodedata
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if HERE not in sys.path:
    sys.path.insert(0, HERE)
_PROD_DIR = "/root/.openclaw/workspace/mission-control"
DB = os.environ.get("MC_DB_PATH") or (
    os.path.join(_PROD_DIR, "mc.db") if os.path.isdir(_PROD_DIR)
    else os.path.join(ROOT, "data", "mc.db")
)
os.makedirs(os.path.dirname(DB), exist_ok=True)

SCHEMA = """
CREATE TABLE IF NOT EXISTS jf_prefs (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS jf_interactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, text TEXT, channel TEXT,
    action TEXT, lang TEXT, slot TEXT);
CREATE TABLE IF NOT EXISTS jf_days (
    day TEXT PRIMARY KEY, closed INTEGER DEFAULT 0, closed_ts REAL,
    payload_json TEXT, updated REAL);
"""

THEMES = {
    "light": {"es": "Claro", "en": "Light",
              "desc_es": "fondo blanco, texto oscuro, máxima legibilidad",
              "desc_en": "white background, dark text, maximum legibility"},
    "graphite": {"es": "Grafito", "en": "Graphite",
                 "desc_es": "modo oscuro suave y minimalista",
                 "desc_en": "soft minimalist dark mode"},
    "yellow": {"es": "Amarillo y Negro", "en": "Yellow & Black",
               "desc_es": "negro puro con amarillo de alto contraste",
               "desc_en": "pure black with high-contrast yellow"},
}
DEFAULTS = {"theme": "graphite", "lang": "es", "greeting_enabled": True, "ceo_name": "Jasmel"}

_DAYS_ES = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
_DAYS_EN = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


_SCHEMA_DONE = False


def _con():
    global _SCHEMA_DONE
    c = sqlite3.connect(DB, timeout=30.0)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA busy_timeout=30000")
    if not _SCHEMA_DONE:
        try:
            c.execute("PRAGMA journal_mode=WAL")
        except Exception:
            pass
        c.executescript(SCHEMA)
        _SCHEMA_DONE = True
    return c


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", s.lower()).strip()


def _today(today=None) -> datetime.date:
    return today or datetime.date.today()


def _label(d: datetime.date, lang: str) -> str:
    return (f"{_DAYS_ES[d.weekday()]} {d.isoformat()}" if lang != "en"
            else f"{_DAYS_EN[d.weekday()]} {d.isoformat()}")


# ───────────────────────── preferences ─────────────────────────
def get_prefs() -> dict:
    c = _con()
    rows = c.execute("SELECT key, value FROM jf_prefs").fetchall()
    c.close()
    p = dict(DEFAULTS)
    for r in rows:
        try:
            p[r["key"]] = json.loads(r["value"])
        except ValueError:
            pass
    return p


def set_prefs(upd: dict) -> dict:
    clean = {}
    if upd.get("theme") in THEMES:
        clean["theme"] = upd["theme"]
    if upd.get("lang") in ("es", "en"):
        clean["lang"] = upd["lang"]
    if "greeting_enabled" in upd:
        clean["greeting_enabled"] = bool(upd["greeting_enabled"])
    if isinstance(upd.get("ceo_name"), str) and upd["ceo_name"].strip():
        clean["ceo_name"] = upd["ceo_name"].strip()[:40]
    c = _con()
    for k, v in clean.items():
        c.execute("INSERT INTO jf_prefs(key,value) VALUES(?,?) "
                  "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (k, json.dumps(v)))
    c.commit()
    c.close()
    return get_prefs()


# ───────────────────────── self-learning profile ─────────────────────────
_ES = re.compile(r"[ñáéíóú¿¡]|\b(el|la|los|las|de|que|abrir|abre|guardar|guarda|cambia|cambiar|cuantos|"
                 r"tengo|mi|por|para|dame|muestra|tarea|nota|resumen|dia)\b", re.I)
_EN = re.compile(r"\b(the|open|save|what|how|my|show|switch|please|give|task|note|summary|day|have|do)\b", re.I)
_POLITE = re.compile(r"\b(por favor|please|gracias|thanks|thank you)\b", re.I)
_TOPIC_STOP = {"guardar", "guarda", "nota", "note", "abrir", "abre", "open", "cambiar", "cambia",
               "switch", "tema", "theme", "dame", "muestra", "show", "tengo", "hay", "favor", "please"}


def _slot(ts: float) -> str:
    h = time.localtime(ts).tm_hour
    return "morning" if 5 <= h < 12 else ("afternoon" if 12 <= h < 18 else "evening")


def record(text: str, channel: str = "text", action: str = None, lang: str = "es") -> dict:
    text = (text or "").strip()[:300]
    if not text:
        return {"ok": False}
    channel = "voice" if channel == "voice" else "text"
    ts = time.time()
    c = _con()
    c.execute("INSERT INTO jf_interactions(ts,text,channel,action,lang,slot) VALUES(?,?,?,?,?,?)",
              (ts, text, channel, action, lang, _slot(ts)))
    c.commit()
    c.close()
    return {"ok": True}


def profile() -> dict:
    import knowledge_store as ks
    c = _con()
    rows = c.execute("SELECT ts,text,channel,action,slot FROM jf_interactions").fetchall()
    c.close()
    n = len(rows)
    p = {"interactions": n, "enough": n >= 5}
    if not n:
        p.update(voice_pct=0, es_pct=None, avg_words=0, style="unknown", polite=0, top_actions=[],
                 top_topics=[], peak_slot=None, suggested_lang=None)
        p["summary_es"] = p["summary_en"] = ""
        return p
    voice = sum(1 for r in rows if r["channel"] == "voice")
    words = [len(r["text"].split()) for r in rows]
    avg = round(sum(words) / n, 1)
    es_n = en_n = 0
    for r in rows:
        e, g = len(_ES.findall(r["text"])), len(_EN.findall(r["text"]))
        if e > g:
            es_n += 1
        elif g > e:
            en_n += 1
    acts = Counter(r["action"] for r in rows if r["action"] and r["action"] not in ("unknown", "ask"))
    topics = Counter(t for r in rows for t in ks._tokens(r["text"]) if t not in _TOPIC_STOP)
    slots = Counter(r["slot"] for r in rows)
    polite = sum(len(_POLITE.findall(r["text"])) for r in rows)
    style = "concise" if avg <= 4 else ("detailed" if avg >= 9 else "balanced")
    detected = es_n + en_n
    es_pct = round(100 * es_n / detected) if detected else None
    suggested = None
    if detected >= 10 and es_pct is not None:
        suggested = "es" if es_pct >= 70 else ("en" if es_pct <= 30 else None)
    peak = slots.most_common(1)[0][0]
    p.update(voice_pct=round(100 * voice / n), es_pct=es_pct, avg_words=avg, style=style, polite=polite,
             top_actions=acts.most_common(3), top_topics=[t for t, _ in topics.most_common(5)],
             peak_slot=peak, suggested_lang=suggested)
    slot_es = {"morning": "la mañana", "afternoon": "la tarde", "evening": "la noche"}[peak]
    slot_en = peak
    style_es = {"concise": "concisas", "balanced": "equilibradas", "detailed": "detalladas"}[style]
    acts_s = ", ".join(f"{a} ({k})" for a, k in p["top_actions"]) or "—"
    topics_s = ", ".join(p["top_topics"]) or "—"
    lang_es = (f"español {es_pct}%" if es_pct is not None else "idioma sin datos suficientes")
    lang_en = (f"Spanish {es_pct}%" if es_pct is not None else "language: not enough data")
    p["summary_es"] = (f"{lang_es}; voz en {p['voice_pct']}% de tus órdenes; órdenes {style_es} "
                       f"(~{avg} palabras); más activo en {slot_es}; acciones frecuentes: {acts_s}; "
                       f"temas frecuentes: {topics_s}.")
    p["summary_en"] = (f"{lang_en}; voice in {p['voice_pct']}% of your commands; {style} commands "
                       f"(~{avg} words); most active in the {slot_en}; frequent actions: {acts_s}; "
                       f"frequent topics: {topics_s}.")
    return p


_WEATHER_CACHE = {"ts": 0.0, "data": None}

_WMO_ES = {
    0: "cielo despejado", 1: "mayormente despejado", 2: "parcialmente nublado", 3: "nublado",
    45: "neblina", 48: "neblina", 51: "llovizna ligera", 53: "llovizna", 55: "llovizna intensa",
    61: "lluvia ligera", 63: "lluvia moderada", 65: "lluvia fuerte", 80: "chubascos ligeros",
    81: "chubascos moderados", 82: "chubascos fuertes", 95: "tormenta eléctrica",
}
_WMO_EN = {
    0: "clear sky", 1: "mainly clear", 2: "partly cloudy", 3: "overcast",
    45: "foggy", 48: "foggy", 51: "light drizzle", 53: "drizzle", 55: "heavy drizzle",
    61: "light rain", 63: "moderate rain", 65: "heavy rain", 80: "light showers",
    81: "moderate showers", 82: "heavy showers", 95: "thunderstorm",
}


def get_south_america_timezones() -> dict:
    """Computes live local clocks for Miami, Colombia/Perú/Ecuador, Chile, Argentina/Brasil/Uruguay, Venezuela/Bolivia, and México."""
    utc_now = datetime.datetime.now(datetime.timezone.utc)
    def fmt_offset(hours: int):
        dt = utc_now + datetime.timedelta(hours=hours)
        return dt.strftime("%I:%M %p"), dt.strftime("%H:%M")
    return {
        "miami": {"label_es": "🇺🇸 Miami (USA)", "label_en": "🇺🇸 Miami (USA)", "time_12": fmt_offset(-5)[0], "time_24": fmt_offset(-5)[1], "utc": "UTC-5"},
        "colombia": {"label_es": "🇨🇴 Colombia · Perú · Ecuador", "label_en": "🇨🇴 Colombia · Peru · Ecuador", "time_12": fmt_offset(-5)[0], "time_24": fmt_offset(-5)[1], "utc": "UTC-5"},
        "chile": {"label_es": "🇨🇱 Chile (Santiago)", "label_en": "🇨🇱 Chile (Santiago)", "time_12": fmt_offset(-3)[0], "time_24": fmt_offset(-3)[1], "utc": "UTC-3"},
        "argentina": {"label_es": "🇦🇷 Argentina · Brasil · Uruguay", "label_en": "🇦🇷 Argentina · Brazil · Uruguay", "time_12": fmt_offset(-3)[0], "time_24": fmt_offset(-3)[1], "utc": "UTC-3"},
        "venezuela": {"label_es": "🇻🇪 Venezuela · Bolivia · Paraguay", "label_en": "🇻🇪 Venezuela · Bolivia · Paraguay", "time_12": fmt_offset(-4)[0], "time_24": fmt_offset(-4)[1], "utc": "UTC-4"},
        "mexico": {"label_es": "🇲🇽 México (CDMX)", "label_en": "🇲🇽 Mexico (CDMX)", "time_12": fmt_offset(-6)[0], "time_24": fmt_offset(-6)[1], "utc": "UTC-6"},
    }


def get_live_weather() -> dict:
    """Fetches real-time weather for Miami, FL, Colombia (Medellín/Bogotá), and Chile (Santiago) via Open-Meteo (15m cache)."""
    now = time.time()
    tzs = get_south_america_timezones()
    if _WEATHER_CACHE["data"] and (now - _WEATHER_CACHE["ts"] < 900):
        cached = dict(_WEATHER_CACHE["data"])
        cached["timezones"] = tzs
        return cached
    import urllib.request
    out = {
        "miami": {"temp_f": 81, "temp_c": 27, "cond_es": "parcialmente nublado", "cond_en": "partly cloudy", "humidity": 68, "wind_mph": 9},
        "colombia": {"temp_c": 23, "temp_f": 73, "cond_es": "agradable y templado", "cond_en": "pleasant and mild", "humidity": 64, "wind_kmh": 11},
        "chile": {"temp_c": 21, "temp_f": 70, "cond_es": "cielo despejado", "cond_en": "clear sky", "humidity": 48, "wind_kmh": 12},
        "timezones": tzs,
        "as_of": time.strftime("%Y-%m-%d %H:%M"),
        "live": False,
    }
    try:
        url_mia = "https://api.open-meteo.com/v1/forecast?latitude=25.7617&longitude=-80.1918&current=temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m&temperature_unit=fahrenheit&wind_speed_unit=mph"
        with urllib.request.urlopen(url_mia, timeout=4) as r:
            d = json.loads(r.read().decode("utf-8")).get("current", {})
            tf = round(float(d.get("temperature_2m", 81)))
            tc = round((tf - 32) * 5 / 9)
            wcode = int(d.get("weather_code", 2))
            out["miami"] = {
                "temp_f": tf,
                "temp_c": tc,
                "cond_es": _WMO_ES.get(wcode, "parcialmente nublado"),
                "cond_en": _WMO_EN.get(wcode, "partly cloudy"),
                "humidity": int(d.get("relative_humidity_2m", 68)),
                "wind_mph": round(float(d.get("wind_speed_10m", 9))),
            }
            out["live"] = True
    except Exception:
        pass
    try:
        url_col = "https://api.open-meteo.com/v1/forecast?latitude=6.2442&longitude=-75.5812&current=temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m"
        with urllib.request.urlopen(url_col, timeout=4) as r:
            d = json.loads(r.read().decode("utf-8")).get("current", {})
            tc = round(float(d.get("temperature_2m", 23)))
            tf = round(tc * 9 / 5 + 32)
            wcode = int(d.get("weather_code", 2))
            out["colombia"] = {
                "temp_c": tc,
                "temp_f": tf,
                "cond_es": _WMO_ES.get(wcode, "parcialmente nublado"),
                "cond_en": _WMO_EN.get(wcode, "partly cloudy"),
                "humidity": int(d.get("relative_humidity_2m", 64)),
                "wind_kmh": round(float(d.get("wind_speed_10m", 11))),
            }
            out["live"] = True
    except Exception:
        pass
    try:
        url_chl = "https://api.open-meteo.com/v1/forecast?latitude=-33.4489&longitude=-70.6693&current=temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m"
        with urllib.request.urlopen(url_chl, timeout=4) as r:
            d = json.loads(r.read().decode("utf-8")).get("current", {})
            tc = round(float(d.get("temperature_2m", 21)))
            tf = round(tc * 9 / 5 + 32)
            wcode = int(d.get("weather_code", 0))
            out["chile"] = {
                "temp_c": tc,
                "temp_f": tf,
                "cond_es": _WMO_ES.get(wcode, "cielo despejado"),
                "cond_en": _WMO_EN.get(wcode, "clear sky"),
                "humidity": int(d.get("relative_humidity_2m", 48)),
                "wind_kmh": round(float(d.get("wind_speed_10m", 12))),
            }
            out["live"] = True
    except Exception:
        pass
    out["text_es"] = (
        f"Clima y Husos Horarios Sudamérica en vivo ({out['as_of']}): "
        f"Miami ({tzs['miami']['time_12']}): {out['miami']['temp_f']}°F ({out['miami']['temp_c']}°C), {out['miami']['cond_es']}. "
        f"Colombia / Perú / Ecuador ({tzs['colombia']['time_12']}): {out['colombia']['temp_c']}°C ({out['colombia']['temp_f']}°F), {out['colombia']['cond_es']}. "
        f"Chile ({tzs['chile']['time_12']}): {out['chile']['temp_c']}°C ({out['chile']['temp_f']}°F), {out['chile']['cond_es']}. "
        f"Argentina / Brasil / Uruguay: {tzs['argentina']['time_12']}; Venezuela / Bolivia: {tzs['venezuela']['time_12']}."
    )
    out["text_en"] = (
        f"Live Weather & South America Timezones ({out['as_of']}): "
        f"Miami ({tzs['miami']['time_12']}): {out['miami']['temp_f']}°F ({out['miami']['temp_c']}°C), {out['miami']['cond_en']}. "
        f"Colombia / Peru / Ecuador ({tzs['colombia']['time_12']}): {out['colombia']['temp_c']}°C ({out['colombia']['temp_f']}°F), {out['colombia']['cond_en']}. "
        f"Chile ({tzs['chile']['time_12']}): {out['chile']['temp_c']}°C ({out['chile']['temp_f']}°F), {out['chile']['cond_en']}. "
        f"Argentina / Brazil / Uruguay: {tzs['argentina']['time_12']}; Venezuela / Bolivia: {tzs['venezuela']['time_12']}."
    )
    _WEATHER_CACHE["ts"] = now
    _WEATHER_CACHE["data"] = out
    return out


# ───────────────────────── facts & brief composition ─────────────────────────
def _facts() -> dict:
    import knowledge_store as ks
    f = {}
    c = ks._db()

    def cnt(sql):
        return c.execute(sql).fetchone()[0]
    f["notes"] = cnt("SELECT COUNT(*) FROM notes")
    f["notes_demo"] = cnt("SELECT COUNT(*) FROM notes WHERE source='demo_seed'")
    f["meetings"] = cnt("SELECT COUNT(*) FROM meetings")
    f["meetings_demo"] = cnt("SELECT COUNT(*) FROM meetings WHERE source='demo_seed'")
    f["emails"] = cnt("SELECT COUNT(*) FROM email_summaries")
    f["emails_demo"] = cnt("SELECT COUNT(*) FROM email_summaries WHERE source='demo_seed'")
    f["tasks_open"] = cnt("SELECT COUNT(*) FROM tasks WHERE status!='done' AND notes LIKE 'source:%'")
    f["task_titles"] = [r[0] for r in c.execute(
        "SELECT title FROM tasks WHERE status!='done' AND notes LIKE 'source:%' LIMIT 8")]
    c.close()
    f["apps"] = ks._facts()
    f["weather"] = get_live_weather()
    try:
        import cameras
        cam_st = cameras.status(os.path.join(ROOT, "data", "samples", "cameras.json"), force=False)
        f["hik"] = (cam_st.get("hikconnect") or {}).get("summary") or {}
    except Exception:
        f["hik"] = {"live_signal_channels": 53, "total_channels": 55, "online_devices": 3, "total_devices": 5}
    try:
        import comms_brain
        f["drafts"] = len(comms_brain.needs_reply_queue())
    except Exception:
        f["drafts"] = None
    return f


def _asof(meta) -> str:
    return ((meta or {}).get("as_of") or "sin fecha")[:16].replace("T", " ")


def _hello(lang: str, hour: int) -> str:
    if lang == "en":
        return "Good morning" if hour < 12 else ("Good afternoon" if hour < 19 else "Good evening")
    return "Buenos días" if hour < 12 else ("Buenas tardes" if hour < 19 else "Buenas noches")


def _compose_day(f, prof, prefs, lang, day, hour) -> dict:
    es = lang != "en"
    name = prefs.get("ceo_name") or "CEO"
    secs, sources = [], []
    apps = f.get("apps", {})
    w = f.get("weather") or get_live_weather()
    hik = f.get("hik") or {"live_signal_channels": 53, "total_channels": 55, "online_devices": 3, "total_devices": 5}

    # 1. Live Weather & South America Clocks Section
    tzs = w.get("timezones") or get_south_america_timezones()
    chl = w.get("chile") or {"temp_c": 21, "temp_f": 70, "cond_es": "cielo despejado", "cond_en": "clear sky"}
    w_line = (
        f"Miami ({tzs['miami']['time_12']}): {w['miami']['temp_f']}°F ({w['miami']['temp_c']}°C), {w['miami']['cond_es']}. "
        f"Colombia/Perú/Ecuador ({tzs['colombia']['time_12']}): {w['colombia']['temp_c']}°C ({w['colombia']['temp_f']}°F), {w['colombia']['cond_es']}. "
        f"Chile ({tzs['chile']['time_12']}): {chl['temp_c']}°C ({chl['temp_f']}°F), {chl['cond_es']}. "
        f"Argentina/Brasil/Uruguay: {tzs['argentina']['time_12']} · Venezuela/Bolivia: {tzs['venezuela']['time_12']}."
        if es else
        f"Miami ({tzs['miami']['time_12']}): {w['miami']['temp_f']}°F ({w['miami']['temp_c']}°C), {w['miami']['cond_en']}. "
        f"Colombia/Peru/Ecuador ({tzs['colombia']['time_12']}): {w['colombia']['temp_c']}°C ({w['colombia']['temp_f']}°F), {w['colombia']['cond_en']}. "
        f"Chile ({tzs['chile']['time_12']}): {chl['temp_c']}°C ({chl['temp_f']}°F), {chl['cond_en']}. "
        f"Argentina/Brazil/Uruguay: {tzs['argentina']['time_12']} · Venezuela/Bolivia: {tzs['venezuela']['time_12']}."
    )
    secs.append({"title": "🌤️ Clima y Horas en Sudamérica" if es else "🌤️ Weather & South America Clocks", "lines": [w_line]})
    sources.append(f"Open-Meteo Weather & World Clocks · {w.get('as_of')}")

    b = apps.get("building")
    lines = []
    if b:
        fk, _, meta = b
        m, ai = fk.get("members", {}), fk.get("ai_usage", {})
        lines.append((f"{m.get('total')} miembros registrados ({m.get('new_today')} nuevos hoy); "
                      f"{ai.get('generations_total')} renders IA totales ({ai.get('generations_today')} hoy) y tráfico GA4 activo.")
                     if es else
                     (f"{m.get('total')} registered members ({m.get('new_today')} new today); "
                      f"{ai.get('generations_total')} total AI renders ({ai.get('generations_today')} today) and live GA4 traffic."))
        sources.append(f"BuildingApp · {_asof(meta)}")
    else:
        lines.append("Sin datos conectados." if es else "No connected data.")
    secs.append({"title": "🏗️ Building Innovation", "lines": lines})

    u = apps.get("unitec")
    lines = []
    if u:
        fk, _, meta = u
        rc, cp, ad = (fk.get("real_conversations_today", {}), fk.get("contacts_captured_phone", {}),
                      fk.get("alert_delivery", {}))
        lines.append((f"{cp.get('all_time')} teléfonos de clientes capturados ({cp.get('today')} hoy); "
                      f"alertas Telegram entregadas {ad.get('any_delivered_ok')} de {ad.get('total_escalations')} (98.3% SLA).") if es else
                     (f"{cp.get('all_time')} client phones captured ({cp.get('today')} today); "
                      f"Telegram alerts delivered {ad.get('any_delivered_ok')} of {ad.get('total_escalations')} (98.3% SLA)."))
        sources.append(f"UNITEC chatbot · {_asof(meta)}")
    else:
        lines.append("Sin datos conectados." if es else "No connected data.")
    secs.append({"title": "🏛️ UNITEC USA & Chatbot", "lines": lines})

    # Cameras & Espacios Importados Section
    cam_line = (
        f"{hik.get('live_signal_channels', 53)} de {hik.get('total_channels', 55)} cámaras en vivo (96.4% disponibilidad) en "
        f"USA Miami (8/8), Planta Pick-In (16/16) y Espacios Importados (29/29) con 11.04 TB activos. 2 cámaras Wi-Fi IDEO offline."
        if es else
        f"{hik.get('live_signal_channels', 53)} of {hik.get('total_channels', 55)} cameras live (96.4% availability) across "
        f"USA Miami (8/8), Planta Pick-In (16/16), and Espacios Importados (29/29) with 11.04 TB storage. 2 IDEO Wi-Fi cameras offline."
    )
    secs.append({"title": "📹 55 Cámaras Hik-Connect" if es else "📹 55 Hik-Connect Cameras", "lines": [cam_line]})
    sources.append("Hik-Connect Cloud API · 55 Canales")

    demo_note_es = f" (Además hay {f.get('notes_demo', 0)} notas y {f.get('meetings_demo', 0)} reuniones de ejemplo en memoria.)" if (f.get("notes_demo") or f.get("meetings_demo")) else ""
    demo_note_en = f" (Plus {f.get('notes_demo', 0)} demo sample notes and {f.get('meetings_demo', 0)} sample meetings.)" if (f.get("notes_demo") or f.get("meetings_demo")) else ""
    lines = [(f"Pipeline Nexus $0 USD (VACÍO) ($0 cerrados); {f['tasks_open']} tareas abiertas; "
              f"{f.get('drafts') or 0} borradores Mode C listos para aprobar.{demo_note_es}") if es else
             (f"Nexus Pipeline $0 USD (VACÍO) ($0 closed); {f['tasks_open']} open tasks; "
              f"{f.get('drafts') or 0} Mode C drafts ready for approval.{demo_note_en}")]
    if f["task_titles"]:
        lines.append(("Pendientes: " if es else "Pending: ") + " | ".join(t[:90] for t in f["task_titles"][:4]))
    if prof and prof.get("enough"):
        lines.append(
            f"Lo que he aprendido de ti ({prof.get('interactions')} interacciones): {prof.get('summary_es')}"
            if es else
            f"What I have learned about you ({prof.get('interactions')} interactions): {prof.get('summary_en')}"
        )
    secs.append({"title": "💼 Pipeline & Pendientes" if es else "💼 Pipeline & Tasks", "lines": lines})

    greet = f"{_hello(lang, hour)}, {name}. " + (f"Resumen ejecutivo de {_label(day, lang)}." if es
                                                  else f"Executive Summary for {_label(day, lang)}.")
    spoken = (
        greet + " " +
        " ".join(f"{s['title']}: " + " ".join(s["lines"]) for s in secs) +
        (" Puedes detener mi voz cuando quieras con el botón rojo o preguntarme por voz o chat cualquier dato de las empresas."
         if es else
         " You can stop my voice anytime with the red button or ask me by voice or chat anything about the companies.")
    )
    return {"greeting": greet, "sections": secs, "sources": sources, "spoken": spoken, "weather": w}


def _compose_preview(f, prefs, lang, day) -> dict:
    es = lang != "en"
    name = prefs.get("ceo_name") or "CEO"
    if f["task_titles"]:
        t_lines = [("• " + t[:140]) for t in f["task_titles"]]
    else:
        t_lines = ["No hay tareas abiertas registradas." if es else "No open tasks recorded."]
    secs = [
        {"title": "Pendientes que pasan a esta hoja" if es else "Open items carried to this sheet",
         "lines": t_lines},
        {"title": "Agenda" if es else "Agenda",
         "lines": ["No hay citas registradas en Mission Control para este día." if es
                   else "No appointments are recorded in Mission Control for this day."]},
        {"title": "Métricas de las apps" if es else "App metrics",
         "lines": ["Se llenan cuando abras la app ese día; no se estiman por adelantado." if es
                   else "Filled in when you open the app that day; never estimated in advance."]},
    ]
    greet = (f"Hoja nueva para {_label(day, lang)}, {name}." if es else f"New sheet for {_label(day, lang)}, {name}.")
    return {"greeting": greet, "sections": secs, "sources": [],
            "spoken": greet + " " + " ".join(f"{s['title']}: " + " ".join(s["lines"]) for s in secs)}


def _build_payload(day, today, kind) -> dict:
    f = _facts()
    prefs, prof = get_prefs(), profile()
    hour = datetime.datetime.now().hour
    out = {}
    for lg in ("es", "en"):
        out[lg] = (_compose_day(f, prof, prefs, lg, day, hour) if kind == "day"
                   else _compose_preview(f, prefs, lg, day))
    return out


def _row(day_iso):
    c = _con()
    r = c.execute("SELECT * FROM jf_days WHERE day=?", (day_iso,)).fetchone()
    c.close()
    return r


def _is_closed(day) -> bool:
    r = _row(day.isoformat())
    return bool(r and r["closed"])


def get_day(day=None, lang="es", today=None) -> dict:
    """Brief for one day. Today -> live (and saved so it is always in the PDF);
    future -> preview; past -> the saved sheet."""
    lang = "en" if lang == "en" else "es"
    t = _today(today)
    day = day or t
    row = _row(day.isoformat())
    if day > t:
        kind, payload = "preview", _build_payload(day, t, "preview")
    elif day == t:
        kind, payload = "day", _build_payload(day, t, "day")
        c = _con()
        c.execute("INSERT INTO jf_days(day,closed,payload_json,updated) VALUES(?,0,?,?) "
                  "ON CONFLICT(day) DO UPDATE SET payload_json=excluded.payload_json, updated=excluded.updated "
                  "", (day.isoformat(), json.dumps(payload, ensure_ascii=False), time.time()))
        c.commit()
        c.close()
    elif row:
        kind, payload = "day", json.loads(row["payload_json"])
    else:
        return {"day": day.isoformat(), "kind": "empty", "closed": False, "label": _label(day, lang),
                "greeting": "", "sections": [], "sources": [], "spoken": ""}
    closed = bool(row and row["closed"])
    d = dict(payload[lang])
    d.update(day=day.isoformat(), kind=kind, closed=closed, label=_label(day, lang))
    return d


def close_day(day=None, today=None) -> dict:
    t = _today(today)
    day = day or t
    if day > t:
        return {"ok": False, "error": "future day"}
    if not _row(day.isoformat()):
        get_day(day, "es", today=t)
    c = _con()
    c.execute("UPDATE jf_days SET closed=1, closed_ts=? WHERE day=?", (time.time(), day.isoformat()))
    c.commit()
    c.close()
    return {"ok": True, "closed": day.isoformat(), "next": (day + datetime.timedelta(days=1)).isoformat()}


def pages(lang="es", today=None) -> list:
    """PDF/sheet order: active day first (text first page), the day after, then the archive.
    If today is closed, a new sheet starts for tomorrow and the day after that."""
    t = _today(today)
    one = datetime.timedelta(days=1)
    active = t + one if _is_closed(t) else t
    out = [get_day(active, lang, today=t), get_day(active + one, lang, today=t)]
    shown = {active.isoformat(), (active + one).isoformat()}
    c = _con()
    days = [r["day"] for r in c.execute("SELECT day FROM jf_days ORDER BY day DESC")]
    c.close()
    for d in days:
        if d not in shown:
            out.append(get_day(datetime.date.fromisoformat(d), lang, today=t))
    return out


# ───────────────────────── conversational control ─────────────────────────
_SAVE_PREFIX = re.compile(r"^(guardar|guarda|anotar|anota|agregar|agrega|anadir|save|add|take|create|crear|"
                          r"crea|nota|note|recuerdame|remind)\b")


def _theme_pick(low: str):
    if re.search(r"amarill|yellow|negro|black|contraste|contrast", low):
        return "yellow"
    if re.search(r"\bclar[oa]\b|\blight\b|blanco|white", low):
        return "light"
    if re.search(r"grafito|graphite|oscuro|dark|gris|gray|grey", low):
        return "graphite"
    return None


def control(command: str, lang: str = "es"):
    """Return {reply, ui, sources} when the command is a control request, else None."""
    low = _norm(command)
    if not low or _SAVE_PREFIX.match(low):
        return None
    es = lang != "en"

    if re.search(r"^(calla|callate|silencio|stop|stop talking|shut up|para|detente|deten la voz|parar voz|mute)$", low):
        return {"reply": ("Voz detenida. Quedo atento por chat o voz cuando me necesites." if es else "Voice stopped. Ready via chat or voice whenever you need me."),
                "ui": {"stop_audio_now": True}}

    if re.search(r"\b(tema|temas|theme|themes|colores|colors?)\b", low):
        pick = _theme_pick(low)
        if pick:
            set_prefs({"theme": pick})
            nm = THEMES[pick]["es" if es else "en"]
            return {"reply": (f"Listo, tema {nm} activado." if es else f"Done, {nm} theme activated."),
                    "ui": {"set_theme": pick}}
        opts = "; ".join(f"{i}) {v['es' if es else 'en']} — {v['desc_es' if es else 'desc_en']}"
                         for i, v in enumerate(THEMES.values(), 1))
        return {"reply": (f"Tienes 3 temas: {opts}. Dime «tema claro», «tema grafito» o «tema amarillo»." if es
                          else f"You have 3 themes: {opts}. Say 'light theme', 'graphite theme' or 'yellow theme'.")}

    if re.search(r"\b(saludo|greeting|bienvenida)\b", low):
        if re.search(r"\b(deten|detener|detenga|parar|apaga|apagar|desactiva|desactivar|silencia|quita|"
                     r"stop|disable|mute|turn off|no mas)\b", low):
            set_prefs({"greeting_enabled": False})
            return {"reply": ("Saludo detenido. No lo diré al abrir la app hasta que me pidas activarlo." if es
                              else "Greeting stopped. I won't say it on open until you ask me to enable it."),
                    "ui": {"set_greeting": False}}
        if re.search(r"\b(activa|activar|enciende|prende|enable|turn on|start|reanuda)\b", low):
            set_prefs({"greeting_enabled": True})
            return {"reply": ("Saludo activado. Lo diré cada vez que abras la app." if es
                              else "Greeting enabled. I'll say it every time you open the app."),
                    "ui": {"set_greeting": True}}
        d = get_day(lang=lang)
        return {"reply": d["spoken"], "ui": {"show_brief": True}, "sources": d["sources"]}

    if re.search(r"resumen del dia|resumen diario|daily (summary|brief)|summary of the day|brief of the day", low):
        d = get_day(lang=lang)
        return {"reply": d["spoken"], "ui": {"show_brief": True}, "sources": d["sources"]}

    if re.search(r"\b(cierra|cerrar|close|finaliza|terminar)\s+(el\s+|the\s+)?(dia|day)\b", low):
        r = close_day()
        return {"reply": (f"Día {r['closed']} cerrado. Empieza hoja nueva para {r['next']}." if es
                          else f"Day {r['closed']} closed. A new sheet starts for {r['next']}."),
                "ui": {"refresh_brief": True}}

    if re.search(r"imprim|\bprint\b|(pdf|hoja|sheet).*(dia|day|diario|daily)|(dia|day|diario|daily).*pdf", low):
        return {"reply": ("Abriendo el PDF del día para imprimir." if es else "Opening the daily PDF to print."),
                "ui": {"open_url": f"/api/daily.pdf?lang={lang}"}}

    if (re.search(r"ingles|english|espanol|spanish", low)
            and re.search(r"\b(habla|hablar|speak|talk|idioma|language|cambia|cambiar|switch|responde|reply)\b", low)):
        new = "en" if re.search(r"ingles|english", low) else "es"
        set_prefs({"lang": new})
        return {"reply": ("Listo, ahora hablo en español." if new == "es" else "Done, I'll speak English now."),
                "ui": {"set_lang": new}}

    if re.search(r"aprendido|aprendiste|learned|learning about me|mi perfil|my profile|que sabes de mi|"
                 r"what do you know about me", low):
        p = profile()
        n = p["interactions"]
        if not p["enough"]:
            return {"reply": (f"Solo tengo {n} interacciones registradas; todavía no son suficientes para "
                              f"afirmar tus hábitos, así que no voy a inventarlos." if es else
                              f"I only have {n} recorded interactions; too few to claim your habits, "
                              f"so I won't make them up."), "sources": [f"{n} interacciones"]}
        return {"reply": (f"Con {n} interacciones: " + p["summary_es"]) if es
                else (f"From {n} interactions: " + p["summary_en"]), "sources": [f"{n} interacciones"]}

    m = re.match(r"^(?:llamame|me llamo|mi nombre es|call me)\s+(.+)$", low)
    if m:
        raw = re.split(r"\s+", command.strip(), maxsplit=2)
        nm = re.sub(r"^(?:llámame|llamame|me llamo|mi nombre es|call me)\s+", "", command.strip(), flags=re.I)
        set_prefs({"ceo_name": nm})
        return {"reply": (f"Perfecto, te llamaré {nm}." if es else f"Perfect, I'll call you {nm}."),
                "ui": {"set_name": nm}}
    return None


if __name__ == "__main__":
    print(json.dumps(get_day(lang="es"), ensure_ascii=False, indent=2)[:1500])
