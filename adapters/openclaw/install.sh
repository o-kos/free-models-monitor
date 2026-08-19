#!/usr/bin/env bash
# Installs free_models_monitor into an OpenClaw workspace and takes the
# first snapshot. Safe to re-run (idempotent: overwrites the copied
# package, never touches an existing snapshot/history unless --init would
# have run anyway on a missing snapshot).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

WORKSPACE_DIR="${OPENCLAW_WORKSPACE_DIR:-$HOME/.openclaw/workspace/scripts}"
STATE_DIR="${FMM_STATE_DIR:-$HOME/.free-models-monitor}"

mkdir -p "$WORKSPACE_DIR/free_models_monitor"
cp -r "$REPO_ROOT/free_models_monitor/." "$WORKSPACE_DIR/free_models_monitor/"

mkdir -p "$STATE_DIR"
cd "$WORKSPACE_DIR"
python3 -m free_models_monitor.monitor --state-dir "$STATE_DIR" --init

echo ""
echo "Installed to $WORKSPACE_DIR/free_models_monitor"
echo "State dir: $STATE_DIR"
echo ""
echo "Next: add the cron job. Either edit jobs.json with"
echo "  adapters/openclaw/cron-job.example.json (fill in the placeholders),"
echo "or, if your OpenClaw build supports it, run:"
echo "  openclaw cron add --file adapters/openclaw/cron-job.example.json"
