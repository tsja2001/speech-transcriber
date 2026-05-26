# Agent Instructions

This project is a CLI wrapper around speech-to-text providers.

Before changing code:

- Read `README.md` and `docs/AI_USAGE.md`.
- Use tests first for behavior changes.
- Keep Tencent Cloud details inside provider modules.
- Do not add HTTP/FastAPI modules unless the user explicitly reverses the CLI-only decision.
- Do not commit real Tencent credentials or generated transcript output.

Verification before completion:

```bash
uv run pytest
uv run ruff check .
uv run mypy src
```

Smoke tests call real Tencent Cloud services and must stay gated:

```bash
RUN_SMOKE=1 uv run pytest tests/smoke/test_tencent_cli_real.py -v
```
