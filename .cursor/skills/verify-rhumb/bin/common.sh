set -euo pipefail

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  exit 2
fi

VERIFY_RHUMB_BIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VERIFY_RHUMB_SKILL_DIR="$(cd "$VERIFY_RHUMB_BIN_DIR/.." && pwd)"
VERIFY_RHUMB_REPO_ROOT="$(cd "$VERIFY_RHUMB_SKILL_DIR/../../.." && pwd)"

VERIFY_RHUMB_BASE="${VERIFY_RHUMB_BASE:-https://api.rhumb.dev}"
VERIFY_RHUMB_SITE="${VERIFY_RHUMB_SITE:-https://rhumb.dev}"
VERIFY_RHUMB_RUN_ID="${VERIFY_RHUMB_RUN_ID:-$(date -u +%Y%m%dT%H%M%SZ)}"
VERIFY_RHUMB_EVIDENCE_DIR="${VERIFY_RHUMB_EVIDENCE_DIR:-$VERIFY_RHUMB_SKILL_DIR/evidence/$VERIFY_RHUMB_RUN_ID}"
VERIFY_RHUMB_STATE_DIR="${VERIFY_RHUMB_STATE_DIR:-/tmp/verify-rhumb-state-$VERIFY_RHUMB_RUN_ID}"
VERIFY_RHUMB_UA="${VERIFY_RHUMB_UA:-rhumb-verify/1.0}"

verify_rhumb_prepare() {
  mkdir -p "$VERIFY_RHUMB_EVIDENCE_DIR/http" "$VERIFY_RHUMB_STATE_DIR"
  printf '%s\n' "$VERIFY_RHUMB_RUN_ID" >"$VERIFY_RHUMB_STATE_DIR/run-id"
  printf '%s\n' "$VERIFY_RHUMB_EVIDENCE_DIR" >"$VERIFY_RHUMB_STATE_DIR/evidence-dir"
}

verify_rhumb_curl() {
  local method="$1"
  local url="$2"
  local body_out="$3"
  local meta_out="$4"
  local tmp_headers
  tmp_headers="$(mktemp "$VERIFY_RHUMB_STATE_DIR/headers.XXXXXX")"
  local http_code
  http_code="$(
    curl -sS -X "$method" \
      -H "User-Agent: $VERIFY_RHUMB_UA" \
      -H "Accept: application/json" \
      -D "$tmp_headers" \
      -o "$body_out" \
      -w '%{http_code}' \
      "$url"
  )"
  {
    printf 'url=%s\n' "$url"
    printf 'method=%s\n' "$method"
    printf 'http_code=%s\n' "$http_code"
    cat "$tmp_headers"
  } >"$meta_out"
  rm -f "$tmp_headers"
  printf '%s\n' "$http_code"
}

verify_rhumb_python() {
  python3 - "$@"
}
