#!/usr/bin/env python3
"""Generic config-file model switcher.

Backs up each target file, then replaces one model id string with another.
Knows nothing about any specific harness (no openclaw.json, no restart
command); adapters handle that step after calling this, see
adapters/openclaw/README.md for an example.
"""
import argparse
import os
import shutil
import sys
from datetime import datetime

from free_models_monitor.monitor import (
    default_state_dir,
    find_best_fallback,
    load_banned_models,
    load_fallback_chain,
    load_json_safe,
)


def backup_file(path):
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = f"{path}.bak-{ts}"
    shutil.copy2(path, backup_path)
    return backup_path


def apply_switch(path, from_model, to_model, apply):
    with open(path) as f:
        content = f.read()
    count = content.count(from_model)
    if count == 0 or not apply:
        return count, None
    backup_path = backup_file(path)
    with open(path, "w") as f:
        f.write(content.replace(from_model, to_model))
    return count, backup_path


def resolve_auto_target(state_dir, from_model, min_context):
    snapshot = load_json_safe(os.path.join(state_dir, "snapshot.json"), {})
    banned = load_banned_models(state_dir)
    fallback_chain = load_fallback_chain(None)
    return find_best_fallback(
        snapshot,
        fallback_chain,
        banned,
        exclude_model=from_model,
        min_context=min_context,
    )


def parse_args(argv=None):
    p = argparse.ArgumentParser(
        prog="free-models-switch",
        description="Replace a model id across one or more config files.",
    )
    p.add_argument("--from", dest="from_model", required=True)
    p.add_argument("--to", dest="to_model", default=None)
    p.add_argument(
        "--auto",
        action="store_true",
        help="pick --to from the fallback chain using the last snapshot",
    )
    p.add_argument("--file", dest="files", action="append", default=[], required=True)
    p.add_argument("--apply", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--state-dir", default=None)
    p.add_argument("--min-context", type=int, default=32768)
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    apply = args.apply and not args.dry_run

    to_model = args.to_model
    if args.auto or not to_model:
        state_dir = args.state_dir or default_state_dir()
        to_model, info = resolve_auto_target(
            state_dir, args.from_model, args.min_context
        )
        if not to_model:
            print("ERROR: no fallback model found in snapshot", file=sys.stderr)
            return 1
        print(f"auto-selected fallback: {to_model} ({info.get('name', 'unknown')})")

    print(f"PLAN: {args.from_model} -> {to_model}")
    print(f"apply={apply}")

    any_found = False
    for path in args.files:
        if not os.path.isfile(path):
            print(f"  SKIP {path}: file not found", file=sys.stderr)
            continue
        any_found = True
        count, backup_path = apply_switch(path, args.from_model, to_model, apply)
        if count == 0:
            print(f"  {path}: no occurrences")
        elif apply:
            print(f"  {path}: replaced {count} occurrence(s), backup at {backup_path}")
        else:
            print(f"  {path}: would replace {count} occurrence(s) (dry run)")

    return 0 if any_found else 1


if __name__ == "__main__":
    sys.exit(main())
