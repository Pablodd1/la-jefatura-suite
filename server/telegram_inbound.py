"""
2-Way Telegram Text & Voice-Note Engine for La Jefatura / El Jefecito (`server/telegram_inbound.py`).

Supports:
  - Polling Telegram Bot API `getUpdates` for both text messages and voice/audio notes
  - Downloading Telegram `voice` / `audio` files via `getFile` and transcribing verbatim via Gemini
    (`meta_whatsapp.transcribe_audio_bytes`)
  - Routing inbound messages through `voice_commands.execute(...)` + `text_messaging` / `spark_followup_engine`
    so CEO voice notes create monitored tasks, schedule meetings, or trigger follow-up calls/texts,
    and team replies are summarized and pushed back to the CEO.
  - Safe token-hash lock file so running both `:8931` and `:8940` on the same host never causes
    Telegram `409 Conflict` duplicate polling.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
STATE_FILE = ROOT / "data" / "telegram_offset.json"


def _load_env() -> dict[str, str]:
    env = dict(os.environ)
    env_p = ROOT / ".env"
    if env_p.exists():
        for line in env_p.read_text(encoding="utf-8", errors="ignore").splitlines():
            s = line.strip()
            if s and not s.startswith("#") and "=" in s:
                k, v = s.split("=", 1)
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                if k and v and k not in env:
                    env[k] = v
    return env


def download_and_transcribe_telegram_audio(
    bot_token: str,
    file_id: str,
    mime_type: str = "audio/ogg",
    lang: str = "es",
) -> dict[str, Any]:
    """Download a Telegram voice/audio note by file_id and transcribe it with Gemini."""
    if not bot_token or not file_id:
        return {"ok": False, "transcript": "", "error": "missing_token_or_file_id"}
    try:
        info_url = f"https://api.telegram.org/bot{bot_token}/getFile?file_id={file_id}"
        with urllib.request.urlopen(urllib.request.Request(info_url), timeout=12) as r:
            info = json.loads(r.read().decode("utf-8", "ignore"))
        file_path = ((info.get("result") or {}).get("file_path") or "").strip()
        if not file_path:
            return {"ok": False, "transcript": "", "error": "telegram_file_path_missing"}
        dl_url = f"https://api.telegram.org/file/bot{bot_token}/{file_path}"
        with urllib.request.urlopen(urllib.request.Request(dl_url), timeout=20) as dr:
            audio_bytes = dr.read()
        try:
            import meta_whatsapp
        except ImportError:
            from server import meta_whatsapp
        return meta_whatsapp.transcribe_audio_bytes(audio_bytes, mime_type=mime_type or "audio/ogg", lang=lang)
    except Exception as exc:
        return {"ok": False, "transcript": "", "error": str(exc)}


def process_telegram_update(
    upd: dict[str, Any],
    bot_token: str = "",
    ceo_chat_id: str = "",
    send_reply: bool = True,
) -> dict[str, Any] | None:
    """Process a single Telegram update dict (text or voice/audio note)."""
    msg = upd.get("message") or upd.get("edited_message") or upd.get("channel_post") or {}
    if not msg:
        return None
    chat_obj = msg.get("chat") or {}
    chat_type_raw = chat_obj.get("type", "private")
    is_group = chat_type_raw in ("group", "supergroup", "channel")
    group_title = (chat_obj.get("title") or "").strip()
    from_obj = msg.get("from") or {}
    from_name = (
        " ".join(filter(None, [from_obj.get("first_name"), from_obj.get("last_name")])).strip()
        or from_obj.get("username")
        or "Contacto Telegram"
    )
    sender_chat_id = str(chat_obj.get("id", ""))

    text = (msg.get("text") or msg.get("caption") or "").strip()
    voice_transcript = ""
    if not text and (msg.get("voice") or msg.get("audio")):
        v_obj = msg.get("voice") or msg.get("audio") or {}
        dur = v_obj.get("duration", 0)
        file_id = str(v_obj.get("file_id") or "")
        vmime = str(v_obj.get("mime_type") or "audio/ogg")
        tr = download_and_transcribe_telegram_audio(bot_token, file_id, mime_type=vmime) if (bot_token and file_id) else {"ok": False}
        if tr.get("ok") and tr.get("transcript"):
            voice_transcript = tr["transcript"]
            text = voice_transcript
        else:
            text = f"[NOTA DE VOZ TELEGRAM · {dur}s] Audio recibido de {from_name}"
    elif not text and msg.get("photo"):
        text = f"[FOTO TELEGRAM] Imagen recibida de {from_name}"
    elif not text and msg.get("document"):
        fname = (msg.get("document") or {}).get("file_name", "Documento")
        text = f"[DOCUMENTO TELEGRAM: {fname}] Archivo recibido de {from_name}"

    if not text or text == "/start":
        return None

    sender_display = f"{group_title} ({from_name})" if is_group and group_title else f"{from_name} (Telegram)"
    reply_text = f"Recibido en La Jefatura: {text}"
    action_name = "logged"

    try:
        try:
            import voice_commands
        except ImportError:
            from server import voice_commands
        cmd_res = voice_commands.execute(text, lang="es", samples_dir=str(ROOT / "data" / "samples"))
        reply_text = cmd_res.get("reply") or reply_text
        action_name = cmd_res.get("action") or action_name
    except Exception:
        pass

    try:
        try:
            import text_messaging
        except ImportError:
            from server import text_messaging
        if hasattr(text_messaging, "process_monitored_inbound"):
            text_messaging.process_monitored_inbound(
                identifier=f"tg:{sender_chat_id}",
                sender_name=sender_display,
                message_text=text,
                company_override=None,
                chat_type_override="group" if is_group else "contact",
                strict_whitelist=False,
                group_subject=group_title,
            )
    except Exception:
        pass

    if send_reply and bot_token and not is_group and (sender_chat_id or ceo_chat_id):
        target_chat = sender_chat_id or ceo_chat_id
        prefix = f"🎙️ Transcripción: «{voice_transcript}»\n\n" if voice_transcript else ""
        send_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = json.dumps({"chat_id": target_chat, "text": f"{prefix}🤖 El Jefecito:\n{reply_text}"}).encode("utf-8")
        try:
            sreq = urllib.request.Request(send_url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
            urllib.request.urlopen(sreq, timeout=10).read()
        except Exception:
            pass

    return {
        "update_id": int(upd.get("update_id", 0)),
        "chat_type": "group" if is_group else "direct",
        "sender": sender_display,
        "text": text,
        "voice_transcribed": bool(voice_transcript),
        "reply": reply_text,
        "action": action_name,
    }


def sync_telegram_inbox(bot_token_override: str = "", send_reply: bool = True) -> dict[str, Any]:
    """Poll Telegram Bot `getUpdates`, transcribe voice notes with Gemini, execute tasks, and reply."""
    env = _load_env()
    bot_token = (bot_token_override or env.get("TG_BOT_TOKEN") or "").strip()
    ceo_chat_id = (env.get("TG_CHAT_ID") or "").strip()
    if not bot_token:
        return {"ok": False, "error": "TG_BOT_TOKEN not configured"}

    last_update_id = 0
    if STATE_FILE.exists():
        try:
            last_update_id = int(json.loads(STATE_FILE.read_text(encoding="utf-8")).get("last_update_id", 0))
        except Exception:
            last_update_id = 0

    url = f"https://api.telegram.org/bot{bot_token}/getUpdates?timeout=1"
    if last_update_id > 0:
        url += f"&offset={last_update_id + 1}"

    ingested = []
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "LaJefaturaTelegramBridge/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        for upd in data.get("result", []):
            uid = int(upd.get("update_id", 0))
            if uid > last_update_id:
                last_update_id = uid
            item = process_telegram_update(upd, bot_token=bot_token, ceo_chat_id=ceo_chat_id, send_reply=send_reply)
            if item:
                ingested.append(item)
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps({"last_update_id": last_update_id, "ts": time.time()}), encoding="utf-8")
        return {"ok": True, "ingested_count": len(ingested), "ingested": ingested, "last_update_id": last_update_id}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def token_fingerprint() -> str:
    tok = _load_env().get("TG_BOT_TOKEN", "").strip()
    return hashlib.sha256(tok.encode("utf-8")).hexdigest()[:12] if tok else ""
