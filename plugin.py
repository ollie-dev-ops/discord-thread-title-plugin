from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional
from urllib import error, request

SESSION_ID_TO_SOURCE: dict[str, dict[str, Any]] = {}
TITLE_SOFT_LIMIT = 40
CHANGE_TOOL_NAME = "change_thread_title"
GET_TOOL_NAME = "get_thread_title"


def hermes_home() -> Path:
    return Path(os.environ.get("HERMES_HOME", str(Path.home() / ".hermes")))


def sessions_file() -> Path:
    return hermes_home() / "sessions" / "sessions.json"


def load_sessions_index() -> dict[str, Any]:
    path = sessions_file()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def remember_session_source(session_id: str, source: Any) -> None:
    if not session_id or source is None:
        return
    try:
        if hasattr(source, "to_dict"):
            data = source.to_dict()
        elif isinstance(source, dict):
            data = source
        else:
            return
        if isinstance(data, dict):
            SESSION_ID_TO_SOURCE[session_id] = data
    except Exception:
        return


def source_for_session(session_id: str) -> Optional[dict[str, Any]]:
    if session_id in SESSION_ID_TO_SOURCE:
        return SESSION_ID_TO_SOURCE[session_id]
    for entry in load_sessions_index().values():
        if not isinstance(entry, dict) or entry.get("session_id") != session_id:
            continue
        origin = entry.get("origin")
        if isinstance(origin, dict):
            SESSION_ID_TO_SOURCE[session_id] = origin
            return origin
    return None


def normalize_title(raw: str, max_len: int = TITLE_SOFT_LIMIT) -> str:
    title = " ".join((raw or "").strip().split())
    title = title.strip("#`'\" ")
    if len(title) > max_len:
        title = title[:max_len].rstrip()
    return title


def current_thread_title(source: Optional[dict[str, Any]]) -> str:
    if not source:
        return ""
    chat_name = str(source.get("chat_name") or "")
    if " / " in chat_name:
        return chat_name.split(" / ")[-1].strip()
    return chat_name.strip()


def load_discord_bot_token_from_env_file() -> str:
    env_path = Path.home() / ".hermes" / ".env"
    if not env_path.exists():
        return ""
    try:
        for line in env_path.read_text(encoding="utf-8", errors="replace").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            if key.strip() != "DISCORD_BOT_TOKEN":
                continue
            token = value.strip().strip('"').strip("'")
            if token:
                os.environ["DISCORD_BOT_TOKEN"] = token
                return token
    except Exception:
        return ""
    return ""


def discord_token() -> str:
    token = os.environ.get("DISCORD_BOT_TOKEN", "").strip()
    if token:
        return token
    return load_discord_bot_token_from_env_file()


def discord_patch_thread(thread_id: str, new_name: str) -> dict[str, Any]:
    token = discord_token()
    if not token:
        return {"ok": False, "error": "DISCORD_BOT_TOKEN not available"}

    req = request.Request(
        f"https://discord.com/api/v10/channels/{thread_id}",
        data=json.dumps({"name": new_name}).encode("utf-8"),
        method="PATCH",
        headers={
            "Authorization": f"Bot {token}",
            "Content-Type": "application/json",
            "User-Agent": "DiscordThreadTitlePlugin/4.0",
        },
    )
    try:
        with request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8") or "{}")
            return {
                "ok": True,
                "status": getattr(resp, "status", 200),
                "thread_id": data.get("id", thread_id),
                "name": data.get("name", new_name),
            }
    except error.HTTPError as e:
        try:
            detail = json.loads(e.read().decode("utf-8") or "{}")
        except Exception:
            detail = {"message": str(e)}
        return {"ok": False, "status": e.code, "error": detail.get("message") or str(e)}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


def build_topic_guard_context(session_id: str, is_first_turn: bool = False) -> Optional[str]:
    source = source_for_session(session_id) if session_id else None
    if not source or source.get("platform") != "discord":
        return None
    thread_id = str(source.get("thread_id") or "").strip()
    if not thread_id:
        return None
    title = current_thread_title(source)
    if not title:
        return None
    if not is_first_turn:
        return None
    return (
        f"Current Discord thread title: {title}. "
        f"On the first turn, assign a fitting thread title now using `{CHANGE_TOOL_NAME}`. "
        f"Do not ask for confirmation first. "
        f"Later, rename only if the main topic clearly changes. "
        f"Keep titles concise (soft limit: {TITLE_SOFT_LIMIT} chars) and use the user's habitual language."
    )


def get_thread_title(args: dict[str, Any], session_id: str = "") -> str:
    source = source_for_session(session_id) if session_id else None
    if not source or source.get("platform") != "discord":
        return json.dumps({"success": False, "error": "current session is not a Discord thread"}, ensure_ascii=False)
    thread_id = str(source.get("thread_id") or "").strip()
    title = current_thread_title(source)
    if not thread_id or not title:
        return json.dumps({"success": False, "error": "thread metadata unavailable"}, ensure_ascii=False)
    return json.dumps({"success": True, "thread_id": thread_id, "title": title}, ensure_ascii=False)


def change_thread_title(args: dict[str, Any], session_id: str = "") -> str:
    source = source_for_session(session_id) if session_id else None
    current_thread_id = str((source or {}).get("thread_id") or "").strip()
    requested_thread_id = str(args.get("thread_id") or "").strip()
    title = normalize_title(str(args.get("title") or ""), max_len=200)

    if not current_thread_id:
        return json.dumps({"success": False, "error": "current session is not an active Discord thread"}, ensure_ascii=False)
    if not requested_thread_id:
        return json.dumps({"success": False, "error": "thread_id is required"}, ensure_ascii=False)
    if requested_thread_id != current_thread_id:
        return json.dumps({"success": False, "error": "thread_id mismatch with current session"}, ensure_ascii=False)
    if not title:
        return json.dumps({"success": False, "error": "title is required"}, ensure_ascii=False)

    result = discord_patch_thread(current_thread_id, title)
    if result.get("ok"):
        return json.dumps({"success": True, "thread_id": current_thread_id, "title": result.get("name", title)}, ensure_ascii=False)
    return json.dumps(
        {
            "success": False,
            "error": result.get("error", "unknown error"),
            "status": result.get("status"),
        },
        ensure_ascii=False,
    )


def register(ctx) -> None:
    def on_session_start(**kwargs):
        remember_session_source(kwargs.get("session_id") or "", kwargs.get("source"))

    def pre_llm_call(**kwargs):
        return build_topic_guard_context(
            kwargs.get("session_id") or "",
            is_first_turn=bool(kwargs.get("is_first_turn")),
        )

    ctx.register_hook("on_session_start", on_session_start)
    ctx.register_hook("pre_llm_call", pre_llm_call)
    ctx.register_tool(
        name=GET_TOOL_NAME,
        toolset="discord-thread-title",
        description="Get the current Discord thread title and thread ID for the active session.",
        schema={
            "name": GET_TOOL_NAME,
            "description": "Get the current Discord thread title and thread ID for the active session.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        handler=lambda args, **kwargs: get_thread_title(args, session_id=str(kwargs.get("session_id") or "")),
        check_fn=lambda: True,
        requires_env=[],
        emoji="🔎",
    )
    ctx.register_tool(
        name=CHANGE_TOOL_NAME,
        toolset="discord-thread-title",
        description="Rename the current Discord thread when the topic has clearly changed.",
        schema={
            "name": CHANGE_TOOL_NAME,
            "description": "Rename the current Discord thread when the main topic has clearly changed.",
            "parameters": {
                "type": "object",
                "properties": {
                    "thread_id": {
                        "type": "string",
                        "description": "Current Discord thread ID. Prefer the ID returned by get_thread_title.",
                    },
                    "title": {
                        "type": "string",
                        "description": f"New concise thread title. Keep it within about {TITLE_SOFT_LIMIT} characters.",
                    },
                },
                "required": ["thread_id", "title"],
                "additionalProperties": False,
            },
        },
        handler=lambda args, **kwargs: change_thread_title(args, session_id=str(kwargs.get("session_id") or "")),
        check_fn=lambda: bool(discord_token()),
        requires_env=["DISCORD_BOT_TOKEN"],
        emoji="🧵",
    )
