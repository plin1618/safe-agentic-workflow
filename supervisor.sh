#!/usr/bin/env bash
#
# supervisor.sh — Component 4 outer loop driver.
#
# Repeatedly invokes short, capped headless Claude Code sessions rather than
# one long-running session (long bypass-permissions sessions have a known
# bug where they silently downgrade permission mode after 2-6 hours).
# Checkpoints entirely through the state files in .claude/state/, so each
# invocation picks up where the last left off regardless of why it stopped.
#
# Stops automatically when either:
#   - audit-tally.json reports production_ready: true, or
#   - every cluster is parked awaiting the attention queue (nothing left to
#     do without you), or
#   - state has stopped changing for STALL_LIMIT consecutive invocations --
#     covers the case nothing_unblocked_left() can't see: everything got
#     blocked BEFORE any clustering happened, so cluster-status.json never
#     existed and that check never fires (see stall detection below), or
#   - the cumulative circuit breaker in run-ledger.json trips (Component 4.3)
#
# Automatically waits out Claude's usage-limit window and resumes without
# you needing to notice or intervene.
#
# CAVEATS, read before relying on this unattended:
# - A blocking `sleep` (used below to wait out a rate limit) pauses along
#   with the rest of the process if your machine actually sleeps -- this is
#   NOT the same guarantee as cloud execution that keeps running with your
#   laptop closed. Run this via nohup/tmux so it survives your terminal
#   closing, and keep the machine awake for genuinely unattended multi-hour
#   runs.
# - `--max-turns`/`--max-budget-usd` are assumed-current `claude -p` flags,
#   not verified against a live run. The reset-time regex in
#   parse_reset_time() is the single biggest untested risk in this whole
#   script -- force a rate limit deliberately (or unit-test against
#   captured real output) before trusting any unattended run.
# - This build's real circuit breaker is turns/iterations/failure-count
#   based, not dollar-based -- see .claude/loop-constraints.md's "Budget
#   discipline" section. MAX_BUDGET_USD is only passed to `claude -p` if
#   you explicitly set SUPERVISOR_MAX_BUDGET_USD; it is not defaulted,
#   since under subscription auth there is no real per-call dollar cost.

set -uo pipefail

STATE_DIR=".claude/state"
AUDIT_TALLY="$STATE_DIR/audit-tally.json"
CLUSTER_STATUS="$STATE_DIR/cluster-status.json"
ATTENTION_QUEUE="$STATE_DIR/attention-queue.json"
RUN_LEDGER="$STATE_DIR/run-ledger.json"
LOG_FILE="$STATE_DIR/supervisor.log"

MAX_TURNS="${SUPERVISOR_MAX_TURNS:-50}"
MAX_BUDGET_USD="${SUPERVISOR_MAX_BUDGET_USD:-}"          # unset by default -- see caveats above
MAX_ITERATIONS="${SUPERVISOR_MAX_ITERATIONS:-100}"       # cumulative breaker condition (c)
MAX_CONSECUTIVE_FAILURES="${SUPERVISOR_MAX_CONSECUTIVE_FAILURES:-5}"
MAX_SAME_ERROR_STREAK="${SUPERVISOR_MAX_SAME_ERROR_STREAK:-5}"
STALL_LIMIT="${SUPERVISOR_STALL_LIMIT:-2}"               # consecutive no-change invocations before stopping

# Only matters for a genuinely fresh kickoff (no audit-tally.json yet).
# Once state exists, the loop is fully state-driven and this is ignored.
#   2 = build from the current blueprint/DDD first, then audit and continue
#   3 = skip building -- audit whatever's already in the repo and continue
# No default on purpose: guessing wrong here either wastes a build cycle
# or skips a necessary one. Fails loudly instead of assuming.
START_STEP="${SUPERVISOR_START_STEP:-}"

log() {
  echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) $1" | tee -a "$LOG_FILE"
}

# --- auth-mode pre-flight check (informational, not enforced) --------------
check_auth_mode() {
  if [[ -n "${ANTHROPIC_API_KEY:-}" ]]; then
    log "Auth mode: ANTHROPIC_API_KEY is set -- this run bills per-token. Consider setting RUN_LEDGER_MAX_COST_USD for real (see loop-budget.md)."
  else
    log "Auth mode: no ANTHROPIC_API_KEY detected -- assuming subscription login. Usage counts against rate-limit windows, not per-token billing. Dollar figures in the dashboard are informational estimates only."
  fi
}

# --- run-ledger.json: cumulative circuit breaker (Component 4.3) ----------
init_run_ledger() {
  [[ -f "$RUN_LEDGER" ]] || python -c "
import json
from pathlib import Path
Path('$RUN_LEDGER').write_text(json.dumps({
    'consecutive_failures': 0,
    'same_error_streak': {'error_signature': None, 'count': 0},
    'total_iterations_this_run': 0,
    'cumulative_cost_usd': 0.0,
    'tripped': False,
    'tripped_reason': None,
}, indent=2) + '\n')
"
}

run_ledger_tripped() {
  python -c "
import json
print(json.load(open('$RUN_LEDGER')).get('tripped', False))
" 2>/dev/null | grep -qi true
}

# Records one invocation's outcome and checks trip conditions. Prints
# 'TRIPPED' to stdout if this call caused a trip (caller should stop).
record_invocation() {
  local success="$1" error_signature="${2:-}"
  python - "$success" "$error_signature" "$MAX_ITERATIONS" "$MAX_CONSECUTIVE_FAILURES" "$MAX_SAME_ERROR_STREAK" <<'PYEOF'
import json
import sys
from pathlib import Path

success, error_sig, max_iter, max_fail, max_streak = sys.argv[1:6]
max_iter, max_fail, max_streak = int(max_iter), int(max_fail), int(max_streak)

p = Path(".claude/state/run-ledger.json")
state = json.loads(p.read_text())

state["total_iterations_this_run"] += 1

if success == "true":
    state["consecutive_failures"] = 0
    state["same_error_streak"] = {"error_signature": None, "count": 0}
else:
    state["consecutive_failures"] += 1
    streak = state["same_error_streak"]
    if streak["error_signature"] == error_sig and error_sig:
        streak["count"] += 1
    else:
        streak["error_signature"] = error_sig
        streak["count"] = 1

reason = None
if state["consecutive_failures"] >= max_fail:
    reason = f"{state['consecutive_failures']} consecutive failed invocations (cap {max_fail})"
elif state["same_error_streak"]["count"] >= max_streak:
    reason = f"same error signature repeated {state['same_error_streak']['count']} times in a row (cap {max_streak}): {state['same_error_streak']['error_signature']}"
elif state["total_iterations_this_run"] >= max_iter:
    reason = f"{state['total_iterations_this_run']} total iterations this run (cap {max_iter})"

if reason:
    state["tripped"] = True
    state["tripped_reason"] = reason

p.write_text(json.dumps(state, indent=2) + "\n")
if reason:
    print("TRIPPED:" + reason)
PYEOF
}

production_ready() {
  [[ -f "$AUDIT_TALLY" ]] && \
    [[ "$(python -c "import json; print(json.load(open('$AUDIT_TALLY')).get('production_ready', False))" 2>/dev/null)" == "True" ]]
}

# Fingerprint of everything a session could have changed. Two consecutive
# invocations producing an identical hash means nothing happened -- the
# session looked, found nothing new to cluster/build/park, and exited.
# That's the stall signal nothing_unblocked_left() misses when
# cluster-status.json never got created in the first place (e.g. every
# finding from an audit was blocked pre-clustering, so there was never
# anything to cluster).
state_hash() {
  cat "$AUDIT_TALLY" "$CLUSTER_STATUS" "$ATTENTION_QUEUE" 2>/dev/null | md5sum | cut -d' ' -f1
}

# Everything either "complete" or "parked_*" -- nothing "in_progress" or
# unstarted left for a fresh invocation to pick up.
nothing_unblocked_left() {
  [[ -f "$CLUSTER_STATUS" ]] || return 1
  python -c "
import json
state = json.load(open('$CLUSTER_STATUS'))
active = [c for c in state.get('clusters', {}).values()
          if c.get('status') in ('in_progress', 'ready_for_qas', 'pending_review')]
raise SystemExit(0 if not active else 1)
" 2>/dev/null
}

# Parses a reset time out of Claude Code's own error message format, e.g.
# "You've hit your session limit · resets 3:45pm". NOT YET TESTED against a
# real rate-limit hit -- verify this regex against the actual message
# before trusting it; see the caveats at the top of this file.
parse_reset_time() {
  local output="$1"
  echo "$output" | grep -oiE 'resets?[: ]+[0-9]{1,2}(:[0-9]{2})?\s*(am|pm)?' | head -1
}

seconds_until() {
  local target="$1"
  local target_epoch
  target_epoch=$(date -d "$target" +%s 2>/dev/null || date -j -f "%I:%M%p" "$target" +%s 2>/dev/null)
  local now_epoch
  now_epoch=$(date +%s)
  local diff=$(( target_epoch - now_epoch ))
  # If the parsed time is earlier today than now, it means tomorrow.
  if (( diff < 0 )); then
    diff=$(( diff + 86400 ))
  fi
  echo "$diff"
}

trip_and_stop() {
  local reason="$1"
  log "CIRCUIT BREAKER TRIPPED: $reason"
  python .claude/loop-engineering/attention_queue.py add \
    --type blocker --description "Supervisor circuit breaker tripped: $reason. See run-ledger.json." || true
}

main() {
  mkdir -p "$STATE_DIR"
  log "Supervisor starting."
  check_auth_mode
  init_run_ledger

  if run_ledger_tripped; then
    log "run-ledger.json already shows tripped: true from a prior run. Not resuming automatically -- resolve the attention-queue entry and reset run-ledger.json's tripped flag first."
    exit 1
  fi

  # Fresh kickoff check -- only relevant once, before any state exists.
  if [[ ! -f "$AUDIT_TALLY" ]]; then
    if [[ "$START_STEP" != "2" && "$START_STEP" != "3" ]]; then
      log "No prior state found (fresh kickoff) and SUPERVISOR_START_STEP is not set to 2 or 3. Stopping rather than guessing."
      echo "Set SUPERVISOR_START_STEP=2 (build first) or =3 (audit what's already in the repo) and rerun." >&2
      exit 1
    fi
    if [[ "$START_STEP" == "2" ]]; then
      FIRST_INSTRUCTION="Start from Step 2: build the current blueprint/DDD from
scratch using bypass permissions. Once the build is done, proceed straight
into the audit step (build-fidelity-audit) and continue the loop from there."
    else
      FIRST_INSTRUCTION="Start from the audit step: do NOT build anything first
-- assume a build already exists in the repo. Run build-fidelity-audit
against the current state of the code as-is, then continue the loop from
there."
    fi
    log "Fresh kickoff, starting from Step $START_STEP."
  else
    FIRST_INSTRUCTION=""
  fi

  STALL_COUNT=0
  PREV_STATE_HASH="$(state_hash)"

  while true; do
    if production_ready; then
      log "production_ready: true — stopping. Two consecutive clean audits reached."
      break
    fi

    if nothing_unblocked_left; then
      log "Everything is parked awaiting the attention queue — stopping until you engage. See $ATTENTION_QUEUE."
      break
    fi

    BUDGET_ARGS=()
    [[ -n "$MAX_BUDGET_USD" ]] && BUDGET_ARGS=(--max-budget-usd "$MAX_BUDGET_USD")

    log "Invoking a capped headless session (max-turns=$MAX_TURNS${MAX_BUDGET_USD:+, max-budget=\$$MAX_BUDGET_USD})."

    OUTPUT=$(claude -p "Before anything else, read .claude/loop-constraints.md
in full -- it has hard constraints on scope, path restrictions, process,
and escalation that apply to this entire session. ${FIRST_INSTRUCTION:+$FIRST_INSTRUCTION

}Resume the continuous build loop. Check $STATE_DIR/ for
current progress (audit-tally.json, cluster-status.json). Do whatever
unblocked work exists: implement tickets in their assigned worktrees, run
build-fidelity-audit when a tier's clusters are done, dispatch the next
tier's clustering if the current one is fully complete. If a cluster hits
a blocker or needs a design decision, write an entry to
$ATTENTION_QUEUE describing exactly what's needed, mark that cluster
parked in cluster-status.json, and move on to other unblocked work rather
than stopping." \
      --dangerously-skip-permissions \
      --max-turns "$MAX_TURNS" \
      "${BUDGET_ARGS[@]}" \
      --output-format json 2>&1)

    EXIT_CODE=$?
    FIRST_INSTRUCTION=""  # only prepended once, on the genuinely fresh pass

    if echo "$OUTPUT" | grep -qiE "session limit|usage limit|rate limit"; then
      RESET_TIME=$(parse_reset_time "$OUTPUT")
      if [[ -n "$RESET_TIME" ]]; then
        WAIT_SECONDS=$(seconds_until "$RESET_TIME")
        log "Hit the usage limit. Parsed reset time: $RESET_TIME (~$((WAIT_SECONDS / 60)) min). Sleeping, will resume automatically."
        sleep "$WAIT_SECONDS"
      else
        log "Hit a limit but couldn't parse the reset time from the message. Falling back to a fixed 5-hour wait."
        sleep $((5 * 60 * 60))
      fi
      continue  # rate limits don't count against the failure/error-streak breaker
    fi

    if [[ $EXIT_CODE -ne 0 ]]; then
      ERROR_SIG=$(echo "$OUTPUT" | tail -c 200 | tr -d '\n' | md5sum | cut -d' ' -f1)
      TRIP_RESULT=$(record_invocation false "$ERROR_SIG")
      log "Session exited with code $EXIT_CODE (not a rate limit). $OUTPUT"
      if [[ "$TRIP_RESULT" == TRIPPED:* ]]; then
        trip_and_stop "${TRIP_RESULT#TRIPPED:}"
        break
      fi
      log "Retrying in 60s."
      sleep 60
      continue
    fi

    TRIP_RESULT=$(record_invocation true "")
    if [[ "$TRIP_RESULT" == TRIPPED:* ]]; then
      trip_and_stop "${TRIP_RESULT#TRIPPED:}"
      break
    fi

    NEW_STATE_HASH="$(state_hash)"
    if [[ "$NEW_STATE_HASH" == "$PREV_STATE_HASH" ]]; then
      STALL_COUNT=$((STALL_COUNT + 1))
      log "No change in audit-tally/cluster-status/attention-queue this cycle (stall $STALL_COUNT/$STALL_LIMIT)."
      if [[ "$STALL_COUNT" -ge "$STALL_LIMIT" ]]; then
        log "State unchanged for $STALL_LIMIT consecutive invocations — nothing left to do without you. Stopping. Check $ATTENTION_QUEUE for anything pending your decision."
        break
      fi
    else
      STALL_COUNT=0
    fi
    PREV_STATE_HASH="$NEW_STATE_HASH"

    log "Session cycle complete. Looping immediately to pick up more work."
  done

  log "Supervisor stopped."
}

main
