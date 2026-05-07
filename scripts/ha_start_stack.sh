#!/usr/bin/env bash
set -u

PROJECT="/home/mpwsl2/a-eye/idea_2/scamguardian-v2"
LOGDIR="$PROJECT/.scamguardian/logs"
LOGFILE="$LOGDIR/start_from_ha.log"

mkdir -p "$LOGDIR"

{
  echo ""
  echo "=============================="
  echo "[HA START] $(date -Is)"
  echo "[HA START] cwd=$PROJECT"
  cd "$PROJECT"
  chmod +x scripts/start_stack.sh
  bash scripts/start_stack.sh
  echo "[HA END] $(date -Is)"
} >> "$LOGFILE" 2>&1