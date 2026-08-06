#!/usr/bin/env python3
"""Import exported Firebase Auth users into Clerk without changing app user IDs."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from clerk_backend_api import Clerk  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")


def firebase_password_digest(user: dict, *, signer_key: str, salt_separator: str,
                             rounds: str, memory_cost: str) -> str:
    values = [user.get("passwordHash"), user.get("salt"), signer_key,
              salt_separator, rounds, memory_cost]
    if any(value in (None, "") for value in values):
        raise ValueError("Firebase password user or hash parameters are incomplete")
    return "$".join(str(value) for value in values)


def migration_payload(user: dict, args) -> dict:
    uid = str(user.get("localId") or "").strip()
    email = str(user.get("email") or "").strip()
    if not uid or not email:
        raise ValueError("Every migrated Firebase user must have localId and email")
    display_name = str(user.get("displayName") or "").strip().split()
    payload = {
        "external_id": uid,
        "email_address": [email],
        "first_name": display_name[0] if display_name else None,
        "last_name": " ".join(display_name[1:]) if len(display_name) > 1 else None,
        "skip_legal_checks": True,
    }
    if user.get("passwordHash"):
        payload.update({
            "password_hasher": "scrypt_firebase",
            "password_digest": firebase_password_digest(
                user,
                signer_key=args.signer_key,
                salt_separator=args.salt_separator,
                rounds=args.rounds,
                memory_cost=args.memory_cost,
            ),
        })
    else:
        payload["skip_password_requirement"] = True
    return {key: value for key, value in payload.items() if value is not None}


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("firebase_export", type=Path)
    parser.add_argument("--expected-count", type=int, default=1)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--write-firestore-mapping", action="store_true")
    parser.add_argument("--signer-key", default=os.getenv("FIREBASE_AUTH_SIGNER_KEY", ""))
    parser.add_argument("--salt-separator", default=os.getenv("FIREBASE_AUTH_SALT_SEPARATOR", ""))
    parser.add_argument("--rounds", default=os.getenv("FIREBASE_AUTH_ROUNDS", ""))
    parser.add_argument("--memory-cost", default=os.getenv("FIREBASE_AUTH_MEMORY_COST", ""))
    return parser.parse_args()


def main():
    args = parse_args()
    exported = json.loads(args.firebase_export.read_text())
    users = exported.get("users") or []
    if len(users) != args.expected_count:
        raise SystemExit(f"Expected {args.expected_count} Firebase user(s), found {len(users)}")
    payloads = [migration_payload(user, args) for user in users]
    if not args.apply:
        print(json.dumps({
            "mode": "dry-run",
            "users": len(payloads),
            "firebase_uids": [item["external_id"] for item in payloads],
            "password_users": sum("password_digest" in item for item in payloads),
        }, indent=2))
        return

    secret_key = os.getenv("CLERK_SECRET_KEY", "")
    if not secret_key:
        raise SystemExit("CLERK_SECRET_KEY is required with --apply")
    clerk = Clerk(bearer_auth=secret_key)
    results = []
    for payload in payloads:
        existing = clerk.users.list(request={"external_id": [payload["external_id"]], "limit": 2})
        if len(existing) > 1:
            raise RuntimeError(f"Multiple Clerk users have external_id {payload['external_id']}")
        clerk_user = existing[0] if existing else clerk.users.create(**payload)
        results.append({
            "firebase_uid": payload["external_id"],
            "clerk_user_id": clerk_user.id,
            "status": "existing" if existing else "created",
        })
        if args.write_firestore_mapping:
            import config
            from services.firestore import get_firestore_client
            from services.tenancy import now

            ref = get_firestore_client().collection(config.FIRESTORE_USERS_COLLECTION).document(
                payload["external_id"])
            if not ref.get().exists:
                raise RuntimeError(f"Firestore user {payload['external_id']} does not exist")
            ref.set({
                "auth_provider": "clerk",
                "auth_status": "active",
                "clerk_user_id": clerk_user.id,
                "legacy_firebase_uid": payload["external_id"],
                "updated_at": now(),
            }, merge=True)
    print(json.dumps({"mode": "applied", "users": results}, indent=2))


if __name__ == "__main__":
    main()
