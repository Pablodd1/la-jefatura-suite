"""Shared Mission Control token handling.

The token is read from the MC_EXPORT_TOKEN env var or from the git-ignored file
data/mc_token.secret. It is NEVER hardcoded in source.
"""
import hmac
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
TOKEN_FILE = os.path.join(ROOT, "data", "mc_token.secret")


def get_token() -> str:
    env = os.environ.get("MC_EXPORT_TOKEN", "").strip()
    if env:
        return env
    try:
        with open(TOKEN_FILE, encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""


def token_ok(provided: str) -> bool:
    expected = get_token()
    if not expected or not provided:
        return False
    return hmac.compare_digest(provided.strip(), expected)


def is_remote(headers) -> bool:
    """Requests that arrive through the Cloudflare tunnel / a proxy are remote."""
    return bool(headers.get("Cf-Connecting-Ip") or headers.get("X-Forwarded-For"))
