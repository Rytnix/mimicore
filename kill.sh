#!/usr/bin/env bash
# Kill any VoiceClone Studio processes (uvicorn FastAPI on :8000, vite dev on :5173).
#
# Usage:
#   ./kill.sh           # graceful stop, then SIGKILL after 2s if still alive
#   ./kill.sh --force   # SIGKILL immediately

set -u

FORCE=0
[[ "${1:-}" == "--force" || "${1:-}" == "-9" ]] && FORCE=1

# Collect target pids: any process whose command line shows it serves *this* app.
# Done as one pass so the same process isn't signalled twice.
collect_pids() {
  pgrep -af 'uvicorn server:app|vite' 2>/dev/null \
    | awk -v self=$$ '
        $1 == self { next }                         # this script itself
        /kill\.sh/ { next }                         # any kill.sh helper shell
        / pgrep / { next }                          # the pgrep we just spawned
        { print $1 }
      ' \
    | sort -un
}

PIDS=$(collect_pids)

if [[ -z "$PIDS" ]]; then
  echo "[kill] nothing running."
else
  sig="TERM"; [[ $FORCE -eq 1 ]] && sig="KILL"
  for pid in $PIDS; do
    cmd=$(ps -o args= -p "$pid" 2>/dev/null | head -c 120)
    [[ -z "$cmd" ]] && continue
    echo "[kill] SIG$sig $pid  ($cmd)"
    kill -$sig "$pid" 2>/dev/null || true
  done

  # Escalate to SIGKILL if anything survives the graceful stop.
  if [[ $FORCE -eq 0 ]]; then
    sleep 2
    LEFT=$(collect_pids)
    for pid in $LEFT; do
      cmd=$(ps -o args= -p "$pid" 2>/dev/null | head -c 120)
      [[ -z "$cmd" ]] && continue
      echo "[kill] still alive — SIGKILL $pid  ($cmd)"
      kill -KILL "$pid" 2>/dev/null || true
    done
  fi
fi

# Bonus: if anything is still bound to our ports, surface it.
for port in 8000 5173; do
  if command -v ss >/dev/null 2>&1; then
    holders=$(ss -ltnp "sport = :$port" 2>/dev/null | tail -n +2)
  else
    holders=$(lsof -iTCP:$port -sTCP:LISTEN 2>/dev/null | tail -n +2)
  fi
  if [[ -n "$holders" ]]; then
    echo "[kill] WARNING: port $port still in use:"
    echo "$holders"
  fi
done
