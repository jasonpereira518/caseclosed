"""Verification for Google-signed service-account OIDC requests."""
from __future__ import annotations

from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2 import id_token


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
