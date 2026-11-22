"""Unified LLM router for La Jefatura Suite.

Provides resilient text generation with verified Gemini 3 model fallback and
zero-cost local Ollama (`gemma3:4b`) failover, plus non-secret health probing.
"""

from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

try:
    import llm_observability  # type: ignore
except ImportError:
    llm_observability = None  # type: ignore

ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT / ".env"

FLASH_CHAIN: tuple[str, ...] = (
    "gemini-3.1-flash-lite",
    "gemini-3-flash-preview",
    "gemini-flash-latest",
)
PRO_MODEL = "gemini-3.1-pro-preview"
DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"
DEFAULT_OLLAMA_MODEL = "gemma3:4b"

_STATE_LOCK = threading.Lock()
_ROUTER_STATS: dict[str, Any] = {
    "calls_total": 0,
    "calls_ok": 0,
    "calls_failed": 0,
    "last_provider": None,
    "last_model": None,
    "last_latency_ms": None,
    "last_error": None,
    "last_ok_at": None,
}


def _load_env_var(name: str, default: str = "") -> str:
    """Read an environment variable, falling back to repo `.env` on disk."""
    val = os.environ.get(name, "").strip()
    if val:
        return val
    if ENV_PATH.is_file():
        try:
            for raw_line in ENV_PATH.read_text(encoding="utf-8", errors="ignore").splitlines():
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                if k.strip() == name:
                    cleaned = v.strip().strip('"').strip("'")
                    if cleaned:
                        return cleaned
        except OSError:
            pass
    return default


def _gemini_models(prefer_pro: bool) -> list[str]:
    """Return ordered Gemini model IDs to attempt."""
    override = _load_env_var("GEMINI_MODEL", "")
    models: list[str] = []
    if prefer_pro:
        models.append(PRO_MODEL)
    if override and override not in models:
        models.append(override)
    for m in FLASH_CHAIN:
        if m not in models:
            models.append(m)
    return models


def _call_gemini_model(
    model: str,
    prompt: str,
    system: str,
    max_tokens: int,
    temperature: float,
    json_mode: bool,
    api_key: str,
    timeout: float,
) -> tuple[str | None, str | None]:
    """Invoke a single Gemini `generateContent` endpoint. Returns `(text, error)`."""
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?key={api_key}"
    )
    gen_cfg: dict[str, Any] = {
        "temperature": float(temperature),
        "maxOutputTokens": int(max_tokens),
    }
    if json_mode:
        gen_cfg["responseMimeType"] = "application/json"

    payload: dict[str, Any] = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": gen_cfg,
    }
    if system and system.strip():
        payload["systemInstruction"] = {"parts": [{"text": system.strip()}]}

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        data = json.loads(raw)
        candidates = data.get("candidates") or []
        if not candidates:
            return None, f"{model}: empty candidates"
        parts = candidates[0].get("content", {}).get("parts") or []
        non_thought = [p.get("text", "") for p in parts if isinstance(p, dict) and not p.get("thought") and p.get("text")]
        if not non_thought:
            non_thought = [p.get("text", "") for p in parts if isinstance(p, dict) and p.get("text")]
        text = "".join(non_thought).strip()
        if not text:
            return None, f"{model}: blank text"
        return text, None
    except urllib.error.HTTPError as exc:
        body_snippet = ""
        try:
            body_snippet = exc.read().decode("utf-8", errors="ignore")[:180].replace("\n", " ")
        except Exception:
            pass
        return None, f"{model}: HTTP {exc.code} {body_snippet}".strip()
    except Exception as exc:
        return None, f"{model}: {type(exc).__name__}: {exc}"


def _call_ollama(
    prompt: str,
    system: str,
    max_tokens: int,
    temperature: float,
    json_mode: bool,
    model: str,
    base_url: str,
    timeout: float,
) -> tuple[str | None, str | None]:
    """Invoke local Ollama `/api/generate` endpoint as offline fallback."""
    url = base_url.rstrip("/") + "/api/generate"
    payload: dict[str, Any] = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": float(temperature),
            "num_predict": int(max_tokens),
        },
    }
    if system and system.strip():
        payload["system"] = system.strip()
    if json_mode:
        payload["format"] = "json"

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        data = json.loads(raw)
        text = (data.get("response") or "").strip()
        if not text:
            return None, f"ollama/{model}: blank response"
        return text, None
    except Exception as exc:
        return None, f"ollama/{model}: {type(exc).__name__}: {exc}"


def _record_outcome(
    ok: bool,
    provider: str | None,
    model: str | None,
    latency_ms: int,
    error: str | None,
    prompt_chars: int = 0,
    completion_chars: int = 0,
) -> None:
    """Record thread-safe telemetry for `/api/health` and SQLite/Langfuse observability."""
    with _STATE_LOCK:
        _ROUTER_STATS["calls_total"] += 1
        if ok:
            _ROUTER_STATS["calls_ok"] += 1
            _ROUTER_STATS["last_provider"] = provider
            _ROUTER_STATS["last_model"] = model
            _ROUTER_STATS["last_latency_ms"] = latency_ms
            _ROUTER_STATS["last_error"] = None
            _ROUTER_STATS["last_ok_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        else:
            _ROUTER_STATS["calls_failed"] += 1
            _ROUTER_STATS["last_error"] = error
    if llm_observability is not None:
        try:
            llm_observability.record_trace(
                ok=ok,
                provider=provider,
                model=model,
                latency_ms=latency_ms,
                prompt_chars=prompt_chars,
                completion_chars=completion_chars,
                error=error,
            )
        except Exception:
            pass


def _clean_json_text(raw_text: str) -> tuple[bool, str]:
    """Strip optional markdown fences and verify JSON validity when json_mode is enabled."""
    txt = (raw_text or "").strip()
    if txt.startswith("```"):
        lines = txt.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        txt = "\n".join(lines).strip()
    try:
        json.loads(txt)
        return True, txt
    except Exception:
        return False, txt


def generate_text_with_meta(
    prompt: str,
    system: str = "",
    max_tokens: int = 900,
    temperature: float = 0.1,
    json_mode: bool = False,
    prefer_pro: bool = False,
    timeout: float = 20.0,
) -> dict[str, Any]:
    """Generate text using Gemini 3 models with local Ollama fallback, returning metadata."""
    t0 = time.monotonic()
    errors: list[str] = []
    api_key = _load_env_var("GEMINI_API_KEY", "")

    if api_key:
        for model in _gemini_models(prefer_pro=prefer_pro):
            text, err = _call_gemini_model(
                model=model,
                prompt=prompt,
                system=system,
                max_tokens=max_tokens,
                temperature=temperature,
                json_mode=json_mode,
                api_key=api_key,
                timeout=timeout,
            )
            if text:
                if json_mode:
                    valid_json, cleaned = _clean_json_text(text)
                    if not valid_json:
                        errors.append(f"{model}: non-JSON reply ({text[:40]!r})")
                        continue
                    text = cleaned
                latency_ms = int((time.monotonic() - t0) * 1000)
                _record_outcome(
                    True,
                    "gemini",
                    model,
                    latency_ms,
                    None,
                    prompt_chars=len(prompt) + len(system),
                    completion_chars=len(text),
                )
                return {
                    "ok": True,
                    "text": text,
                    "provider": "gemini",
                    "model": model,
                    "latency_ms": latency_ms,
                    "errors": errors,
                }
            if err:
                errors.append(err)
    else:
        errors.append("gemini: GEMINI_API_KEY missing")

    ollama_url = _load_env_var("OLLAMA_URL", DEFAULT_OLLAMA_URL)
    ollama_model = _load_env_var("OLLAMA_MODEL", DEFAULT_OLLAMA_MODEL)
    text, err = _call_ollama(
        prompt=prompt,
        system=system,
        max_tokens=max_tokens,
        temperature=temperature,
        json_mode=json_mode,
        model=ollama_model,
        base_url=ollama_url,
        timeout=min(timeout, 15.0),
    )
    latency_ms = int((time.monotonic() - t0) * 1000)
    if text:
        if json_mode:
            valid_json, cleaned = _clean_json_text(text)
            if valid_json:
                text = cleaned
            else:
                errors.append(f"ollama/{ollama_model}: non-JSON reply")
                text = None
    if text:
        _record_outcome(
            True,
            "ollama",
            ollama_model,
            latency_ms,
            None,
            prompt_chars=len(prompt) + len(system),
            completion_chars=len(text),
        )
        return {
            "ok": True,
            "text": text,
            "provider": "ollama",
            "model": ollama_model,
            "latency_ms": latency_ms,
            "errors": errors,
        }
    if err:
        errors.append(err)

    joined_err = " | ".join(errors[-4:]) if errors else "no providers available"
    _record_outcome(
        False,
        None,
        None,
        latency_ms,
        joined_err,
        prompt_chars=len(prompt) + len(system),
        completion_chars=0,
    )
    return {
        "ok": False,
        "text": None,
        "provider": "none",
        "model": "none",
        "latency_ms": latency_ms,
        "errors": errors,
    }


def generate_text(
    prompt: str,
    system: str = "",
    max_tokens: int = 900,
    temperature: float = 0.1,
    json_mode: bool = False,
    prefer_pro: bool = False,
) -> str | None:
    """One-shot routed LLM text completion. Returns generated text or None on total failure."""
    res = generate_text_with_meta(
        prompt=prompt,
        system=system,
        max_tokens=max_tokens,
        temperature=temperature,
        json_mode=json_mode,
        prefer_pro=prefer_pro,
    )
    return res.get("text")


def _probe_ollama_tags(base_url: str, timeout: float = 1.5) -> dict[str, Any]:
    """Check whether local Ollama daemon responds and list loaded model names."""
    url = base_url.rstrip("/") + "/api/tags"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
        models = [m.get("name") for m in (data.get("models") or []) if m.get("name")]
        return {"reachable": True, "models": models}
    except Exception as exc:
        return {"reachable": False, "models": [], "error": f"{type(exc).__name__}: {exc}"}


def health_probe(live_call: bool = False) -> dict[str, Any]:
    """Return safe diagnostics about configured LLM providers (never exposes API keys)."""
    api_key = _load_env_var("GEMINI_API_KEY", "")
    ollama_url = _load_env_var("OLLAMA_URL", DEFAULT_OLLAMA_URL)
    ollama_model = _load_env_var("OLLAMA_MODEL", DEFAULT_OLLAMA_MODEL)
    ollama_status = _probe_ollama_tags(ollama_url)

    with _STATE_LOCK:
        stats_copy = dict(_ROUTER_STATS)

    report: dict[str, Any] = {
        "gemini_configured": bool(api_key),
        "primary_chain": list(_gemini_models(prefer_pro=False)),
        "pro_model": PRO_MODEL,
        "ollama": {
            "url": ollama_url,
            "default_model": ollama_model,
            **ollama_status,
        },
        "runtime_stats": stats_copy,
    }
    if live_call:
        probe = generate_text_with_meta(
            prompt="Responde exactamente con: OK",
            system="Health check",
            max_tokens=16,
            temperature=0.0,
            timeout=10.0,
        )
        report["live_probe"] = {
            "ok": probe["ok"],
            "provider": probe["provider"],
            "model": probe["model"],
            "latency_ms": probe["latency_ms"],
            "reply_preview": (probe.get("text") or "")[:40],
            "errors": probe.get("errors", []),
        }
    return report
