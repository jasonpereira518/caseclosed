"""Verification for Google-signed service-account OIDC requests."""
from __future__ import annotations

import hmac

from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2 import id_token

import config


TRUSTED_ISSUERS = frozenset({"accounts.google.com", "https://accounts.google.com"})


def verify_service_account_request(flask_request, *, expected_email: str,
                                   audience: str) -> dict | None:
    authorization = str(flask_request.headers.get("Authorization") or "")
    if not authorization.startswith("Bearer ") or not expected_email or not audience:
        return None
    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        return None
    try:
        claims = id_token.verify_oauth2_token(token, GoogleAuthRequest(), audience=audience)
    except Exception:
        return None
    if claims.get("iss") not in TRUSTED_ISSUERS:
        return None
    if str(claims.get("email") or "").lower() != str(expected_email).lower():
        return None
    if claims.get("email_verified") is not True:
        return None
    return claims


def verify_worker_request(flask_request) -> bool:
    """Shared auth check for internal job-worker callbacks.

    Accepts either the static X-Worker-Token (emulator/local fallback) or a
    verified Google-signed OIDC token from the configured task service account.
    """
    token = flask_request.headers.get("X-Worker-Token", "")
    token_ok = bool(config.INTERNAL_WORKER_TOKEN and hmac.compare_digest(
        token, config.INTERNAL_WORKER_TOKEN))
    oidc_ok = bool(verify_service_account_request(
        flask_request, expected_email=config.TASKS_SERVICE_ACCOUNT,
        audience=config.TASKS_WORKER_AUDIENCE))
    return token_ok or oidc_ok
