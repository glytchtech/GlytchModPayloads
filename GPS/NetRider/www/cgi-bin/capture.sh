#!/bin/sh
WIGLE_DIR="${WIGLE_DIR:-/root/loot/wigle}"

url_decode() {
  printf '%b' "$(printf '%s' "$1" | sed 's/+/ /g; s/%/\\x/g')"
}

name="$(url_decode "${QUERY_STRING#file=}")"
case "$name" in
  *.csv) ;;
  *) printf 'Status: 400 Bad Request\r\nContent-Type: text/plain\r\n\r\nInvalid capture name'; exit 0 ;;
esac
case "$name" in
  *'/'*|*'\\'*|*'..'*) printf 'Status: 400 Bad Request\r\nContent-Type: text/plain\r\n\r\nInvalid capture name'; exit 0 ;;
esac

file="$WIGLE_DIR/$name"
if [ ! -f "$file" ]; then
  printf 'Status: 404 Not Found\r\nContent-Type: text/plain\r\n\r\nCapture not found'
  exit 0
fi

printf 'Content-Type: text/csv; charset=utf-8\r\nCache-Control: no-store\r\n\r\n'
cat "$file"
