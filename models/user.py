"""
Firestore-backed user records for Flask-Login.
"""
from flask_login import UserMixin

import config
from services.firestore import get_firestore_client


class User(UserMixin):
    """Flask-Login user backed by Google account fields."""

    def __init__(self, id, email=None, name=None, profile_pic=None, **profile):
        self.id = str(id)
        self.email = email
        self.name = name
        self.profile_pic = profile_pic
        self.profile = profile

    @property
    def access_status(self):
        """None (pre-gate account, treated as approved), pending, approved, or revoked."""
        return self.profile.get("access_status")


def load_user(user_id):
    """Load a User from Firestore by Google user id (sub), or None."""
    if not user_id:
        return None
    try:
        db = get_firestore_client()
    except RuntimeError:
        return None
    snap = db.collection(config.FIRESTORE_USERS_COLLECTION).document(str(user_id)).get()
    if not snap.exists:
        return None
    d = snap.to_dict() or {}
    profile_pic = d.get("avatar_url") or d.get("profile_pic")
    if d.get("avatar_storage_path"):
        try:
            from services.storage import signed_download_url
            profile_pic = signed_download_url(d["avatar_storage_path"], minutes=60)
        except RuntimeError:
            profile_pic = None
    return User(
        id=str(user_id),
        email=d.get("email"),
        name=d.get("display_name") or d.get("name"),
        profile_pic=profile_pic,
        **{key: value for key, value in d.items() if key not in {"name", "display_name", "profile_pic", "avatar_url", "email"}},
    )
