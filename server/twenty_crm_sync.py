"""Shared Twenty CRM -> Mission Control (`nexus_ingest`) sync bridge.

Replaces browser-locked IndexedDB CRM data (Nexus CRM) with Twenty CRM's
shared PostgreSQL REST API (`/rest/opportunities`, `/rest/people`), while
keeping the exact `nexus_ingest.summary()` schema consumed by CEO Mission
Control and PDF board reports.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import nexus_ingest

ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT / ".env"

STAGE_PROBABILITY: dict[str, tuple[str, int]] = {
    "NEW": ("no_contactado", 15),
    "NO_CONTACTADO": ("no_contactado", 15),
    "SCREENING": ("contactado", 35),
    "CONTACTADO": ("contactado", 35),
    "MEETING": ("cotizacion", 60),
    "PROPOSAL": ("cotizacion", 65),
    "COTIZACION": ("cotizacion", 65),
    "CUSTOMER": ("cerrado", 100),
    "WON": ("cerrado", 100),
    "CERRADO": ("cerrado", 100),
}


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


def get_status() -> dict[str, Any]:
    """Return non-secret Twenty CRM integration readiness."""
    base_url = _env_var("TWENTY_BASE_URL", "http://localhost:3020").rstrip("/")
    api_key = _env_var("TWENTY_API_KEY", "")
    reachable = False
    error = None
    if api_key:
        req = urllib.request.Request(
            f"{base_url}/rest/opportunities?limit=1",
            headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                reachable = 200 <= resp.getcode() < 300
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
    return {
        "ok": True,
        "base_url": base_url,
        "api_key_configured": bool(api_key),
        "reachable": reachable,
        "error": error,
        "fallback_mode": "sample_or_webhook_push" if not api_key else "live_rest_api",
    }


def _map_opportunity(opp: dict[str, Any]) -> dict[str, Any]:
    raw_stage = str(opp.get("stage") or opp.get("etapa") or "SCREENING").strip().upper()
    etapa, default_prob = STAGE_PROBABILITY.get(raw_stage, (raw_stage.lower(), 40))

    amount_obj = opp.get("amount")
    if isinstance(amount_obj, dict) and amount_obj.get("amountMicros") is not None:
        valor_usd = round(float(amount_obj["amountMicros"]) / 1_000_000.0, 2)
    else:
        valor_usd = float(opp.get("valor_usd") or opp.get("amountUsd") or 0.0)

    poc = opp.get("pointOfContact") or {}
    if isinstance(poc, dict):
        poc_name_obj = poc.get("name")
        if isinstance(poc_name_obj, dict):
            contacto = f"{poc_name_obj.get('firstName', '')} {poc_name_obj.get('lastName', '')}".strip()
        else:
            contacto = str(poc_name_obj or opp.get("contacto") or "Contacto")
    else:
        contacto = str(opp.get("contacto") or "Contacto")

    company_obj = opp.get("company")
    if isinstance(company_obj, dict):
        empresa = str(company_obj.get("name") or opp.get("name") or opp.get("empresa") or "Cuenta Twenty")
        addr = company_obj.get("address") or {}
        pais = str((addr.get("addressCountry") if isinstance(addr, dict) else "") or opp.get("pais") or "USA")
    else:
        empresa = str(opp.get("empresa") or opp.get("name") or "Cuenta Twenty")
        pais = str(opp.get("pais") or "USA")

    owner_obj = opp.get("owner")
    if isinstance(owner_obj, dict):
        oname = owner_obj.get("name")
        if isinstance(oname, dict):
            vendedor = f"{oname.get('firstName', '')} {oname.get('lastName', '')}".strip() or "Equipo"
        else:
            vendedor = str(oname or opp.get("vendedor") or "Equipo")
    else:
        vendedor = str(opp.get("vendedor") or "Equipo")

    return {
        "id": str(opp.get("id") or f"twenty-{empresa.lower().replace(' ', '-')[:24]}"),
        "empresa": empresa,
        "contacto": contacto or "Contacto",
        "pais": pais,
        "etapa": etapa,
        "valor_usd": valor_usd,
        "probabilidad_pct": int(opp.get("probabilidad_pct") or opp.get("probability") or default_prob),
        "dias": int(opp.get("dias") or opp.get("daysOpen") or 1),
        "vendedor": vendedor,
        "ultima_nota": str(opp.get("ultima_nota") or opp.get("notes") or f"Synced from Twenty CRM ({raw_stage})"),
    }


def _fetch_twenty_opportunities(base_url: str, api_key: str, limit: int = 100) -> list[dict[str, Any]]:
    req = urllib.request.Request(
        f"{base_url.rstrip('/')}/rest/opportunities?limit={int(limit)}",
        headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=10.0) as resp:
        data = json.loads(resp.read().decode("utf-8", errors="replace"))
    if isinstance(data, dict):
        inner = data.get("data")
        if isinstance(inner, dict) and isinstance(inner.get("opportunities"), list):
            return inner["opportunities"]
        if isinstance(data.get("opportunities"), list):
            return data["opportunities"]
        if isinstance(data.get("data"), list):
            return data["data"]
    return data if isinstance(data, list) else []


def sync_from_twenty(
    base_url: str | None = None,
    api_key: str | None = None,
    sample_leads: list[dict[str, Any]] | None = None,
    sample_visits: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Pull deals from Twenty CRM REST API (or ingest pushed sample_leads) into `mc.db`."""
    resolved_url = (base_url or _env_var("TWENTY_BASE_URL", "http://localhost:3020")).rstrip("/")
    resolved_key = (api_key if api_key is not None else _env_var("TWENTY_API_KEY", "")).strip()

    raw_items: list[dict[str, Any]]
    mode = "webhook_payload"
    if isinstance(sample_leads, list):
        raw_items = sample_leads
    elif resolved_key:
        try:
            raw_items = _fetch_twenty_opportunities(resolved_url, resolved_key)
            mode = "live_twenty_rest"
        except Exception as exc:
            return {
                "ok": False,
                "mode": "live_twenty_rest",
                "base_url": resolved_url,
                "error": f"{type(exc).__name__}: {exc}",
            }
    else:
        return {
            "ok": False,
            "mode": "unconfigured",
            "base_url": resolved_url,
            "error": "TWENTY_API_KEY not configured and no sample_leads provided.",
        }

    mapped_leads = [_map_opportunity(item) for item in raw_items if isinstance(item, dict)]
    mapped_visits = sample_visits if isinstance(sample_visits, list) else []
    push_res = nexus_ingest.push({"leads": mapped_leads, "visits": mapped_visits}, source="twenty_crm")
    return {
        "ok": True,
        "mode": mode,
        "base_url": resolved_url,
        "synced_leads": push_res.get("leads", 0),
        "synced_visits": push_res.get("visits", 0),
        "summary": nexus_ingest.summary(),
    }
