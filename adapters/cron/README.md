# Plain cron adapter (no agent)

No harness at all: just system cron and a notification channel.

## Install

```bash
pip install git+https://github.com/nikolasdehor/free-models-monitor.git
free-models-monitor --init
```

## Schedule

Copy `crontab.example` (edit the paths and environment first), or add
manually:

```cron
10 8 * * * TELEGRAM_BOT_TOKEN=xxx TELEGRAM_CHAT_ID=xxx free-models-monitor --notify telegram
```

Set only the environment variables for the channel you use, see the main
`README.md`, "Notification setup" table.

## Applying a suggested fallback without an agent

The monitor only reports and notifies, it does not edit files on its own.
Read the alert, then run `free-models-switch` by hand (or from a second
cron step that inspects the JSON output):

```bash
free-models-switch --from "<removed model id>" --auto --file /path/to/config --apply
```
