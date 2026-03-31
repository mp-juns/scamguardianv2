#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="$ROOT_DIR/.scamguardian/logs"
OLLAMA_MODELS_DIR="$ROOT_DIR/.scamguardian/ollama_models"
mkdir -p "$LOG_DIR" "$OLLAMA_MODELS_DIR"

BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-3100}"
OLLAMA_PORT="${OLLAMA_PORT:-11434}"

CONDA_ENV="${CONDA_ENV:-capstone}"

echo "[start] root=$ROOT_DIR"
echo "[start] logs=$LOG_DIR"

kill_port() {
  local port="$1"
  if command -v fuser >/dev/null 2>&1; then
    fuser -k "${port}/tcp" >/dev/null 2>&1 || true
  fi
}

kill_matches() {
  local pattern="$1"
  pkill -f "$pattern" >/dev/null 2>&1 || true
}

echo "[start] stopping previous processes..."
kill_matches "uvicorn api_server:app"
kill_matches "next-server"
kill_matches "ollama serve"
kill_port "$BACKEND_PORT"
kill_port "$FRONTEND_PORT"
kill_port "$OLLAMA_PORT"

sleep 0.5

echo "[start] starting Ollama..."
OLLAMA_MODELS="$OLLAMA_MODELS_DIR" nohup ollama serve >"$LOG_DIR/ollama.log" 2>&1 &
sleep 0.5

echo "[start] starting backend (uvicorn :$BACKEND_PORT) in conda env '$CONDA_ENV'..."
cd "$ROOT_DIR"
nohup conda run -n "$CONDA_ENV" python -m uvicorn api_server:app --host 0.0.0.0 --port "$BACKEND_PORT" --reload \
  >"$LOG_DIR/backend.log" 2>&1 &

echo "[start] starting frontend (next dev :$FRONTEND_PORT)..."
cd "$ROOT_DIR/apps/web"
SCAMGUARDIAN_API_URL="http://127.0.0.1:${BACKEND_PORT}" \
nohup npm run dev -- --hostname 0.0.0.0 --port "$FRONTEND_PORT" \
  >"$LOG_DIR/frontend.log" 2>&1 &

echo "[start] done."
echo "[start] tail logs:"
echo "  tail -f \"$LOG_DIR/ollama.log\""
echo "  tail -f \"$LOG_DIR/backend.log\""
echo "  tail -f \"$LOG_DIR/frontend.log\""

