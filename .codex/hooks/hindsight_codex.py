#!/usr/bin/env python3
"""Codex lifecycle hooks for the local Hindsight memory API."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

HOME = Path.home()
PLUGIN_ROOT = Path(
    os.environ.get(
        "CLAUDE_PLUGIN_ROOT",
        str(HOME / ".codex/plugins/cache/hindsight/hindsight-memory/0.7.4"),
    )
).expanduser()
PLUGIN_DATA = Path(
    os.environ.get("CLAUDE_PLUGIN_DATA", str(HOME / ".codex/plugins/data/hindsight-memory"))
).expanduser()
DEFAULT_API_URL = "http://127.0.0.1:8888"
DEFAULT_BANK_ID = "hermes-unified"
DEFAULT_AGENT_NAME = "codex"
DEFAULT_RECALL_TIMEOUT = 10
DEFAULT_RETAIN_TIMEOUT = 20


def setup_plugin_env() -> None:
    os.environ.setdefault("CLAUDE_PLUGIN_ROOT", str(PLUGIN_ROOT))
    os.environ.setdefault("CLAUDE_PLUGIN_DATA", str(PLUGIN_DATA))
    os.environ.setdefault("HINDSIGHT_API_URL", DEFAULT_API_URL)
    os.environ.setdefault("HINDSIGHT_BANK_ID", DEFAULT_BANK_ID)
    os.environ.setdefault("HINDSIGHT_AGENT_NAME", DEFAULT_AGENT_NAME)
    os.environ.setdefault("HINDSIGHT_REQUEST_TIMEOUT_SECONDS", str(DEFAULT_RECALL_TIMEOUT))
    PLUGIN_DATA.mkdir(parents=True, exist_ok=True)
    scripts_dir = str(PLUGIN_ROOT / "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)


setup_plugin_env()

from lib.bank import derive_bank_id, ensure_bank_mission  # noqa: E402
from lib.client import HindsightClient  # noqa: E402
from lib.config import debug_log, load_config  # noqa: E402
from lib.content import (  # noqa: E402
    compose_recall_query,
    format_current_time,
    format_memories,
    prepare_retention_transcript,
    slice_last_turns_by_user_boundary,
    strip_memory_tags,
    truncate_recall_query,
)
from lib.daemon import get_api_url  # noqa: E402
from lib.state import write_state  # noqa: E402


def read_hook_input() -> dict[str, Any]:
    try:
        data = json.load(sys.stdin)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, EOFError):
        return {}


def text_from_content(content: Any) -> str:
    if isinstance(content, str):
        return strip_memory_tags(content).strip()
    if not isinstance(content, list):
        return ""

    parts: list[str] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        block_type = block.get("type")
        if block_type in {"input_text", "output_text", "text"}:
            text = block.get("text")
            if isinstance(text, str) and text.strip():
                parts.append(strip_memory_tags(text).strip())
        elif block_type == "tool_result":
            result_content = block.get("content", "")
            if isinstance(result_content, str) and result_content.strip():
                parts.append(strip_memory_tags(result_content).strip())
    return "\n".join(part for part in parts if part).strip()


def is_codex_message_payload(payload: dict[str, Any]) -> bool:
    return payload.get("type") == "message" and payload.get("role") in {"user", "assistant"}


def should_skip_message(role: str, text: str) -> bool:
    stripped = text.lstrip()
    if not stripped:
        return True
    if role == "user" and stripped.startswith("# AGENTS.md instructions"):
        return True
    if role == "user" and stripped.startswith("<environment_context>"):
        return True
    return False


def read_codex_transcript(transcript_path: str | None) -> list[dict[str, Any]]:
    if not transcript_path:
        return []
    path = Path(transcript_path)
    if not path.is_file():
        return []

    messages: list[dict[str, Any]] = []
    try:
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                payload = entry.get("payload")
                if not isinstance(payload, dict) or not is_codex_message_payload(payload):
                    continue
                role = payload.get("role")
                text = text_from_content(payload.get("content"))
                if should_skip_message(role, text):
                    continue
                messages.append({"role": role, "content": text, "timestamp": entry.get("timestamp", "")})
    except OSError:
        return []
    return messages


def latest_prompt_from_hook_or_transcript(hook_input: dict[str, Any]) -> str:
    for key in ("prompt", "user_prompt", "userPrompt", "message"):
        value = hook_input.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    messages = read_codex_transcript(hook_input.get("transcript_path"))
    for msg in reversed(messages):
        if msg.get("role") == "user":
            content = msg.get("content")
            if isinstance(content, str) and content.strip():
                return content.strip()
    return ""


def load_hindsight_config() -> dict[str, Any]:
    config = load_config()
    config["agentName"] = os.environ.get("HINDSIGHT_AGENT_NAME", DEFAULT_AGENT_NAME)
    config["bankId"] = os.environ.get("HINDSIGHT_BANK_ID", DEFAULT_BANK_ID)
    config["hindsightApiUrl"] = os.environ.get("HINDSIGHT_API_URL", DEFAULT_API_URL)
    config["requestTimeoutSeconds"] = int(os.environ.get("HINDSIGHT_REQUEST_TIMEOUT_SECONDS", DEFAULT_RECALL_TIMEOUT))
    config["retainContext"] = os.environ.get("HINDSIGHT_RETAIN_CONTEXT", "codex-hook")
    config["retainTags"] = ["codex", "codex-hook", "{session_id}"]
    return config


def make_client(config: dict[str, Any], *, allow_daemon_start: bool) -> tuple[HindsightClient | None, str | None]:
    def dbg(*args: Any) -> None:
        debug_log(config, *args)

    try:
        api_url = get_api_url(config, debug_fn=dbg, allow_daemon_start=allow_daemon_start)
        return HindsightClient(
            api_url,
            config.get("hindsightApiToken"),
            request_timeout_override=config.get("requestTimeoutSeconds"),
        ), None
    except Exception as exc:  # graceful degradation for hooks
        return None, str(exc)


def filter_by_min_scores(results: list[dict[str, Any]], min_scores: dict[str, Any]) -> list[dict[str, Any]]:
    floors: dict[str, float] = {}
    for field, floor in (min_scores or {}).items():
        try:
            floors[field] = float(floor)
        except (TypeError, ValueError):
            continue
    if not floors:
        return results

    filtered: list[dict[str, Any]] = []
    for result in results:
        scores = result.get("scores") or {}
        keep = True
        for field, floor in floors.items():
            value = scores.get(field)
            if isinstance(value, (int, float)) and value < floor:
                keep = False
                break
        if keep:
            filtered.append(result)
    return filtered


def command_recall(args: argparse.Namespace) -> int:
    hook_input = read_hook_input()
    config = load_hindsight_config()
    prompt = latest_prompt_from_hook_or_transcript(hook_input)
    if len(prompt) < 5:
        return 0

    client, error = make_client(config, allow_daemon_start=False)
    if client is None:
        print(f"[Hindsight] Recall skipped: {error}", file=sys.stderr)
        return 0

    bank_id = derive_bank_id(hook_input, config)
    ensure_bank_mission(client, bank_id, config, debug_fn=lambda *a: debug_log(config, *a))

    recall_context_turns = int(config.get("recallContextTurns", 1) or 1)
    recall_max_query_chars = int(config.get("recallMaxQueryChars", 800) or 800)
    if recall_context_turns > 1:
        messages = read_codex_transcript(hook_input.get("transcript_path"))
        query = compose_recall_query(prompt, messages, recall_context_turns, config.get("recallRoles"))
    else:
        query = prompt
    query = truncate_recall_query(query, prompt, recall_max_query_chars)

    try:
        response = client.recall(
            bank_id=bank_id,
            query=query,
            max_tokens=int(config.get("recallMaxTokens", 1024) or 1024),
            budget=config.get("recallBudget", "mid"),
            types=config.get("recallTypes"),
            tags=config.get("recallTags") or None,
            tags_match=config.get("recallTagsMatch") if config.get("recallTags") else None,
            tag_groups=config.get("recallTagGroups") or None,
            timeout=DEFAULT_RECALL_TIMEOUT,
        )
    except Exception as exc:
        print(f"[Hindsight] Recall failed: {exc}", file=sys.stderr)
        return 0

    results = filter_by_min_scores(response.get("results", []), config.get("recallMinScores") or {})
    if not results:
        return 0

    context_message = (
        "<hindsight_memories>\n"
        f"{config.get('recallPromptPreamble', '')}\n"
        f"Current time - {format_current_time()}\n\n"
        f"{format_memories(results)}\n"
        "</hindsight_memories>"
    )
    write_state(
        "codex_last_recall.json",
        {
            "bank_id": bank_id,
            "result_count": len(results),
            "saved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        },
    )
    output = {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": context_message,
        }
    }
    if args.dry_run:
        output["dryRun"] = True
    json.dump(output, sys.stdout, ensure_ascii=False)
    return 0


def resolve_templates(values: list[str], template_vars: dict[str, str]) -> list[str]:
    out: list[str] = []
    for value in values:
        resolved = value
        for key, replacement in template_vars.items():
            resolved = resolved.replace(f"{{{key}}}", replacement)
        if ":" in resolved and resolved.split(":", 1)[1] == "":
            continue
        out.append(resolved)
    return out


def command_retain(args: argparse.Namespace) -> int:
    hook_input = read_hook_input()
    config = load_hindsight_config()
    messages = read_codex_transcript(hook_input.get("transcript_path"))
    if not messages:
        return 0

    messages_to_retain = slice_last_turns_by_user_boundary(messages, int(os.environ.get("HINDSIGHT_CODEX_RETAIN_TURNS", "1")))
    transcript, message_count = prepare_retention_transcript(
        messages_to_retain,
        retain_roles=config.get("retainRoles", ["user", "assistant"]),
        retain_full_window=True,
        include_tool_calls=False,
    )
    if not transcript:
        return 0

    session_id = str(hook_input.get("session_id") or "unknown")
    turn_id = str(hook_input.get("turn_id") or len(messages))
    cwd = str(hook_input.get("cwd") or "")
    model = str(hook_input.get("model") or "")
    content = (
        "# Codex hook transcript retained for Hindsight\n"
        + json.dumps(
            {
                "session_id": session_id,
                "turn_id": turn_id,
                "cwd": cwd,
                "model": model,
                "message_count": message_count,
                "retention_policy": "last_codex_turn",
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        + "\n\n"
        + transcript
    )

    if args.dry_run:
        json.dump(
            {
                "would_retain": True,
                "session_id": session_id,
                "turn_id": turn_id,
                "message_count": message_count,
                "content_chars": len(content),
            },
            sys.stdout,
            ensure_ascii=False,
        )
        return 0

    client, error = make_client(config, allow_daemon_start=False)
    if client is None:
        print(f"[Hindsight] Retain skipped: {error}", file=sys.stderr)
        return 0

    bank_id = derive_bank_id(hook_input, config)
    ensure_bank_mission(client, bank_id, config, debug_fn=lambda *a: debug_log(config, *a))
    timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    template_vars = {
        "session_id": session_id,
        "bank_id": bank_id,
        "timestamp": timestamp,
        "user_id": os.environ.get("HINDSIGHT_USER_ID", ""),
    }
    tags = resolve_templates(config.get("retainTags", []), template_vars)
    metadata = {
        "retained_at": timestamp,
        "message_count": str(message_count),
        "session_id": session_id,
        "turn_id": turn_id,
        "cwd": cwd,
        "model": model,
        "source": "codex-hook",
    }

    try:
        client.retain(
            bank_id=bank_id,
            content=content,
            document_id=f"codex:{session_id}:turn:{turn_id}",
            context=config.get("retainContext", "codex-hook"),
            metadata=metadata,
            tags=tags or None,
            timeout=DEFAULT_RETAIN_TIMEOUT,
        )
    except Exception as exc:
        print(f"[Hindsight] Retain failed: {exc}", file=sys.stderr)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Codex Hindsight recall/retain hooks")
    parser.add_argument("command", choices=["recall", "retain"])
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.command == "recall":
        return command_recall(args)
    if args.command == "retain":
        return command_retain(args)
    return 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"[Hindsight] Codex hook unexpected error: {exc}", file=sys.stderr)
        raise SystemExit(0)
