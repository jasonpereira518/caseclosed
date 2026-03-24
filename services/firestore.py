"""
Firestore persistence for session context documents.
"""
import logging
import os

import firebase_admin
from firebase_admin import credentials, firestore

import config

_db = None
_init_error = None


def _ensure_initialized():
    """Initialize Firebase Admin and Firestore client once. Logs errors; returns True if usable."""
    global _db, _init_error
    if _db is not None:
        return True
    if _init_error is not None:
        return False
    cred_path = config.FIREBASE_CREDENTIALS
    if not cred_path or not os.path.isfile(cred_path):
        _init_error = FileNotFoundError(
            f"Firebase credentials file not found: {cred_path!r}"
        )
        logging.error(
            "Firestore: credentials file missing or invalid path (%s). "
            "Context persistence will not work until FIREBASE_CREDENTIALS points to a valid JSON key.",
            cred_path,
        )
        return False
    try:
        if not firebase_admin._apps:
            cred = credentials.Certificate(cred_path)
            firebase_admin.initialize_app(cred)
        _db = firestore.client()
        logging.info("Firestore client initialized (collection=%s).", config.FIRESTORE_COLLECTION)
        return True
    except Exception as e:
        _init_error = e
        logging.error(
            "Firestore initialization failed: %s. Context persistence is unavailable.",
            e,
            exc_info=True,
        )
        return False


def get_firestore_client():
    """Return the Firestore client, initializing if needed. Raises if initialization failed."""
    if not _ensure_initialized():
        raise RuntimeError(
            "Firestore is not available; check logs for Firebase initialization errors."
        ) from _init_error
    return _db


def save_context(context_id, data):
    """Save or replace the context document for context_id."""
    db = get_firestore_client()
    col = db.collection(config.FIRESTORE_COLLECTION)
    col.document(str(context_id)).set(dict(data))


def load_context(context_id):
    """Load context document; return None if missing."""
    if not _ensure_initialized():
        return None
    db = _db
    col = db.collection(config.FIRESTORE_COLLECTION)
    snap = col.document(str(context_id)).get()
    if not snap.exists:
        return None
    data = snap.to_dict()
    if data:
        data.pop("last_accessed", None)
    return data


def delete_context(context_id):
    """Delete the context document for context_id."""
    db = get_firestore_client()
    col = db.collection(config.FIRESTORE_COLLECTION)
    col.document(str(context_id)).delete()


def list_contexts():
    """Return all context document IDs in the collection."""
    db = get_firestore_client()
    col = db.collection(config.FIRESTORE_COLLECTION)
    return [doc.id for doc in col.stream()]


def try_startup_init():
    """Attempt early init so misconfiguration is visible when the app loads modules."""
    _ensure_initialized()
