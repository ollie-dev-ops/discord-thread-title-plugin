from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Optional
from urllib import error, request

SESSION_ID_TO_SOURCE: dict[str, dict[str, Any]] = {}
LAST_AUTO_TITLE_BY_SESSION: dict[str, str] = {}
LAST_MESSAGE_SIG_BY_SESSION: dict[str, str] = {}

ALLOWED_SENDERS = {"xtra", "mics"}
SMALL_TALK_PATTERNS = [
    re.compile(p, re.I)
    for p in [r"棒棒", r"謝啦|謝謝|thanks?", r"哈哈|lol|lmao", r"^ok$|^okay$|^收到$", r"牛阿"]
]
KEYWORD_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("全自動模式", re.compile(r"全自動|auto\s*mode|自動改名", re.I)),
    ("半自動模式", re.compile(r"半自動|semi[-\s]*auto", re.I)),
    ("主題改名", re.compile(r"改名|rename|標題", re.I)),
    ("Plugin 擴充", re.compile(r"plugin|擴充", re.I)),
    ("上下文", re.compile(r"上下文|context", re.I)),
]

LAST_AUTO_RENAME_RESULT: Optional[str] = None
LAST_AUTO_RENAME_STATUS: Optional[str] = None
LAST_AUTO_RENAME_TITLE: Optional[str] = None
LAST_AUTO_RENAME_SKIPPED_REASON: Optional[str] = None


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


def normalize_title(raw: str, max_len: int = 100) -> str:
    title = " ".join((raw or "").strip().split())
    title = title.strip("#`'\" ")
    if len(title) > max_len:
        title = title[:max_len].rstrip()
    return title


def sender_name(text: str) -> str:
    m = re.match(r"\[(.*?)\]", (text or "").strip())
    return m.group(1).strip().lower() if m else ""


def sender_allowed(text: str) -> bool:
    return sender_name(text) in ALLOWED_SENDERS


def is_small_talk(text: str) -> bool:
    compact = normalize_title(re.sub(r"^\[[^\]]+\]\s*", "", text or ""), max_len=200)
    if not compact:
        return True
    return any(p.search(compact) for p in SMALL_TALK_PATTERNS)


def current_thread_title(source: Optional[dict[str, Any]]) -> str:
    if not source:
        return ""
    chat_name = str(source.get("chat_name") or "")
    if " / " in chat_name:
        return chat_name.split(" / ")[-1].strip()
    return chat_name.strip()


def propose_auto_title(current_title: str, user_message: str, assistant_response: str) -> Optional[str]:
    if not sender_allowed(user_message):
        return None
    if is_small_talk(user_message) and is_small_talk(assistant_response):
        return None

    combined = f"{user_message}\n{assistant_response}"
    hits = [label for label, pattern in KEYWORD_PATTERNS if pattern.search(combined)]
    if not hits:
        return None

    unique_hits = list(dict.fromkeys(hits))
    candidate = normalize_title(" / ".join(unique_hits[:2]))
    if not candidate or candidate == normalize_title(current_title):
        return None
    return candidate


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
            "User-Agent": "DiscordThreadTitlePlugin/1.0",
        },
    )
    try:
        with request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8") or "{}")
            return {"ok": True, "status": getattr(resp, "status", 200), "name": data.get("name", new_name)}
    except error.HTTPError as e:
        try:
            detail = json.loads(e.read().decode("utf-8") or "{}")
        except Exception:
            detail = {"message": str(e)}
        return {"ok": False, "status": e.code, "error": detail.get("message") or str(e)}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


def rename_current_thread(session_id: str, new_title: str) -> str:
    source = source_for_session(session_id) if session_id else None
    if not source:
        return "找不到目前 session 的來源資訊，無法判定 thread。"
    if source.get("platform") != "discord":
        return "這個指令目前只支援 Discord gateway session。"
    thread_id = str(source.get("thread_id") or "").strip()
    if not thread_id:
        return "目前不是 Discord 討論串／找不到 thread_id。"

    title = normalize_title(new_title)
    if not title:
        return "用法：`/rename-thread 新標題`"
    result = discord_patch_thread(thread_id, title)
    if result.get("ok"):
        return f"已改名為：`{result.get('name', title)}`"
    if result.get("status"):
        return f"改名失敗（HTTP {result['status']}）：{result.get('error', 'unknown error')}"
    return f"改名失敗：{result.get('error', 'unknown error')}"


def suggest_title(session_id: str, raw_args: str) -> str:
    current = current_thread_title(source_for_session(session_id) if session_id else None)
    hint = normalize_title(raw_args)
    if not hint:
        return f"目前標題參考：`{current}`\n用法：`/suggest-thread-title 新方向或關鍵字`" if current else "用法：`/suggest-thread-title 新方向或關鍵字`"
    return f"目前：`{current}`\n建議改名：`{hint}`" if current else f"建議改名：`{hint}`"


def maybe_auto_rename(session_id: str, user_message: str, assistant_response: str) -> None:
    global LAST_AUTO_RENAME_RESULT, LAST_AUTO_RENAME_STATUS, LAST_AUTO_RENAME_TITLE, LAST_AUTO_RENAME_SKIPPED_REASON

    LAST_AUTO_RENAME_RESULT = None
    LAST_AUTO_RENAME_STATUS = None
    LAST_AUTO_RENAME_TITLE = None
    LAST_AUTO_RENAME_SKIPPED_REASON = None

    source = source_for_session(session_id) if session_id else None
    if not source or source.get("platform") != "discord":
        LAST_AUTO_RENAME_STATUS = "skipped"
        LAST_AUTO_RENAME_SKIPPED_REASON = "not-discord"
        return
    thread_id = str(source.get("thread_id") or "").strip()
    if not thread_id:
        LAST_AUTO_RENAME_STATUS = "skipped"
        LAST_AUTO_RENAME_SKIPPED_REASON = "no-thread"
        return
    if not sender_allowed(user_message):
        LAST_AUTO_RENAME_STATUS = "skipped"
        LAST_AUTO_RENAME_SKIPPED_REASON = "sender-not-allowed"
        return

    proposal = propose_auto_title(current_thread_title(source), user_message, assistant_response)
    if not proposal:
        LAST_AUTO_RENAME_STATUS = "skipped"
        LAST_AUTO_RENAME_SKIPPED_REASON = "no-proposal"
        return

    signature = f"{sender_name(user_message)}::{proposal}::{normalize_title(user_message, 160)}"
    if LAST_MESSAGE_SIG_BY_SESSION.get(session_id) == signature or LAST_AUTO_TITLE_BY_SESSION.get(session_id) == proposal:
        LAST_AUTO_RENAME_STATUS = "skipped"
        LAST_AUTO_RENAME_SKIPPED_REASON = "duplicate"
        return

    result = discord_patch_thread(thread_id, proposal)
    if result.get("ok"):
        LAST_MESSAGE_SIG_BY_SESSION[session_id] = signature
        LAST_AUTO_TITLE_BY_SESSION[session_id] = proposal
        LAST_AUTO_RENAME_STATUS = "renamed"
        LAST_AUTO_RENAME_TITLE = proposal
        LAST_AUTO_RENAME_RESULT = result.get("name", proposal)
        return

    LAST_AUTO_RENAME_STATUS = "error"
    LAST_AUTO_RENAME_SKIPPED_REASON = result.get("error", "patch-failed")


def register(ctx) -> None:
    state: dict[str, Any] = {"last_session_id": None}

    def on_session_start(**kwargs):
        session_id = kwargs.get("session_id")
        source = kwargs.get("source")
        if session_id:
            state["last_session_id"] = session_id
        remember_session_source(session_id, source)

    def rename_thread_command(raw_args: str) -> str:
        return rename_current_thread(state.get("last_session_id") or "", raw_args)

    def suggest_thread_title_command(raw_args: str) -> str:
        return suggest_title(state.get("last_session_id") or "", raw_args)

    def post_llm_call(**kwargs):
        maybe_auto_rename(
            session_id=kwargs.get("session_id") or "",
            user_message=kwargs.get("user_message") or "",
            assistant_response=kwargs.get("assistant_response") or "",
        )

    ctx.register_hook("on_session_start", on_session_start)
    ctx.register_hook("post_llm_call", post_llm_call)
    ctx.register_command("rename-thread", rename_thread_command, description="Rename the current Discord thread.")
    ctx.register_command("suggest-thread-title", suggest_thread_title_command, description="Suggest a clearer title.")
