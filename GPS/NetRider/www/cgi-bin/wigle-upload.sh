#!/bin/bash
# Upload selected Pager WiGLE CSVs only through the device-native WIGLE_UPLOAD
# command. Captures remain in /root/loot/wigle after a successful upload.
set -o pipefail
umask 077

WIGLE_DIR="${WIGLE_DIR:-/root/loot/wigle}"
MAX_BODY=16384
FILES=()

reply() {
  local status="$1"
  local body="$2"
  printf 'Status: %s\r\nContent-Type: application/json\r\nCache-Control: no-store, no-cache, must-revalidate\r\nPragma: no-cache\r\nX-Content-Type-Options: nosniff\r\n\r\n%s' "$status" "$body"
}

configured() {
  /usr/bin/PAYLOAD_GET_CONFIG wigle token >/dev/null 2>&1 && /usr/bin/PAYLOAD_GET_CONFIG wigle authname >/dev/null 2>&1
}

secure_request() {
  # uhttpd exposes HTTPS=on and the standard Origin/Host CGI variables, but
  # not arbitrary X-* headers. Require TLS plus the exact dashboard origin.
  [ "${HTTPS:-}" = 'on' ] && [ -n "${HTTP_ORIGIN:-}" ] && [ "${HTTP_ORIGIN}" = "https://${HTTP_HOST:-}" ]
}

url_decode() {
  local data="${1//+/ }" decoded='' char i=0 length
  length=${#data}
  while (( i < length )); do
    char="${data:i:1}"
    if [[ "$char" == '%' && "${data:i+1:2}" =~ ^[0-9A-Fa-f]{2}$ ]]; then
      printf -v char '%b' "\\x${data:i+1:2}"
      decoded+="$char"
      ((i+=3))
    else
      decoded+="$char"
      ((i++))
    fi
  done
  printf '%s' "$decoded"
}

parse_files() {
  local remaining="$1" pair value
  while [[ -n "$remaining" ]]; do
    pair="${remaining%%&*}"
    if [[ "$remaining" == "$pair" ]]; then remaining=''; else remaining="${remaining#*&}"; fi
    case "$pair" in
      file=*) value="${pair#*=}"; FILES+=("$(url_decode "$value")") ;;
    esac
  done
}

valid_capture_name() {
  [[ "$1" == *.csv ]] || return 1
  [[ "$1" != */* && "$1" != *\\* && "$1" != *..* && "$1" != *$'\n'* && "$1" != *$'\r'* ]]
}

if [ "${REQUEST_METHOD:-}" != 'POST' ]; then
  reply '405 Method Not Allowed' '{"ok":false,"message":"METHOD NOT ALLOWED"}'
  exit 0
fi

if ! secure_request; then
  reply '403 Forbidden' '{"ok":false,"message":"SECURE HTTPS REQUEST REQUIRED"}'
  exit 0
fi

if ! configured; then
  reply '401 Unauthorized' '{"ok":false,"message":"PAGER WiGLE SIGN-IN REQUIRED"}'
  exit 0
fi

if ! [[ "${CONTENT_LENGTH:-}" =~ ^[0-9]+$ ]] || [ "${CONTENT_LENGTH:-0}" -gt "$MAX_BODY" ]; then
  reply '413 Payload Too Large' '{"ok":false,"message":"INVALID REQUEST BODY"}'
  exit 0
fi

body=''
IFS= read -r -N "$CONTENT_LENGTH" body || true
parse_files "$body"
unset body

if [ "${#FILES[@]}" -eq 0 ]; then
  reply '400 Bad Request' '{"ok":false,"message":"NO WiGLE LOGS SELECTED"}'
  exit 0
fi

uploaded=0
total=0
for name in "${FILES[@]}"; do
  valid_capture_name "$name" || continue
  file="$WIGLE_DIR/$name"
  [ -f "$file" ] || continue
  total=$((total + 1))
  # The native command owns the saved token and performs the WiGLE request.
  # Its output is intentionally discarded; this CGI response contains counts
  # only, never tokens, native output, or browser credentials.
  if /usr/bin/WIGLE_UPLOAD "$file" >/dev/null 2>&1; then
    uploaded=$((uploaded + 1))
  fi
done

if [ "$total" -eq 0 ]; then
  reply '400 Bad Request' '{"ok":false,"message":"NO VALID WiGLE LOGS SELECTED"}'
elif [ "$uploaded" -eq "$total" ]; then
  reply '200 OK' "{\"ok\":true,\"uploaded\":$uploaded,\"total\":$total}"
else
  reply '200 OK' "{\"ok\":true,\"uploaded\":$uploaded,\"total\":$total,\"message\":\"ONE OR MORE NATIVE UPLOADS FAILED\"}"
fi
