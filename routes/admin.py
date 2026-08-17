"""Admin surface for the access gate.

Admins are the emails in config.ADMIN_EMAILS. Everyone else — including
signed-in users and anonymous visitors — gets a 404, not a 403, so the
surface's existence is not advertised.
"""
import logging

from flask import Blueprint, abort, jsonify, render_template, request
from flask_login import current_user

import config
from services.mailer import send_access_approved
from services.tenancy import ValidationError, list_access_requests, set_access_status

admin_bp = Blueprint("admin", __name__)


def _require_admin():
    if not current_user.is_authenticated:
        abort(404)
    email = (current_user.email or "").strip().lower()
    if not email or email not in config.ADMIN_EMAILS:
        abort(404)


@admin_bp.route("/admin/access")
def access_dashboard():
    _require_admin()
    return render_template("admin_access.html", requests=list_access_requests())


@admin_bp.route("/api/admin/access/<uid>", methods=["POST"])
def update_access(uid):
    _require_admin()
    action = str((request.get_json(silent=True) or {}).get("action") or "").strip()
    if action not in ("approve", "revoke"):
        return jsonify({"error": "action must be approve or revoke"}), 400
    try:
        record = set_access_status(uid, "approved" if action == "approve" else "revoked")
    except ValidationError as exc:
        return jsonify({"error": str(exc)}), 400

    # Access is the source of truth; the email is a courtesy. A failed send
    # must not roll back the approval — the dashboard surfaces mail_sent
    # instead so the admin can follow up by hand.
    mail_sent = False
    if record["access_status"] == "approved" and record.get("email"):
        try:
            mail_sent = bool(send_access_approved(record["email"]))
        except Exception as exc:
            logging.warning("Approval mail to %s failed: %s", record["email"], exc.__class__.__name__)
    return jsonify({**record, "mail_sent": mail_sent})
