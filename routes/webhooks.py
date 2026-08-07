"""Verified Clerk lifecycle webhooks."""
from __future__ import annotations

from datetime import timedelta

from flask import Blueprint, jsonify, request
from svix.webhooks import Webhook, WebhookVerificationError

import config
from services.clerk_auth import mark_clerk_user_deleted, sync_clerk_user
from services.firestore import get_firestore_client
from services.tenancy import now


webhooks_bp = Blueprint("webhooks", __name__, url_prefix="/webhooks")


@webhooks_bp.post("/clerk")
def clerk_webhook():
    if not config.CLERK_WEBHOOK_SIGNING_SECRET:
        return jsonify({"error": "Clerk webhook is not configured"}), 503
    try:
        event = Webhook(config.CLERK_WEBHOOK_SIGNING_SECRET).verify(
            request.get_data(), dict(request.headers))
    except WebhookVerificationError:
        return jsonify({"error": "invalid signature"}), 400

    delivery_id = str(request.headers.get("svix-id") or "").strip()
    event_ref = None
    if delivery_id:
        event_ref = get_firestore_client().collection(
            config.FIRESTORE_CLERK_WEBHOOK_EVENTS_COLLECTION).document(delivery_id)
        if event_ref.get().exists:
            return jsonify({"status": "duplicate"})

    event_type = event.get("type")
    data = event.get("data") or {}
    if event_type in {"user.created", "user.updated"}:
        sync_clerk_user(data)
    elif event_type == "user.deleted" and data.get("id"):
        mark_clerk_user_deleted(str(data["id"]))

    if event_ref:
        timestamp = now()
        event_ref.set({
            "event_type": event_type,
            "processed_at": timestamp,
            "expires_at": timestamp + timedelta(hours=24),
        })
    return jsonify({"status": "ok"})
