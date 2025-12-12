#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="${ROOT_DIR}/logs"
PID_DIR="${ROOT_DIR}/.pids"

BACKEND_HOST="${BACKEND_HOST:-0.0.0.0}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_HOST="${FRONTEND_HOST:-0.0.0.0}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"

# By default: start everything (backend + frontend + tv loop).
# You can disable any component via env:
#   START_TV=0 ./start.sh
#   START_FRONTEND=0 ./start.sh
#   START_BACKEND=0 ./start.sh
START_BACKEND="${START_BACKEND:-1}"
START_FRONTEND="${START_FRONTEND:-1}"
START_TV="${START_TV:-1}"

mkdir -p "$LOG_DIR" "$PID_DIR"

cleanup() {
  set +e
  echo ""
  echo "Stopping..."

  for name in tv frontend backend; do
    pid_file="${PID_DIR}/${name}.pid"
    if [[ -f "$pid_file" ]]; then
      pid="$(cat "$pid_file" 2>/dev/null || true)"
      if [[ -n "${pid:-}" ]] && kill -0 "$pid" 2>/dev/null; then
        kill "$pid" 2>/dev/null || true
      fi
      rm -f "$pid_file" 2>/dev/null || true
    fi
  done

  exit 0
}

trap cleanup INT TERM

cd "$ROOT_DIR"

echo "Repo: $ROOT_DIR"
echo "Logs: $LOG_DIR"

if [[ "$START_BACKEND" == "1" ]]; then
  echo ""
  echo "Starting backend (FastAPI) on http://${BACKEND_HOST}:${BACKEND_PORT} ..."

  if [[ -x "${ROOT_DIR}/venv/bin/python" ]]; then
    PYTHON="${ROOT_DIR}/venv/bin/python"
  else
    PYTHON="python3"
  fi

  # Uvicorn is installed via requirements-web.txt (or globally). This keeps it simple.
  "$PYTHON" -m uvicorn server:app --host "$BACKEND_HOST" --port "$BACKEND_PORT" > "${LOG_DIR}/backend.log" 2>&1 &
  echo $! > "${PID_DIR}/backend.pid"
  echo "Backend PID: $(cat "${PID_DIR}/backend.pid") (log: ${LOG_DIR}/backend.log)"
fi

if [[ "$START_FRONTEND" == "1" ]]; then
  echo ""
  echo "Starting frontend (Svelte) on http://${FRONTEND_HOST}:${FRONTEND_PORT} ..."

  if [[ ! -d "${ROOT_DIR}/frontend/node_modules" ]]; then
    echo "NOTE: frontend dependencies not installed yet."
    echo "Run: (cd frontend && npm install)"
  fi

  (cd "${ROOT_DIR}/frontend" && npm run dev -- --host "$FRONTEND_HOST" --port "$FRONTEND_PORT") > "${LOG_DIR}/frontend.log" 2>&1 &
  echo $! > "${PID_DIR}/frontend.pid"
  echo "Frontend PID: $(cat "${PID_DIR}/frontend.pid") (log: ${LOG_DIR}/frontend.log)"
fi

if [[ "$START_TV" == "1" ]]; then
  echo ""
  echo "Starting TV loop (main.py) ..."

  if [[ -x "${ROOT_DIR}/venv/bin/python" ]]; then
    PYTHON="${ROOT_DIR}/venv/bin/python"
  else
    PYTHON="python3"
  fi

  "$PYTHON" "${ROOT_DIR}/main.py" > "${LOG_DIR}/tv.log" 2>&1 &
  echo $! > "${PID_DIR}/tv.pid"
  echo "TV PID: $(cat "${PID_DIR}/tv.pid") (log: ${LOG_DIR}/tv.log)"
fi

echo ""
echo "All started. Press Ctrl+C to stop."
echo ""

# Keep this script running so Ctrl+C triggers cleanup
while true; do
  sleep 1
done


