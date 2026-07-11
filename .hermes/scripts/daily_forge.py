#!/usr/bin/env python3
"""Forge daily AI artifacts and developer knowledge from the shared Hindsight bank.

The default path is intentionally manual-friendly:
- collect only a compact source index, not a transcript/evidence pack;
- use high-budget Hindsight reflect for topic selection and drafting;
- write local markdown first;
- mark Feishu sync as a later explicit publish step.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys
import textwrap
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


HOME = Path.home()
HERMES_HOME = Path(os.environ.get("HERMES_HOME", str(HOME / ".hermes"))).expanduser()
STATE_DB = HERMES_HOME / "state.db"
INGEST_SCRIPT = HERMES_HOME / "scripts" / "ingest_external_agent_sessions.py"
DEFAULT_ROOT = Path(os.environ.get("DAILY_FORGE_ROOT", str(HOME / "repo" / "developer-knowledge"))).expanduser()
DEFAULT_API_URL = os.environ.get("HINDSIGHT_API_URL", "http://127.0.0.1:8888")
DEFAULT_BANK_ID = os.environ.get("HINDSIGHT_BANK_ID", "hermes-unified")
DEFAULT_LARK_WIKI_URL = os.environ.get(
    "DAILY_FORGE_LARK_WIKI_URL",
    "",
)


TECH_HINT_RE = re.compile(
    r"(easygo|sros|hermes|hindsight|codex|claude|feishu|lark|ros2|mqtt|vda5050|"
    r"rust|python|typescript|sqlite|postgres|pgvector|systemd|docker|deploy|"
    r"hook|mcp|backfill|memory|knowledge|skill|rule|runbook|api|schema|"
    r"build|test|lint|debug|root cause|architecture|架构|边界|验证|根因|"
    r"部署|回滚|接口|契约|知识库|技能|规则|记忆)",
    re.IGNORECASE,
)
NOISE_RE = re.compile(r"^(ok|好的|嗯|谢谢|thanks|继续|收到|在吗|怎么样|^$)", re.IGNORECASE)


@dataclass
class SessionIndex:
    session_id: str
    source: str
    title: str
    cwd: str
    started_at: float
    ended_at: float
    message_count: int
    tool_call_count: int
    archived: bool
    topic_hint: str
    score: int

    def to_json(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "source": self.source,
            "title": self.title,
            "cwd": self.cwd,
            "started_at": fmt_ts(self.started_at),
            "ended_at": fmt_ts(self.ended_at),
            "message_count": self.message_count,
            "tool_call_count": self.tool_call_count,
            "archived": self.archived,
            "topic_hint": self.topic_hint,
            "score": self.score,
        }


def local_now() -> dt.datetime:
    return dt.datetime.now().astimezone()


def parse_target_date(raw: str | None) -> dt.date:
    if raw:
        return dt.date.fromisoformat(raw)
    env = os.environ.get("DAILY_FORGE_DATE")
    if env:
        return dt.date.fromisoformat(env)
    return (local_now() - dt.timedelta(days=1)).date()


def day_window(target: dt.date, late_hours: float) -> tuple[dt.datetime, dt.datetime]:
    tz = local_now().tzinfo
    start = dt.datetime.combine(target, dt.time.min, tzinfo=tz)
    end = dt.datetime.combine(target + dt.timedelta(days=1), dt.time.min, tzinfo=tz)
    if late_hours > 0:
        end = min(local_now(), end + dt.timedelta(hours=late_hours))
    return start, end


def fmt_ts(ts: float) -> str:
    return dt.datetime.fromtimestamp(float(ts), tz=local_now().tzinfo).isoformat()


def slugify(title: str, prefix: str) -> str:
    raw = title.lower()
    raw = re.sub(r"[^a-z0-9]+", "-", raw).strip("-")
    if not raw:
        raw = f"{prefix}-{hashlib.sha1(title.encode('utf-8')).hexdigest()[:8]}"
    return raw[:72].strip("-") or f"{prefix}-{hashlib.sha1(title.encode('utf-8')).hexdigest()[:8]}"


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, text: str, *, dry_run: bool) -> None:
    if dry_run:
        print(f"DRY-RUN write {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_json(path: Path, data: Any, *, dry_run: bool) -> None:
    write_text(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n", dry_run=dry_run)


def append_jsonl(path: Path, rows: list[dict[str, Any]], *, dry_run: bool) -> None:
    if dry_run:
        print(f"DRY-RUN write {path} ({len(rows)} rows)")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def run_ingest(timeout: int = 900) -> str:
    if not INGEST_SCRIPT.exists():
        return f"WARN: ingest script not found: {INGEST_SCRIPT}"
    proc = subprocess.run(
        [sys.executable, str(INGEST_SCRIPT), "--quiet"],
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    out = "\n".join(part for part in (proc.stdout.strip(), proc.stderr.strip()) if part)
    return f"ingest exit_code={proc.returncode}\n{out[-3000:]}" if out else f"ingest exit_code={proc.returncode}"


def connect_state() -> sqlite3.Connection:
    if not STATE_DB.exists():
        raise SystemExit(f"Hermes state db not found: {STATE_DB}")
    conn = sqlite3.connect(f"file:{STATE_DB}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def one_line(text: str | None, limit: int = 160) -> str:
    s = re.sub(r"\s+", " ", text or "").strip()
    return s[:limit] + ("..." if len(s) > limit else "")


def score_session(row: sqlite3.Row) -> int:
    title = row["title"] or ""
    cwd = row["cwd"] or ""
    score = 0
    score += min(int(row["message_count"] or 0), 200) // 8
    score += min(int(row["tool_call_count"] or 0), 80) // 8
    haystack = f"{title}\n{cwd}"
    if TECH_HINT_RE.search(haystack):
        score += 12
    if NOISE_RE.match(title.strip()[:40]):
        score -= 8
    if row["archived"]:
        score += 1
    return score


def collect_sessions(
    conn: sqlite3.Connection,
    start: dt.datetime,
    end: dt.datetime,
    max_sessions: int,
    include_archived: bool,
) -> list[SessionIndex]:
    archived_clause = "" if include_archived else "AND archived = 0"
    rows = conn.execute(
        f"""
        SELECT id, source, title, cwd, started_at, COALESCE(ended_at, started_at) AS ended_at,
               message_count, tool_call_count, archived
        FROM sessions
        WHERE started_at <= ?
          AND COALESCE(ended_at, started_at) >= ?
          {archived_clause}
        ORDER BY COALESCE(ended_at, started_at) DESC
        LIMIT ?
        """,
        (end.timestamp(), start.timestamp(), max_sessions * 3),
    ).fetchall()
    sessions: list[SessionIndex] = []
    for row in rows:
        title = one_line(row["title"] or row["id"], 180)
        cwd = one_line(row["cwd"] or "", 180)
        item = SessionIndex(
            session_id=str(row["id"]),
            source=str(row["source"] or ""),
            title=title,
            cwd=cwd,
            started_at=float(row["started_at"] or 0),
            ended_at=float(row["ended_at"] or row["started_at"] or 0),
            message_count=int(row["message_count"] or 0),
            tool_call_count=int(row["tool_call_count"] or 0),
            archived=bool(row["archived"]),
            topic_hint=one_line(" | ".join(p for p in (title, cwd) if p), 240),
            score=score_session(row),
        )
        sessions.append(item)
    sessions.sort(key=lambda s: (s.score, s.ended_at), reverse=True)
    return sessions[:max_sessions]


def source_inventory(sessions: list[SessionIndex]) -> str:
    by_source: dict[str, dict[str, int]] = {}
    for sess in sessions:
        bucket = by_source.setdefault(sess.source or "unknown", {"sessions": 0, "messages": 0})
        bucket["sessions"] += 1
        bucket["messages"] += sess.message_count
    if not by_source:
        return "No sessions found in the target window."
    return "\n".join(
        f"- {source}: sessions={v['sessions']}, messages={v['messages']}"
        for source, v in sorted(by_source.items(), key=lambda item: item[1]["sessions"], reverse=True)
    )


def reflect(
    *,
    api_url: str,
    bank_id: str,
    query: str,
    budget: str,
    max_tokens: int,
    timeout: int,
    response_schema: dict[str, Any] | None = None,
    include_facts: bool = True,
    exclude_mental_models: bool = False,
    fact_types: list[str] | None = None,
) -> dict[str, Any]:
    url = f"{api_url.rstrip('/')}/v1/default/banks/{urllib.parse.quote(bank_id, safe='')}/reflect"
    payload: dict[str, Any] = {
        "query": query,
        "budget": budget,
        "max_tokens": max_tokens,
    }
    if include_facts:
        payload["include"] = {"facts": {}}
    if response_schema:
        payload["response_schema"] = response_schema
    if exclude_mental_models:
        payload["exclude_mental_models"] = True
    if fact_types:
        payload["fact_types"] = fact_types
    req = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Hindsight reflect failed HTTP {exc.code}: {body[:1200]}") from exc


def retry_budgets(first: str) -> list[str]:
    out: list[str] = []
    for item in (first, "mid", "low"):
        if item not in out:
            out.append(item)
    return out


def reflect_with_budget_fallback(
    *,
    api_url: str,
    bank_id: str,
    query: str,
    budget: str,
    max_tokens: int,
    timeout: int,
    include_facts: bool,
    exclude_mental_models: bool,
    fact_types: list[str] | None,
) -> dict[str, Any]:
    errors: list[str] = []
    for candidate in retry_budgets(budget):
        try:
            return reflect(
                api_url=api_url,
                bank_id=bank_id,
                query=query,
                budget=candidate,
                max_tokens=max_tokens,
                timeout=timeout,
                include_facts=include_facts,
                exclude_mental_models=exclude_mental_models,
                fact_types=fact_types,
            )
        except RuntimeError as exc:
            errors.append(f"{candidate}: {exc}")
            if "HTTP 504" not in str(exc) and "timed out" not in str(exc).lower():
                raise
    raise RuntimeError("Hindsight reflect failed after budget fallback:\n" + "\n".join(errors))


PLAN_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "ai_artifacts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": {"type": "string", "enum": ["skill", "rule", "playbook"]},
                    "title": {"type": "string"},
                    "slug": {"type": "string"},
                    "reason": {"type": "string"},
                    "source_queries": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["type", "title", "reason"],
            },
        },
        "kb_articles": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "format": {"type": "string", "enum": ["blog", "book", "runbook"]},
                    "category": {"type": "string"},
                    "title": {"type": "string"},
                    "slug": {"type": "string"},
                    "thesis": {"type": "string"},
                    "source_queries": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["format", "category", "title", "thesis"],
            },
        },
        "skip_reason": {"type": "string"},
    },
    "required": ["ai_artifacts", "kb_articles"],
}


def plan_prompt(target: dt.date, start: dt.datetime, end: dt.datetime, sessions: list[SessionIndex]) -> str:
    session_lines = "\n".join(
        f"- {s.source} {s.session_id}: {s.topic_hint} messages={s.message_count} score={s.score}"
        for s in sessions[:40]
    )
    return textwrap.dedent(
        f"""
        你是一个本机 AI/开发工作沉淀系统。请基于 Hindsight 记忆层，为 {target.isoformat()} 选择值得沉淀的产物。

        时间窗口：{start.isoformat()} 到 {end.isoformat()}

        目标：
        1. AI 产物只选能提升后续 agent 行为的 skill/rule/playbook 候选，宁缺毋滥。
        2. 开发者知识库只选能写成博客长文、专业书籍章节或 runbook 的主题。
        3. 不要选择普通日报、状态汇报、背景介绍、空泛方案。
        4. evidence 不给人复查；如你需要来源，只用下方 session 索引和 Hindsight 自己的记忆检索。
        5. 质量优先，可以选 0 个或很少的主题；不要为了数量补水。

        本地 session 最小索引：
        {session_lines or "- empty"}

        输出必须满足 JSON schema。slug 可以省略或使用英文短横线。
        """
    ).strip()


def fallback_plan(target: dt.date, sessions: list[SessionIndex]) -> dict[str, Any]:
    hint = sessions[0].topic_hint if sessions else f"{target.isoformat()} local agent work"
    return {
        "ai_artifacts": [
            {
                "type": "playbook",
                "title": f"{target.isoformat()} 工作流复盘候选",
                "reason": "Hindsight reflect unavailable; keep a prompt-only candidate for manual rerun.",
                "source_queries": [hint],
            }
        ],
        "kb_articles": [],
        "skip_reason": "Hindsight reflect was skipped or unavailable; no knowledge article drafted.",
    }


def normalize_plan(raw: dict[str, Any], max_ai: int, max_articles: int) -> dict[str, Any]:
    plan = raw.get("structured_output") if isinstance(raw.get("structured_output"), dict) else raw
    ai = [item for item in plan.get("ai_artifacts", []) if isinstance(item, dict)]
    articles = [item for item in plan.get("kb_articles", []) if isinstance(item, dict)]
    for idx, item in enumerate(ai, 1):
        item.setdefault("type", "playbook")
        item.setdefault("title", f"AI artifact {idx}")
        item["slug"] = slugify(str(item.get("slug") or item["title"]), item["type"])
    for idx, item in enumerate(articles, 1):
        item.setdefault("format", "blog")
        item.setdefault("category", "general")
        item.setdefault("title", f"Knowledge article {idx}")
        item["slug"] = slugify(str(item.get("slug") or item["title"]), "article")
    return {
        "ai_artifacts": ai[:max_ai],
        "kb_articles": articles[:max_articles],
        "skip_reason": plan.get("skip_reason", ""),
    }


def ai_artifact_prompt(target: dt.date, item: dict[str, Any]) -> str:
    artifact_type = item.get("type", "playbook")
    title = item.get("title", "AI artifact")
    reason = item.get("reason", "")
    queries = "\n".join(f"- {q}" for q in item.get("source_queries", []) if q)
    return textwrap.dedent(
        f"""
        请把 {target.isoformat()} 的会话记忆沉淀为一个 Hermes/Codex/Claude 都可读的 AI 产物候选。

        产物类型：{artifact_type}
        标题：{title}
        选择理由：{reason}
        建议检索线索：
        {queries or "- 使用 Hindsight 自主检索相关记忆"}

        写作要求：
        - 只输出 Markdown 正文，不要解释你如何生成。
        - 这是 candidates，不是立即生效规则；frontmatter 必须包含 status: proposed。
        - skill：写成可执行能力说明，包含适用场景、输入、步骤、验证、反例。
        - rule：写成短而硬的行为约束，包含触发条件、必须做、禁止做、验证方式。
        - playbook：写成可复用流程，包含入口条件、步骤、失败恢复、完成标准。
        - 充分利用 Hindsight 记忆归纳共性，但不要粘贴 transcript 或 evidence。
        - 中文为主，命令、路径、API 名称保留英文。
        """
    ).strip()


def article_prompt(target: dt.date, item: dict[str, Any]) -> str:
    fmt = item.get("format", "blog")
    title = item.get("title", "Knowledge article")
    category = item.get("category", "general")
    thesis = item.get("thesis", "")
    queries = "\n".join(f"- {q}" for q in item.get("source_queries", []) if q)
    format_rule = {
        "blog": "写成深度技术博客：直接进入问题、机制、取舍、实现细节、验证和可迁移结论。",
        "book": "写成专业书籍章节：定义术语、建立模型、拆解接口和边界，像教材一样可复用。",
        "runbook": "写成工程 runbook：入口症状、检查命令、判断分支、修复步骤、回归验证。",
    }.get(fmt, "写成深度技术文章。")
    return textwrap.dedent(
        f"""
        请为开发者知识库写一篇本地 Markdown 长文。

        日期：{target.isoformat()}
        格式路线：{fmt}
        类别：{category}
        标题：{title}
        核心命题：{thesis}
        建议检索线索：
        {queries or "- 使用 Hindsight 自主检索相关记忆"}

        写作要求：
        - {format_rule}
        - 不要写日报，不要写项目汇报，不要大量铺背景/方案/愿景。
        - 不设置“背景”“方案”“总结”这种空泛章节；标题要指向具体技术内容。
        - 深度要接近博客长文或专业书章节，优先讲机制、边界、失败路径、验证方法。
        - 对开发者自己和外部开发者都要有用，不能只写“今天做了什么”。
        - 不要粘贴 transcript，不要给人类 evidence 复查负担；必要来源只保留为极短的文末 source index。
        - 只围绕“建议检索线索”相关记忆展开，不要扩散成全局回忆录。
        - 如果素材不足，写成较短但扎实的文章，不要为了篇幅泛化。
        - 中文为主，命令、路径、API 名称保留英文。
        - 只输出 Markdown 正文。
        """
    ).strip()


def frontmatter(extra: dict[str, Any]) -> str:
    lines = ["---"]
    for key, value in extra.items():
        if isinstance(value, list):
            lines.append(f"{key}:")
            for item in value:
                lines.append(f"  - {json.dumps(item, ensure_ascii=False)}")
        else:
            lines.append(f"{key}: {json.dumps(value, ensure_ascii=False)}")
    lines.append("---")
    return "\n".join(lines) + "\n\n"


def artifact_path(root: Path, target: dt.date, item: dict[str, Any]) -> Path:
    kind = str(item.get("type", "playbook"))
    slug = str(item.get("slug") or slugify(str(item.get("title", kind)), kind))
    folder = {
        "skill": root / "ai-products" / "skills" / "candidates" / target.isoformat(),
        "rule": root / "ai-products" / "rules" / "candidates" / target.isoformat(),
        "playbook": root / "ai-products" / "playbooks" / "candidates" / target.isoformat(),
    }.get(kind, root / "ai-products" / "playbooks" / "candidates" / target.isoformat())
    return folder / f"{slug}.md"


def article_path(root: Path, target: dt.date, item: dict[str, Any]) -> Path:
    fmt = str(item.get("format", "blog"))
    category = slugify(str(item.get("category", "general")), "category")
    slug = str(item.get("slug") or slugify(str(item.get("title", fmt)), "article"))
    if fmt == "book":
        return root / "knowledge" / "books" / category / f"{slug}.md"
    if fmt == "runbook":
        return root / "knowledge" / "runbooks" / category / f"{slug}.md"
    return root / "knowledge" / "blog" / str(target.year) / f"{slug}.md"


def based_on_index(resp: dict[str, Any]) -> list[dict[str, str]]:
    based_on = resp.get("based_on") or {}
    memories = based_on.get("memories") if isinstance(based_on, dict) else []
    out: list[dict[str, str]] = []
    for mem in memories or []:
        if not isinstance(mem, dict):
            continue
        out.append(
            {
                "id": str(mem.get("id", "")),
                "type": str(mem.get("type", "")),
                "context": one_line(str(mem.get("context", "")), 160),
            }
        )
    return out[:12]


def draft_outputs(
    *,
    root: Path,
    target: dt.date,
    plan: dict[str, Any],
    api_url: str,
    bank_id: str,
    budget: str,
    timeout: int,
    max_tokens: int,
    no_hindsight: bool,
    dry_run: bool,
    overwrite_outputs: bool,
) -> list[dict[str, Any]]:
    outputs: list[dict[str, Any]] = []
    for item in plan.get("ai_artifacts", []):
        path = artifact_path(root, target, item)
        if path.exists() and path.stat().st_size > 0 and not overwrite_outputs:
            outputs.append({"kind": "ai-artifact", "path": str(path), "title": item.get("title", path.stem), "sync": "never"})
            continue
        prompt = ai_artifact_prompt(target, item)
        if no_hindsight:
            body = "# Prompt-only AI artifact candidate\n\n```text\n" + prompt + "\n```\n"
            source_refs: list[dict[str, str]] = []
        else:
            resp = reflect(
                api_url=api_url,
                bank_id=bank_id,
                query=prompt,
                budget=budget,
                max_tokens=max_tokens,
                timeout=timeout,
                include_facts=True,
            )
            body = resp.get("text") or ""
            source_refs = based_on_index(resp)
        content = frontmatter(
            {
                "title": item.get("title", path.stem),
                "type": item.get("type", "playbook"),
                "status": "proposed",
                "source_date": target.isoformat(),
                "hindsight_bank": bank_id,
                "lark_sync": "never",
                "source_index": source_refs,
            }
        ) + body.strip() + "\n"
        write_text(path, content, dry_run=dry_run)
        outputs.append({"kind": "ai-artifact", "path": str(path), "title": item.get("title", path.stem), "sync": "never"})

    for item in plan.get("kb_articles", []):
        path = article_path(root, target, item)
        if path.exists() and path.stat().st_size > 0 and not overwrite_outputs:
            outputs.append({"kind": "knowledge", "path": str(path), "title": item.get("title", path.stem), "sync": "draft"})
            continue
        prompt = article_prompt(target, item)
        if no_hindsight:
            body = "# Prompt-only knowledge draft\n\n```text\n" + prompt + "\n```\n"
            source_refs = []
        else:
            resp = reflect_with_budget_fallback(
                api_url=api_url,
                bank_id=bank_id,
                query=prompt,
                budget=budget,
                max_tokens=max_tokens,
                timeout=timeout,
                include_facts=True,
                exclude_mental_models=True,
                fact_types=["experience", "observation"],
            )
            body = resp.get("text") or ""
            source_refs = based_on_index(resp)
        content = frontmatter(
            {
                "title": item.get("title", path.stem),
                "format": item.get("format", "blog"),
                "category": item.get("category", "general"),
                "status": "draft",
                "source_date": target.isoformat(),
                "hindsight_bank": bank_id,
                "lark_sync": "draft",
                "source_index": source_refs,
            }
        ) + body.strip() + "\n"
        write_text(path, content, dry_run=dry_run)
        outputs.append({"kind": "knowledge", "path": str(path), "title": item.get("title", path.stem), "sync": "draft"})
    return outputs


def update_lark_manifest(root: Path, outputs: list[dict[str, Any]], target_wiki_url: str, *, dry_run: bool) -> None:
    manifest_path = root / "manifests" / "lark-sync.json"
    existing: dict[str, Any] = {"target_wiki_url": target_wiki_url, "documents": []}
    if manifest_path.exists():
        try:
            existing = json.loads(read_text(manifest_path))
        except json.JSONDecodeError:
            existing = {"target_wiki_url": target_wiki_url, "documents": []}
    existing["target_wiki_url"] = target_wiki_url
    docs_by_path = {doc.get("local_path"): doc for doc in existing.get("documents", []) if isinstance(doc, dict)}
    for out in outputs:
        if out.get("kind") != "knowledge":
            continue
        path = Path(str(out["path"]))
        if not path.exists() and not dry_run:
            continue
        content_hash = "" if dry_run else hashlib.sha256(read_text(path).encode("utf-8")).hexdigest()
        doc = docs_by_path.setdefault(str(path), {"local_path": str(path)})
        doc.update(
            {
                "title": out.get("title", path.stem),
                "sync_state": out.get("sync", "draft"),
                "content_hash": content_hash,
                "updated_at": local_now().isoformat(),
            }
        )
    existing["documents"] = sorted(docs_by_path.values(), key=lambda d: str(d.get("local_path", "")))
    write_json(manifest_path, existing, dry_run=dry_run)


def render_daily_index(
    *,
    target: dt.date,
    start: dt.datetime,
    end: dt.datetime,
    root: Path,
    plan: dict[str, Any],
    outputs: list[dict[str, Any]],
    sessions: list[SessionIndex],
    ingest_summary: str,
    lark_wiki_url: str,
) -> str:
    lines = [
        f"# {target.isoformat()} Daily Forge",
        "",
        f"- window: `{start.isoformat()} -> {end.isoformat()}`",
        f"- root: `{root}`",
        f"- lark_wiki_url: `{lark_wiki_url}`",
        f"- sessions_indexed: {len(sessions)}",
        "",
        "## AI Artifacts",
    ]
    for out in outputs:
        if out["kind"] == "ai-artifact":
            lines.append(f"- [{out['title']}]({out['path']})")
    if not any(out["kind"] == "ai-artifact" for out in outputs):
        lines.append("- none")
    lines.extend(["", "## Knowledge Drafts"])
    for out in outputs:
        if out["kind"] == "knowledge":
            lines.append(f"- [{out['title']}]({out['path']})")
    if not any(out["kind"] == "knowledge" for out in outputs):
        lines.append("- none")
    if plan.get("skip_reason"):
        lines.extend(["", "## Skip Reason", "", str(plan["skip_reason"])])
    lines.extend(
        [
            "",
            "## Source Inventory",
            "",
            source_inventory(sessions),
            "",
            "## Ingest",
            "",
            "```text",
            ingest_summary.strip(),
            "```",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def command_collect(args: argparse.Namespace) -> tuple[dt.date, dt.datetime, dt.datetime, list[SessionIndex], str]:
    target = parse_target_date(args.date)
    start, end = day_window(target, args.late_hours)
    ingest_summary = "ingest skipped" if args.no_ingest or args.dry_run else run_ingest()
    conn = connect_state()
    try:
        sessions = collect_sessions(conn, start, end, args.max_sessions, args.include_archived)
    finally:
        conn.close()
    daily_dir = args.root / "daily" / target.isoformat()
    append_jsonl(daily_dir / "source-index.jsonl", [s.to_json() for s in sessions], dry_run=args.dry_run)
    write_text(daily_dir / "source-inventory.md", source_inventory(sessions) + "\n", dry_run=args.dry_run)
    return target, start, end, sessions, ingest_summary


def load_or_create_plan(
    args: argparse.Namespace,
    target: dt.date,
    start: dt.datetime,
    end: dt.datetime,
    sessions: list[SessionIndex],
) -> dict[str, Any]:
    plan_path = args.root / "daily" / target.isoformat() / "plan.json"
    prompt_path = args.root / "daily" / target.isoformat() / "prompts" / "topic-selection.md"
    prompt = plan_prompt(target, start, end, sessions)
    write_text(prompt_path, prompt + "\n", dry_run=args.dry_run)
    if args.stage == "draft" and plan_path.exists():
        return json.loads(read_text(plan_path))
    if args.no_hindsight:
        plan = fallback_plan(target, sessions)
    else:
        raw = reflect(
            api_url=args.api_url,
            bank_id=args.bank_id,
            query=prompt,
            budget=args.budget,
            max_tokens=args.plan_max_tokens,
            timeout=args.reflect_timeout,
            response_schema=PLAN_SCHEMA,
            include_facts=False,
        )
        plan = normalize_plan(raw, args.max_ai_artifacts, args.max_articles)
    write_json(plan_path, plan, dry_run=args.dry_run)
    return plan


def main() -> int:
    ap = argparse.ArgumentParser(description="Daily Hindsight forge for AI artifacts and developer knowledge")
    ap.add_argument("--date", help="target local date YYYY-MM-DD; default previous local day")
    ap.add_argument("--root", type=Path, default=DEFAULT_ROOT, help="developer knowledge root")
    ap.add_argument("--stage", choices=["collect", "plan", "draft", "full"], default=os.environ.get("DAILY_FORGE_STAGE", "full"))
    ap.add_argument("--api-url", default=DEFAULT_API_URL)
    ap.add_argument("--bank-id", default=DEFAULT_BANK_ID)
    ap.add_argument("--lark-wiki-url", default=DEFAULT_LARK_WIKI_URL)
    ap.add_argument("--budget", choices=["low", "mid", "high"], default=os.environ.get("DAILY_FORGE_REFLECT_BUDGET", "high"))
    ap.add_argument("--reflect-timeout", type=int, default=int(os.environ.get("DAILY_FORGE_REFLECT_TIMEOUT_SECONDS", "3600")))
    ap.add_argument("--plan-max-tokens", type=int, default=int(os.environ.get("DAILY_FORGE_PLAN_MAX_TOKENS", "4096")))
    ap.add_argument("--draft-max-tokens", type=int, default=int(os.environ.get("DAILY_FORGE_DRAFT_MAX_TOKENS", "12000")))
    ap.add_argument("--max-ai-artifacts", type=int, default=int(os.environ.get("DAILY_FORGE_MAX_AI_ARTIFACTS", "6")))
    ap.add_argument("--max-articles", type=int, default=int(os.environ.get("DAILY_FORGE_MAX_ARTICLES", "3")))
    ap.add_argument("--max-sessions", type=int, default=int(os.environ.get("DAILY_FORGE_MAX_SESSIONS", "80")))
    ap.add_argument("--late-hours", type=float, default=float(os.environ.get("DAILY_FORGE_LATE_HOURS", "3.5")))
    ap.add_argument("--no-ingest", action="store_true", help="skip external session ingest before reading Hermes state.db")
    ap.add_argument("--no-hindsight", action="store_true", help="write prompts/plan without calling Hindsight reflect")
    ap.add_argument("--dry-run", action="store_true", help="print writes without changing files or calling ingest")
    ap.add_argument("--overwrite-outputs", action="store_true", help="regenerate output files even when they already exist")
    include_archived_default = os.environ.get("DAILY_FORGE_INCLUDE_ARCHIVED", "1").lower() not in {"0", "false", "no", "off"}
    ap.add_argument("--include-archived", action="store_true", default=include_archived_default)
    ap.add_argument("--exclude-archived", action="store_false", dest="include_archived")
    args = ap.parse_args()
    args.root = args.root.expanduser()

    target, start, end, sessions, ingest_summary = command_collect(args)
    if args.stage == "collect":
        print(f"collected source index for {target.isoformat()}: sessions={len(sessions)}")
        return 0

    plan = load_or_create_plan(args, target, start, end, sessions)
    if args.stage == "plan":
        print(f"wrote daily forge plan for {target.isoformat()}: {args.root / 'daily' / target.isoformat() / 'plan.json'}")
        return 0

    outputs = draft_outputs(
        root=args.root,
        target=target,
        plan=plan,
        api_url=args.api_url,
        bank_id=args.bank_id,
        budget=args.budget,
        timeout=args.reflect_timeout,
        max_tokens=args.draft_max_tokens,
        no_hindsight=args.no_hindsight,
        dry_run=args.dry_run,
        overwrite_outputs=args.overwrite_outputs,
    )
    update_lark_manifest(args.root, outputs, args.lark_wiki_url, dry_run=args.dry_run)
    daily_dir = args.root / "daily" / target.isoformat()
    index = render_daily_index(
        target=target,
        start=start,
        end=end,
        root=args.root,
        plan=plan,
        outputs=outputs,
        sessions=sessions,
        ingest_summary=ingest_summary,
        lark_wiki_url=args.lark_wiki_url,
    )
    write_text(daily_dir / "index.md", index, dry_run=args.dry_run)
    write_json(
        daily_dir / "outputs.json",
        {"target_date": target.isoformat(), "outputs": outputs, "generated_at": local_now().isoformat()},
        dry_run=args.dry_run,
    )
    print(f"daily forge complete: {target.isoformat()}")
    print(f"root: {args.root}")
    print(f"outputs: {len(outputs)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
