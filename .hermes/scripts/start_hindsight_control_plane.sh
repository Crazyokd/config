#!/usr/bin/env bash
set -euo pipefail

HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
HERMES_ENV="$HERMES_HOME/.env"
CONTROL_PLANE_ENV="$HERMES_HOME/hindsight/control-plane.env"
LOG_DIR="$HERMES_HOME/logs"
mkdir -p "$LOG_DIR" "$HERMES_HOME/hindsight"

if [[ -f "$HERMES_ENV" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$HERMES_ENV"
  set +a
fi
if [[ -f "$CONTROL_PLANE_ENV" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$CONTROL_PLANE_ENV"
  set +a
fi

: "${HINDSIGHT_CP_DATAPLANE_API_URL:=http://127.0.0.1:8888}"
: "${HINDSIGHT_CP_HOSTNAME:=127.0.0.1}"
: "${HINDSIGHT_CP_PORT:=9999}"
: "${HINDSIGHT_CP_INTERNAL_PORT:=10000}"
: "${HINDSIGHT_CP_DEFAULT_LOCALE:=zh-CN}"
: "${HINDSIGHT_CONTROL_PLANE_ROOT:=$HERMES_HOME/hindsight/control-plane/0.8.4}"

NODE_BIN="${NODE_BIN:-$HOME/.nvm/versions/node/v24.11.0/bin/node}"
if [[ ! -x "$NODE_BIN" ]]; then
  NODE_BIN="$(command -v node)"
fi
NODE_BIN_DIR="$(dirname "$NODE_BIN")"
export PATH="$NODE_BIN_DIR:$PATH"

CONTROL_PLANE_CLI="$HINDSIGHT_CONTROL_PLANE_ROOT/bin/cli.js"
if [[ ! -f "$CONTROL_PLANE_CLI" ]]; then
  echo "hindsight control plane CLI not found: $CONTROL_PLANE_CLI" >&2
  exit 1
fi
CONTROL_PLANE_PROXY="$HERMES_HOME/scripts/hindsight_control_plane_locale_proxy.js"
if [[ ! -f "$CONTROL_PLANE_PROXY" ]]; then
  echo "hindsight control plane locale proxy not found: $CONTROL_PLANE_PROXY" >&2
  exit 1
fi

export NODE_BIN
export HINDSIGHT_CONTROL_PLANE_CLI="$CONTROL_PLANE_CLI"
export HINDSIGHT_CP_DATAPLANE_API_URL
export HINDSIGHT_CP_HOSTNAME
export HINDSIGHT_CP_PORT
export HINDSIGHT_CP_INTERNAL_PORT
export HINDSIGHT_CP_DEFAULT_LOCALE

exec "$NODE_BIN" "$CONTROL_PLANE_PROXY"
