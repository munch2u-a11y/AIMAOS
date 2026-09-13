#!/usr/bin/env python3
"""Deterministic CLI boundary for the shared Codex/Claude case skill."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def _find_root(explicit: str | None) -> Path:
    candidates = []
    if explicit:
        candidates.append(Path(explicit))
    if os.environ.get("AIMAOS_ROOT"):
        candidates.append(Path(os.environ["AIMAOS_ROOT"]))
    candidates.extend([Path.cwd(), *Path.cwd().parents])
    for candidate in candidates:
        resolved = candidate.expanduser().resolve()
        if (resolved / "aimaos_config.yaml").is_file() and (resolved / "core").is_dir():
            return resolved
    raise FileNotFoundError(
        "Could not locate AIMAOS. Run from its repository or pass --aimaos-root."
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage an AIMAOS matter-local case specialist.")
    parser.add_argument("operation", choices=("initialize", "refresh", "status", "audit", "dry-run"))
    parser.add_argument("--case", required=True, dest="case_reference", help="Approved case path or AIMAOS case identifier.")
    parser.add_argument("--client-name", help="Matter name for a generic approved folder.")
    parser.add_argument("--aimaos-root", help="AIMAOS repository root when not running inside it.")
    parser.add_argument("--force", action="store_true", help="Review even when the successful digest is unchanged.")
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        root = _find_root(args.aimaos_root)
        sys.path.insert(0, str(root))
        from core.case_specialist_service import (
            audit_case,
            case_status,
            initialize_case,
            refresh_case,
        )

        common = {"client_name": args.client_name}
        if args.operation == "initialize":
            result = initialize_case(args.case_reference, **common)
        elif args.operation == "status":
            result = case_status(args.case_reference, **common)
        elif args.operation == "audit":
            result = audit_case(args.case_reference, **common)
        else:
            result = refresh_case(
                args.case_reference,
                force=args.force,
                dry_run=args.operation == "dry-run",
                reason=f"{args.operation} requested by plugin skill",
                **common,
            )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except Exception as exc:  # safe CLI boundary; no local path echo
        print(json.dumps({"status": "error", "error": str(exc)[:1000]}, indent=2), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
