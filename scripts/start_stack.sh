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
ENABLE_FUNNEL="${ENABLE_FUNNEL:-true}"
ENABLE_NGROK="${ENABLE_NGROK:-true}"
NGROK_BIN="${NGROK_BIN:-$HOME/bin/ngrok}"
NGROK_DOMAIN="${NGROK_DOMAIN:-}"  # 예약 도메인 있으면 지정, 없으면 매번 랜덤
NGROK_API="http://127.0.0.1:4040/api/tunnels"

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
kill_matches "ngrok http"
kill_port "$BACKEND_PORT"
kill_port "$FRONTEND_PORT"
kill_port "$OLLAMA_PORT"
kill_port 4040

sleep 0.5

echo "[start] starting Ollama..."
OLLAMA_MODELS="$OLLAMA_MODELS_DIR" nohup ollama serve >"$LOG_DIR/ollama.log" 2>&1 &
sleep 0.5

echo "[start] starting backend (uvicorn :$BACKEND_PORT) in conda env '$CONDA_ENV'..."
cd "$ROOT_DIR"
PYTHONUNBUFFERED=1 nohup conda run --no-capture-output -n "$CONDA_ENV" python -u -m uvicorn api_server:app --host 0.0.0.0 --port "$BACKEND_PORT" --reload --log-level info \
  >"$LOG_DIR/backend.log" 2>&1 &

echo "[start] starting frontend (next dev :$FRONTEND_PORT)..."
cd "$ROOT_DIR/apps/web"
SCAMGUARDIAN_API_URL="http://127.0.0.1:${BACKEND_PORT}" \
nohup npm run dev -- --hostname 0.0.0.0 --port "$FRONTEND_PORT" \
  >"$LOG_DIR/frontend.log" 2>&1 &

if [[ "$ENABLE_FUNNEL" == "true" ]] && command -v tailscale >/dev/null 2>&1; then
  echo "[start] enabling tailscale funnel (backend:$BACKEND_PORT, frontend:$FRONTEND_PORT)..."
  # funnel은 실패해도 스택 구동을 막지 않는다.
  nohup tailscale funnel --bg "$BACKEND_PORT" >/dev/null 2>&1 || true
  nohup tailscale funnel --bg "$FRONTEND_PORT" >/dev/null 2>&1 || true
  tailscale funnel status 2>/dev/null || true
fi

# 카카오 오픈빌더는 .ts.net 도메인을 거부하므로 ngrok 으로 보조 터널 제공
NGROK_PUBLIC_URL=""
if [[ "$ENABLE_NGROK" == "true" ]] && [[ -x "$NGROK_BIN" ]]; then
  echo "[start] starting ngrok tunnel (frontend:$FRONTEND_PORT)..."
  if [[ -n "$NGROK_DOMAIN" ]]; then
    nohup "$NGROK_BIN" http "$FRONTEND_PORT" --domain="$NGROK_DOMAIN" --log=stdout \
      >"$LOG_DIR/ngrok.log" 2>&1 &
  else
    nohup "$NGROK_BIN" http "$FRONTEND_PORT" --log=stdout \
      >"$LOG_DIR/ngrok.log" 2>&1 &
  fi
  # ngrok 로컬 API 가 뜰 때까지 최대 5초 대기
  for _ in 1 2 3 4 5 6 7 8 9 10; do
    if curl -sS -m 1 "$NGROK_API" >/dev/null 2>&1; then break; fi
    sleep 0.5
  done
  NGROK_PUBLIC_URL="$(curl -sS -m 2 "$NGROK_API" 2>/dev/null \
    | python -c 'import json,sys
try:
    d=json.load(sys.stdin)
    urls=[t["public_url"] for t in d.get("tunnels",[]) if t.get("public_url","").startswith("https")]
    print(urls[0] if urls else "")
except Exception:
    print("")' 2>/dev/null)"
  if [[ -n "$NGROK_PUBLIC_URL" ]]; then
    echo "[start] ngrok up: $NGROK_PUBLIC_URL"
    echo "[start] kakao webhook URL: ${NGROK_PUBLIC_URL}/webhook/kakao"
  else
    echo "[start] ngrok 시작은 했지만 public URL 조회 실패. $LOG_DIR/ngrok.log 확인."
  fi
elif [[ "$ENABLE_NGROK" == "true" ]]; then
  echo "[start] ENABLE_NGROK=true 지만 $NGROK_BIN 가 없음 — ngrok 스킵"
fi

echo "[start] done."
echo "[start] tail logs:"
echo "  tail -f \"$LOG_DIR/ollama.log\""
echo "  tail -f \"$LOG_DIR/backend.log\""
echo "  tail -f \"$LOG_DIR/frontend.log\""
echo "  tail -f \"$LOG_DIR/ngrok.log\""

