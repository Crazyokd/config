#!/usr/bin/env python3
"""Ingest Codex and Claude Code session JSONL files into Hermes state.db.

Idempotent daily job:
- scans ~/.codex/sessions/**, ~/.codex/archived_sessions/** and Codex state_5.sqlite rollout paths
- scans ~/.claude/projects/**/*.jsonl (including subagents/workflows)
- parses user/assistant/tool records into Hermes sessions/messages
- tracks file sha256 in ~/.hermes/external-session-ingest/index.sqlite so unchanged files are skipped

This script intentionally does not require an LLM. It writes directly to the
Hermes session DB so session_search can retrieve imported transcripts.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any, Iterable

HOME = Path.home()
HERMES_HOME = Path(os.environ.get("HERMES_HOME", str(HOME / ".hermes"))).expanduser()
STATE_DB = HERMES_HOME / "state.db"
INDEX_DIR = HERMES_HOME / "external-session-ingest"
INDEX_DB = INDEX_DIR / "index.sqlite"
HERMES_SRC = HERMES_HOME / "hermes-agent"

MAX_MESSAGE_CHARS = 120_000
MAX_TITLE_CHARS = 120


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def stable_path_hash(path: Path) -> str:
    return hashlib.sha1(str(path).encode("utf-8", "replace")).hexdigest()[:16]


def parse_ts(value: Any, fallback: float | None = None) -> float:
    if value is None:
        return fallback if fallback is not None else time.time()
    if isinstance(value, (int, float)):
        # Claude uses milliseconds, Codex sometimes seconds.
        return float(value) / 1000.0 if value > 10_000_000_000 else float(value)
    if isinstance(value, str):
        text = value.strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            return dt.datetime.fromisoformat(text).timestamp()
        except ValueError:
            return fallback if fallback is not None else time.time()
    return fallback if fallback is not None else time.time()


def truncate(text: str | None, limit: int = MAX_MESSAGE_CHARS) -> str | None:
    if text is None:
        return None
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n\n[... truncated by external-session ingest at {limit} chars ...]"


def stringify(obj: Any) -> str:
    if obj is None:
        return ""
    if isinstance(obj, str):
        return obj
    return json.dumps(obj, ensure_ascii=False, sort_keys=True)


def flatten_content(content: Any) -> str:
    """Flatten OpenAI/Codex/Claude content shapes into searchable text."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
                continue
            if not isinstance(part, dict):
                parts.append(stringify(part))
                continue
            ptype = part.get("type", "part")
            # Common text-bearing keys across Codex/Claude/OpenAI shapes.
            for key in ("text", "input_text", "output_text", "content"):
                if isinstance(part.get(key), str):
                    parts.append(part[key])
                    break
            else:
                if ptype in {"tool_use", "function_call"}:
                    name = part.get("name") or part.get("tool_name") or "tool"
                    args = part.get("input") or part.get("arguments") or {}
                    parts.append(f"[tool_use:{name}]\n{stringify(args)}")
                elif ptype in {"tool_result", "function_call_output"}:
                    parts.append(f"[tool_result]\n{stringify(part.get('content') or part.get('output') or part)}")
                elif ptype not in {"thinking", "redacted_thinking"}:
                    parts.append(stringify(part))
        return "\n".join(p for p in parts if p)
    if isinstance(content, dict):
        return flatten_content([content])
    return stringify(content)


def read_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for line_no, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                yield {"type": "_parse_error", "timestamp": path.stat().st_mtime, "message": f"JSON parse error at line {line_no}"}
                continue
            if isinstance(obj, dict):
                yield obj


def load_codex_thread_index() -> dict[str, dict[str, Any]]:
    db_path = HOME / ".codex" / "state_5.sqlite"
    out: dict[str, dict[str, Any]] = {}
    if not db_path.exists():
        return out
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        for row in conn.execute("SELECT id, rollout_path, source, model_provider, cwd, title, created_at, updated_at FROM threads"):
            path = str(row["rollout_path"] or "")
            if path:
                out[path] = dict(row)
        conn.close()
    except Exception as exc:
        print(f"WARN: could not read Codex thread index {db_path}: {exc}", file=sys.stderr)
    return out


def readable_file(path: Path) -> bool:
    try:
        return path.exists() and path.is_file()
    except OSError:
        return False


def codex_paths() -> list[Path]:
    seen: set[Path] = set()
    paths: list[Path] = []
    for raw in load_codex_thread_index().keys():
        p = Path(raw).expanduser()
        if readable_file(p) and p.suffix == ".jsonl" and p not in seen:
            paths.append(p); seen.add(p)
    root = HOME / ".codex"
    for pattern in ("sessions/**/*.jsonl", "archived_sessions/**/*.jsonl"):
        for p in root.glob(pattern):
            if p.is_file() and p not in seen:
                paths.append(p); seen.add(p)
    return sorted(paths, key=lambda p: str(p))


def claude_paths() -> list[Path]:
    root = HOME / ".claude"
    paths: list[Path] = []
    for p in root.glob("projects/**/*.jsonl"):
        if p.is_file():
            paths.append(p)
    # Keep prompt history searchable as a small auxiliary transcript. Project
    # JSONLs are the primary full Claude sessions.
    history = root / "history.jsonl"
    if history.exists():
        paths.append(history)
    return sorted(paths, key=lambda p: str(p))


def first_nonempty_title(text: str | None) -> str | None:
    if not text:
        return None
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return None
    return text[:MAX_TITLE_CHARS]


def parse_codex(path: Path, codex_index: dict[str, dict[str, Any]]) -> dict[str, Any]:
    meta = codex_index.get(str(path), {})
    sid: str | None = None
    cwd = meta.get("cwd")
    title = meta.get("title")
    model = meta.get("model_provider") or "Codex"
    started = parse_ts(meta.get("created_at"), path.stat().st_mtime)
    ended = parse_ts(meta.get("updated_at"), path.stat().st_mtime)
    messages: list[dict[str, Any]] = []

    for obj in read_jsonl(path):
        ts = parse_ts(obj.get("timestamp"), path.stat().st_mtime)
        typ = obj.get("type")
        raw_payload = obj.get("payload")
        payload: dict[str, Any] = raw_payload if isinstance(raw_payload, dict) else {}
        ptype = payload.get("type")
        if typ == "session_meta":
            p = payload or {}
            sid = sid or p.get("id")
            cwd = cwd or p.get("cwd")
            model = p.get("model_provider") or model
            started = min(started, parse_ts(p.get("timestamp"), started))
            continue
        if typ == "turn_context":
            p = payload or {}
            cwd = cwd or p.get("cwd")
            model = p.get("model") or model
            continue
        if typ != "response_item" and typ != "event_msg":
            continue
        role = None
        content = ""
        tool_name = None
        tool_call_id = None
        if ptype == "message":
            role = payload.get("role")
            if role not in {"user", "assistant"}:
                continue
            content = flatten_content(payload.get("content"))
        elif ptype == "user_message":
            role = "user"
            content = flatten_content(payload.get("message"))
        elif ptype == "agent_message":
            role = "assistant"
            content = flatten_content(payload.get("message"))
        elif ptype in {"function_call", "custom_tool_call", "tool_search_call"}:
            role = "assistant"
            tool_name = payload.get("name") or payload.get("tool") or ptype
            tool_call_id = payload.get("call_id")
            args = payload.get("arguments") or payload.get("input") or payload
            content = f"[tool_call:{tool_name}]\n{stringify(args)}"
        elif ptype in {"function_call_output", "custom_tool_call_output", "tool_search_output"}:
            role = "tool"
            tool_call_id = payload.get("call_id")
            tool_name = ptype
            content = flatten_content(payload.get("output") or payload.get("tools") or payload)
        else:
            continue
        content = truncate(content)
        if content:
            if title is None and role == "user":
                title = first_nonempty_title(content)
            messages.append({"role": role, "content": content, "timestamp": ts, "tool_name": tool_name, "tool_call_id": tool_call_id})
    match = re.search(r"([0-9a-f]{8,}-[0-9a-f-]{20,})", path.name, re.I)
    sid = sid or (match.group(1) if match else stable_path_hash(path))
    return {
        "session_id": f"codex:{sid}",
        "source": "codex",
        "model": model,
        "cwd": cwd,
        "title": f"[Codex] {first_nonempty_title(title) or sid} ({str(sid)[:8]})",
        "started_at": started,
        "ended_at": max([ended] + [m["timestamp"] for m in messages]) if messages else ended,
        "messages": messages,
    }


def parse_claude(path: Path) -> dict[str, Any]:
    is_history = path.name == "history.jsonl" and "projects" not in path.parts
    sid: str | None = None
    cwd: str | None = None
    model = "Claude Code"
    title: str | None = None
    started = path.stat().st_mtime
    ended = path.stat().st_mtime
    messages: list[dict[str, Any]] = []

    for obj in read_jsonl(path):
        ts = parse_ts(obj.get("timestamp"), path.stat().st_mtime)
        started = min(started, ts)
        ended = max(ended, ts)
        typ = obj.get("type")
        if typ == "ai-title":
            sid = sid or obj.get("sessionId")
            title = obj.get("aiTitle") or title
            continue
        if is_history:
            # Claude history is prompt-only but useful when no full project log
            # is available. Each line can have its own sessionId; aggregate into
            # a single searchable history transcript.
            sid = "history"
            cwd = obj.get("project") or cwd
            content = flatten_content(obj.get("display"))
            if content:
                messages.append({"role": "user", "content": truncate(content), "timestamp": ts})
                title = title or "Claude prompt history"
            continue
        if typ not in {"user", "assistant"}:
            continue
        raw_msg = obj.get("message")
        msg: dict[str, Any] = raw_msg if isinstance(raw_msg, dict) else {}
        role = msg.get("role") or typ
        if obj.get("toolUseResult") is not None or obj.get("sourceToolUseID") is not None:
            role = "tool"
        if role not in {"user", "assistant", "tool"}:
            role = typ if typ in {"user", "assistant"} else "user"
        sid = sid or obj.get("sessionId")
        cwd = cwd or obj.get("cwd")
        content = flatten_content(msg.get("content"))
        if not content and obj.get("toolUseResult") is not None:
            content = flatten_content(obj.get("toolUseResult"))
        content = truncate(content)
        if content:
            if title is None and role == "user":
                title = first_nonempty_title(content)
            messages.append({"role": role, "content": content, "timestamp": ts, "tool_call_id": obj.get("sourceToolUseID")})
    sid = sid or stable_path_hash(path)
    # Use path hash to keep subagent/workflow JSONLs distinct even when Claude
    # repeats the parent sessionId in nested files.
    sid_with_path = f"{sid}:{stable_path_hash(path)}"
    return {
        "session_id": f"claude:{sid_with_path}",
        "source": "claude",
        "model": model,
        "cwd": cwd,
        "title": f"[Claude] {first_nonempty_title(title) or sid} ({stable_path_hash(path)[:8]})",
        "started_at": started,
        "ended_at": ended,
        "messages": messages,
    }


def ensure_hermes_schema() -> None:
    if str(HERMES_SRC) not in sys.path:
        sys.path.insert(0, str(HERMES_SRC))
    try:
        from hermes_state import SessionDB  # type: ignore
        db = SessionDB(STATE_DB)
        db.close()
    except Exception as exc:
        raise SystemExit(f"ERROR: could not initialize Hermes state DB {STATE_DB}: {exc}")


def connect_state() -> sqlite3.Connection:
    conn = sqlite3.connect(str(STATE_DB), timeout=30.0, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def connect_index() -> sqlite3.Connection:
    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(INDEX_DB), timeout=30.0, isolation_level=None)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS source_files ("
        "path TEXT PRIMARY KEY, source_kind TEXT NOT NULL, sha256 TEXT NOT NULL, "
        "size INTEGER NOT NULL, mtime_ns INTEGER NOT NULL, session_id TEXT NOT NULL, "
        "message_count INTEGER NOT NULL, ingested_at REAL NOT NULL)"
    )
    return conn


def session_exists(conn: sqlite3.Connection, session_id: str) -> bool:
    row = conn.execute("SELECT 1 FROM sessions WHERE id = ?", (session_id,)).fetchone()
    return row is not None


def title_unique(conn: sqlite3.Connection, title: str, session_id: str) -> str:
    candidate = title
    suffix = 2
    while True:
        row = conn.execute("SELECT id FROM sessions WHERE title = ? AND id <> ?", (candidate, session_id)).fetchone()
        if row is None:
            return candidate
        candidate = f"{title} #{suffix}"
        suffix += 1


def write_session(conn: sqlite3.Connection, sess: dict[str, Any]) -> int:
    sid = sess["session_id"]
    messages = sess.get("messages") or []
    now = time.time()
    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute("DELETE FROM messages WHERE session_id = ?", (sid,))
        conn.execute("DELETE FROM sessions WHERE id = ?", (sid,))
        title = title_unique(conn, sess.get("title") or sid, sid)
        tool_count = sum(1 for m in messages if m.get("role") == "tool" or m.get("tool_name"))
        conn.execute(
            """INSERT INTO sessions
               (id, source, user_id, model, model_config, system_prompt, parent_session_id,
                started_at, ended_at, end_reason, message_count, tool_call_count, cwd, title)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                sid,
                sess.get("source"),
                None,
                sess.get("model"),
                json.dumps({"external_ingest": True, "source_file": sess.get("source_file")}, ensure_ascii=False),
                None,
                None,
                float(sess.get("started_at") or now),
                float(sess.get("ended_at") or now),
                "external_ingest",
                len(messages),
                tool_count,
                sess.get("cwd"),
                title,
            ),
        )
        for m in messages:
            conn.execute(
                """INSERT INTO messages
                   (session_id, role, content, tool_call_id, tool_calls, tool_name,
                    timestamp, token_count, finish_reason, reasoning, reasoning_content,
                    reasoning_details, codex_reasoning_items, codex_message_items,
                    platform_message_id, observed, active)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    sid,
                    m.get("role") or "user",
                    m.get("content"),
                    m.get("tool_call_id"),
                    None,
                    m.get("tool_name"),
                    float(m.get("timestamp") or now),
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    1,
                    1,
                ),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return len(messages)


def ingest_file(path: Path, kind: str, state: sqlite3.Connection, idx: sqlite3.Connection, codex_index: dict[str, dict[str, Any]], force: bool = False) -> tuple[str, str, int]:
    size = path.stat().st_size
    mtime_ns = path.stat().st_mtime_ns
    digest = sha256_file(path)
    parser = parse_codex if kind == "codex" else parse_claude
    sess = parser(path, codex_index) if kind == "codex" else parser(path)  # type: ignore[arg-type]
    sess["source_file"] = str(path)
    sid = sess["session_id"]

    row = idx.execute("SELECT sha256, session_id, message_count FROM source_files WHERE path = ?", (str(path),)).fetchone()
    if not force and row and row[0] == digest and row[1] == sid and session_exists(state, sid):
        return ("skipped", sid, int(row[2]))
    if not sess.get("messages"):
        # Still record empty/unsupported files to avoid daily reparsing churn.
        idx.execute(
            "INSERT OR REPLACE INTO source_files (path, source_kind, sha256, size, mtime_ns, session_id, message_count, ingested_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (str(path), kind, digest, size, mtime_ns, sid, 0, time.time()),
        )
        idx.commit()
        return ("empty", sid, 0)
    count = write_session(state, sess)
    idx.execute(
        "INSERT OR REPLACE INTO source_files (path, source_kind, sha256, size, mtime_ns, session_id, message_count, ingested_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (str(path), kind, digest, size, mtime_ns, sid, count, time.time()),
    )
    idx.commit()
    return ("ingested", sid, count)


def main() -> int:
    ap = argparse.ArgumentParser(description="Ingest Codex and Claude sessions into Hermes state.db")
    ap.add_argument("--force", action="store_true", help="re-ingest even if source hash is unchanged")
    ap.add_argument("--quiet", action="store_true", help="print only errors")
    ap.add_argument("--limit", type=int, default=0, help="limit number of files for testing")
    args = ap.parse_args()

    ensure_hermes_schema()
    codex_index = load_codex_thread_index()
    files: list[tuple[str, Path]] = []
    files += [("codex", p) for p in codex_paths()]
    files += [("claude", p) for p in claude_paths()]
    # Deduplicate by resolved path when possible.
    dedup: dict[str, tuple[str, Path]] = {}
    for kind, p in files:
        dedup[str(p)] = (kind, p)
    files = sorted(dedup.values(), key=lambda kp: (kp[0], str(kp[1])))
    if args.limit and args.limit > 0:
        files = files[: args.limit]

    state = connect_state()
    idx = connect_index()
    counts = {"ingested": 0, "skipped": 0, "empty": 0, "errors": 0, "messages": 0}
    for kind, path in files:
        try:
            status, sid, n = ingest_file(path, kind, state, idx, codex_index, force=args.force)
            counts[status] = counts.get(status, 0) + 1
            counts["messages"] += n if status == "ingested" else 0
            if not args.quiet and status == "ingested":
                print(f"{status}: {kind} {sid} messages={n} file={path}")
        except Exception as exc:
            counts["errors"] += 1
            print(f"ERROR: {kind} {path}: {exc}", file=sys.stderr)
    state.close(); idx.close()
    summary = (
        f"external-session ingest complete: files={len(files)} ingested={counts['ingested']} "
        f"skipped={counts['skipped']} empty={counts['empty']} errors={counts['errors']} "
        f"messages_added={counts['messages']}"
    )
    print(summary)
    return 1 if counts["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
