# Discord Thread Title Plugin for Hermes

A minimal Hermes plugin for Discord thread title management without modifying Hermes core.
It reads only `DISCORD_BOT_TOKEN` from `~/.hermes/.env` and does not bulk-load other environment variables.

## What it does

When the conversation is inside a Discord thread, the plugin provides the agent with:

- `get_thread_title` — read the current Discord thread title and thread ID
- `change_thread_title` — rename the current Discord thread

It also injects a short English prompt before the model call telling Hermes to:

- check whether the current conversation still matches the current thread title
- avoid renaming if the current title still fits
- rename only when the topic has clearly changed
- keep the new title concise, with a soft limit of 40 characters (not a hard truncation)
- use the user's habitual language for the title itself

These tools are for the agent, not for end users.

## Design

This plugin intentionally stays simple:

- no extra AI rename judge inside the plugin
- no user-facing slash commands
- no sender allowlist logic
- no topic heuristics unrelated to the tools above
- no fallback to `DISCORD_TOKEN`

The main model decides whether to rename, using the injected prompt and the tools.

## Install

Copy these files into a Hermes plugin directory such as:

```text
~/.hermes/plugins/discord-thread-title/
```

Required files:

- `plugin.yaml`
- `__init__.py`
- `plugin.py`

## Token loading

This project intentionally reads only one value from `~/.hermes/.env`:

- `DISCORD_BOT_TOKEN`

It does not import `python-dotenv`, does not bulk-load `.env`, and does not read other secrets.

## Internal tools

### `get_thread_title`
Returns the current thread title and thread ID for the active Discord thread session.

### `change_thread_title`
Renames the current Discord thread.

Parameters:

- `thread_id`
- `title`

The plugin validates required fields, requires an active Discord thread session, and enforces that the requested `thread_id` matches the current session before calling Discord.
It does not hard-truncate titles to 40 characters; the 40-character rule is a soft limit communicated to the main model.

## Tests

```bash
pytest -q test_plugin.py
```

## Security / publishing notes

This repo is safe to publish only if you do **not** commit your real `~/.hermes/.env`, session files, or local machine paths containing secrets.
