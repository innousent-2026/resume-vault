#!/usr/bin/env bash
# Load the extension into a real Chromium and drive it against a fixture
# application form. Requires: node with playwright, and the backend venv.
#
#   ./extension/e2e/run.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
if [[ ! -d "$ROOT/extension/e2e/node_modules/playwright" ]]; then
  echo "playwright is missing — run: (cd extension/e2e && npm install)" >&2
  exit 1
fi
TMP="$(mktemp -d)"
PORT_API=5099
PORT_SITE=8899
PYTHON="${JAA_PYTHON:-$ROOT/.venv/bin/python}"

cleanup() {
  [[ -n "${API_PID:-}" ]] && kill "$API_PID" 2>/dev/null || true
  [[ -n "${SITE_PID:-}" ]] && kill "$SITE_PID" 2>/dev/null || true
  rm -rf "$TMP"
}
trap cleanup EXIT

# The shipped manifest only matches real ATS domains, so the test copy also
# matches the local fixture host. Nothing else about the extension changes.
mkdir -p "$TMP/extension"
cp -r "$ROOT/extension/"* "$TMP/extension/"
rm -rf "$TMP/extension/e2e"
"$PYTHON" - "$TMP/extension/manifest.json" "$PORT_SITE" "$PORT_API" <<'PATCH'
import json, sys
path, site_port, api_port = sys.argv[1], sys.argv[2], sys.argv[3]
manifest = json.load(open(path))
manifest["content_scripts"][0]["matches"].append(f"http://localhost:{site_port}/*")
manifest["host_permissions"] += [f"http://localhost:{site_port}/*", f"http://127.0.0.1:{api_port}/*"]
json.dump(manifest, open(path, "w"), indent=2)
PATCH

# ...and point the test copy at this run's API port rather than the default.
sed -i "s|http://127.0.0.1:5057|http://127.0.0.1:$PORT_API|g" "$TMP/extension/background.js"

cp "$ROOT/resume_data.example.json" "$TMP/resume.json"

# Seed the job the fixture page advertises, so cover-letter placeholders resolve.
JAA_DB_PATH="$TMP/e2e.db" "$PYTHON" - "$PORT_SITE" <<PY
import sys
sys.path.insert(0, "$ROOT/backend")
import database as db
db.init_db()
db.upsert_job({
    "source_kind": "greenhouse", "external_id": "gh:e2e-1", "company": "Acme Corp",
    "title": "Director of People Operations", "location": "Portland, OR", "remote": False,
    "url": f"http://localhost:{sys.argv[1]}/fixture.html",
    "description": "Own people operations, talent acquisition and Workday HRIS.",
    "salary_min": 160000, "salary_max": 190000,
})
PY

JAA_DB_PATH="$TMP/e2e.db" JAA_RESUME_PATH="$TMP/resume.json" PORT=$PORT_API \
  "$PYTHON" "$ROOT/backend/app.py" > "$TMP/api.log" 2>&1 &
API_PID=$!
(cd "$ROOT/extension/e2e" && exec python3 -m http.server $PORT_SITE > "$TMP/site.log" 2>&1) &
SITE_PID=$!

for _ in $(seq 1 15); do
  curl -sf "http://127.0.0.1:$PORT_API/api/health" >/dev/null && break
  sleep 1
done

JAA_E2E_TMP="$TMP" JAA_E2E_SITE="http://localhost:$PORT_SITE" JAA_E2E_API="http://127.0.0.1:$PORT_API" \
  node "$ROOT/extension/e2e/run.mjs"
