# Deterministic daily-report cron pipeline

Use this reference when the user asks how the current developer diary/daily-report automation is produced, or whether changing Hermes' provider/model will affect it.

## Current architecture pattern

The daily report can be produced in **script-only/no-agent mode**. In that mode the cron job does not call the Hermes main model, provider, Codex runtime server, or auxiliary LLMs. The Python script writes the report and prints stdout; Hermes cron only schedules and delivers the output.

Typical job shape observed:

```text
name: daily-developer-work-diary
schedule: 20 3 * * *
script: daily_developer_report_context.py
mode: no-agent / script stdout delivered directly
```

Therefore, changing Hermes' default provider/model (for example to Codex) will not improve the prose or reasoning quality of this specific daily report unless the job is converted back to agent mode or the script itself calls a model.

## Data flow

```text
Codex / Claude / Hermes local sessions
        ↓
ingest_external_agent_sessions.py
        ↓
~/.hermes/state.db
        ↓
daily_developer_report_context.py
        ↓
$DAILY_REPORT_DIR or ~/hermes-home/reports/work-daily/YYYY-MM-DD.md
        ↓
cron no-agent delivery
```

The deterministic report script usually:

1. Defaults to the previous local day because the cron runs after midnight.
2. Runs `ingest_external_agent_sessions.py --quiet` unless disabled.
3. Reads Hermes `state.db` directly.
4. Selects sessions overlapping the target time window.
5. Scores and filters user/assistant messages with keyword and noise heuristics.
6. Writes a fixed-structure Markdown report with metadata, main progress, technical sediment, pitfalls, follow-ups, and indexes.

## External-session ingest

`ingest_external_agent_sessions.py` is model-free and idempotent. It can scan sources such as:

- `~/.codex/sessions/**`
- `~/.codex/archived_sessions/**`
- Codex `state_5.sqlite` rollout paths
- `~/.claude/projects/**/*.jsonl`
- `~/.claude/history.jsonl`

It parses user/assistant/tool records into Hermes sessions/messages and tracks source hashes in an ingest index so unchanged files are skipped.

## Separate bridge job

A second cron such as `daily-external-agent-session-bridge` may run `external_agent_session_bridge_cron.py`. That wrapper ingests external sessions and then runs a native review script for memory/skill evolution. It is not the daily-report author unless explicitly wired into the report job.

## How to answer the common user question

If the user asks, "Will using Codex Hermes help the daily report?":

- Say **not for the current no-agent report-writing step**; provider changes do not affect a script-only cron.
- Say **Codex still helps as a data source** because Codex transcripts are ingested into `state.db` and can appear in the report.
- If they want a smarter report, propose one of:
  1. keep no-agent and improve deterministic clustering/filtering/rubrics;
  2. convert the cron to agent mode with a bounded context pack;
  3. keep deterministic extraction but add an explicit model-backed distillation stage inside the script.

## Quality implication

The no-agent approach is resilient to provider empty streams, timeouts, and context failures, but it tends to produce extractive reports. For this user's preferred developer-knowledge-pack quality, the deterministic pipeline needs stronger topic clustering, deduplication, causal-chain reconstruction, and article generation, or a controlled model-backed second pass.
