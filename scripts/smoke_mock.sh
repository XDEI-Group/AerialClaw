#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

python_ok() {
  "$@" -c 'import sys, pytest; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' >/dev/null 2>&1
}

PYTHON_CMD=()
if [ -n "${PYTHON:-}" ]; then
  PYTHON_CMD=("$PYTHON")
  if ! python_ok "${PYTHON_CMD[@]}"; then
    echo "error: PYTHON must point to Python >=3.10 with pytest installed" >&2
    exit 1
  fi
else
  for candidate in python python3 python3.12 python3.11 python3.10; do
    if command -v "$candidate" >/dev/null 2>&1 && python_ok "$candidate"; then
      PYTHON_CMD=("$candidate")
      break
    fi
  done

  if [ "${#PYTHON_CMD[@]}" -eq 0 ] && command -v pyenv >/dev/null 2>&1; then
    while IFS= read -r version; do
      if [[ "$version" =~ ^3\.(1[0-9]|[2-9][0-9]) ]] && python_ok env PYENV_VERSION="$version" pyenv exec python; then
        PYTHON_CMD=(env PYENV_VERSION="$version" pyenv exec python)
        break
      fi
    done < <(pyenv versions --bare 2>/dev/null)
  fi
fi

if [ "${#PYTHON_CMD[@]}" -eq 0 ]; then
  echo "error: Python >=3.10 with pytest installed is required" >&2
  exit 1
fi

echo "Using Python: $("${PYTHON_CMD[@]}" --version)"
"${PYTHON_CMD[@]}" scripts/check_artifact.py
"${PYTHON_CMD[@]}" -m compileall -q adapters brain config llm memory runtime scripts sim skills swarm server.py
"${PYTHON_CMD[@]}" -m pytest
(
  cd ui
  npm run lint
  npm run build
)

echo "mock artifact smoke checks passed"
