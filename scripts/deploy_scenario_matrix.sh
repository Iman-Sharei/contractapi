#!/usr/bin/env bash
# Live deploy scenario matrix against a running contractapi stack.
# Usage: STUDIO_API_KEY=... DATA_API_KEY=... ./scripts/deploy_scenario_matrix.sh
set -euo pipefail

API="${API_BASE:-http://127.0.0.1:8000}"
STUDIO_KEY="${STUDIO_API_KEY:-dev-studio-key-change-me}"
DATA_KEY="${DATA_API_KEYS:-${DATA_API_KEY:-dev-data-key}}"
WEB="${WEB_BASE:-http://127.0.0.1:3000}"
# Inside Docker Compose the DB hostname is "db"; from host use localhost:5433.
DB_URL="${DB_URL:-postgresql://postgres:postgres@db:5432/app}"
HOST_DB_URL="${HOST_DB_URL:-postgresql://postgres:postgres@localhost:5433/app}"

PASS=0
FAIL=0
SKIP=0
REPORT=()

redact() { sed -E 's/(api[_-]?key|Bearer|password|secret)[=:][^"&, }]+/\1=<REDACTED>/gi'; }

assert_http() {
  local name="$1" method="$2" url="$3" expect="$4"
  shift 4
  local tmp code body
  tmp=$(mktemp)
  code=$(curl -sS -o "$tmp" -w "%{http_code}" -X "$method" "$url" "$@" || echo "000")
  body=$(head -c 800 "$tmp" | redact || true)
  rm -f "$tmp"
  if [[ "$code" == "$expect" ]]; then
    PASS=$((PASS + 1))
    REPORT+=("PASS  $name ($code)")
  else
    FAIL=$((FAIL + 1))
    REPORT+=("FAIL  $name expected=$expect got=$code body=${body}")
  fi
}

assert_json_field() {
  local name="$1" method="$2" url="$3" jq_expr="$4"
  shift 4
  local tmp code val
  tmp=$(mktemp)
  code=$(curl -sS -o "$tmp" -w "%{http_code}" -X "$method" "$url" "$@" || echo "000")
  if [[ "$code" != "200" && "$code" != "201" ]]; then
    FAIL=$((FAIL + 1))
    REPORT+=("FAIL  $name http=$code body=$(head -c 400 "$tmp" | redact)")
    rm -f "$tmp"
    return
  fi
  if ! command -v jq >/dev/null 2>&1; then
    PASS=$((PASS + 1))
    REPORT+=("PASS  $name (http=$code; jq missing, skipped field assert)")
    rm -f "$tmp"
    return
  fi
  val=$(jq -e "$jq_expr" "$tmp" 2>/dev/null || true)
  if [[ -n "$val" && "$val" != "null" && "$val" != "false" ]]; then
    PASS=$((PASS + 1))
    REPORT+=("PASS  $name")
  else
    FAIL=$((FAIL + 1))
    REPORT+=("FAIL  $name jq='$jq_expr' body=$(head -c 400 "$tmp" | redact)")
  fi
  rm -f "$tmp"
}

echo "== contractapi deploy scenario matrix =="
echo "API=$API WEB=$WEB"

# --- health / ready ---
assert_json_field "root health" GET "$API/health" '.status=="ok"'
assert_http "web home" GET "$WEB/" "200"
assert_http "studio via BFF health" GET "$WEB/api/studio/health" "200"

# --- studio auth ---
assert_http "studio without key" GET "$API/studio/health" "401"
assert_json_field "studio with key" GET "$API/studio/health" '.status=="ok"' \
  -H "X-API-Key: $STUDIO_KEY"
assert_json_field "oidc config public" GET "$API/studio/oidc/config" '.login_path'

# --- introspect ---
assert_json_field "introspect postgres" POST "$API/studio/introspect" '.count > 0' \
  -H "X-API-Key: $STUDIO_KEY" -H "Content-Type: application/json" \
  -d "{\"database_url\":\"$DB_URL\",\"schema_name\":\"public\"}"

# --- activate primary read-only customers ---
SPEC_RO=$(cat <<EOF
{
  "database": {"url": "$DB_URL", "driver": "postgres"},
  "app": {
    "title": "Deploy Matrix API",
    "version": "0.5.0",
    "description": "live scenario",
    "read_only": true,
    "auth": "api_key",
    "api_prefix": "",
    "rate_limit": {"enabled": true, "requests_per_minute": 600}
  },
  "endpoints": [
    {
      "name": "customers",
      "path": "/customers",
      "table": "customers",
      "schema": "public",
      "methods": ["GET"],
      "primary_key": "id",
      "fields": ["id", "name", "email", "created_at"],
      "filters": ["email", "name"],
      "filter_operators": ["eq", "contains", "in"],
      "sortable": ["id", "name"],
      "soft_delete": {"column": "deleted_at"},
      "pagination": {"enabled": true, "mode": "offset", "default_limit": 20, "max_limit": 100},
      "relations": [{
        "name": "orders",
        "table": "orders",
        "schema": "public",
        "type": "one_to_many",
        "local_key": "id",
        "foreign_key": "customer_id",
        "primary_key": "id",
        "fields": ["id", "customer_id", "total", "status"],
        "max_per_parent": 20
      }],
      "csv_export": true,
      "ndjson_export": true
    },
    {
      "name": "order_stats",
      "path": "/stats/orders",
      "aggregate": {
        "table": "orders",
        "schema": "public",
        "group_by": ["status"],
        "where": [{"field": "total", "op": "gt", "value": 0}],
        "metrics": [
          {"name": "n", "op": "count"},
          {"name": "revenue", "op": "sum", "field": "total"}
        ],
        "having": [{"metric": "revenue", "op": "gte", "value": 1}]
      },
      "pagination": {"enabled": true, "mode": "offset", "default_limit": 50, "max_limit": 200}
    }
  ]
}
EOF
)

assert_json_field "validate spec" POST "$API/studio/validate" '.valid==true' \
  -H "X-API-Key: $STUDIO_KEY" -H "Content-Type: application/json" \
  -d "{\"check_db\": true, \"name\": \"deploy_matrix\", \"spec\": $SPEC_RO}"

assert_json_field "activate primary" POST "$API/studio/activate" '.name' \
  -H "X-API-Key: $STUDIO_KEY" -H "Content-Type: application/json" \
  -d "{\"check_db\": true, \"name\": \"deploy_matrix\", \"spec\": $SPEC_RO}"

# --- data plane ---
assert_http "data without key" GET "$API/data/customers" "401"
assert_json_field "list customers" GET "$API/data/customers?limit=5" '.items | length > 0' \
  -H "X-API-Key: $DATA_KEY"
assert_json_field "filter contains __" GET "$API/data/customers?name__contains=Ada" '.items | length >= 1' \
  -H "X-API-Key: $DATA_KEY"
assert_json_field "filter contains soft alias" GET "$API/data/customers?name_contains=Ada" '.items | length >= 1' \
  -H "X-API-Key: $DATA_KEY"
assert_json_field "include relations" GET "$API/data/customers?limit=2&include=orders" \
  '.items[0].orders | type=="array"' \
  -H "X-API-Key: $DATA_KEY"
assert_json_field "include none skips relations" GET "$API/data/customers?limit=1&include=none" \
  '(.items[0].orders|not)' \
  -H "X-API-Key: $DATA_KEY"
assert_json_field "aggregate stats" GET "$API/data/stats/orders" '.items | length >= 1' \
  -H "X-API-Key: $DATA_KEY"
assert_http "csv export" GET "$API/data/customers?format=csv&limit=5" "200" \
  -H "X-API-Key: $DATA_KEY" -H "Accept: text/csv"
assert_http "ndjson export" GET "$API/data/customers?format=ndjson&limit=5" "200" \
  -H "X-API-Key: $DATA_KEY"

# detail by id
CID=$(curl -sS "$API/data/customers?limit=1" -H "X-API-Key: $DATA_KEY" | jq -r '.items[0].id')
assert_json_field "get customer $CID" GET "$API/data/customers/$CID" '.id=='"$CID" \
  -H "X-API-Key: $DATA_KEY"

# --- multi-active named mount ---
SPEC_NAMED=$(cat <<EOF
{
  "database": {"url": "$DB_URL", "driver": "postgres"},
  "app": {
    "title": "Named Mount",
    "version": "0.5.0",
    "description": "multi-active",
    "read_only": true,
    "auth": "api_key",
    "api_prefix": ""
  },
  "endpoints": [{
    "name": "orders",
    "path": "/orders",
    "table": "orders",
    "schema": "public",
    "methods": ["GET"],
    "primary_key": "id",
    "fields": ["id", "customer_id", "total", "status"],
    "filters": ["status"],
    "sortable": ["id"],
    "pagination": {"enabled": true, "mode": "offset", "default_limit": 20, "max_limit": 100}
  }]
}
EOF
)
assert_json_field "activate named" POST "$API/studio/activate/orders_api?primary=false" '.name' \
  -H "X-API-Key: $STUDIO_KEY" -H "Content-Type: application/json" \
  -d "{\"check_db\": true, \"spec\": $SPEC_NAMED}"
assert_json_field "named mount list" GET "$API/apis/orders_api/orders?limit=5" '.items | length >= 1' \
  -H "X-API-Key: $DATA_KEY"

# --- JWT write scenario ---
SPEC_JWT=$(cat <<EOF
{
  "database": {"url": "$DB_URL", "driver": "postgres"},
  "app": {
    "title": "JWT Write",
    "version": "0.5.0",
    "description": "writes",
    "read_only": false,
    "auth": "jwt",
    "api_prefix": "",
    "jwt": {
      "issuer": "contractapi",
      "audience": "contractapi-clients",
      "algorithm": "HS256",
      "access_ttl_minutes": 30,
      "refresh_ttl_days": 7
    },
    "rbac": [{
      "role": "editor",
      "endpoints": {"customers": ["id", "name", "email", "owner_id"]}
    }]
  },
  "endpoints": [{
    "name": "customers",
    "path": "/customers",
    "table": "customers",
    "schema": "public",
    "methods": ["GET", "POST", "PATCH"],
    "primary_key": "id",
    "fields": ["id", "name", "email", "owner_id"],
    "writable_fields": ["name", "email", "owner_id"],
    "filters": ["email"],
    "sortable": ["id"],
    "roles": ["editor"],
    "row_level": {"column": "owner_id", "claim": "sub", "required": false},
    "validations": [{"field": "email", "format": "email"}],
    "pagination": {"enabled": true, "mode": "offset", "default_limit": 20, "max_limit": 100}
  }]
}
EOF
)

assert_json_field "activate jwt write as named" POST "$API/studio/activate/jwt_write?primary=false" '.name' \
  -H "X-API-Key: $STUDIO_KEY" -H "Content-Type: application/json" \
  -d "{\"check_db\": false, \"spec\": $SPEC_JWT}"

TOKEN=$(curl -sS -X POST "$API/studio/token" \
  -H "X-API-Key: $STUDIO_KEY" -H "Content-Type: application/json" \
  -d '{"sub":"deploy-user","roles":["editor"],"expires_minutes":30}' | jq -r '.access_token')

if [[ -n "$TOKEN" && "$TOKEN" != "null" ]]; then
  assert_json_field "jwt list customers" GET "$API/apis/jwt_write/customers?limit=5" '.items' \
    -H "Authorization: Bearer $TOKEN"
  EMAIL="deploy-$(date +%s)@example.com"
  assert_http "jwt create customer" POST "$API/apis/jwt_write/customers" "201" \
    -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
    -H "Idempotency-Key: deploy-$(date +%s)" \
    -d "{\"name\":\"Deploy User\",\"email\":\"$EMAIL\",\"owner_id\":\"deploy-user\"}"
else
  FAIL=$((FAIL + 1))
  REPORT+=("FAIL  issue jwt token")
fi

# --- dbt import + git ---
assert_json_field "dbt import" POST "$API/studio/import/dbt" '.count==1' \
  -H "X-API-Key: $STUDIO_KEY" -H "Content-Type: application/json" \
  -d '{"models":[{"name":"fct_orders","columns":[{"name":"id"},{"name":"status"}]}]}'
assert_json_field "git status" GET "$API/studio/git/status" '.branch' \
  -H "X-API-Key: $STUDIO_KEY"
assert_json_field "git branches" GET "$API/studio/git/branches" '.branches | length >= 1' \
  -H "X-API-Key: $STUDIO_KEY"

# --- GraphQL (may be absent if image lacks strawberry) ---
GQL=$(curl -sS "$API/health" | jq -r '.graphql // false')
if [[ "$GQL" == "true" ]]; then
  assert_json_field "graphql availableEndpoints" POST "$API/data/graphql" \
    '.data.availableEndpoints | length >= 1' \
    -H "X-API-Key: $DATA_KEY" -H "Content-Type: application/json" \
    -d '{"query":"{ availableEndpoints }"}'
else
  SKIP=$((SKIP + 1))
  REPORT+=("SKIP  graphql (not installed in image)")
fi

# --- ready after activate ---
assert_json_field "ready with db" GET "$API/ready" '.status=="ready"'

echo
echo "---- summary ----"
printf '%s\n' "${REPORT[@]}"
echo "PASS=$PASS FAIL=$FAIL SKIP=$SKIP"
if [[ "$FAIL" -gt 0 ]]; then
  exit 1
fi
