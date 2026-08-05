#!/usr/bin/env python3
"""Validate deployment configuration without making external changes."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.runtime_config import validate_runtime_config  # noqa: E402


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--production", action="store_true")
    args = parser.parse_args()
    result = validate_runtime_config(production=args.production)
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["valid"] else 1)
