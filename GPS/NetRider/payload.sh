#!/bin/bash
# Title: NetRider WiGLE Map
# Description: Native green map display and Pager-hosted NetRider WiGLE dashboard.
# Author: Glytch + Codex
# Version: 2.1.2-beta.1
# Category: general
#
# The dashboard is served only from this Pager and reads CSVs from /root/loot/wigle.
# Native double-tap A explicitly starts WiGLE logging; no radio/engagement settings change.

HTTP_PORT=8090
HTTPS_PORT=8443
PATH="/usr/sbin:/usr/bin:/sbin:/bin:/mmc/bin:/mmc/sbin:/mmc/usr/bin:/mmc/usr/sbin:${PATH:-}"
export PATH
# Pager provides this native variable as the root of the active payload, so the
# dashboard works from any payload category or folder. The fallback is solely
# for manual shell execution outside the Pager payload runner.
PAYLOAD_DIR="${_PAYLOAD_HOME:-${NETRIDER_PAYLOAD_DIR:-}}"
if [ -z "$PAYLOAD_DIR" ]; then
  PAYLOAD_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
fi
PAYLOAD_DIR="${PAYLOAD_DIR%/}"
WEB_ROOT="$PAYLOAD_DIR/www"
PID_FILE=/tmp/netrider-wigle-map.pid
LOG_FILE=/tmp/netrider-wigle-map.log
WIGLE_DIR=/root/loot/wigle
RUNTIME="$PAYLOAD_DIR/runtime"
UHTTPD="$RUNTIME/usr/sbin/uhttpd"
CERT_DIR="$PAYLOAD_DIR/certs"
CERT_FILE="$CERT_DIR/netrider-pager.crt"
KEY_FILE="$CERT_DIR/netrider-pager.key"

is_running() {
  [ -s "$PID_FILE" ] || return 1
  local pid
  pid="$(cat "$PID_FILE" 2>/dev/null)"
  [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null
}

active_log() {
  ls -1t "$WIGLE_DIR"/*.csv 2>/dev/null | head -n 1
}

ensure_web_server() {
  if [ ! -f "$UHTTPD" ]; then
    ERROR_DIALOG "Bundled web server missing. Reinstall the complete NetRider beta folder."
    return 1
  fi
  chmod 755 "$UHTTPD" "$WEB_ROOT"/cgi-bin/*.sh || return 1
}

ensure_tls_certificate() {
  [ -r "$CERT_FILE" ] && [ -r "$KEY_FILE" ] && return 0
  if ! command -v openssl >/dev/null 2>&1; then
    ERROR_DIALOG "NetRider needs OpenSSL to create its local HTTPS certificate."
    return 1
  fi
  mkdir -p "$CERT_DIR" || return 1
  chmod 700 "$CERT_DIR" 2>/dev/null || true
  # Create a per-Pager certificate on first launch. The private key is never
  # copied from this project or sent to a browser; accept the local certificate
  # warning once when opening the dashboard from a new client.
  umask 077
  openssl req -x509 -newkey rsa:2048 -nodes -sha256 -days 3650 \
    -keyout "$KEY_FILE" -out "$CERT_FILE" \
    -subj '/CN=172.16.52.1' \
    -addext 'subjectAltName=IP:172.16.52.1,DNS:netrider.pager' \
    >/dev/null 2>&1 || {
      ERROR_DIALOG "Could not create NetRider HTTPS certificate."
      return 1
    }
  chmod 600 "$KEY_FILE" 2>/dev/null || true
  chmod 644 "$CERT_FILE" 2>/dev/null || true
}

start_server() {
  if is_running; then
    PROMPT "NETRIDER ALREADY RUNNING\n\nHTTPS PORT: $HTTPS_PORT"
    return
  fi
  if [ ! -d "$WEB_ROOT" ]; then
    ERROR_DIALOG "Dashboard files are missing from this payload."
    return
  fi
  ensure_web_server || return
  ensure_tls_certificate || return
  LOG blue "Starting NetRider on HTTPS port $HTTPS_PORT..."
  # The Pager menu runner closes its own session after a payload action.
  # Run uhttpd in a new session so the dashboard persists in the background.
  NETRIDER_HTTPS_PORT="$HTTPS_PORT" /usr/bin/setsid "$UHTTPD" -f \
    -p "0.0.0.0:$HTTP_PORT" -s "0.0.0.0:$HTTPS_PORT" -q \
    -C "$CERT_FILE" -K "$KEY_FILE" -h "$WEB_ROOT" -x /cgi-bin -D -S \
    < /dev/null > "$LOG_FILE" 2>&1 &
  local pid=$!
  echo "$pid" > "$PID_FILE"
  sleep 1
  if is_running; then
    LOG green "NetRider running on HTTPS port $HTTPS_PORT"
    PROMPT "NETRIDER ONLINE\n\nHTTPS PORT: $HTTPS_PORT\nHTTP REDIRECT: $HTTP_PORT\n\nOpen https://<PAGER-IP>:$HTTPS_PORT\n\nAccept the local certificate once."
  else
    rm -f "$PID_FILE"
    ERROR_DIALOG "NetRider did not start. See /tmp/netrider-wigle-map.log"
  fi
}

stop_server() {
  if ! is_running; then
    rm -f "$PID_FILE"
    PROMPT "NETRIDER IS NOT RUNNING\n\nHTTPS PORT: $HTTPS_PORT"
    return
  fi
  local pid
  pid="$(cat "$PID_FILE")"
  kill "$pid" 2>/dev/null
  sleep 1
  if kill -0 "$pid" 2>/dev/null; then
    ERROR_DIALOG "Could not stop NetRider (PID $pid)."
    return
  fi
  rm -f "$PID_FILE"
  LOG yellow "NetRider stopped"
  PROMPT "NETRIDER STOPPED\n\nHTTPS PORT: $HTTPS_PORT"
}

show_status() {
  local service_state="STOPPED"
  is_running && service_state="RUNNING"
  local current
  current="$(active_log)"
  local log_state="NO WiGLE CSV FOUND"
  [ -n "$current" ] && log_state="$(basename "$current")"
  PROMPT "NETRIDER: $service_state\nHTTPS PORT: $HTTPS_PORT\nHTTP REDIRECT: $HTTP_PORT\n\nLIVE LOG:\n$log_state"
}

exit_payload() {
  if ! is_running; then
    return 0
  fi
  local response
  response="$(CONFIRMATION_DIALOG "NETRIDER SERVER IS RUNNING.\n\nKeep the dashboard running after exit?")"
  case "$?" in
    "$DUCKYSCRIPT_REJECTED"|"$DUCKYSCRIPT_ERROR")
      LOG yellow "Exit confirmation cancelled"
      return 1
      ;;
  esac
  case "$response" in
    "$DUCKYSCRIPT_USER_CONFIRMED")
      LOG green "NetRider remains running on HTTPS port $HTTPS_PORT"
      return 0
      ;;
    "$DUCKYSCRIPT_USER_DENIED")
      stop_server
      return 0
      ;;
    *)
      LOG yellow "Exit confirmation cancelled"
      return 1
      ;;
  esac
}

open_pager_map() {
  if [ ! -f "$RUNTIME/usr/bin/python3.11" ]; then
    ERROR_DIALOG "Bundled Python missing. Reinstall the complete NetRider beta folder."
    return
  fi
  chmod 755 "$RUNTIME/python3" "$RUNTIME/usr/bin/python3.11" || return
  if [ ! -x /usr/bin/UI_TAKEOVER ] || [ ! -x /usr/bin/UI_RELEASE ]; then
    ERROR_DIALOG "Native map requires Pager firmware 1.1.2 or newer."
    return
  fi
  LOG green "Native map: A mode; double A logging; double Power display settings; Back exits."
  "$RUNTIME/python3" -B "$PAYLOAD_DIR/native/main.py"
  local result=$?
  if [ "$result" -ne 0 ]; then
    LOG red "Native map exited with an error. See payload output; firmware UI release was requested."
  fi
}

while true; do
  choice="$(LIST_PICKER "NETRIDER MAP" "OPEN PAGER MAP" "START SERVER" "STOP SERVER" "SERVER STATUS" "EXIT" "OPEN PAGER MAP")"
  case "$choice" in
    "OPEN PAGER MAP") open_pager_map ;;
    "START SERVER") start_server ;;
    "STOP SERVER") stop_server ;;
    "SERVER STATUS") show_status ;;
    "EXIT") exit_payload && exit 0 ;;
    *) LOG yellow "NetRider menu cancelled"; exit_payload && exit 0 ;;
  esac
done
