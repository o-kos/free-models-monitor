# OpenClaw adapter

How to run free-models-monitor as a daily cron job inside OpenClaw.

## Install

```bash
bash adapters/openclaw/install.sh
```

This copies `free_models_monitor` into your OpenClaw workspace (default
`~/.openclaw/workspace/scripts`, override with `OPENCLAW_WORKSPACE_DIR`)
and takes the first snapshot (default state dir
`~/.free-models-monitor`, override with `FMM_STATE_DIR`). It is safe to
re-run; it only overwrites the copied package, never an existing snapshot.

If you want the dedicated Monitor persona, also copy `AGENT.md` from this
folder into your agent's workspace, for example:

```bash
cp adapters/openclaw/AGENT.md /path/to/your/openclaw/workspace/agents/monitor/AGENT.md
```

## Cron job

Copy `cron-job.example.json` into your `jobs.json`, replacing:

- `<GENERATE_A_UUID>` with a fresh UUID.
- `<PATH_TO_AGENT_CONFIGS>` with the directory (or directories) the monitor
  should scan for affected agents.
- `<YOUR_CHAT_ID>` with your Telegram chat id.

Or add it through the OpenClaw CLI/UI cron editor using the same schedule
(`10 8 * * *`, i.e. 08:10 daily) and payload.

The job runs the monitor, and if the report contains a `removed` change,
follows `SKILL.md` at the repo root to decide whether to apply the
suggested fallback and restart the gateway (`openclaw gateway restart`)
after editing the config with `free_models_monitor.switch`.

### pt-BR prompt variant

If your agent replies in pt-BR, use this message instead in the cron
payload:

```text
Execute o monitor de modelos gratuitos:

python3 -m free_models_monitor.monitor --format json --scan-dir <PATH_TO_AGENT_CONFIGS>

Se o código de saída for 2 (mudança detectada):
1. Envie o relatório completo para o usuário no canal de notificação dele.
2. Se um modelo foi removido e existe um fallback sugerido, siga o SKILL.md para aplicar a troca com free_models_monitor.switch, e reinicie o gateway se o harness precisar.

Se o código de saída for 0, envie um resumo de uma linha.
Se o código de saída for 1, informe o erro.

Regras:
- Sem markdown
- Sem emojis
- Responda apenas com o texto final
- Encerre com NO_REPLY
```

## Notes

- OpenClaw's cron payload is `agentTurn`, so the agent doing the reasoning
  in step 2 (interpreting the report) is whichever model your cron job's
  `agentId` points to. Give it `SKILL.md` as context, or point it at this
  adapter's `AGENT.md` persona.
- `AGENT.md` in this folder is a generic persona template with no personal
  data. Fill in the placeholders (`<YOUR_NAME>`, `<YOUR_VPS_HOST_OR_IP>`,
  etc) or delete the sections you do not need.
