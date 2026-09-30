#!/bin/bash
# Delete only explicitly selected WiGLE CSV loot files. This endpoint requires
# the HTTPS dashboard origin and a second, explicit DELETE confirmation token.
set -o pipefail
umask 077

WIGLE_DIR="${WIGLE_DIR:-/root/loot/wigle}"
CACHE_DIR="${NETRIDER_METADATA_CACHE:-/tmp/netrider-wigle-metadata}"
MAX_BODY=16384
FILES=()
CONFIRM=''

reply() {
  local status="$1"
  local body="$2"
  printf 'Status: %s\r\nContent-Type: application/json\r\nCache-Control: no-store, no-cache, must-revalidate\r\nPragma: no-cache\r\nX-Content-Type-Options: nosniff\r\n\r\n%s' "$status" "$body"
}

secure_request() {
  # uhttpd exposes HTTPS=on and standard Origin/Host CGI variables.
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

parse_request() {
  local remaining="$1" pair key value
  while [[ -n "$remaining" ]]; do
    pair="${remaining%%&*}"
    if [[ "$remaining" == "$pair" ]]; then remaining=''; else remaining="${remaining#*&}"; fi
    key="${pair%%=*}"
    value="${pair#*=}"
    case "$key" in
      file) FILES+=("$(url_decode "$value")") ;;
      confirm) CONFIRM="$(url_decode "$value")" ;;
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

if ! [[ "${CONTENT_LENGTH:-}" =~ ^[0-9]+$ ]] || [ "${CONTENT_LENGTH:-0}" -gt "$MAX_BODY" ]; then
  reply '413 Payload Too Large' '{"ok":false,"message":"INVALID REQUEST BODY"}'
  exit 0
fi

body=''
IFS= read -r -N "$CONTENT_LENGTH" body || true
parse_request "$body"
unset body

if [ "$CONFIRM" != 'DELETE' ]; then
  reply '400 Bad Request' '{"ok":false,"message":"DELETE CONFIRMATION REQUIRED"}'
  exit 0
fi

if [ "${#FILES[@]}" -eq 0 ]; then
  reply '400 Bad Request' '{"ok":false,"message":"NO WiGLE LOGS SELECTED"}'
  exit 0
fi

deleted=0
total=0
for name in "${FILES[@]}"; do
  valid_capture_name "$name" || continue
  file="$WIGLE_DIR/$name"
  [ -f "$file" ] || continue
  total=$((total + 1))
  if rm -f "$file"; then
    [ -z "$CACHE_DIR" ] || rm -f "$CACHE_DIR/$name.meta"
    deleted=$((deleted + 1))
  fi
done

if [ "$total" -eq 0 ]; then
  reply '400 Bad Request' '{"ok":false,"message":"NO VALID WiGLE LOGS SELECTED"}'
elif [ "$deleted" -eq "$total" ]; then
  reply '200 OK' "{\"ok\":true,\"deleted\":$deleted,\"total\":$total}"
else
  reply '200 OK' "{\"ok\":true,\"deleted\":$deleted,\"total\":$total,\"message\":\"ONE OR MORE FILES COULD NOT BE DELETED\"}"
fi
