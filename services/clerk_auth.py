"""Clerk request authentication and Firestore identity synchronization."""
from __future__ import annotations

import logging
from typing import Any

from clerk_backend_api import Clerk
from clerk_backend_api.security import authenticate_request as verify_clerk_request
from clerk_backend_api.security.types import AuthenticateRequestOptions
from google.cloud import firestore as gc_firestore

import config
from models.user import load_user
from services.firestore import get_firestore_client
from services.tenancy import ensure_user, now


_client: Clerk | None = None


def get_clerk_client() -> Clerk:
    global _client
    if not config.CLERK_SECRET_KEY:
        raise RuntimeError("CLERK_SECRET_KEY is not configured")
    if _client is None:
        _client = Clerk(bearer_auth=config.CLERK_SECRET_KEY)
    return _client


def authenticate_clerk_request(flask_request):
    """Return the local Flask-Login user represented by a Clerk session."""
    if not config.CLERK_SECRET_KEY:
        return None
    options = AuthenticateRequestOptions(
        secret_key=config.CLERK_SECRET_KEY,
        jwt_key=config.CLERK_JWT_KEY or None,
        authorized_parties=config.CLERK_AUTHORIZED_PARTIES,
        accepts_token=["session_token"],
    )
    state = verify_clerk_request(flask_request, options)
    if not state.is_authenticated:
        reason = getattr(state.reason, "name", None) or str(state.reason or "unknown")
        logging.info("Clerk session authentication failed: %s", reason)
        return None
    payload = state.payload or {}
    if payload.get("sts") == "pending":
        logging.info("Clerk session is pending required tasks")
        return None
    clerk_user_id = str(payload.get("sub") or "").strip()
    app_user_id = str(payload.get("userId") or clerk_user_id).strip()
    if not clerk_user_id or not app_user_id:
        return None

    user = load_user(app_user_id)
    if user and user.profile.get("clerk_user_id") == clerk_user_id:
        return user
    try:
        sync_clerk_user(get_clerk_client().users.get(user_id=clerk_user_id), app_user_id=app_user_id)
    except Exception as exc:
        logging.warning("Could not provision Clerk user: %s", exc.__class__.__name__)
        return None
    return load_user(app_user_id)


def sync_clerk_user(user: Any, *, app_user_id: str | None = None) -> dict:
    """Upsert a Clerk SDK user or webhook user payload into the local identity record."""
    clerk_user_id = str(_value(user, "id") or "").strip()
    external_id = str(_value(user, "external_id") or "").strip()
    uid = str(app_user_id or external_id or clerk_user_id).strip()
    if not clerk_user_id or not uid:
        raise ValueError("Clerk user is missing an id")
    email, verified = _primary_email(user)
    first = str(_value(user, "first_name") or "").strip()
    last = str(_value(user, "last_name") or "").strip()
    name = " ".join(value for value in (first, last) if value)
    claims = {
        "uid": uid,
        "email": email,
        "email_verified": verified,
        "name": name,
        "picture": _value(user, "image_url") or _value(user, "profile_image_url") or "",
        "providers": _providers(user),
        "auth_provider": "clerk",
        "auth_status": "active",
        "clerk_user_id": clerk_user_id,
    }
    if external_id and external_id != clerk_user_id:
        claims["legacy_firebase_uid"] = external_id
    return ensure_user(claims)


def find_app_user_id(clerk_user_id: str) -> str | None:
    """Resolve a Clerk foreign key to the stable app user id."""
    db = get_firestore_client()
    direct = db.collection(config.FIRESTORE_USERS_COLLECTION).document(str(clerk_user_id)).get()
    if direct.exists and (direct.to_dict() or {}).get("clerk_user_id") == clerk_user_id:
        return direct.id
    matches = list(
        db.collection(config.FIRESTORE_USERS_COLLECTION)
        .where(filter=gc_firestore.FieldFilter("clerk_user_id", "==", str(clerk_user_id)))
        .limit(1)
        .stream()
    )
    return matches[0].id if matches else None


def mark_clerk_user_deleted(clerk_user_id: str) -> None:
    """Disable the local identity without destructively deleting tenant data."""
    uid = find_app_user_id(clerk_user_id)
    if uid:
        get_firestore_client().collection(config.FIRESTORE_USERS_COLLECTION).document(uid).set(
            {"auth_status": "deleted", "auth_deleted_at": now(), "updated_at": now()}, merge=True)


def delete_clerk_identity(clerk_user_id: str) -> None:
    get_clerk_client().users.delete(user_id=str(clerk_user_id))


def _value(source: Any, key: str, default=None):
    if isinstance(source, dict):
        return source.get(key, default)
    return getattr(source, key, default)


def _primary_email(user: Any) -> tuple[str | None, bool]:
    addresses = _value(user, "email_addresses", []) or []
    primary_id = _value(user, "primary_email_address_id")
    primary = next((item for item in addresses if _value(item, "id") == primary_id), None)
    primary = primary or (addresses[0] if addresses else None)
    if not primary:
        return None, False
    verification = _value(primary, "verification")
    status = _value(verification, "status")
    if hasattr(status, "value"):
        status = status.value
    return _value(primary, "email_address"), str(status or "").lower() == "verified"


def _providers(user: Any) -> list[str]:
    result = []
    for account in _value(user, "external_accounts", []) or []:
        provider = _value(account, "provider")
        if provider:
            result.append(str(provider))
    if _value(user, "password_enabled", False):
        result.append("password")
    return sorted(set(result))
