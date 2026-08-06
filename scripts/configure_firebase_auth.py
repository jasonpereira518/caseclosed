#!/usr/bin/env python3
"""Inspect or add Firebase Authentication authorized web domains."""
from __future__ import annotations

import argparse
import json

import google.auth
from google.auth.transport.requests import AuthorizedSession


def configure(project: str, domains: list[str], *, apply: bool) -> dict:
    credentials, _ = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"])
    session = AuthorizedSession(credentials)
    config_url = (
        "https://identitytoolkit.googleapis.com/admin/v2/"
        f"projects/{project}/config")
    response = session.get(config_url, timeout=30)
    response.raise_for_status()
    config = response.json()
    existing = list(config.get("authorizedDomains") or [])
    requested = [domain.strip().lower() for domain in domains if domain.strip()]
    updated = list(dict.fromkeys(existing + requested))
    changed = updated != existing
    if apply and changed:
        response = session.patch(
            config_url,
            params={"updateMask": "authorizedDomains"},
            json={"authorizedDomains": updated},
            timeout=30,
        )
        response.raise_for_status()
        updated = list(response.json().get("authorizedDomains") or updated)

    provider_url = (
        "https://identitytoolkit.googleapis.com/admin/v2/"
        f"projects/{project}/defaultSupportedIdpConfigs/google.com")
    provider_response = session.get(provider_url, timeout=30)
    google_enabled = (
        bool(provider_response.json().get("enabled"))
        if provider_response.ok else False)
    return {
        "authorized_domains": updated if apply else existing,
        "change_required": changed and not apply,
        "changed": changed and apply,
        "google_provider_enabled": google_enabled,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--domain", action="append", default=[])
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    print(json.dumps(configure(args.project, args.domain, apply=args.apply), indent=2))
