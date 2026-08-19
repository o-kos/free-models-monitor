# Hermes Agent adapter

## Install as a skill

```bash
mkdir -p ~/.hermes/skills/free-models-monitor
cp SKILL.md ~/.hermes/skills/free-models-monitor/SKILL.md
cp -r free_models_monitor ~/.hermes/skills/free-models-monitor/free_models_monitor
```

Point Hermes at that skill directory the way your Hermes setup expects
skills to be loaded (a skills directory scan, or an explicit skill path in
its config).

## Schedule it

If your Hermes deployment has a cron primitive (`hermes cron`, or whatever
your build calls it), give it a prompt that mirrors the OpenClaw one, see
`adapters/openclaw/README.md` for the exact text (English and pt-BR
variants). The command it should run is:

```bash
cd ~/.hermes/skills/free-models-monitor && python3 -m free_models_monitor.monitor --format json
```

If the exit code is 2, have the agent follow `SKILL.md` to act on the
report (notify, and apply a switch only with confirmation or a standing
rule to auto-apply). If it is 0, send a one-line summary. If it is 1,
report the error.

Schedule it daily, or on whatever interval fits your Hermes cron syntax.

## State

Snapshot, history, and banlist live under `--state-dir`
(`~/.free-models-monitor` by default, override with `FMM_STATE_DIR`). That
is independent of the skill directory, so re-copying the skill on update
does not wipe your history.
