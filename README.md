# Discord Thread Title Plugin for Hermes

A Hermes plugin that renames Discord thread titles without modifying Hermes core.
It reads only `DISCORD_BOT_TOKEN` from `~/.hermes/.env` and does not bulk-load other environment variables.

## Features

- `/rename-thread <title>` manually renames the current Discord thread
- `/suggest-thread-title <hint>` suggests a clearer title
- Fully automatic rename mode after each assistant response
- Sender allowlist is configurable via `DISCORD_ALLOWED_USERS`
- Default sender filter: `Xtra` and `Mics` when `DISCORD_ALLOWED_USERS` is unset
- Small-talk filter to avoid noisy renames
- Reads **only** `DISCORD_BOT_TOKEN` from `~/.hermes/.env`
- Does **not** load the rest of `.env`
- Does **not** fall back to `DISCORD_TOKEN`

## How it works

The plugin stores the current gateway session origin, recovers Discord `thread_id` from Hermes session metadata, and calls Discord REST API:

- `PATCH /channels/{thread_id}`

## Install

Copy these files into a Hermes plugin directory such as:

```text
~/.hermes/plugins/discord-thread-title/
```

Required files:

- `plugin.yaml`
- `__init__.py`
- `plugin.py`

A minimal `__init__.py` can simply re-export:

```python
from .plugin import register
```

## Token loading

This project intentionally reads only one value from `~/.hermes/.env`:

- `DISCORD_BOT_TOKEN`

It does not import `python-dotenv`, does not bulk-load `.env`, and does not read other secrets.

## Sender allowlist

You can override the default sender names via environment variable:

```text
DISCORD_ALLOWED_USERS=Xtra,Mics
```

The plugin currently compares normalized bracketed sender display names like `[Xtra]` and `[Mics]` against this comma-separated list.
If `DISCORD_ALLOWED_USERS` is unset, or if it contains no valid non-empty entries, it falls back to the built-in default allowlist.

Examples:

```text
DISCORD_ALLOWED_USERS=Xtra,Mics
DISCORD_ALLOWED_USERS=alpha,beta
```

Note: this v2 implementation uses sender names from the message prefix, not raw Discord numeric user IDs.

## Tests

```bash
pytest -q test_plugin.py
```

## Security / publishing notes

This repo is safe to publish only if you do **not** commit your real `~/.hermes/.env`, session files, or local machine paths containing secrets.
