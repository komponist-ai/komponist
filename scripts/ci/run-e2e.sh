#!/usr/bin/env bash
set -Eeuo pipefail

if docker compose version >/dev/null 2>&1; then
  compose=(docker compose)
elif command -v docker-compose >/dev/null 2>&1; then
  compose=(docker-compose)
else
  echo "Docker Compose is required to run the E2E suite." >&2
  exit 1
fi

compose+=(
  -f docker/docker-compose.yml
  -f docker/docker-compose.ci.yml
)

run_in_service() {
  local service="$1"
  local test_path="$2"
  shift 2

  echo "::group::${service}: ${test_path} $*"
  "${compose[@]}" exec -T \
    -e KOMPONIST_AI_MODE=mock \
    -e PYTHONPATH=/app/apps/api:/app/apps/mcp:/app/packages \
    "$service" python "$test_path" "$@"
  echo "::endgroup::"
}

run_pytest_in_service() {
  local service="$1"
  local test_path="$2"

  echo "::group::${service}: pytest ${test_path}"
  "${compose[@]}" exec -T \
    -e KOMPONIST_AI_MODE=mock \
    -e PYTHONPATH=/app/apps/api:/app/apps/mcp:/app/packages \
    "$service" python -m pytest -q "$test_path"
  echo "::endgroup::"
}

wait_for_url() {
  local name="$1"
  local url="$2"
  local accept_http_error="${3:-false}"

  for _ in {1..60}; do
    if [[ "$accept_http_error" == "true" ]] && \
      curl -sS --max-time 2 -o /dev/null "$url"; then
      return 0
    fi
    if [[ "$accept_http_error" != "true" ]] && curl -fsS "$url" >/dev/null; then
      return 0
    fi
    sleep 2
  done

  echo "Timed out waiting for ${name} at ${url}" >&2
  return 1
}

wait_for_url "API" "http://localhost:8000/healthz"
wait_for_url "web" "http://localhost:3000/"
wait_for_url "MCP" "http://localhost:8080/mcp" true

api_tests=(
  auth_session_e2e.py
  email_password_auth_e2e.py
  organization_membership_e2e.py
  organization_departments_e2e.py
  oauth_persistence_e2e.py
  source_documents_e2e.py
  document_versions_e2e.py
  document_upload_e2e.py
  review_lifecycle_e2e.py
  export_e2e.py
  generated_artifacts_e2e.py
  workroom_queue_e2e.py
  workroom_roles_e2e.py
  workroom_plans_e2e.py
  workroom_context_e2e.py
  workroom_messages_e2e.py
  workrooms_e2e.py
  platform_ai_and_api_keys_e2e.py
  chat_history_e2e.py
  chat_e2e.py
  demo_query_e2e.py
)

for test_file in "${api_tests[@]}"; do
  run_in_service api "tests/${test_file}"
done

run_pytest_in_service api /app/packages/core/tests/test_queries.py
run_pytest_in_service api /app/packages/core/tests/test_versioning.py

run_in_service api tests/auth_session_e2e.py seed-restart
"${compose[@]}" restart api
wait_for_url "API after restart" "http://localhost:8000/healthz"
run_in_service api tests/auth_session_e2e.py verify-restart

run_in_service api tests/persistence_e2e.py seed
"${compose[@]}" restart api
wait_for_url "API persistence restart" "http://localhost:8000/healthz"
run_in_service api tests/persistence_e2e.py verify
run_in_service api tests/persistence_e2e.py cleanup

# Queued Workroom agent work lives in Postgres, so restarting both the API and
# the worker must leave it claimable rather than silently dropping it.
run_in_service api tests/workroom_queue_e2e.py seed-restart
"${compose[@]}" restart api worker
wait_for_url "API after worker restart" "http://localhost:8000/healthz"
run_in_service api tests/workroom_queue_e2e.py verify-restart

mcp_tests=(
  search_context_e2e.py
  report_result_e2e.py
  tool_contract_e2e.py
)

for test_file in "${mcp_tests[@]}"; do
  run_in_service mcp "tests/${test_file}"
done

run_in_service mcp tests/approval_persistence_e2e.py seed
"${compose[@]}" restart mcp
wait_for_url "MCP after restart" "http://localhost:8080/mcp" true
run_in_service mcp tests/approval_persistence_e2e.py verify

run_in_service api \
  /app/packages/pipelines/tests/document_relationships_e2e.py
run_in_service api \
  /app/packages/pipelines/tests/identical_document_reuse_e2e.py

echo "All provider-free end-to-end checks passed."
