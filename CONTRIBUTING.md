# Contributing

Issues and pull requests are welcome.

- Keep runtime dependencies at zero: `free_models_monitor` must stay stdlib-only (Python 3.9+).
- Run `ruff check .` and `python3 -m unittest discover -s tests -v` before opening a PR.
- Keep files under 400 lines and functions under 50 lines.
- Adding a provider: write a `fetch_<name>_free()` in `free_models_monitor/providers.py` and register it in `PROVIDERS`.
- Adding a harness adapter: add a folder under `adapters/<harness>/` with its own `README.md`. Do not put harness-specific logic (paths, restart commands) inside `free_models_monitor/`.
- No PII, tokens, or infra-specific details (IPs, container names, chat IDs) in anything committed.
