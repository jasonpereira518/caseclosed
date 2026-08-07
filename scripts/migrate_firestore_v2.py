#!/usr/bin/env python3
"""Migrate legacy user_contexts into workspace-scoped normalized matters.

Dry-run is the default. Run with --apply only after reviewing the generated
report and taking a Firestore export/backup.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from firebase_admin import auth as firebase_auth  # noqa: E402

import config  # noqa: E402
from services.firestore import get_firestore_client  # noqa: E402
from services.matters import create_matter, locate_matter  # noqa: E402
from services.tenancy import ensure_user, personal_workspace_id  # noqa: E402


def auth_claims_for_email(email):
    record = firebase_auth.get_user_by_email(email)
    providers = [item.provider_id for item in record.provider_data]
    return {"uid": record.uid, "email": record.email, "email_verified": record.email_verified,
            "name": record.display_name, "picture": record.photo_url,
            "firebase": {"sign_in_provider": " ".join(providers)}}


def migrate(apply=False):
    db = get_firestore_client()
    users = {}
    for snap in db.collection(config.FIRESTORE_USERS_COLLECTION).stream():
        data = snap.to_dict() or {}
        email = str(data.get("email") or "").strip().lower()
        if email:
            try:
                claims = auth_claims_for_email(email)
                users[snap.id] = claims
                if apply:
                    ensure_user(claims)
            except firebase_auth.UserNotFoundError:
                users[snap.id] = None

    report = {"mode": "apply" if apply else "dry-run", "migrated": [], "skipped": [], "quarantined": []}
    for snap in db.collection(config.FIRESTORE_COLLECTION).stream():
        data = snap.to_dict() or {}
        legacy_uid = str(data.get("user_id") or "")
        if not legacy_uid:
            report["quarantined"].append({"context_id": snap.id, "reason": "missing user_id"})
            if apply:
                db.collection("migration_quarantine").document(snap.id).set(
                    {"reason": "missing user_id", "source_collection": config.FIRESTORE_COLLECTION,
                     "quarantined_at": datetime.now(timezone.utc)})
            continue
        claims = users.get(legacy_uid)
        if not claims:
            report["quarantined"].append({"context_id": snap.id, "reason": "no matching Firebase verified email"})
            continue
        if locate_matter(snap.id)[0]:
            report["skipped"].append({"context_id": snap.id, "reason": "already migrated"})
            continue
        if apply:
            create_matter(personal_workspace_id(claims["uid"]), claims["uid"], matter_id=snap.id, initial=data)
            snap.reference.set({"migration_status": "migrated", "migrated_uid": claims["uid"],
                                "migrated_at": datetime.now(timezone.utc)}, merge=True)
        report["migrated"].append({"context_id": snap.id, "legacy_uid": legacy_uid,
                                   "firebase_uid": claims["uid"]})
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="write changes; default is dry-run")
    parser.add_argument("--report", default="migration-report.json")
    args = parser.parse_args()
    result = migrate(args.apply)
    Path(args.report).write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({key: len(value) if isinstance(value, list) else value for key, value in result.items()}, indent=2))
