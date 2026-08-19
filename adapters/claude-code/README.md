# Claude Code / Codex / OpenCode adapter

These harnesses do not need an adapter script, just the skill and a
scheduler.

## Install as a skill

```bash
mkdir -p ~/.claude/skills/free-models-monitor
cp SKILL.md ~/.claude/skills/free-models-monitor/SKILL.md
cp -r free_models_monitor ~/.claude/skills/free-models-monitor/free_models_monitor
```

For Codex or OpenCode, use whichever directory your build reads skills or
custom tools from, the contents are the same two files/folders.

## Run it

Interactively, ask the agent to run the skill. For unattended runs, use
whatever recurring mechanism the harness offers:

- Claude Code: the `/loop` skill, or a scheduled agent if your setup has
  one.
- Codex / OpenCode: their own scheduling primitive, if any, or fall back to
  the plain `cron` adapter below and have the agent read the last report on
  demand.

## No native scheduler? Use system cron

```bash
python3 -m free_models_monitor.monitor --format json --state-dir ~/.free-models-monitor
```

on a cron schedule (see `adapters/cron/crontab.example`), and have the
agent read the last report on demand, or wire `--notify` directly (see the
`cron` adapter) and skip the agent step entirely when a plain alert is
enough.
