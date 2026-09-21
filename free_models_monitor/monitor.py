#!/usr/bin/env python3
"""Portable monitor for free-tier LLM models across providers.

Tracks free models (OpenRouter, Groq) between runs, reports what was added
or removed, suggests a fallback per a preference chain, and can notify
Telegram/Discord/Slack/a generic webhook. Works standalone via cron or as
an agent skill in any harness, see SKILL.md at the repo root.
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone

from free_models_monitor import notify as notify_mod
from free_models_monitor.providers import (
    DEFAULT_FALLBACK_CHAIN,
    fetch_groq_free,
    fetch_openrouter_catalog,
    fetch_openrouter_free,
    openrouter_free_from_catalog,
)
from free_models_monitor.quality import (
    DEFAULT_AGENTIC_RATIO,
    DEFAULT_CODING_RATIO,
    DEFAULT_QUALITY_MIN_CONTEXT,
    build_paid_frontier,
    classify_free_catalog,
)

HISTORY_CAP = 200
DEFAULT_MIN_CONTEXT = 32768
SCAN_EXTENSIONS = (".md", ".json", ".yaml", ".yml", ".toml")


def default_state_dir():
    return os.environ.get("FMM_STATE_DIR") or os.path.expanduser(
        "~/.free-models-monitor"
    )


def normalize_model_id(model_id):
    """Adds the openrouter/ prefix config files use to key OpenRouter ids."""
    if model_id.startswith("openrouter/") or model_id.startswith("groq/"):
        return model_id
    return f"openrouter/{model_id}"


def denormalize_model_id(model_id):
    if model_id.startswith("openrouter/"):
        return model_id[len("openrouter/") :]
    return model_id


def load_json_safe(path, default=None):
    default = {} if default is None else default
    if not os.path.exists(path):
        return default
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return default


def save_json_safe(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def load_banned_models(state_dir):
    data = load_json_safe(os.path.join(state_dir, "banned.json"), {"banned_models": []})
    return set(data.get("banned_models", []))


def load_fallback_chain(path):
    if not path:
        return list(DEFAULT_FALLBACK_CHAIN)
    with open(path) as f:
        data = json.load(f)
    if isinstance(data, dict):
        return list(data.get("fallback_chain", []))
    return list(data)


def fetch_current_models(providers, banned, quality_config=None):
    """Fetches and merges free models across the requested providers."""
    current, counts, errors = {}, {}, []
    quality_context = None
    if "openrouter" in providers:
        if quality_config:
            catalog, err = fetch_openrouter_catalog()
            or_free = None
            if not err:
                or_free = openrouter_free_from_catalog(catalog)
                try:
                    frontier = build_paid_frontier(catalog)
                    or_free = classify_free_catalog(
                        or_free,
                        frontier,
                        coding_ratio=quality_config["coding_ratio"],
                        agentic_ratio=quality_config["agentic_ratio"],
                        min_context=quality_config["min_context"],
                    )
                    quality_context = {
                        "available": True,
                        "frontier": frontier,
                        "thresholds": dict(quality_config),
                    }
                except ValueError as exc:
                    errors.append(f"OpenRouter quality scoring error: {exc}")
                    quality_context = {"available": False, "error": str(exc)}
        else:
            or_free, err = fetch_openrouter_free()
        if err:
            errors.append(err)
        else:
            filtered = {
                normalize_model_id(mid): info
                for mid, info in or_free.items()
                if normalize_model_id(mid) not in banned and mid not in banned
            }
            current.update(filtered)
            counts["openrouter"] = len(filtered)
    if "groq" in providers:
        groq_free, err = fetch_groq_free()
        if err:
            errors.append(err)
        else:
            filtered = {k: v for k, v in groq_free.items() if k not in banned}
            current.update(filtered)
            counts["groq"] = len(filtered)
    return current, counts, errors, quality_context


def find_agents_using_model(model_id, scan_dirs):
    """Walks scan_dirs looking for files that reference model_id."""
    affected = []
    needles = {model_id, denormalize_model_id(model_id)}
    for scan_dir in scan_dirs:
        if not os.path.isdir(scan_dir):
            continue
        for root, _dirs, files in os.walk(scan_dir):
            for fname in files:
                if not fname.endswith(SCAN_EXTENSIONS):
                    continue
                fpath = os.path.join(root, fname)
                try:
                    with open(fpath, errors="ignore") as f:
                        content = f.read()
                except OSError:
                    continue
                if any(n in content for n in needles):
                    affected.append(
                        {"file": fpath, "agent": os.path.relpath(fpath, scan_dir)}
                    )
    return affected


def find_best_fallback(
    current, fallback_chain, banned, exclude_model=None, min_context=DEFAULT_MIN_CONTEXT
):
    """Picks a replacement model: chain order first, then highest context."""
    exclude = (
        {exclude_model, denormalize_model_id(exclude_model)} if exclude_model else set()
    )
    for model_id in fallback_chain:
        if model_id in exclude or model_id in banned:
            continue
        info = current.get(model_id)
        if info and info.get("context_length", 0) >= min_context:
            return model_id, info
    by_context = sorted(
        current.items(), key=lambda kv: kv[1].get("context_length", 0), reverse=True
    )
    for model_id, info in by_context:
        if model_id in exclude or model_id in banned:
            continue
        if info.get("context_length", 0) >= min_context:
            return model_id, info
    return None, None


def add_history_entry(history, change_type, model_id, model_info, details=None):
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "type": change_type,
        "model_id": model_id,
        "model_info": model_info,
    }
    if details:
        entry["details"] = details
    history.setdefault("changes", []).append(entry)
    history["changes"] = history["changes"][-HISTORY_CAP:]
    return history


def quality_status(model_info):
    quality = model_info.get("quality", {})
    return quality.get("status") if isinstance(quality, dict) else None


def quality_change_type(model_id, model_info, quality_mode):
    """Returns the event type for a newly seen model, or None if filtered."""
    if quality_mode == "none" or model_id.startswith("groq/"):
        return "added"
    status = quality_status(model_info)
    if status == "confirmed":
        return "quality_confirmed"
    if quality_mode == "candidate" and status == "candidate":
        return "quality_candidate"
    return None


def quality_summary(model_info):
    quality = model_info.get("quality", {})
    coding = model_info.get("coding_index")
    agentic = model_info.get("agentic_index")
    coding_ratio = quality.get("coding_ratio")
    agentic_ratio = quality.get("agentic_ratio")

    def score_text(label, score, relative):
        if score is None:
            return f"{label}=pending"
        if relative is None:
            return f"{label}={score:g}"
        return f"{label}={score:g} ({relative * 100:.1f}% of paid frontier)"

    return ", ".join(
        [
            score_text("coding", coding, coding_ratio),
            score_text("agentic", agentic, agentic_ratio),
        ]
    )


def build_report_text(changes, affected_by_model, switches, now_label):
    lines = [f"ALERT: change detected in free models monitor ({now_label})"]
    switch_by_from = {s["from"]: s for s in switches}
    for change in changes:
        mid, info = change["model_id"], change["model_info"]
        if change["type"] == "removed":
            lines += [
                "",
                "Model REMOVED from free tier:",
                f"  - {mid} ({info.get('name', mid)})",
            ]
            for a in affected_by_model.get(mid, []):
                lines.append(f"  affected config: {a['file']}")
            switch = switch_by_from.get(mid)
            if switch and switch["to"]:
                lines.append(f"  suggested switch: {mid} -> {switch['to']}")
            elif switch:
                lines.append("  suggested switch: FAILED - no fallback found")
        elif change["type"] == "added":
            ctx = info.get("context_length", 0)
            lines += [
                "",
                "Model ADDED to free tier:",
                f"  + {mid} ({info.get('name', mid)}, ctx={ctx})",
            ]
        elif change["type"] == "quality_candidate":
            ctx = info.get("context_length", 0)
            lines += [
                "",
                "Promising free development model; benchmarks pending:",
                f"  ? {mid} ({info.get('name', mid)}, ctx={ctx})",
                f"  {quality_summary(info)}",
            ]
        elif change["type"] == "quality_confirmed":
            ctx = info.get("context_length", 0)
            lines += [
                "",
                "Free model reached paid-frontier quality thresholds:",
                f"  + {mid} ({info.get('name', mid)}, ctx={ctx})",
                f"  {quality_summary(info)}",
            ]
    return "\n".join(lines)


def compute_diff(
    current,
    snapshot,
    scan_dirs,
    fallback_chain,
    banned,
    min_context,
    history,
    quality_mode="none",
):
    """Diffs current against the previous snapshot, updating history in place."""
    normalized_snapshot = {
        normalize_model_id(mid): info for mid, info in snapshot.items()
    }
    new_models = {k: v for k, v in current.items() if k not in normalized_snapshot}
    removed_models = {k: v for k, v in normalized_snapshot.items() if k not in current}

    changes, affected_by_model, switches = [], {}, []

    for mid, info in new_models.items():
        change_type = quality_change_type(mid, info, quality_mode)
        if change_type:
            changes.append(
                {"type": change_type, "model_id": mid, "model_info": info}
            )
            history = add_history_entry(history, change_type, mid, info)

    if quality_mode != "none":
        for mid in current.keys() & normalized_snapshot.keys():
            info = current[mid]
            old_info = normalized_snapshot[mid]
            if (
                quality_status(info) == "confirmed"
                and quality_status(old_info) != "confirmed"
            ):
                changes.append(
                    {
                        "type": "quality_confirmed",
                        "model_id": mid,
                        "model_info": info,
                    }
                )
                history = add_history_entry(
                    history, "quality_confirmed", mid, info
                )

    for mid, info in removed_models.items():
        changes.append({"type": "removed", "model_id": mid, "model_info": info})
        history = add_history_entry(history, "removed", mid, info)
        affected_by_model[mid] = find_agents_using_model(mid, scan_dirs)
        fb_id, fb_info = find_best_fallback(
            current, fallback_chain, banned, exclude_model=mid, min_context=min_context
        )
        if fb_id:
            switches.append(
                {"from": mid, "to": fb_id, "to_name": fb_info.get("name", fb_id)}
            )
            history = add_history_entry(
                history,
                "switch_suggested",
                mid,
                {"name": fb_info.get("name", "unknown")},
                details=f"{mid} -> {fb_id}",
            )
        else:
            switches.append({"from": mid, "to": None, "to_name": None})

    return changes, affected_by_model, switches, history


def parse_args(argv=None):
    p = argparse.ArgumentParser(
        prog="free-models-monitor",
        description="Track free LLM model availability across providers.",
    )
    p.add_argument("--state-dir", default=None)
    p.add_argument("--scan-dir", action="append", default=[])
    p.add_argument("--providers", default="openrouter,groq")
    p.add_argument("--format", choices=["text", "json"], default="text")
    p.add_argument("--min-context", type=int, default=DEFAULT_MIN_CONTEXT)
    p.add_argument(
        "--quality-filter",
        choices=("none", "candidate", "frontier"),
        default="none",
        help=(
            "filter new-model alerts by dynamic OpenRouter quality: "
            "candidate includes capable unscored models; frontier only confirmed models"
        ),
    )
    p.add_argument(
        "--coding-ratio",
        type=ratio,
        default=DEFAULT_CODING_RATIO,
        help="minimum fraction of the best paid coding score (default: 0.90)",
    )
    p.add_argument(
        "--agentic-ratio",
        type=ratio,
        default=DEFAULT_AGENTIC_RATIO,
        help="minimum fraction of the best paid agentic score (default: 0.80)",
    )
    p.add_argument(
        "--quality-min-context",
        type=positive_int,
        default=DEFAULT_QUALITY_MIN_CONTEXT,
        help="minimum context for a quality candidate (default: 128000)",
    )
    p.add_argument(
        "--notify",
        choices=["telegram", "discord", "slack", "webhook", "none"],
        default="none",
    )
    p.add_argument("--notify-always", action="store_true")
    p.add_argument("--init", action="store_true")
    p.add_argument("--fallback-chain-file", default=None)
    return p.parse_args(argv)


def ratio(value):
    parsed = float(value)
    if not 0 < parsed <= 1:
        raise argparse.ArgumentTypeError("must be greater than 0 and no greater than 1")
    return parsed


def positive_int(value):
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be positive")
    return parsed


def main(argv=None):
    args = parse_args(argv)
    state_dir = args.state_dir or default_state_dir()
    snapshot_path = os.path.join(state_dir, "snapshot.json")
    history_path = os.path.join(state_dir, "history.json")

    providers = {p.strip() for p in args.providers.split(",") if p.strip()}
    banned = load_banned_models(state_dir)
    fallback_chain = load_fallback_chain(args.fallback_chain_file)

    quality_config = None
    if args.quality_filter != "none":
        quality_config = {
            "coding_ratio": args.coding_ratio,
            "agentic_ratio": args.agentic_ratio,
            "min_context": args.quality_min_context,
        }

    current, counts, errors, quality_context = fetch_current_models(
        providers, banned, quality_config=quality_config
    )
    if quality_config and (
        not quality_context or not quality_context.get("available", False)
    ):
        for error in errors or ["OpenRouter quality scoring is unavailable"]:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    if errors and not current:
        for err in errors:
            print(f"ERROR: {err}", file=sys.stderr)
        return 1

    snapshot = load_json_safe(snapshot_path, {})
    history = load_json_safe(history_path, {"changes": []})
    now_label = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    if args.init or not snapshot:
        save_json_safe(snapshot_path, current)
        save_json_safe(
            history_path,
            add_history_entry(history, "init", "all", {"count": len(current)}),
        )
        print(
            f"free-models-monitor: initialized with {len(current)} free models ({now_label})"
        )
        return 0

    changes, affected_by_model, switches, history = compute_diff(
        current,
        snapshot,
        args.scan_dir,
        fallback_chain,
        banned,
        args.min_context,
        history,
        quality_mode=args.quality_filter,
    )
    save_json_safe(snapshot_path, current)
    save_json_safe(history_path, history)

    changed = bool(changes)
    if args.format == "json":
        report = json.dumps(
            {
                "changed": changed,
                "changes": changes,
                "affected_configs": affected_by_model,
                "switches": switches,
                "provider_counts": counts,
                "quality": quality_context,
            },
            indent=2,
            ensure_ascii=False,
        )
    elif changed:
        report = build_report_text(changes, affected_by_model, switches, now_label)
    else:
        report = f"free-models-monitor: no changes ({now_label}). {len(current)} free models tracked."

    print(report)
    for err in errors:
        print(f"WARNING: {err}", file=sys.stderr)

    if args.notify != "none" and (changed or args.notify_always):
        ok, notify_err = notify_mod.notify(args.notify, report)
        if not ok:
            print(f"WARNING: notify failed: {notify_err}", file=sys.stderr)

    return 2 if changed else 0


if __name__ == "__main__":
    sys.exit(main())
