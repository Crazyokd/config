---
name: developer-knowledge-packs
description: "Generate developer-facing daily knowledge packs from long agent/session histories: multiple long-form technical knowledge documents plus a README index, not a lightweight status report."
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [developer-diary, knowledge-management, retrospectives, session-synthesis, documentation]
    related_skills: [productivity-suite, software-dev-lifecycle]
---

# Developer Knowledge Packs

## When to use

Use this skill when the user asks for, critiques, or schedules any of these from long local sessions / Codex / Claude / Hermes history:

- developer daily reports / work diaries / retrospectives;
- daily technical learning summaries;
- digesting many long agent sessions into reusable engineering knowledge;
- improving a cron job that generates developer-facing reports;
- converting session history into documentation.

If the user says a "日报" should teach them something, support next-day recovery, or preserve technical learning, treat the deliverable as a **Daily Knowledge Pack**, not as a short daily summary.

## Core principle

A high-value developer daily deliverable is not one document that says what happened. It is a small documentation set:

```text
YYYY-MM-DD-knowledge-pack/
  README.md                         # index, reading route, topic map
  01-<topic>.md                     # long-form knowledge document
  02-<topic>.md
  03-<topic>.md
  ...
```

For a normal high-signal workday, produce **at least three long-form technical documents**. If the day genuinely has fewer than three high-value knowledge topics, say so explicitly in the README and only generate the documents that meet the quality bar. Do not pad with low-value summaries.

## User preference encoded from prior corrections

The user rejected short "developer diary" summaries, card-only summaries, and generic retrospectives as too low-information. For this user, a good daily output must read like **new internal technical documentation** produced from the day's sessions.

Do not optimize toward:

- leadership/KPI reporting;
- status updates;
- commit lists;
- chat/session excerpts;
- short "what I did today" prose;
- a single monolithic daily report.

Optimize toward:

- long-form explanations of new system knowledge;
- root-cause and boundary analysis;
- source paths, commits, runtime states, commands, and verification evidence;
- reusable debugging / design rules;
- next-day recovery steps.

## Required output shape

### Teaching-depth requirement

Do not only "pose the right questions" or list what each document is about. The user explicitly wants to **learn** from each article. Write every long-form document so that a capable engineer who has not worked on that subsystem can understand the context, the moving parts, the failure mode, and the reusable rule.

Each article should therefore include an explanatory spine:

1. **Concept primer** — define the subsystem boundary and key vocabulary before jumping into the incident. Example: explain what `/mapping/stop`, state-center pose, VDA5050 `initPosition`, REST DTO units, or ROS topic subscribers mean in this system.
2. **Mechanism walkthrough** — describe the normal flow step by step, not just the broken part.
3. **Failure anatomy** — show how the observed symptoms map onto the mechanism and where the chain broke.
4. **Why the fix works** — connect the code/config change to the mechanism, so the reader learns the design principle instead of memorizing a patch.
5. **Transfer rule** — end with a rule the reader can apply to a different EasyGo/SROS problem.

A document that only lists "questions answered" is not enough. The README may list questions; the article body must teach the answers with enough background for a newcomer to the topic.

### README.md

The README is only an index and reading route. It should include:

1. date/window and evidence sources;
2. list of generated knowledge documents;
3. for each document: questions answered, when to read it later, key repositories/sessions;
4. cross-cutting lessons from the day;
5. explicit note if fewer than three long docs were generated and why.

### Each long-form document

Each topic document should be a standalone technical article. It must include most of:

- problem background and why it mattered;
- wrong initial model / likely bad assumption;
- corrected system model;
- source paths, branches, commits, runtime objects, config paths;
- root-cause chain or design decision chain;
- verification commands and actual results;
- what was deliberately not changed;
- next-day recovery commands / files to open;
- reusable rules for future similar work.

A good document should usually be 700-1500+ words when the topic is substantial. Do not compress a complex topic into a 5-bullet summary.

## Existing cron/report automation audit

When the user asks how the current 日报 is produced, or whether changing Hermes/Codex provider settings will affect it, first determine the cron job mode:

- If the daily-report job is `no_agent` / script-only, explain that Hermes provider/model changes do **not** affect the report-writing step. The script writes the Markdown and stdout directly; Hermes only schedules and delivers it.
- Distinguish **Codex as data source** from **Codex as report writer**. Codex/Claude transcripts can still matter because ingest scripts import them into Hermes `state.db`, but the current report prose/reasoning remains deterministic unless the cron is converted to agent mode or the script calls a model.
- Inspect and explain both jobs when present: the report generator (for example `daily_developer_report_context.py`) and the external-session bridge/review job (for example `external_agent_session_bridge_cron.py`). Do not conflate the bridge's memory/skill review with daily-report authoring.
- For quality improvements, prefer a deliberate choice among: improving deterministic clustering/filtering, converting the cron to agent mode with a bounded context pack, or adding a controlled model-backed distillation stage inside the script.

### Script-only daily report optimization pattern

When improving an existing deterministic/no-agent report script, do not only describe the desired editorial standard. Make a small, verifiable script change and generate a sample from a real recent day for user acceptance.

Useful durable improvements:

1. **Filter inside the target-day message window.** Long-lived Feishu/Telegram/Codex sessions can overlap many days; if the renderer scores the whole session, old high-signal messages pollute today's report. Summarize each overlapping session from messages whose timestamps fall inside `[day_start, day_end(+late_hours)]`, with only a tiny fallback for empty overlaps.
2. **Treat Codex/Claude as data sources.** Run the ingest step before sampling so newly completed external sessions are visible in `state.db`; keep the report-writing step deterministic unless the user explicitly wants model-backed rewriting.
3. **Generate an acceptance draft without overwriting the official report.** Use a drafts directory such as `reports/work-daily/drafts/<experiment>/YYYY-MM-DD.md`. If testing after midnight, consider `--late-hours 0` so the current optimization conversation does not contaminate yesterday's sample.
4. **Favor article-mode extraction over fixed status columns.** The user may reject fixed daily-report formats. For this user, a good single-report draft should read like distilled developer learning from today's sessions: group by engineering theme, preserve concrete paths/tests/commands, explain the reusable boundary or debugging rule, and avoid `user:`/`assistant:` transcript dumps.
5. **Verify before reporting.** At minimum run `python -m py_compile` on the script, run it against the sample date, and check the generated file has plausible size/content.

See `references/deterministic-daily-report-cron.md` for the current script-only pipeline pattern and answer template.

### Hindsight daily knowledge-pack cron pattern

When the source of truth is Hindsight rather than Hermes `state.db`, use the Hindsight knowledge-pack pattern in `references/hindsight-daily-knowledge-pack-cron.md`.

Key lessons from the proven implementation:

1. **Use a deterministic context script plus an agent-mode cron.** The script should emit target date, local window, output directory, quality gate, and suggested Hindsight queries; the agent should write `README.md` plus long-form topic docs.
2. **Do not assume Hindsight tools are exposed inside cron.** If `hindsight_recall` / `hindsight_reflect` are unavailable, fall back to the Python SDK in the Hermes venv and read `/home/standard/.hermes/hindsight/config.json` for `api_url` / `bank_id`.
3. **Reflect is not enough.** Date-window `reflect` can return no themes even when focused recall has useful material. Run several focused recalls and cluster evidence into durable engineering topics.
4. **Avoid direct script-only LLM long-pack generation unless tightly bounded.** Long multi-article generation through a Python LLM call can exceed cron/script time budgets. Prefer agent file-writing with verification.
5. **Verify article-pack quality.** Check file sizes and scan for transcript labels (`user:`, `assistant:`), `关键证据摘录`, KPI/leadership tone, and missing concrete evidence.

## Workflow

1. **Pick a sample/workday**
   - Prefer the most recent workday with enough engineering signal.
   - Use session counts/message counts/recent report files to select the day if the user permits "recent day" rather than a specific date.

2. **Cluster sessions into knowledge topics**
   - Cluster by engineering problem, not by session title.
   - Merge design discussion, implementation, verification, deployment, and user corrections for the same topic.
   - Drop pure noise, greetings, duplicated context compactions, and raw tool-call chatter.

3. **Extract evidence cards before writing prose**
   For each candidate topic, capture:
   - repo/worktree/branch;
   - commits and commit messages;
   - files and modules;
   - runtime endpoints/topics/services;
   - commands and test results;
   - failures and root cause;
   - user corrections / changed assumptions;
   - unresolved risks.

4. **Write long-form documents**
   - One document per durable knowledge topic.
   - Do not paste chat transcripts.
   - Do not merely list facts; explain the system boundary or debugging rule.

5. **Write README index last**
   - The README should point to documents and explain the reading order.
   - It should not duplicate the long documents.

6. **Verify quality**
   Run a quick textual inspection. Reject outputs that contain:
   - `user:` / `assistant:` as transcript labels;
   - "关键证据摘录" as a section style;
   - vague words like "推进/显著提升" without adjacent concrete evidence;
   - only one report file for a high-signal day;
   - no commands, paths, or runtime states.

## Quality gate

A high-signal workday pack should satisfy:

- [ ] README plus at least three long-form docs, unless explicitly justified.
- [ ] Each long doc answers a real engineering question.
- [ ] Each long doc has concrete evidence: paths/commits/commands/status fields.
- [ ] Each long doc includes a corrected model, root-cause chain, or design boundary.
- [ ] Each long doc includes next-day recovery steps.
- [ ] No chat transcript dumps.
- [ ] No leadership-report tone.

## Common pitfalls

### Pitfall: treating an empty date-window reflect as proof the day had no signal

Wrong: stop after `hindsight_reflect` says it has no information for an exact date window, especially when the Hindsight bank is reachable and recent documents exist.

Right: record the empty reflect as a retrieval limitation, then run focused `hindsight_recall` queries for the target date, likely repositories, scripts, services, error terms, and paths. If first-class Hindsight tools are not exposed in the current Hermes tool schema but the local Hindsight API is reachable, use the API directly: `POST /v1/default/banks/<bank_id>/reflect` and `POST /v1/default/banks/<bank_id>/memories/recall`. Prefer unambiguous ISO timestamps and explicit local/UTC windows in the query; inspect recall result `occurred_start`, `document_id`, `chunk_id`, and metadata before selecting topics. If reflect is empty and recall is also empty, write a README failure report rather than inventing topics.

### Pitfall: treating the deliverable as a better daily report

Wrong: keep refining one Markdown daily report with denser bullets.

Right: generate a directory of knowledge documents and a README index.

### Pitfall: summarizing sessions one by one

Wrong: `Session A`, `Session B`, `Session C` sections.

Right: `Mapping stop initial localization`, `playAudio runtime chain`, `HMI volume applier`, etc.

### Pitfall: writing cards but not articles

Cards are useful intermediate evidence, but the user asked for long documents. Convert cards into explanatory long-form docs.

### Pitfall: equating tests/commits with knowledge

A commit hash or test result is evidence. The knowledge is the boundary it proves: e.g. API success semantics, runtime consumer chain, config overlay order.

## Reference example

See `references/2026-07-01-knowledge-pack-example.md` for a concrete example derived from a session where daily report quality was repeatedly corrected into a multi-document knowledge-pack format.
