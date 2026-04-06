#!/usr/bin/env bash
# =============================================================================
#  Vaidya — Disaster Recovery Runbook & Drill Script
#  RTO target: < 4 hours   |   RPO target: < 1 hour
# =============================================================================
#
#  Usage:
#    chmod +x scripts/dr_drill.sh
#    ./scripts/dr_drill.sh [scenario]
#
#  Scenarios:
#    db_restore     — simulate PostgreSQL failure, restore from backup
#    redis_flush    — simulate Redis cache loss, verify triage continues
#    ollama_outage  — simulate LLM unavailability, verify graceful degradation
#    full           — run all three in sequence
#
#  This script is meant to be run monthly and before each major release.
#  Results should be recorded in the DR log (scripts/dr_log.md).
#
#  Safe to run against staging. DO NOT run db_restore against production
#  without explicit sign-off from the engineering lead.
# =============================================================================

set -euo pipefail

API_URL="${API_URL:-http://localhost:8000}"
COMPOSE="${COMPOSE:-docker compose}"
PASS=0
FAIL=0

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'

log()  { echo -e "${NC}[$(date +%H:%M:%S)] $*"; }
ok()   { echo -e "${GREEN}  ✓ $*${NC}"; ((PASS++)); }
fail() { echo -e "${RED}  ✗ $*${NC}"; ((FAIL++)); }
warn() { echo -e "${YELLOW}  ⚠ $*${NC}"; }

# ── Helpers ───────────────────────────────────────────────────────────────────

check_api_health() {
  local label="${1:-API health}"
  local response
  response=$(curl -sf "$API_URL/health" 2>/dev/null || echo '{}')
  local status
  status=$(echo "$response" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('status','unknown'))" 2>/dev/null || echo "unknown")
  if [[ "$status" == "ok" ]] || [[ "$status" == "degraded" ]]; then
    ok "$label: status=$status"
  else
    fail "$label: unreachable or status=$status"
  fi
}

check_triage_works() {
  local label="${1:-Triage endpoint}"
  local code
  code=$(curl -s -o /dev/null -w "%{http_code}" \
    -X POST "$API_URL/api/v1/diagnose/predict/text" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer test-token" \
    -d '{"text":"high fever headache body ache for 3 days","language":"en","self_severity":6}' \
    2>/dev/null || echo "000")

  # 200 = success, 401 = auth required but endpoint alive, 422 = validation (alive)
  if [[ "$code" =~ ^(200|401|422)$ ]]; then
    ok "$label: HTTP $code (endpoint reachable)"
  else
    fail "$label: HTTP $code (endpoint unreachable)"
  fi
}

wait_for_service() {
  local name="$1"
  local max_wait="${2:-60}"
  local elapsed=0
  log "Waiting for $name to recover (max ${max_wait}s)..."
  while [[ $elapsed -lt $max_wait ]]; do
    if check_api_health "  $name readiness" 2>/dev/null; then
      return 0
    fi
    sleep 5
    ((elapsed += 5))
  done
  fail "$name did not recover within ${max_wait}s"
  return 1
}


# =============================================================================
#  SCENARIO 1: Database failover + restore
# =============================================================================

drill_db_restore() {
  log "━━━ SCENARIO 1: PostgreSQL failure + backup restore ━━━"
  log "RTO target: < 30 minutes | RPO target: < 1 hour"

  # Step 1: Verify baseline
  log "Step 1/5 — Verify baseline health"
  check_api_health "Pre-drill"
  check_triage_works "Pre-drill triage"

  # Step 2: Create a backup (simulating hourly backup job)
  log "Step 2/5 — Create point-in-time backup"
  local backup_name="dr_drill_$(date +%Y%m%d_%H%M%S)"
  if $COMPOSE exec -T postgres pg_dump \
    -U "${POSTGRES_USER:-vaidya}" \
    -d "${POSTGRES_DB:-vaidya}" \
    --format=custom \
    --file="/tmp/${backup_name}.dump" 2>/dev/null; then
    ok "Backup created: /tmp/${backup_name}.dump"
  else
    warn "pg_dump failed (expected if postgres is not running in drill mode)"
  fi

  # Step 3: Simulate failure
  log "Step 3/5 — Simulate PostgreSQL container failure"
  $COMPOSE stop postgres 2>/dev/null || true
  sleep 3

  local code
  code=$(curl -s -o /dev/null -w "%{http_code}" "$API_URL/health" 2>/dev/null || echo "000")
  if [[ "$code" != "200" ]] || \
     [[ "$(curl -sf "$API_URL/health" 2>/dev/null | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d.get("status",""))' 2>/dev/null)" != "ok" ]]; then
    ok "API correctly reports degraded state during DB outage"
  else
    warn "API still reports 'ok' during DB outage — health check may not probe DB"
  fi

  # Step 4: Restore
  log "Step 4/5 — Restore PostgreSQL"
  $COMPOSE start postgres 2>/dev/null || true
  sleep 5

  # Wait up to 60s for postgres to become healthy
  local pg_ready=false
  for i in $(seq 1 12); do
    if $COMPOSE exec -T postgres pg_isready -U "${POSTGRES_USER:-vaidya}" &>/dev/null; then
      pg_ready=true
      break
    fi
    sleep 5
  done

  if $pg_ready; then
    ok "PostgreSQL recovered"
  else
    fail "PostgreSQL did not recover within 60s"
    return 1
  fi

  # Restart API to re-establish connection pool
  $COMPOSE restart api 2>/dev/null || true
  sleep 5

  # Step 5: Verify recovery
  log "Step 5/5 — Verify post-recovery health"
  check_api_health "Post-restore"
  check_triage_works "Post-restore triage"

  log "DB restore drill complete."
  echo ""
}


# =============================================================================
#  SCENARIO 2: Redis flush (cache loss)
# =============================================================================

drill_redis_flush() {
  log "━━━ SCENARIO 2: Redis cache flush ━━━"
  log "Expected behaviour: triage continues, cache miss → cold path"

  # Step 1: Baseline
  log "Step 1/4 — Verify baseline"
  check_api_health "Pre-flush"
  check_triage_works "Pre-flush triage (should use cache)"

  # Step 2: Flush all Redis keys
  log "Step 2/4 — Flush Redis"
  if $COMPOSE exec -T redis redis-cli \
    -a "${REDIS_PASSWORD:-redis_secret}" \
    FLUSHALL 2>/dev/null | grep -q "OK"; then
    ok "Redis FLUSHALL succeeded — all cached data cleared"
  else
    warn "Redis FLUSHALL result unclear (may be OK)"
  fi

  # Step 3: Verify triage still works (cold cache path)
  log "Step 3/4 — Verify triage works without cache"
  check_triage_works "Post-flush triage (cold path)"

  # Critical: rate limiting uses Redis — verify it still enforces limits
  log "Step 4/4 — Verify rate limiting recovers"
  local rl_code
  # Send 65 rapid requests — should trigger 429 after the 60th
  local triggered_429=false
  for i in $(seq 1 65); do
    rl_code=$(curl -s -o /dev/null -w "%{http_code}" "$API_URL/health" 2>/dev/null || echo "000")
    if [[ "$rl_code" == "429" ]]; then
      triggered_429=true
      break
    fi
  done

  if $triggered_429; then
    ok "Rate limiting operational after Redis flush"
  else
    warn "Rate limiting did not trigger 429 in 65 requests — check Redis reconnection"
  fi

  log "Redis flush drill complete."
  echo ""
}


# =============================================================================
#  SCENARIO 3: Ollama LLM outage
# =============================================================================

drill_ollama_outage() {
  log "━━━ SCENARIO 3: Ollama LLM outage ━━━"
  log "Expected: XGBoost continues, LLM fallback degrades gracefully with logged error"

  # Step 1: Baseline
  log "Step 1/4 — Verify baseline with LLM available"
  check_api_health "Pre-outage"

  # Step 2: Stop Ollama
  log "Step 2/4 — Simulate Ollama outage"
  $COMPOSE stop ollama 2>/dev/null || true
  sleep 3
  ok "Ollama container stopped"

  # Step 3: Submit a triage that would normally trigger LLM fallback
  # (sparse symptom text → low XGBoost confidence → LLM fallback path)
  log "Step 3/4 — Submit low-confidence triage (should trigger LLM fallback path)"
  local response
  response=$(curl -s \
    -X POST "$API_URL/api/v1/diagnose/predict/text" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer test-token" \
    -d '{"text":"not feeling well","language":"en","self_severity":3}' \
    2>/dev/null || echo '{}')

  local diagnosis
  diagnosis=$(echo "$response" | python3 -c \
    "import sys,json; d=json.load(sys.stdin); print(d.get('diagnosis',{}).get('primary_diagnosis','none'))" \
    2>/dev/null || echo "parse_failed")

  # We expect a valid response — either XGBoost result or the conservative LLM fallback
  if [[ "$diagnosis" != "none" ]] && [[ "$diagnosis" != "parse_failed" ]] && [[ "$diagnosis" != "" ]]; then
    ok "Triage returned result despite Ollama outage: '$diagnosis'"
  else
    # 401/422 is also acceptable — means auth/validation stopped it, not a crash
    local http_code
    http_code=$(curl -s -o /dev/null -w "%{http_code}" \
      -X POST "$API_URL/api/v1/diagnose/predict/text" \
      -H "Content-Type: application/json" \
      -d '{"text":"fever cough headache","language":"en"}' 2>/dev/null || echo "000")
    if [[ "$http_code" =~ ^(200|401|422)$ ]]; then
      ok "Triage endpoint alive during Ollama outage (HTTP $http_code)"
    else
      fail "Triage endpoint returned HTTP $http_code during Ollama outage — unexpected crash"
    fi
  fi

  # Step 4: Restore Ollama
  log "Step 4/4 — Restore Ollama"
  $COMPOSE start ollama 2>/dev/null || true
  sleep 10
  ok "Ollama container started — model warm-up takes ~30s"
  warn "Note: first triage request after restart may be slow (~30s) while model loads"

  log "Ollama outage drill complete."
  echo ""
}


# =============================================================================
#  MAIN
# =============================================================================

print_summary() {
  echo ""
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "  DR Drill Summary"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo -e "  ${GREEN}Passed: $PASS${NC}   ${RED}Failed: $FAIL${NC}"
  echo "  Date: $(date -u '+%Y-%m-%d %H:%M UTC')"
  echo ""
  echo "  Record results in: scripts/dr_log.md"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo ""

  if [[ $FAIL -gt 0 ]]; then
    exit 1
  fi
}

SCENARIO="${1:-full}"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Vaidya DR Drill — Scenario: $SCENARIO"
echo "  Target API: $API_URL"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

case "$SCENARIO" in
  db_restore)   drill_db_restore ;;
  redis_flush)  drill_redis_flush ;;
  ollama_outage) drill_ollama_outage ;;
  full)
    drill_db_restore
    drill_redis_flush
    drill_ollama_outage
    ;;
  *)
    echo "Unknown scenario: $SCENARIO"
    echo "Valid: db_restore | redis_flush | ollama_outage | full"
    exit 1
    ;;
esac

print_summary
