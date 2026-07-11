# 2026-07-01 Knowledge Pack Example

This reference captures the session learning that changed the correct output shape for developer daily reports.

## User correction

The user repeatedly rejected single-report summaries as low quality. The final clarification was:

> For a day with many long sessions, new material should become knowledge documents. A day should produce at least three long-form articles, not just a daily report.

Therefore, for this user's developer-report workflow, the target is a **Daily Knowledge Pack**:

```text
YYYY-MM-DD-knowledge-pack/
  README.md
  01-mapping-stop-initial-localization.md
  02-playaudio-runtime-chain.md
  03-hmi-volume-parameter-vs-runtime-applier.md
  04-sim-deploy-readiness-cfg-overlay.md
```

The README is only a navigation layer. The value is in the long documents.

## Why earlier attempts failed

Earlier outputs failed because they were:

- generic methodology documents with no real information;
- single daily summaries;
- dense cards but not long-form knowledge documents;
- still optimized around the word "日报" rather than the user's real desired artifact: reusable engineering knowledge.

## Example topics from 2026-07-01

The session produced a sample pack under:

```text
/home/standard/hermes-home/reports/work-daily/drafts/2026-07-01-knowledge-pack/
```

The generated documents were:

1. `01-mapping-stop-initial-localization.md`
   - Key idea: `/mapping/stop` may best-effort publish VDA5050 `initPosition`, but must not wait for or promise `localized=true`.
   - Reusable rule: do not collapse workflow side effects into the parent API's success condition.

2. `02-playaudio-runtime-chain.md`
   - Key idea: REST success and VDA5050 action `FINISHED` do not prove audio played; `/play_audio/command` needs a subscriber and the playback node must resolve `/sros/music/...wav` correctly.
   - Reusable rule: for physical effects, trace REST -> protocol -> ROS topic -> consumer node -> resource path -> hardware/backend.

3. `03-hmi-volume-parameter-vs-runtime-applier.md`
   - Key idea: `hmi.volume` persistence is not runtime effect. Without a ROS audio node, `easygo-app` needed a `VolumeApplier` using `amixer -c 0 sset "DAC VOLUME" <n>%`.
   - Reusable rule: distinguish truth storage from side-effect execution.

4. `04-sim-deploy-readiness-cfg-overlay.md`
   - Key idea: 6.14.0 simulation deploy was stuck because generic `cfg/bringup/managed_nodes.yaml` made a mock environment wait for missing Nav2 lifecycle services. `cfg-sim` overlay and orchestrator semantics must agree.
   - Reusable rule: readiness failures often mean the waiting condition is wrong for the environment, not that the process crashed.

## Practical generation guidance

When generating future packs:

1. Start with session clustering, not prose.
2. Select 3-6 high-value knowledge topics.
3. Build evidence cards for each topic.
4. Write one standalone article per topic.
5. Write README last.
6. If only summaries/cards are produced, the job is incomplete.

## Minimum document content

Each article should contain:

- problem background;
- wrong assumption / ambiguity;
- corrected model;
- concrete evidence paths/commits/commands/status fields;
- verification results;
- next-day recovery steps;
- reusable rule.

Avoid:

- chat transcript excerpts;
- session-by-session sections;
- "today advanced/progressed/improved" wording;
- commit-only evidence without explaining the system boundary.
