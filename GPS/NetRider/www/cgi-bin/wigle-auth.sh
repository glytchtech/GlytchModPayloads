#!/bin/bash
# NetRider delegates WiGLE sign-in to the Pager's native WIGLE_LOGIN command.
# It never calls the WiGLE API directly and never writes browser credentials to
# a file, response body, or process log.
set -o pipefail
umask 077

MAX_BODY=8192

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
  # does not pass arbitrary X-* headers to CGI. Require both TLS and a browser
  # POST from this exact dashboard origin before invoking WIGLE_LOGIN.
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

form_value() {
  local key="$1" remaining="$2" pair value
  while [[ -n "$remaining" ]]; do
    pair="${remaining%%&*}"
    if [[ "$remaining" == "$pair" ]]; then remaining=''; else remaining="${remaining#*&}"; fi
    case "$pair" in
      "$key"=*) value="${pair#*=}"; url_decode "$value"; return 0 ;;
    esac
  done
  return 1
}

if [ "${REQUEST_METHOD:-GET}" = 'GET' ]; then
  if configured; then reply '200 OK' '{"ok":true,"configured":true}'; else reply '200 OK' '{"ok":true,"configured":false}'; fi
  exit 0
fi

if [ "${REQUEST_METHOD:-}" != 'POST' ]; then
  reply '405 Method Not Allowed' '{"ok":false,"configured":false,"message":"METHOD NOT ALLOWED"}'
  exit 0
fi

# uhttpd's HTTPS flag keeps credentials off the HTTP listener, while the
# same-origin check prevents another site from invoking native sign-in.
if ! secure_request; then
  reply '403 Forbidden' '{"ok":false,"configured":false,"message":"SECURE HTTPS REQUEST REQUIRED"}'
  exit 0
fi

if ! [[ "${CONTENT_LENGTH:-}" =~ ^[0-9]+$ ]] || [ "${CONTENT_LENGTH:-0}" -gt "$MAX_BODY" ]; then
  reply '413 Payload Too Large' '{"ok":false,"configured":false,"message":"INVALID REQUEST BODY"}'
  exit 0
fi

body=''
IFS= read -r -N "$CONTENT_LENGTH" body || true
username="$(form_value username "$body")"
password="$(form_value password "$body")"
unset body

if [ -z "$username" ] || [ -z "$password" ]; then
  unset username password
  reply '400 Bad Request' '{"ok":false,"configured":false,"message":"USERNAME AND PASSWORD REQUIRED"}'
  exit 0
fi

# WIGLE_LOGIN is the Pager's native setup workflow. Its output is discarded so
# neither native command text nor credentials can reach the dashboard log.
if /usr/bin/WIGLE_LOGIN "$username" "$password" >/dev/null 2>&1 && configured; then
  unset username password
  reply '200 OK' '{"ok":true,"configured":true,"message":"PAGER TOKEN READY"}'
else
  unset username password
  reply '401 Unauthorized' '{"ok":false,"configured":false,"message":"NATIVE WiGLE SIGN-IN FAILED"}'
fi
