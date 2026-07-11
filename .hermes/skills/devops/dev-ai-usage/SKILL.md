---
name: dev-ai-usage
version: 1.0.0
author: Hermes Agent
license: MIT
description: "Check dev.ai.sr API/token quota and usage for the current Hermes OpenAI-compatible key."
metadata:
  hermes:
    tags: [dev-ai, usage, quota, billing, provider, openai-compatible]
---

# dev.ai.sr Usage / Quota Check

## When to use

Use this skill when the user asks any of:

- “查一下 dev.ai.sr 额度 / 用量 / token 使用量”
- “现在 ai token 还剩多少”
- “今天/本周/本月 dev.ai.sr 用了多少”
- “哪个模型最烧钱 / gpt-5.5 用量占比”
- “当前 Hermes provider 是不是 dev.ai.sr / codex-openai”

## Fast path

Run the local helper script:

```bash
python3 /home/standard/.hermes/scripts/dev_ai_usage.py --daily 10
```

Useful variants:

```bash
# Shorter recent daily history
python3 /home/standard/.hermes/scripts/dev_ai_usage.py --daily 3

# Raw JSON, still no secrets in request output
python3 /home/standard/.hermes/scripts/dev_ai_usage.py --json

# If the endpoint/key env changes
DEV_AI_BASE_URL=http://dev.ai.sr DEV_AI_KEY_ENV=OPENAI_API_KEY \
  python3 /home/standard/.hermes/scripts/dev_ai_usage.py
```

## What the helper does

- Reads `OPENAI_API_KEY` from environment or `/home/standard/.hermes/.env`.
- Calls:

```text
http://dev.ai.sr/v1/usage
Authorization: Bearer <OPENAI_API_KEY>
```

- Prints:
  - plan / validity / unit;
  - daily, weekly, monthly usage and remaining quota;
  - today’s requests/tokens/cost;
  - realtime rpm/tpm/average duration;
  - account total;
  - cost breakdown by model;
  - recent daily rows.

## Current provider check

If the user also asks “现在 provider 是？”, verify live config rather than relying on memory:

```bash
python3 - <<'PY'
from pathlib import Path
import yaml, json
p=Path.home()/'.hermes/config.yaml'
cfg=yaml.safe_load(p.read_text())
model=cfg.get('model', {})
provider=model.get('provider')
providers=cfg.get('providers', {})
print(json.dumps({
  'model.default': model.get('default'),
  'model.provider': provider,
  'model.base_url': model.get('base_url'),
  'model.api_mode': model.get('api_mode'),
  'model.openai_runtime': model.get('openai_runtime'),
  'provider_config': providers.get(provider, {}),
}, ensure_ascii=False, indent=2))
PY
```

As of this skill’s creation, the default profile was:

```text
provider: codex-openai
model: gpt-5.5
base_url: http://dev.ai.sr/v1
api_mode: codex_responses
openai_runtime: codex_app_server
key_env: OPENAI_API_KEY
```

Always re-check if the user asks for the current provider.

## Safety / privacy

- Never print API keys.
- Do not paste raw `.env` contents.
- If showing raw JSON, it should come from `/v1/usage`; the response does not include the API key.
- Browser login to dev.ai.sr may require user credentials or Feishu auth; prefer the API endpoint with the already configured key.

## Verification

A successful run should show output similar to:

```text
# dev.ai.sr usage @ YYYY-MM-DD HH:MM:SS +0800
plan: 06-GPT
mode: unrestricted
valid: True

## quota
- daily: used $... / limit $300.0000 (...%), remaining $...
- weekly: used $... / limit $1,500.0000 (...%), remaining $...
- monthly: used $... / limit $6,000.0000 (...%), remaining $...
```

If it fails with `API_KEY_REQUIRED`, the key was not sent; inspect `--key-env` and `/home/standard/.hermes/.env` without printing the secret.

If `/v1/usage` returns 404/401 unexpectedly, first test `/v1/models` with the same Authorization header to distinguish endpoint availability from quota endpoint changes.
