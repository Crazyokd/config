#!/usr/bin/env python3
"""Check and publish local knowledge markdown into a Feishu/Lark Wiki node.

This script is deliberately explicit:
- `check` only verifies local lark-cli auth and target Wiki readability.
- `dry-run` lists local documents that would be published.
- `publish` requires `--yes`; drafts are skipped unless `--include-drafts`.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


HOME = Path.home()
DEFAULT_ROOT = Path(os.environ.get("DAILY_FORGE_ROOT", str(HOME / "repo" / "developer-knowledge"))).expanduser()
DEFAULT_WIKI_URL = os.environ.get(
    "DAILY_FORGE_LARK_WIKI_URL",
    "",
)


def run_lark(args: list[str], *, input_text: str | None = None) -> tuple[int, str, str]:
    env = os.environ.copy()
    env.setdefault("LARKSUITE_CLI_NO_UPDATE_NOTIFIER", "1")
    env.setdefault("LARKSUITE_CLI_NO_SKILLS_NOTIFIER", "1")
    proc = subprocess.run(
        ["lark-cli", *args],
        text=True,
        input=input_text,
        capture_output=True,
        env=env,
        check=False,
    )
    return proc.returncode, proc.stdout, proc.stderr


def load_manifest(root: Path) -> dict[str, Any]:
    path = root / "manifests" / "lark-sync.json"
    if not path.exists():
        raise SystemExit(f"manifest not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def save_manifest(root: Path, manifest: dict[str, Any]) -> None:
    path = root / "manifests" / "lark-sync.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def wiki_token(raw: str) -> str:
    match = re.search(r"/wiki/([A-Za-z0-9]+)", raw)
    return match.group(1) if match else raw


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def publishable_markdown(text: str) -> str:
    """Strip local-only YAML frontmatter before publishing to Feishu."""
    if text.startswith("---\n"):
        end = text.find("\n---\n", 4)
        if end >= 0:
            return text[end + len("\n---\n") :].lstrip()
    return text


def parse_json_envelope(stdout: str, stderr: str) -> dict[str, Any] | None:
    for text in (stdout, stderr):
        text = text.strip()
        if not text:
            continue
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            continue
    return None


def command_check(args: argparse.Namespace) -> int:
    code, out, err = run_lark(["auth", "status", "--json", "--verify"])
    print(out.strip() or err.strip())
    if code != 0:
        return code

    target = args.wiki_url
    code, out, err = run_lark(["wiki", "+node-get", "--node-token", target, "--as", "user", "--format", "json"])
    if code == 0:
        print(out.strip())
        return 0
    print(err.strip() or out.strip())
    envelope = parse_json_envelope(out, err)
    missing = (((envelope or {}).get("error") or {}).get("missing_scopes") or [])
    if missing:
        scope_arg = " ".join(missing)
        print(f"\nmissing wiki read scopes; run:\n  lark-cli auth login --scope \"{scope_arg}\" --no-wait --json")
    return code


def selected_documents(manifest: dict[str, Any], include_drafts: bool) -> list[dict[str, Any]]:
    docs = []
    for doc in manifest.get("documents", []):
        if not isinstance(doc, dict):
            continue
        state = str(doc.get("sync_state", "draft"))
        if state == "ready" or include_drafts:
            docs.append(doc)
    return docs


def command_dry_run(args: argparse.Namespace) -> int:
    manifest = load_manifest(args.root)
    docs = selected_documents(manifest, args.include_drafts)
    print(f"target_wiki_url: {manifest.get('target_wiki_url') or args.wiki_url}")
    print(f"documents_considered: {len(docs)}")
    for doc in docs:
        path = Path(str(doc.get("local_path", ""))).expanduser()
        status = "missing"
        changed = "unknown"
        if path.exists():
            status = "exists"
            changed = "yes" if file_hash(path) != doc.get("published_hash") else "no"
        print(f"- {doc.get('sync_state', 'draft')} {status} changed={changed} {doc.get('title', path.stem)} :: {path}")
    return 0


def create_doc(parent_token: str, title: str, content: str) -> tuple[int, dict[str, Any] | None, str]:
    code, out, err = run_lark(
        [
            "docs",
            "+create",
            "--as",
            "user",
            "--doc-format",
            "markdown",
            "--title",
            title,
            "--parent-token",
            parent_token,
            "--content",
            "-",
            "--format",
            "json",
        ],
        input_text=content,
    )
    return code, parse_json_envelope(out, err), err.strip() or out.strip()


def overwrite_doc(doc_token: str, content: str) -> tuple[int, dict[str, Any] | None, str]:
    code, out, err = run_lark(
        [
            "docs",
            "+update",
            "--as",
            "user",
            "--doc",
            doc_token,
            "--command",
            "overwrite",
            "--doc-format",
            "markdown",
            "--content",
            "-",
            "--format",
            "json",
        ],
        input_text=content,
    )
    return code, parse_json_envelope(out, err), err.strip() or out.strip()


def command_publish(args: argparse.Namespace) -> int:
    if not args.yes:
        print("publish is a write operation; rerun with --yes after reviewing dry-run output")
        return 2
    manifest = load_manifest(args.root)
    target = manifest.get("target_wiki_url") or args.wiki_url
    parent_token = wiki_token(str(target))
    docs = selected_documents(manifest, args.include_drafts)
    failures = 0
    for doc in docs:
        path = Path(str(doc.get("local_path", ""))).expanduser()
        if not path.exists():
            print(f"missing local file: {path}")
            failures += 1
            continue
        content = publishable_markdown(path.read_text(encoding="utf-8"))
        current_hash = file_hash(path)
        if current_hash == doc.get("published_hash"):
            print(f"unchanged: {path}")
            continue
        title = str(doc.get("title") or path.stem)
        doc_token = str(doc.get("doc_token") or "")
        if doc_token:
            if not args.allow_overwrite:
                print(f"skip existing doc without --allow-overwrite: {title} ({doc_token})")
                continue
            code, envelope, msg = overwrite_doc(doc_token, content)
        else:
            code, envelope, msg = create_doc(parent_token, title, content)
        if code != 0 or not envelope or not envelope.get("ok"):
            print(f"publish failed: {title}\n{msg}")
            failures += 1
            continue
        document = ((envelope.get("data") or {}).get("document") or {})
        doc["doc_token"] = document.get("document_id") or doc.get("doc_token")
        doc["url"] = document.get("url") or doc.get("url")
        doc["published_hash"] = current_hash
        doc["sync_state"] = "published"
        print(f"published: {title} -> {doc.get('url') or doc.get('doc_token')}")
    save_manifest(args.root, manifest)
    return 1 if failures else 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Sync daily forge knowledge docs to a Feishu/Lark Wiki target")
    ap.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    ap.add_argument("--wiki-url", default=DEFAULT_WIKI_URL)
    sub = ap.add_subparsers(dest="command", required=True)
    sub.add_parser("check", help="verify auth and target wiki node readability")
    dry = sub.add_parser("dry-run", help="show documents that would be published")
    dry.add_argument("--include-drafts", action="store_true")
    pub = sub.add_parser("publish", help="create/update Feishu docs from local markdown")
    pub.add_argument("--include-drafts", action="store_true")
    pub.add_argument("--allow-overwrite", action="store_true")
    pub.add_argument("--yes", action="store_true")
    args = ap.parse_args()
    args.root = args.root.expanduser()
    if args.command == "check":
        return command_check(args)
    if args.command == "dry-run":
        return command_dry_run(args)
    if args.command == "publish":
        return command_publish(args)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
