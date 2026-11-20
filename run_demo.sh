#!/usr/bin/env bash
# One-command setup and start for macOS / Linux.
#   ./run_demo.sh          set up (first time) and start the server
#   ./run_demo.sh reset    delete the demo database, re-seed it, then start
#   ./run_demo.sh setup    set up only
#   ./run_demo.sh ml       also install the optional ML layer
set -e
cd "$(dirname "$0")"
command -v python3 >/dev/null || { echo "Python 3.12+ is required"; exit 1; }
[ -x .venv/bin/python ] || python3 -m venv .venv
VPY=.venv/bin/python
if [ ! -f .venv/deps_ok.txt ]; then
  $VPY -m pip install --upgrade pip >/dev/null
  $VPY -m pip install -r requirements.txt
  echo ok > .venv/deps_ok.txt
fi
[ "$1" = "ml" ] && { $VPY -m pip install fastembed numpy && $VPY -m eval.fetch_model; }
[ "$1" = "reset" ] && rm -f inheritance_platform.db
if [ ! -f inheritance_platform.db ]; then
  echo "Seeding synthetic demo data..."
  $VPY -m data.generate_seed && $VPY -m data.seed_outcomes && $VPY -m data.seed_cases
fi
[ "$1" = "setup" ] && { echo "Setup complete. Start with ./run_demo.sh"; exit 0; }
echo "Patient app: http://127.0.0.1:8000/app   Portal: /portal   Dashboard: /dashboard"
exec $VPY -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
