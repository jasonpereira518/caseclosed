"""Clerk authentication flows. Clerk is the only identity provider; the
Firebase Authentication rollback path was retired in Cycle 2 (rollback story:
git revert + redeploy)."""
from urllib.parse import urlparse

from flask import Blueprint, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


# Browsers strip ASCII tab/CR/LF before parsing a URL, so "/<TAB>\evil.com"
# must be normalized before it is inspected rather than after.
_URL_STRIPPED_CHARS = str.maketrans("", "", "\t\r\n")


def _safe_next(value):
    """Accept only same-origin, path-relative destinations.

    urlparse on its own is not enough: browsers normalize "\\" to "/" inside a
    special scheme, so "/\\evil.com" -- which urlparse reports as a relative
    path with no netloc -- resolves to https://evil.com. That matters because
    the value is reflected raw into data-next (templates/login.html) and can
    reach window.location.assign().
    """
    candidate = (value or "").translate(_URL_STRIPPED_CHARS).strip()
    parsed = urlparse(candidate)
    if (candidate.startswith("/")
            and not candidate.startswith(("//", "/\\"))
            and not parsed.scheme
            and not parsed.netloc):
        return candidate
    return url_for("main.workspace")


@auth_bp.route("/login")
def login():
    next_url = _safe_next(request.args.get("next"))
    invite_token = request.args.get("invite", "")
    if current_user.is_authenticated:
        if invite_token:
            return redirect(url_for("auth.complete_login", next=next_url, invite=invite_token))
        return redirect(next_url)
    complete_url = url_for("auth.complete_login", next=next_url, invite=invite_token)
    sso_callback_url = url_for("auth.sso_callback", next=next_url, invite=invite_token)
    return render_template(
        "login.html",
        next_url=next_url,
        invite_token=invite_token,
        complete_url=complete_url,
        sso_callback_url=sso_callback_url,
        error=request.args.get("error", ""),
    )


@auth_bp.route("/sso-callback")
def sso_callback():
    """Land here after Google redirects back mid-OAuth; finish the Clerk handshake client-side."""
    next_url = _safe_next(request.args.get("next"))
    invite_token = request.args.get("invite", "")
    complete_url = url_for("auth.complete_login", next=next_url, invite=invite_token)
    if current_user.is_authenticated:
        return redirect(complete_url)
    return render_template(
        "auth_callback.html",
        next_url=next_url,
        invite_token=invite_token,
        complete_url=complete_url,
    )


@auth_bp.route("/complete")
@login_required
def complete_login():
    """Finish app-specific onboarding after Clerk establishes its session."""
    next_url = _safe_next(request.args.get("next"))
    invite_token = request.args.get("invite", "")
    if invite_token:
        from services.tenancy import AuthorizationError, ValidationError, accept_invitation

        try:
            accept_invitation(str(current_user.get_id()), current_user.email, invite_token)
        except (AuthorizationError, ValidationError) as exc:
            # The user is signed in either way; a redirect would silently
            # swallow the failure (the login page bounces authenticated
            # visitors). Show the problem, then let them continue.
            session.clear()
            return render_template("invite_error.html", error=str(exc), next_url=next_url)
    session.clear()
    return redirect(next_url)


@auth_bp.route("/logout", methods=["GET", "POST"])
def logout():
    session.clear()
    return render_template("logout.html", redirect_url=url_for("main.index"))
