"""Workspace, profile, invitation, and authorization primitives.

All server code uses the Firebase Admin SDK, which bypasses Firestore security
rules.  These helpers are therefore the mandatory authorization boundary for
workspace and matter data.
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from google.cloud import firestore as gc_firestore

import config
from services.firestore import get_firestore_client


ROLES = frozenset({"owner", "admin", "member"})
ADMIN_ROLES = frozenset({"owner", "admin"})
PROFILE_FIELDS = frozenset({
    "display_name", "job_title", "organization", "phone",
    "timezone", "notification_preferences", "bar_number", "jurisdictions",
    "office_address", "bio", "practice_areas",
})


class AuthorizationError(PermissionError):
    pass


class ValidationError(ValueError):
    pass


def now():
    return datetime.now(timezone.utc)


def personal_workspace_id(uid: str) -> str:
    digest = hashlib.sha256(str(uid).encode("utf-8")).hexdigest()[:32]
    return f"personal-{digest}"


def public_profile(data: dict) -> dict:
    result = {key: data.get(key) for key in PROFILE_FIELDS}
    result.update({
        "uid": data.get("uid"),
        "email": data.get("email"),
        "email_verified": bool(data.get("email_verified")),
        "created_at": data.get("created_at"),
        "updated_at": data.get("updated_at"),
    })
    avatar = data.get("avatar_url") or ""
    if data.get("avatar_storage_path"):
        try:
            from services.storage import signed_download_url
            avatar = signed_download_url(data["avatar_storage_path"], minutes=60)
        except RuntimeError:
            avatar = ""
    result["avatar_url"] = avatar
    return result


def ensure_user(claims: dict) -> dict:
    """Upsert identity fields and create the user's private workspace."""
    uid = str(claims.get("uid") or claims.get("sub") or "").strip()
    if not uid:
        raise ValidationError("authenticated identity is missing a uid")
    db = get_firestore_client()
    user_ref = db.collection(config.FIRESTORE_USERS_COLLECTION).document(uid)
    snap = user_ref.get()
    existing = snap.to_dict() if snap.exists else {}
    timestamp = now()
    identity = {
        "uid": uid,
        "email": claims.get("email") or existing.get("email"),
        "email_verified": bool(claims.get("email_verified", existing.get("email_verified", False))),
        "display_name": existing.get("display_name") or claims.get("name") or "",
        "avatar_url": existing.get("avatar_url") or claims.get("picture") or "",
        "providers": sorted(
            set(existing.get("providers") or [])
            | set((claims.get("firebase") or {}).get("sign_in_provider", "").split())
            | set(((claims.get("firebase") or {}).get("identities") or {}).keys())
        ),
        "updated_at": timestamp,
    }
    if not snap.exists:
        identity["created_at"] = timestamp
    wid = personal_workspace_id(uid)
    identity["personal_workspace_id"] = wid
    identity["workspace_ids"] = gc_firestore.ArrayUnion([wid])
    user_ref.set(identity, merge=True)

    workspace_ref = db.collection(config.FIRESTORE_WORKSPACES_COLLECTION).document(wid)
    if not workspace_ref.get().exists:
        workspace_ref.set({
            "name": "Personal",
            "type": "personal",
            "owner_id": uid,
            "created_at": timestamp,
            "updated_at": timestamp,
        })
    workspace_ref.collection("members").document(uid).set({
        "uid": uid, "role": "owner", "status": "active",
        "joined_at": timestamp, "updated_at": timestamp,
    }, merge=True)
    return public_profile(user_ref.get().to_dict() or {})


def get_profile(uid: str) -> dict | None:
    snap = get_firestore_client().collection(config.FIRESTORE_USERS_COLLECTION).document(str(uid)).get()
    return public_profile(snap.to_dict() or {}) if snap.exists else None


def update_profile(uid: str, payload: dict) -> dict:
    updates = {key: payload[key] for key in PROFILE_FIELDS if key in payload}
    for list_field in ("jurisdictions", "practice_areas"):
        if list_field in updates and not isinstance(updates[list_field], list):
            raise ValidationError(f"{list_field} must be an array")
    if "notification_preferences" in updates and not isinstance(updates["notification_preferences"], dict):
        raise ValidationError("notification_preferences must be an object")
    for key, value in list(updates.items()):
        if isinstance(value, str):
            updates[key] = value.strip()[:4000]
    updates["updated_at"] = now()
    ref = get_firestore_client().collection(config.FIRESTORE_USERS_COLLECTION).document(str(uid))
    ref.set(updates, merge=True)
    return public_profile(ref.get().to_dict() or {})


def membership(workspace_id: str, uid: str) -> dict | None:
    snap = (get_firestore_client().collection(config.FIRESTORE_WORKSPACES_COLLECTION)
            .document(str(workspace_id)).collection("members").document(str(uid)).get())
    data = snap.to_dict() if snap.exists else None
    return data if data and data.get("status") == "active" else None


def require_workspace(workspace_id: str, uid: str, *, admin=False, owner=False) -> dict:
    member = membership(workspace_id, uid)
    if not member:
        raise AuthorizationError("workspace access denied")
    role = member.get("role")
    if owner and role != "owner":
        raise AuthorizationError("workspace owner access required")
    if admin and role not in ADMIN_ROLES:
        raise AuthorizationError("workspace administrator access required")
    return member


def list_workspaces(uid: str) -> list[dict]:
    db = get_firestore_client()
    user = db.collection(config.FIRESTORE_USERS_COLLECTION).document(str(uid)).get()
    ids = (user.to_dict() or {}).get("workspace_ids") if user.exists else []
    result = []
    for wid in ids or []:
        member = membership(wid, uid)
        snap = db.collection(config.FIRESTORE_WORKSPACES_COLLECTION).document(wid).get()
        if not member or not snap.exists:
            continue
        item = snap.to_dict() or {}
        item.update({"workspace_id": wid, "role": member.get("role")})
        result.append(item)
    result.sort(key=lambda item: (item.get("type") != "personal", item.get("name") or ""))
    return result


def active_workspace(uid: str) -> str:
    db = get_firestore_client()
    snap = db.collection(config.FIRESTORE_USERS_COLLECTION).document(str(uid)).get()
    data = snap.to_dict() if snap.exists else {}
    preferred = (data or {}).get("active_workspace_id")
    if preferred and membership(preferred, uid):
        return preferred
    wid = (data or {}).get("personal_workspace_id") or personal_workspace_id(uid)
    return wid


def set_active_workspace(uid: str, workspace_id: str):
    require_workspace(workspace_id, uid)
    get_firestore_client().collection(config.FIRESTORE_USERS_COLLECTION).document(str(uid)).set(
        {"active_workspace_id": str(workspace_id), "updated_at": now()}, merge=True)


def active_matter(uid: str) -> str | None:
    snap = get_firestore_client().collection(config.FIRESTORE_USERS_COLLECTION).document(str(uid)).get()
    return (snap.to_dict() or {}).get("active_matter_id") if snap.exists else None


def set_active_matter(uid: str, matter_id: str):
    get_firestore_client().collection(config.FIRESTORE_USERS_COLLECTION).document(str(uid)).set(
        {"active_matter_id": str(matter_id), "updated_at": now()}, merge=True)


def create_team(uid: str, name: str) -> dict:
    clean_name = (name or "").strip()[:120]
    if not clean_name:
        raise ValidationError("workspace name is required")
    db = get_firestore_client()
    ref = db.collection(config.FIRESTORE_WORKSPACES_COLLECTION).document()
    timestamp = now()
    ref.set({"name": clean_name, "type": "team", "owner_id": str(uid),
             "created_at": timestamp, "updated_at": timestamp})
    ref.collection("members").document(str(uid)).set({
        "uid": str(uid), "role": "owner", "status": "active",
        "joined_at": timestamp, "updated_at": timestamp,
    })
    db.collection(config.FIRESTORE_USERS_COLLECTION).document(str(uid)).set(
        {"workspace_ids": gc_firestore.ArrayUnion([ref.id]), "updated_at": timestamp}, merge=True)
    audit(ref.id, uid, "workspace.created", {"name": clean_name})
    return {"workspace_id": ref.id, "name": clean_name, "type": "team", "role": "owner"}


def list_members(workspace_id: str, uid: str) -> list[dict]:
    require_workspace(workspace_id, uid)
    db = get_firestore_client()
    result = []
    for snap in (db.collection(config.FIRESTORE_WORKSPACES_COLLECTION).document(workspace_id)
                 .collection("members").stream()):
        member = snap.to_dict() or {}
        profile = get_profile(snap.id) or {}
        result.append({**member, "uid": snap.id, "profile": profile})
    return result


def set_member_role(workspace_id: str, actor_uid: str, target_uid: str, role: str):
    require_workspace(workspace_id, actor_uid, admin=True)
    if role not in {"admin", "member"}:
        raise ValidationError("invalid role")
    ref = get_firestore_client().collection(config.FIRESTORE_WORKSPACES_COLLECTION).document(workspace_id)
    workspace = ref.get().to_dict() or {}
    if target_uid == workspace.get("owner_id") and role != "owner":
        raise ValidationError("transfer ownership before changing the owner's role")
    ref.collection("members").document(target_uid).set({"role": role, "updated_at": now()}, merge=True)
    audit(workspace_id, actor_uid, "member.role_changed", {"target_uid": target_uid, "role": role})


def revoke_invitation(workspace_id: str, actor_uid: str, invitation_id: str):
    require_workspace(workspace_id, actor_uid, admin=True)
    ref = get_firestore_client().collection(config.FIRESTORE_INVITATIONS_COLLECTION).document(invitation_id)
    snap = ref.get()
    data = snap.to_dict() if snap.exists else None
    if not data or data.get("workspace_id") != workspace_id:
        raise ValidationError("invitation not found")
    ref.set({"status": "revoked", "updated_at": now()}, merge=True)
    audit(workspace_id, actor_uid, "invitation.revoked", {"invitation_id": invitation_id})


def remove_member(workspace_id: str, actor_uid: str, target_uid: str):
    actor = require_workspace(workspace_id, actor_uid)
    if actor_uid != target_uid and actor.get("role") not in ADMIN_ROLES:
        raise AuthorizationError("cannot remove another member")
    ref = get_firestore_client().collection(config.FIRESTORE_WORKSPACES_COLLECTION).document(workspace_id)
    workspace = ref.get().to_dict() or {}
    if target_uid == workspace.get("owner_id"):
        raise ValidationError("transfer ownership before the owner leaves")
    ref.collection("members").document(target_uid).set({"status": "removed", "updated_at": now()}, merge=True)
    for matter_doc in ref.collection("matters").stream():
        matter_doc.reference.set({"assigned_user_ids": gc_firestore.ArrayRemove([str(target_uid)]),
                                  "updated_at": now()}, merge=True)
    get_firestore_client().collection(config.FIRESTORE_USERS_COLLECTION).document(target_uid).set(
        {"workspace_ids": gc_firestore.ArrayRemove([workspace_id]), "updated_at": now()}, merge=True)
    audit(workspace_id, actor_uid, "member.removed", {"target_uid": target_uid})


def transfer_ownership(workspace_id: str, actor_uid: str, target_uid: str):
    require_workspace(workspace_id, actor_uid, owner=True)
    if not membership(workspace_id, target_uid):
        raise ValidationError("new owner must be an active member")
    db = get_firestore_client()
    ref = db.collection(config.FIRESTORE_WORKSPACES_COLLECTION).document(workspace_id)
    ref.set({"owner_id": target_uid, "updated_at": now()}, merge=True)
    ref.collection("members").document(actor_uid).set({"role": "admin", "updated_at": now()}, merge=True)
    ref.collection("members").document(target_uid).set({"role": "owner", "updated_at": now()}, merge=True)
    audit(workspace_id, actor_uid, "workspace.ownership_transferred", {"target_uid": target_uid})


def create_invitation(workspace_id: str, actor_uid: str, email: str, role: str) -> tuple[dict, str]:
    require_workspace(workspace_id, actor_uid, admin=True)
    if role not in {"admin", "member"}:
        raise ValidationError("invitations may grant admin or member access")
    clean_email = (email or "").strip().lower()
    if "@" not in clean_email:
        raise ValidationError("valid email is required")
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    timestamp = now()
    ref = get_firestore_client().collection(config.FIRESTORE_INVITATIONS_COLLECTION).document()
    data = {
        "workspace_id": workspace_id, "email": clean_email, "role": role,
        "token_hash": token_hash, "status": "pending", "created_by": actor_uid,
        "created_at": timestamp,
        "expires_at": timestamp + timedelta(days=config.INVITATION_TTL_DAYS),
    }
    ref.set(data)
    audit(workspace_id, actor_uid, "invitation.created", {"invitation_id": ref.id, "email": clean_email, "role": role})
    return {**data, "invitation_id": ref.id, "token_hash": None}, token


def accept_invitation(uid: str, email: str, token: str) -> str:
    token_hash = hashlib.sha256((token or "").encode()).hexdigest()
    db = get_firestore_client()
    matches = list(db.collection(config.FIRESTORE_INVITATIONS_COLLECTION)
                   .where(filter=gc_firestore.FieldFilter("token_hash", "==", token_hash)).limit(1).stream())
    if not matches:
        raise ValidationError("invalid invitation")
    snap = matches[0]
    invitation = snap.to_dict() or {}
    expires_at = invitation.get("expires_at")
    if invitation.get("status") != "pending" or not expires_at or expires_at <= now():
        raise ValidationError("invitation has expired or was already used")
    if (email or "").strip().lower() != invitation.get("email"):
        raise AuthorizationError("sign in with the invited email address")
    wid = invitation["workspace_id"]
    timestamp = now()
    workspace_ref = db.collection(config.FIRESTORE_WORKSPACES_COLLECTION).document(wid)
    workspace_ref.collection("members").document(str(uid)).set({
        "uid": str(uid), "role": invitation["role"], "status": "active",
        "joined_at": timestamp, "updated_at": timestamp,
    })
    db.collection(config.FIRESTORE_USERS_COLLECTION).document(str(uid)).set(
        {"workspace_ids": gc_firestore.ArrayUnion([wid]), "updated_at": timestamp}, merge=True)
    snap.reference.set({"status": "accepted", "accepted_by": str(uid), "accepted_at": timestamp}, merge=True)
    audit(wid, uid, "invitation.accepted", {"invitation_id": snap.id})
    return wid


def audit(workspace_id: str, actor_uid: str | None, event: str, metadata: dict | None = None,
          matter_id: str | None = None):
    ref = (get_firestore_client().collection(config.FIRESTORE_WORKSPACES_COLLECTION)
           .document(str(workspace_id)).collection("audit_events").document())
    ref.set({"event": event, "actor_uid": actor_uid, "matter_id": matter_id,
             "metadata": metadata or {}, "created_at": now()})
