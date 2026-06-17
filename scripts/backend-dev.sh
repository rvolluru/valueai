#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PID_FILE="${PID_FILE:-/tmp/valueai-backend-dev.pid}"
LOG_FILE="${LOG_FILE:-/tmp/valueai-backend-dev.log}"
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8000}"
SCREEN_SESSION="${SCREEN_SESSION:-valueai-backend-dev}"

is_running() {
  if [[ -f "${PID_FILE}" ]]; then
    local pid
    pid="$(cat "${PID_FILE}" 2>/dev/null || true)"
    if [[ -n "${pid}" ]] && kill -0 "${pid}" 2>/dev/null; then
      return 0
    fi
  fi
  return 1
}

start() {
  if is_running; then
    echo "Backend dev server already running (pid $(cat "${PID_FILE}"))."
    return 0
  fi

  cd "${ROOT_DIR}"

  screen -S "${SCREEN_SESSION}" -X quit >/dev/null 2>&1 || true
  screen -dmS "${SCREEN_SESSION}" bash -lc "
    cd '${ROOT_DIR}' && \
    env PYTHONPATH='apps/api:packages/brand/src:packages/condition/src:packages/valuation/src:src' \
      .venv/bin/python -m uvicorn app.main:app \
      --app-dir apps/api \
      --host '${HOST}' \
      --port '${PORT}' \
      --reload \
      --reload-dir apps/api/app \
      --reload-dir packages/brand/src/brand \
      --reload-dir packages/condition/src/condition \
      --reload-dir packages/valuation/src/valuation \
      >> '${LOG_FILE}' 2>&1
  "

  for _ in {1..20}; do
    if curl -fsS "http://${HOST}:${PORT}/v1/health" >/dev/null 2>&1 && pgrep -f "uvicorn app.main:app" >/dev/null 2>&1; then
      local pid
      pid="$(lsof -ti "tcp:${PORT}" 2>/dev/null | head -n 1 || true)"
      if [[ -n "${pid}" ]]; then
        echo "${pid}" > "${PID_FILE}"
      fi
      echo "Backend dev server started on http://${HOST}:${PORT} (pid ${pid})."
      echo "Hot reload enabled."
      return 0
    fi
    sleep 0.5
  done

  echo "Backend failed to start. See log: ${LOG_FILE}" >&2
  exit 1
}

stop() {
  local stopped=0
  if is_running; then
    local pid
    pid="$(cat "${PID_FILE}")"
    kill "${pid}" 2>/dev/null || true
    rm -f "${PID_FILE}"
    stopped=1
  fi

  local pids
  pids="$(lsof -ti "tcp:${PORT}" 2>/dev/null || true)"
  if [[ -n "${pids}" ]]; then
    echo "${pids}" | tr '\n' ' ' | xargs kill 2>/dev/null || true
    stopped=1
  fi
  screen -S "${SCREEN_SESSION}" -X quit >/dev/null 2>&1 || true

  if [[ "${stopped}" -eq 1 ]]; then
    echo "Backend dev server stopped."
  else
    echo "Backend dev server is not running."
  fi
}

status() {
  if is_running || lsof -ti "tcp:${PORT}" >/dev/null 2>&1 || screen -ls | grep -q "${SCREEN_SESSION}"; then
    local pid
    pid="$(cat "${PID_FILE}" 2>/dev/null || lsof -ti "tcp:${PORT}" 2>/dev/null | head -n 1 || true)"
    echo "Backend dev server running (pid ${pid:-unknown})."
  else
    echo "Backend dev server is not running."
  fi
}

logs() {
  tail -n 120 -f "${LOG_FILE}"
}

case "${1:-}" in
  start) start ;;
  stop) stop ;;
  restart) stop; start ;;
  status) status ;;
  logs) logs ;;
  *)
    echo "Usage: $0 {start|stop|restart|status|logs}" >&2
    exit 1
    ;;
esac
