"""
Firestore-backed user records for Flask-Login.
"""
from flask_login import UserMixin

import config
from services.firestore import get_firestore_client


class User(UserMixin):
    """Flask-Login user backed by Google account fields."""

    def __init__(self, id, email=None, name=None, profile_pic=None):
        self.id = str(id)
        self.email = email
        self.name = name
        self.profile_pic = profile_pic


def save_user(user_data):
    """
    Save or merge a user document in Firestore.
    user_data: dict with keys id (Google sub), email, name, profile_pic (optional picture URL).
    """
    uid = str(user_data["id"])
    doc = {
        "email": user_data.get("email"),
        "name": user_data.get("name"),
        "profile_pic": user_data.get("profile_pic") or user_data.get("picture"),
    }
    db = get_firestore_client()
    db.collection(config.FIRESTORE_USERS_COLLECTION).document(uid).set(doc, merge=True)


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
    return User(
        id=str(user_id),
        email=d.get("email"),
        name=d.get("name"),
        profile_pic=d.get("profile_pic"),
    )
