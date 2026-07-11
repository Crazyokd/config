# Hindsight-backed daily knowledge-pack cron pattern

Use this reference when the user wants a scheduled job that turns the previous day's Hindsight memories into developer-facing knowledge-base articles.

## Proven shape

Create a Hermes cron job that runs in agent mode with `developer-knowledge-packs` loaded, plus a small deterministic context script.

- Context script: `~/.hermes/scripts/hindsight_daily_knowledge_context.py`
- Typical output root: `~/repo/ai/knowledge/daily/`
- Output directory: `YYYY-MM-DD-knowledge-pack/`
- Workdir: the knowledge repo, e.g. `/home/standard/repo/ai`
- Schedule: after other ingest/retain jobs, e.g. `30 4 * * *`

The context script should only emit deterministic facts and constraints:

- target date and local time window;
- output directory;
- quality requirements;
- suggested Hindsight queries.

The cron agent writes the actual documents.

## Required output

A high-signal day should produce:

```text
YYYY-MM-DD-knowledge-pack/
  README.md
  01-<topic>.md
  02-<topic>.md
  03-<topic>.md
  ...
```

The README is an index and reading route. The topic docs are long-form articles, not daily-report bullets.

## Important fallback: Hindsight tools may not be exposed in cron

In a cron-agent session, `hindsight_recall` / `hindsight_reflect` may not appear as direct tool schemas even when Hindsight works in normal chat. Do not treat that as a reason to fail or to fabricate results.

Fallback to the Python SDK from the Hermes venv:

```python
from hindsight_client import Hindsight
client = Hindsight(base_url="http://127.0.0.1:8888")
resp = await client.arecall(
    bank_id="hermes-unified",
    query="2026-07-10 开发 技术 决策 根因 验证 EasyGo SROS Hermes Codex Hindsight",
    budget="low",
    max_tokens=3000,
)
```

Prefer reading config from:

```text
~/.hermes/hindsight/config.json
```

Typical local defaults:

```text
base_url: http://127.0.0.1:8888
bank_id: hermes-unified
python: ~/.hermes/hermes-agent/venv/bin/python
```

## Retrieval strategy

`hindsight_reflect` can be useful, but exact day-window reflect can return sparse or empty themes. Use it as a theme-finding attempt, not the only source.

Robust pattern:

1. Try one date-scoped reflect query for theme discovery.
2. If reflect is empty, weak, or slow, run multiple focused recall queries:
   - `<date> 开发 技术 决策 根因 验证 EasyGo SROS Hermes Codex Hindsight Feishu Lark`
   - `<date> Hindsight Codex Hermes 统一记忆 hooks retain recall external session bridge`
   - `<date> failure root cause verification commands paths commits tests`
   - `<date> architecture design boundary runbook debugging knowledge promotion`
3. Cluster recalled facts by durable engineering topic, not by session title.
4. If evidence is insufficient for three docs, say so in README rather than padding.

## Verification gate

After generation, verify at least:

```bash
find <output_dir> -maxdepth 1 -type f -printf '%f %s bytes\n' | sort
wc -l -c <output_dir>/*.md
grep -R "user:\|assistant:\|关键证据摘录\|KPI\|领导汇报" -n <output_dir> || true
```

Reject or revise output if it contains transcript labels, daily-report style sections, KPI tone, or vague claims without evidence.

## Example of a good generated pack

A successful run generated:

```text
README.md                                      ~8 KB
01-hindsight-local-deployment-boundary.md      ~8 KB
02-codex-hindsight-hooks-and-bank-sharing.md   ~8 KB
03-external-agent-session-bridge-time-budget.md ~9 KB
04-easygo-localization-error-semantics.md      ~9 KB
```

The topics taught subsystem boundaries and reusable rules instead of listing what happened that day.
