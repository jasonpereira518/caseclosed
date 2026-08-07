"""Public liveness and configuration-readiness probes."""
from flask import Blueprint, jsonify

import config
from services.runtime_config import validate_runtime_config


system_bp = Blueprint("system", __name__)


@system_bp.route("/healthz")
@system_bp.route("/livez")
def healthz():
    return jsonify({"status": "ok"})


@system_bp.route("/readyz")
def readyz():
    production = config.ENVIRONMENT == "production"
    report = validate_runtime_config(production=production)
    body = {"status": "ready" if report["valid"] else "not_ready",
            "mode": report["mode"], "warning_count": len(report["warnings"])}
    return jsonify(body), 200 if report["valid"] else 503
