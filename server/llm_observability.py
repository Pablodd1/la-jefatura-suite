"""SQLite + Langfuse LLM Cost, Latency & Error Observability (`server/llm_observability.py`).

Records persistent model usage telemetry in `mc.db` (`llm_traces`) and optionally
streams spans to Langfuse (`/api/public/ingestion`) when `LANGFUSE_PUBLIC_KEY` and
`LANGFUSE_SECRET_KEY` are configured.
"""

from __future__ import annotations

import base64
import json
import os
import sqlite3
import threading
import time
import urllib.request
import uuid
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT / ".env"

# Approximate USD per 1M tokens (input, output)
MODEL_RATES_PER_1M: dict[str, tuple[float, float]] = {
    "gemini-3.1-flash-lite": (0.075, 0.30),
    "gemini-3-flash-preview": (0.10, 0.40),
    "gemini-flash-latest": (0.10, 0.40),
    "gemini-2.5-flash": (0.15, 0.60),
    "gemini-3.1-pro-preview": (1.25, 5.00),
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS llm_traces (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    provider TEXT,
    model TEXT,
    ok INTEGER NOT NULL,
    latency_ms INTEGER NOT NULL,
    prompt_chars INTEGER NOT NULL,
    completion_chars INTEGER NOT NULL,
    est_tokens INTEGER NOT NULL,
    est_cost_usd REAL NOT NULL,
    error TEXT
);
CREATE INDEX IF NOT EXISTS idx_llm_traces_ts ON llm_traces(ts DESC);
"""


def _env_var(name: str, default: str = "") -> str:
    val = os.environ.get(name, "").strip()
    if val:
        return val
    if ENV_PATH.is_file():
        try:
            for line in ENV_PATH.read_text(encoding="utf-8", errors="ignore").splitlines():
                s = line.strip()
                if s and not s.startswith("#") and "=" in s:
                    k, v = s.split("=", 1)
                    if k.strip() == name:
                        cleaned = v.strip().strip('"').strip("'")
                        if cleaned:
                            return cleaned
        except OSError:
            pass
    return default


def _db_path() -> str:
    override = os.environ.get("MC_DB_PATH", "").strip()
    if override:
        return override
    prod_dir = "/root/.openclaw/workspace/mission-control"
    if os.path.isdir(prod_dir):
        return os.path.join(prod_dir, "mc.db")
    return str(ROOT / "data" / "mc.db")


def _connect() -> sqlite3.Connection:
    path = _db_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path, timeout=30.0)
    conn.executescript(SCHEMA)
    return conn


def estimate_cost_usd(provider: str | None, model: str | None, prompt_chars: int, completion_chars: int) -> tuple[int, float]:
    in_tok = max(0, int(round(prompt_chars / 4.0)))
    out_tok = max(0, int(round(completion_chars / 4.0)))
    total_tok = in_tok + out_tok
    if (provider or "").lower() == "ollama" or not model:
        return total_tok, 0.0
    in_rate, out_rate = MODEL_RATES_PER_1M.get(model, (0.15, 0.60))
    cost = (in_tok * in_rate + out_tok * out_rate) / 1_000_000.0
    return total_tok, round(cost, 6)


def _ship_langfuse_async(trace_payload: dict[str, Any]) -> None:
    pub = _env_var("LANGFUSE_PUBLIC_KEY", "")
    sec = _env_var("LANGFUSE_SECRET_KEY", "")
    if not pub or not sec:
        return
    host = _env_var("LANGFUSE_HOST", "https://cloud.langfuse.com").rstrip("/")
    token = base64.b64encode(f"{pub}:{sec}".encode("utf-8")).decode("ascii")
    now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(trace_payload["ts"]))
    tid = str(uuid.uuid4())
    batch = {
        "batch": [
            {
                "id": str(uuid.uuid4()),
                "type": "trace-create",
                "timestamp": now_iso,
                "body": {
                    "id": tid,
                    "name": f"llm_router:{trace_payload.get('model') or 'none'}",
                    "metadata": {
                        "provider": trace_payload.get("provider"),
                        "ok": bool(trace_payload.get("ok")),
                        "latency_ms": trace_payload.get("latency_ms"),
                        "est_cost_usd": trace_payload.get("est_cost_usd"),
                    },
                },
            },
            {
                "id": str(uuid.uuid4()),
                "type": "generation-create",
                "timestamp": now_iso,
                "body": {
                    "id": str(uuid.uuid4()),
                    "traceId": tid,
                    "name": "generate_text",
                    "model": trace_payload.get("model") or "none",
                    "usage": {
                        "total": trace_payload.get("est_tokens", 0),
                    },
                    "level": "DEFAULT" if trace_payload.get("ok") else "ERROR",
                    "statusMessage": trace_payload.get("error"),
                },
            },
        ]
    }

    def _send() -> None:
        try:
            req = urllib.request.Request(
                f"{host}/api/public/ingestion",
                data=json.dumps(batch).encode("utf-8"),
                headers={
                    "Authorization": f"Basic {token}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=5.0):
                pass
        except Exception:
            pass

    threading.Thread(target=_send, daemon=True).start()


def record_trace(
    ok: bool,
    provider: str | None,
    model: str | None,
    latency_ms: int,
    prompt_chars: int = 0,
    completion_chars: int = 0,
    error: str | None = None,
) -> dict[str, Any]:
    ts = time.time()
    est_tokens, est_cost = estimate_cost_usd(provider, model, prompt_chars, completion_chars)
    conn = _connect()
    try:
        conn.execute(
            "INSERT INTO llm_traces (ts, provider, model, ok, latency_ms, prompt_chars, completion_chars, est_tokens, est_cost_usd, error) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (ts, provider or "none", model or "none", 1 if ok else 0, int(latency_ms), int(prompt_chars), int(completion_chars), est_tokens, est_cost, error),
        )
        conn.commit()
    finally:
        conn.close()

    rec = {
        "ts": ts,
        "provider": provider or "none",
        "model": model or "none",
        "ok": bool(ok),
        "latency_ms": int(latency_ms),
        "est_tokens": est_tokens,
        "est_cost_usd": est_cost,
        "error": error,
    }
    _ship_langfuse_async(rec)
    return rec


def summary(hours: int = 24, limit: int = 30) -> dict[str, Any]:
    since = time.time() - max(1, int(hours)) * 3600
    lim = max(1, min(int(limit), 200))
    conn = _connect()
    try:
        agg = conn.execute(
            "SELECT COUNT(*), COALESCE(SUM(ok),0), COALESCE(AVG(latency_ms),0), "
            "COALESCE(SUM(est_tokens),0), COALESCE(SUM(est_cost_usd),0) "
            "FROM llm_traces WHERE ts >= ?",
            (since,),
        ).fetchone()
        by_model = conn.execute(
            "SELECT model, provider, COUNT(*), COALESCE(SUM(ok),0), ROUND(AVG(latency_ms),1), "
            "COALESCE(SUM(est_tokens),0), ROUND(SUM(est_cost_usd),6) "
            "FROM llm_traces WHERE ts >= ? GROUP BY model, provider ORDER BY 3 DESC",
            (since,),
        ).fetchall()
        recent = conn.execute(
            "SELECT ts, provider, model, ok, latency_ms, est_tokens, est_cost_usd, error "
            "FROM llm_traces ORDER BY id DESC LIMIT ?",
            (lim,),
        ).fetchall()
    finally:
        conn.close()

    total = int(agg[0] or 0)
    ok_count = int(agg[1] or 0)
    langfuse_configured = bool(_env_var("LANGFUSE_PUBLIC_KEY", "") and _env_var("LANGFUSE_SECRET_KEY", ""))
    return {
        "ok": True,
        "window_hours": int(hours),
        "langfuse": {
            "configured": langfuse_configured,
            "host": _env_var("LANGFUSE_HOST", "https://cloud.langfuse.com"),
        },
        "totals": {
            "calls": total,
            "ok": ok_count,
            "failed": max(0, total - ok_count),
            "success_rate_pct": round((ok_count / total) * 100.0, 1) if total else 100.0,
            "avg_latency_ms": round(float(agg[2] or 0.0), 1),
            "est_tokens": int(agg[3] or 0),
            "est_cost_usd": round(float(agg[4] or 0.0), 6),
        },
        "by_model": [
            {
                "model": r[0],
                "provider": r[1],
                "calls": r[2],
                "ok": r[3],
                "avg_latency_ms": r[4],
                "est_tokens": r[5],
                "est_cost_usd": r[6],
            }
            for r in by_model
        ],
        "recent": [
            {
                "ts": r[0],
                "provider": r[1],
                "model": r[2],
                "ok": bool(r[3]),
                "latency_ms": r[4],
                "est_tokens": r[5],
                "est_cost_usd": r[6],
                "error": r[7],
            }
            for r in recent
        ],
    }
