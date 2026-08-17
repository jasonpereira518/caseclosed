"""Account center, workspace administration, export, and deletion APIs."""
from __future__ import annotations

import os
import tempfile

from flask import Blueprint, jsonify, request, session
from flask_login import current_user, login_required
from google.cloud import firestore as gc_firestore
from werkzeug.utils import secure_filename

import config
from models.context import default_context
from services.firestore import get_firestore_client
from services.mailer import send_workspace_invitation
from services.jobs import create_account_job, get_account_job, update_account_job
from services.matters import create_matter, delete_matter, list_matters, patch_matter, require_matter
from services.storage import delete_prefix, signed_download_url, upload_avatar
from services.task_queue import enqueue_account_job
from services.tenancy import (
    AuthorizationError, ValidationError, accept_invitation, active_matter, active_workspace,
    audit, create_invitation, create_team, get_profile, list_members,
    list_workspaces, membership, now, remove_member, require_workspace,
    revoke_invitation, set_active_matter, set_active_workspace, set_member_role, transfer_ownership, update_profile,
)

account_bp = Blueprint("account", __name__, url_prefix="/api")


def _uid():
    return str(current_user.get_id())


def _error(exc):
    if isinstance(exc, AuthorizationError):
        return jsonify({"error": str(exc)}), 403
    return jsonify({"error": str(exc)}), 400


@account_bp.route("/bootstrap")
@login_required
def bootstrap():
    uid = _uid()
    workspaces = list_workspaces(uid)
    wid = active_workspace(uid)
    matters = list_matters(wid, uid) if wid else []
    return jsonify({"profile": get_profile(uid), "workspaces": workspaces,
                    "active_workspace_id": wid, "matters": matters,
                    "active_matter_id": session.get("context_id") or active_matter(uid)})


@account_bp.route("/account", methods=["GET", "PATCH"])
@login_required
def account():
    if request.method == "GET":
        return jsonify({"profile": get_profile(_uid()), "workspaces": list_workspaces(_uid())})
    try:
        return jsonify({"profile": update_profile(_uid(), request.get_json(silent=True) or {})})
    except (ValidationError, ValueError) as exc:
        return _error(exc)


@account_bp.route("/account/recent-searches", methods=["GET", "POST"])
@login_required
def recent_searches():
    ref = get_firestore_client().collection(config.FIRESTORE_USERS_COLLECTION).document(_uid())
    current = (ref.get().to_dict() or {}).get("recent_searches") or []
    if request.method == "GET":
        return jsonify({"recent_searches": current[:5]})
    query = str((request.get_json(silent=True) or {}).get("query") or "").strip()[:200]
    if query:
        current = [item for item in current if str(item).lower() != query.lower()]
        current.insert(0, query)
        current = current[:5]
        ref.set({"recent_searches": current, "updated_at": now()}, merge=True)
    return jsonify({"recent_searches": current})


@account_bp.route("/account/avatar", methods=["POST"])
@login_required
def account_avatar():
    upload = request.files.get("avatar")
    if not upload or not upload.filename:
        return jsonify({"error": "avatar is required"}), 400
    if upload.mimetype not in {"image/jpeg", "image/png", "image/webp"}:
        return jsonify({"error": "avatar must be JPEG, PNG, or WebP"}), 400
    suffix = os.path.splitext(secure_filename(upload.filename))[1].lower()
    fd, path = tempfile.mkstemp(suffix=suffix)
    os.close(fd)
    try:
        upload.save(path)
        if os.path.getsize(path) > 5 * 1024 * 1024:
            return jsonify({"error": "avatar must be 5 MB or smaller"}), 400
        storage_path = upload_avatar(path, _uid(), f"avatar{suffix}", upload.mimetype)
        ref = get_firestore_client().collection(config.FIRESTORE_USERS_COLLECTION).document(_uid())
        ref.set({"avatar_storage_path": storage_path, "updated_at": now()}, merge=True)
        profile = get_profile(_uid())
        return jsonify({"profile": profile})
    finally:
        if os.path.exists(path):
            os.remove(path)


@account_bp.route("/workspaces", methods=["GET", "POST"])
@login_required
def workspaces():
    if request.method == "GET":
        return jsonify({"workspaces": list_workspaces(_uid())})
    try:
        return jsonify({"workspace": create_team(_uid(), (request.get_json(silent=True) or {}).get("name"))}), 201
    except (ValidationError, AuthorizationError) as exc:
        return _error(exc)


@account_bp.route("/workspaces/<workspace_id>/activate", methods=["POST"])
@login_required
def activate_workspace(workspace_id):
    try:
        set_active_workspace(_uid(), workspace_id)
        session["workspace_id"] = workspace_id
        matters = [m for m in list_matters(workspace_id, _uid())
                   if m.get("status") != "archived"]
        session["context_id"] = matters[0]["matter_id"] if matters else create_matter(
            workspace_id, _uid(), initial=default_context())[0]
        set_active_matter(_uid(), session["context_id"])
        return jsonify({"workspace_id": workspace_id, "matters": list_matters(workspace_id, _uid()),
                        "active_matter_id": session["context_id"]})
    except (AuthorizationError, ValidationError) as exc:
        return _error(exc)


@account_bp.route("/workspaces/<workspace_id>/members")
@login_required
def workspace_members(workspace_id):
    try:
        return jsonify({"members": list_members(workspace_id, _uid())})
    except AuthorizationError as exc:
        return _error(exc)


@account_bp.route("/workspaces/<workspace_id>/matters")
@login_required
def workspace_matters(workspace_id):
    try:
        return jsonify({"matters": list_matters(workspace_id, _uid())})
    except AuthorizationError as exc:
        return _error(exc)


@account_bp.route("/workspaces/<workspace_id>/invitations", methods=["POST"])
@login_required
def invite_member(workspace_id):
    data = request.get_json(silent=True) or {}
    try:
        invitation, token = create_invitation(workspace_id, _uid(), data.get("email"), data.get("role", "member"))
        workspace = next(item for item in list_workspaces(_uid()) if item["workspace_id"] == workspace_id)
        invite_url = f"{config.APP_BASE_URL.rstrip('/')}/auth/login?invite={token}"
        try:
            sent = send_workspace_invitation(invitation["email"], workspace.get("name", "a workspace"), invite_url)
        except RuntimeError:
            revoke_invitation(workspace_id, _uid(), invitation["invitation_id"])
            raise
        response = {"invitation": invitation, "email_sent": sent}
        if config.DEBUG:
            response["invite_url"] = invite_url
        return jsonify(response), 201
    except (AuthorizationError, ValidationError, RuntimeError, StopIteration) as exc:
        return _error(exc)


@account_bp.route("/workspaces/<workspace_id>/invitations/<invitation_id>", methods=["DELETE"])
@login_required
def cancel_invitation(workspace_id, invitation_id):
    try:
        revoke_invitation(workspace_id, _uid(), invitation_id)
        return jsonify({"status": "ok"})
    except (AuthorizationError, ValidationError) as exc:
        return _error(exc)


@account_bp.route("/invitations/accept", methods=["POST"])
@login_required
def accept_workspace_invitation():
    try:
        wid = accept_invitation(_uid(), current_user.email, (request.get_json(silent=True) or {}).get("token"))
        return jsonify({"workspace_id": wid})
    except (AuthorizationError, ValidationError) as exc:
        return _error(exc)


@account_bp.route("/workspaces/<workspace_id>/members/<target_uid>", methods=["PATCH", "DELETE"])
@login_required
def manage_member(workspace_id, target_uid):
    try:
        if request.method == "PATCH":
            set_member_role(workspace_id, _uid(), target_uid, (request.get_json(silent=True) or {}).get("role"))
        else:
            remove_member(workspace_id, _uid(), target_uid)
        return jsonify({"status": "ok"})
    except (AuthorizationError, ValidationError) as exc:
        return _error(exc)


@account_bp.route("/workspaces/<workspace_id>/transfer-ownership", methods=["POST"])
@login_required
def workspace_transfer(workspace_id):
    try:
        transfer_ownership(workspace_id, _uid(), str((request.get_json(silent=True) or {}).get("uid") or ""))
        return jsonify({"status": "ok"})
    except (AuthorizationError, ValidationError) as exc:
        return _error(exc)


@account_bp.route("/workspaces/<workspace_id>", methods=["DELETE"])
@login_required
def delete_workspace(workspace_id):
    try:
        require_workspace(workspace_id, _uid(), owner=True)
        db = get_firestore_client()
        ref = db.collection(config.FIRESTORE_WORKSPACES_COLLECTION).document(workspace_id)
        workspace = ref.get().to_dict() or {}
        if workspace.get("type") != "team":
            raise ValidationError("personal workspaces are deleted with the account")
        for summary in list_matters(workspace_id, _uid()):
            delete_matter(summary["matter_id"], _uid())
        for member_doc in ref.collection("members").stream():
            db.collection(config.FIRESTORE_USERS_COLLECTION).document(member_doc.id).set(
                {"workspace_ids": gc_firestore.ArrayRemove([workspace_id]),
                 "updated_at": now()}, merge=True)
            member_doc.reference.delete()
        for invitation in db.collection(config.FIRESTORE_INVITATIONS_COLLECTION).where("workspace_id", "==", workspace_id).stream():
            invitation.reference.set({"status": "revoked", "updated_at": now()}, merge=True)
        for event in ref.collection("audit_events").stream():
            event.reference.delete()
        delete_prefix(f"workspaces/{workspace_id}/")
        ref.delete()
        return jsonify({"status": "deleted"})
    except (AuthorizationError, ValidationError) as exc:
        return _error(exc)


@account_bp.route("/matters/<matter_id>/assignments", methods=["PATCH"])
@login_required
def matter_assignments(matter_id):
    try:
        workspace_id, _, data = require_matter(matter_id, _uid())
        assigned = [str(value) for value in (request.get_json(silent=True) or {}).get("user_ids", [])]
        if any(not membership(workspace_id, uid) for uid in assigned):
            raise ValidationError("every assignee must be an active workspace member")
        assigned = list(dict.fromkeys(assigned))
        patch_matter(matter_id, _uid(), root={"assigned_user_ids": assigned})
        audit(workspace_id, _uid(), "matter.assignments_changed", {"assigned_user_ids": assigned}, matter_id)
        return jsonify({"assigned_user_ids": assigned})
    except (AuthorizationError, ValidationError) as exc:
        return _error(exc)


@account_bp.route("/account/export", methods=["POST"])
@login_required
def create_export():
    uid = _uid()
    job = None
    try:
        job, created = create_account_job(uid, "account_export", {})
        if created:
            enqueue_account_job(uid, job["job_id"])
    except Exception as exc:
        if job:
            update_account_job(uid, job["job_id"], status="failed", stage="enqueue_failed",
                               error={"code": "enqueue_failed", "message": str(exc)[:300]})
        return jsonify({"error": "could not schedule export"}), 500
    job["status_url"] = f"/api/account/jobs/{job['job_id']}"
    return jsonify(job), 202


@account_bp.route("/account/jobs/<job_id>")
@login_required
def account_job(job_id):
    job = get_account_job(_uid(), job_id)
    if not job:
        return jsonify({"error": "job not found"}), 404
    result = job.get("result") or {}
    if job.get("status") == "succeeded" and result.get("storage_path"):
        job["download_url"] = signed_download_url(result["storage_path"])
    return jsonify(job)


@account_bp.route("/account", methods=["DELETE"])
@login_required
def delete_account():
    uid = _uid()
    if (request.get_json(silent=True) or {}).get("confirmation") != "DELETE":
        return jsonify({"error": "confirmation must equal DELETE"}), 400
    workspaces = list_workspaces(uid)
    owned_teams = [w for w in workspaces if w.get("type") == "team" and w.get("role") == "owner"]
    if owned_teams:
        return jsonify({"error": "transfer or delete owned teams first",
                        "workspace_ids": [w["workspace_id"] for w in owned_teams]}), 409
    db = get_firestore_client()
    user_ref = db.collection(config.FIRESTORE_USERS_COLLECTION).document(uid)
    user_record = user_ref.get().to_dict() or {}
    for workspace in workspaces:
        wid = workspace["workspace_id"]
        if workspace.get("type") == "personal":
            for matter in list_matters(wid, uid):
                delete_matter(matter["matter_id"], uid)
            for member_doc in db.collection(config.FIRESTORE_WORKSPACES_COLLECTION).document(wid).collection("members").stream():
                member_doc.reference.delete()
            for event in db.collection(config.FIRESTORE_WORKSPACES_COLLECTION).document(wid).collection("audit_events").stream():
                event.reference.delete()
            db.collection(config.FIRESTORE_WORKSPACES_COLLECTION).document(wid).delete()
        else:
            workspace_ref = db.collection(config.FIRESTORE_WORKSPACES_COLLECTION).document(wid)
            workspace_ref.collection("members").document(uid).set(
                {"status": "removed", "former_user": True, "updated_at": now()}, merge=True)
            for matter_doc in workspace_ref.collection("matters").stream():
                matter_doc.reference.set({"assigned_user_ids": gc_firestore.ArrayRemove([uid]),
                                          "updated_at": now()}, merge=True)
    delete_prefix(f"users/{uid}/")
    for job in user_ref.collection("jobs").stream():
        job.reference.delete()
    if current_user.email:
        for invite in db.collection(config.FIRESTORE_INVITATIONS_COLLECTION).where("email", "==", current_user.email.lower()).stream():
            invite.reference.set({"status": "revoked", "email": None, "updated_at": now()}, merge=True)
    from services.clerk_auth import delete_clerk_identity

    clerk_user_id = user_record.get("clerk_user_id")
    if not clerk_user_id:
        user_ref.set({"account_deletion_error": "missing Clerk user id", "updated_at": now()}, merge=True)
        return jsonify({"error": "identity record is incomplete; contact support"}), 409
    try:
        delete_clerk_identity(clerk_user_id)
    except Exception:
        user_ref.set({"account_deletion_error": "Clerk identity deletion failed", "updated_at": now()}, merge=True)
        return jsonify({"error": "account data was removed, but identity deletion must be retried"}), 502
    user_ref.delete()
    response = jsonify({"status": "deleted"})
    session.clear()
    return response
