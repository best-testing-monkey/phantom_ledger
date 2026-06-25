#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8000}"
RELOAD="${RELOAD:-}"

args=(
    phantom.web.app:create_app
    --factory
    --host "$HOST"
    --port "$PORT"
)

if [[ -n "${RELOAD}" ]]; then
    args+=(--reload)
fi

echo "Starting Phantom Ledger web UI at http://${HOST}:${PORT}"
exec uv run uvicorn "${args[@]}"
