#!/usr/bin/env bash
# Start the EQL demo on Tracy's shape-sorting episode with one command:
#
#     ~/Projects/cramera/scripts/eql_demo.sh
#
# It starts the viewer, rebuilds the world the run was recorded in so the first question
# answers at once, and opens the browser on the Tracy episode. Ctrl+C stops it.
#
# Settings, each with a default: CRAMERA_EQL_VENV (the environment install_stack.py
# made), CRAMERA_EQL_PORT (8722), CRAMERA_EQL_SCENE (tracy_shape_sorting).
set -euo pipefail

REPOSITORY="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="${CRAMERA_EQL_VENV:-$HOME/.virtualenvs/cramera-eql}"
PORT="${CRAMERA_EQL_PORT:-8722}"
SCENE="${CRAMERA_EQL_SCENE:-tracy_shape_sorting}"
URL="http://127.0.0.1:${PORT}/?scene=${SCENE}"
API="http://127.0.0.1:${PORT}/api/plugins/questions"

if [[ ! -x "${VENV}/bin/cramera" ]]; then
  echo "No cramera in ${VENV}. Install it first, as docs/eql-demo.md says:" >&2
  echo "  python3 scripts/install_stack.py --cram ~/Projects/cram-eql-demo --venv ${VENV} --dev" >&2
  exit 1
fi
# shellcheck disable=SC1091
source "${VENV}/bin/activate"
cd "${REPOSITORY}"

cramera --demo-scenes demo --port "${PORT}" --no-browser &
VIEWER=$!
trap 'kill "${VIEWER}" 2>/dev/null; wait "${VIEWER}" 2>/dev/null' EXIT INT TERM

echo "Starting the viewer…"
until curl -s -o /dev/null "http://127.0.0.1:${PORT}/api/scenes"; do
  kill -0 "${VIEWER}" 2>/dev/null || { echo "The viewer stopped while starting." >&2; exit 1; }
  sleep 1
done

echo "Rebuilding the world Tracy's run was recorded in…"
curl -s -o /dev/null "${API}/presets?scene=${SCENE}"
curl -s -o /dev/null -X POST "${API}/query" -H 'content-type: application/json' \
  -d "{\"scene\":\"${SCENE}\",\"code\":\"an(Arm)\",\"scope\":\"current_state\",\"frame\":0}"

xdg-open "${URL}" >/dev/null 2>&1 || true
cat <<EOF

Ready: ${URL}
  Write queries, asked of the recorded world at the frame the timeline shows:
  hints as you type, Tab takes one, Ctrl+Space lists every name, Ctrl+Enter runs.
  Ctrl+C here stops the viewer.
EOF
wait "${VIEWER}"
