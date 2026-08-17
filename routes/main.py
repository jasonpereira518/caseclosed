from datetime import datetime, timezone

from flask import Blueprint, redirect, render_template, url_for
from flask_login import current_user, login_required

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def index():
    primary_cta_url = (
        url_for("main.workspace")
        if current_user.is_authenticated
        else url_for("auth.login")
    )
    return render_template(
        "landing.html",
        primary_cta_url=primary_cta_url,
        current_year=datetime.now(timezone.utc).year,
    )


@main_bp.route("/app")
@login_required
def workspace():
    return render_template(
        "workspace.html",
        user_name=current_user.name,
        user_email=current_user.email,
        user_profile_pic=current_user.profile_pic,
    )


@main_bp.route("/privacy")
def privacy():
    return render_template("privacy.html", current_year=datetime.now(timezone.utc).year)


@main_bp.route("/terms")
def terms():
    return render_template("terms.html", current_year=datetime.now(timezone.utc).year)


@main_bp.route("/waitlist")
@login_required
def waitlist():
    """Where the access gate parks signed-in-but-unapproved accounts."""
    if current_user.access_status in (None, "", "approved"):
        return redirect(url_for("main.workspace"))
    return render_template(
        "waitlist.html",
        user_name=current_user.name,
        user_email=current_user.email,
    )


@main_bp.route("/account")
@login_required
def account_center():
    return render_template("account.html", user_name=current_user.name,
                           user_email=current_user.email,
                           user_profile_pic=current_user.profile_pic)
