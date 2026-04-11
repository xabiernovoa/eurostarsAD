#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ -x "${ROOT_DIR}/.venv/bin/python" ]]; then
  PYTHON_BIN="${ROOT_DIR}/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python3)"
else
  echo "No Python interpreter found. Create .venv or install python3." >&2
  exit 1
fi

declare -a PIDS=()

cleanup() {
  local exit_code=$?
  trap - EXIT INT TERM

  if [[ ${#PIDS[@]} -gt 0 ]]; then
    echo
    echo "Stopping services..."
    kill "${PIDS[@]}" 2>/dev/null || true
    wait "${PIDS[@]}" 2>/dev/null || true
  fi

  exit "${exit_code}"
}

trap cleanup EXIT INT TERM

start_service() {
  local name=$1
  local script_path=$2

  (
    cd "${ROOT_DIR}"
    exec "${PYTHON_BIN}" "${script_path}"
  ) &

  local pid=$!
  PIDS+=("${pid}")
  echo "Started ${name} (pid ${pid})"
}

start_service "Gmail demo" "frontend/mail/server.py"
start_service "Reception demo" "frontend/receptionist/server.py"
start_service "Marketing dashboard" "frontend/marketing/server.py"

echo
echo "Services running:"
echo "  Mail:         http://localhost:3001"
echo "  Reception:    http://localhost:3002"
echo "  Marketing:    http://localhost:3003"
echo
echo "Press Ctrl+C to stop all services."

wait
