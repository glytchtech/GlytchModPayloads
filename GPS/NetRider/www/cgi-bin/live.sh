#!/bin/sh
WIGLE_DIR="${WIGLE_DIR:-/root/loot/wigle}"
LIVE_LIMIT=1000

file="$(ls -1t "$WIGLE_DIR"/*.csv 2>/dev/null | head -n 1)"
if [ -z "$file" ] || [ ! -f "$file" ]; then
  printf 'Status: 204 No Content\r\nCache-Control: no-store\r\n\r\n'
  exit 0
fi

header="$(grep -m 1 '^MAC,' "$file" 2>/dev/null)"
case "$header" in
  MAC,*) ;;
  *) printf 'Status: 204 No Content\r\nCache-Control: no-store\r\n\r\n'; exit 0 ;;
esac

printf 'Content-Type: text/csv; charset=utf-8\r\nCache-Control: no-store\r\nX-NetRider-File: %s\r\n\r\n' "$(basename "$file")"
printf '%s\n' "$header"
tail -n "$LIVE_LIMIT" "$file" | awk -v header="$header" 'NR == 1 && $0 == header { next } { print }'
