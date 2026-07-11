#!/usr/bin/env python3
"""Query dev.ai.sr token/usage quota without printing secrets."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
import urllib.request
from pathlib import Path
from typing import Any

HOME = Path.home()
HERMES_HOME = Path(os.environ.get("HERMES_HOME", str(HOME / ".hermes"))).expanduser()
DEFAULT_ENV = HERMES_HOME / ".env"
DEFAULT_BASE_URL = "http://dev.ai.sr"


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def money(v: Any) -> str:
    try:
        return f"${float(v):,.4f}"
    except Exception:
        return str(v)


def integer(v: Any) -> str:
    try:
        return f"{int(v):,}"
    except Exception:
        return str(v)


def pct(used: Any, limit: Any) -> str:
    try:
        limit_f = float(limit)
        used_f = float(used)
        if limit_f == 0:
            return "n/a"
        return f"{used_f / limit_f * 100:.2f}%"
    except Exception:
        return "n/a"


def fetch_usage(base_url: str, api_key: str) -> dict[str, Any]:
    url = base_url.rstrip("/") + "/v1/usage"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {api_key}"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def summarize(data: dict[str, Any], *, show_models: bool, show_daily: int) -> str:
    now = dt.datetime.now().astimezone()
    lines: list[str] = []
    lines.append(f"# dev.ai.sr usage @ {now.strftime('%Y-%m-%d %H:%M:%S %z')}")
    lines.append("")
    lines.append(f"plan: {data.get('planName', 'unknown')}")
    lines.append(f"mode: {data.get('mode', 'unknown')}")
    lines.append(f"valid: {data.get('isValid', 'unknown')}")
    lines.append(f"unit: {data.get('unit', 'USD')}")
    sub = data.get("subscription") or {}
    if sub:
        lines.append("")
        lines.append("## quota")
        for label in ["daily", "weekly", "monthly"]:
            used = sub.get(f"{label}_usage_usd")
            limit = sub.get(f"{label}_limit_usd")
            if used is None and limit is None:
                continue
            rem: float | None = None
            if used is not None and limit is not None:
                try:
                    rem = float(limit) - float(used)
                except Exception:
                    rem = None
            rem_s = money(rem) if rem is not None else "unknown"
            lines.append(
                f"- {label}: used {money(used)} / limit {money(limit)} "
                f"({pct(used, limit)}), remaining {rem_s}"
            )
        if sub.get("expires_at"):
            lines.append(f"- expires_at: {sub['expires_at']}")

    usage = data.get("usage") or {}
    today = usage.get("today") or {}
    total = usage.get("total") or {}
    if today:
        lines.append("")
        lines.append("## today")
        for k in ["requests", "input_tokens", "output_tokens", "cache_read_tokens", "cache_creation_tokens", "total_tokens"]:
            if k in today:
                lines.append(f"- {k}: {integer(today[k])}")
        for k in ["cost", "actual_cost"]:
            if k in today:
                lines.append(f"- {k}: {money(today[k])}")
    if usage:
        lines.append("")
        lines.append("## realtime")
        for k in ["rpm", "tpm", "average_duration_ms"]:
            if k in usage:
                val = f"{float(usage[k]):,.2f}" if isinstance(usage[k], float) else integer(usage[k])
                lines.append(f"- {k}: {val}")
    if total:
        lines.append("")
        lines.append("## account total")
        for k in ["requests", "input_tokens", "output_tokens", "cache_read_tokens", "cache_creation_tokens", "total_tokens"]:
            if k in total:
                lines.append(f"- {k}: {integer(total[k])}")
        for k in ["cost", "actual_cost"]:
            if k in total:
                lines.append(f"- {k}: {money(total[k])}")

    if show_models and data.get("model_stats"):
        models = data["model_stats"]
        model_cost_total = sum(float(m.get("cost") or 0) for m in models)
        lines.append("")
        lines.append("## by model")
        for m in sorted(models, key=lambda x: float(x.get("cost") or 0), reverse=True):
            cost = float(m.get("cost") or 0)
            share = f"{cost / model_cost_total * 100:.2f}%" if model_cost_total else "n/a"
            lines.append(
                f"- {m.get('model')}: requests={integer(m.get('requests'))}, "
                f"total_tokens={integer(m.get('total_tokens'))}, cost={money(cost)}, cost_share={share}"
            )

    daily = sorted(data.get("daily_usage") or [], key=lambda x: x.get("date", ""))
    if show_daily and daily:
        lines.append("")
        lines.append(f"## latest {min(show_daily, len(daily))} daily rows")
        for row in daily[-show_daily:]:
            lines.append(
                f"- {row.get('date')}: requests={integer(row.get('requests'))}, "
                f"total_tokens={integer(row.get('total_tokens'))}, cost={money(row.get('cost'))}"
            )
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description="Query dev.ai.sr usage/quota via /v1/usage")
    ap.add_argument("--base-url", default=os.environ.get("DEV_AI_BASE_URL", DEFAULT_BASE_URL))
    ap.add_argument("--key-env", default=os.environ.get("DEV_AI_KEY_ENV", "OPENAI_API_KEY"))
    ap.add_argument("--env-file", default=str(DEFAULT_ENV))
    ap.add_argument("--json", action="store_true", help="print raw JSON with secrets absent")
    ap.add_argument("--models", action="store_true", default=True, help="include model breakdown")
    ap.add_argument("--no-models", action="store_false", dest="models")
    ap.add_argument("--daily", type=int, default=10, help="number of latest daily rows to show")
    args = ap.parse_args()

    load_dotenv(Path(args.env_file).expanduser())
    key = os.environ.get(args.key_env)
    if not key:
        print(f"ERROR: {args.key_env} is not set; checked env and {args.env_file}", file=sys.stderr)
        return 2
    data = fetch_usage(args.base_url, key)
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print(summarize(data, show_models=args.models, show_daily=args.daily), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
