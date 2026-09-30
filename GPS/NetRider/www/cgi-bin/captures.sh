#!/bin/sh
# Return Pager WiGLE capture metadata. The browser reads selected CSVs using
# capture.sh, so this route never sends capture contents or Pager credentials.
WIGLE_DIR="${WIGLE_DIR:-/root/loot/wigle}"
CACHE_DIR="${NETRIDER_METADATA_CACHE:-/tmp/netrider-wigle-metadata}"
umask 077

json_escape() {
  printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g'
}

file_size() {
  wc -c < "$1" 2>/dev/null | tr -d ' '
}

file_modified() {
  date -r "$1" '+%s' 2>/dev/null || printf '0'
}

read_cached_metadata() {
  cache_signature=''
  cache_metadata=''
  [ -r "$1" ] || return 1
  exec 3< "$1" || return 1
  IFS= read -r cache_signature <&3 || true
  IFS= read -r cache_metadata <&3 || true
  exec 3<&-
  [ "$cache_signature" = "$2" ] && [ -n "$cache_metadata" ]
}

mkdir -p "$CACHE_DIR" 2>/dev/null || CACHE_DIR=''
[ -z "$CACHE_DIR" ] || chmod 700 "$CACHE_DIR" 2>/dev/null || true

printf 'Content-Type: application/json\r\nCache-Control: no-store\r\n\r\n['
first=1
for file in "$WIGLE_DIR"/*.csv; do
  [ -f "$file" ] || continue
  name="$(basename "$file")"
  size="$(file_size "$file")"
  modified="$(file_modified "$file")"
  signature="${size:-0}:${modified:-0}"
  cache_file=''
  metadata=''
  if [ -n "$CACHE_DIR" ]; then
    # basename is inherently separator-free here because it came from the
    # fixed WiGLE_DIR glob; preserve it verbatim instead of depending on an
    # optional hashing applet that is absent on stock Pager firmware.
    cache_file="$CACHE_DIR/$name.meta"
    read_cached_metadata "$cache_file" "$signature" && metadata="$cache_metadata"
  fi
  rows=$(( (${size:-0} + 127) / 128 ))
  estimated=true
  latitude=''
  longitude=''
  first_seen=''
  last_seen=''
  if [ -n "$metadata" ]; then
    rows="${metadata%%|*}"
    remainder="${metadata#*|}"
    latitude="${remainder%%|*}"
    remainder="${remainder#*|}"
    longitude="${remainder%%|*}"
    remainder="${remainder#*|}"
    first_seen="${remainder%%|*}"
    last_seen="${remainder#*|}"
    estimated=false
  fi
  [ "$first" -eq 1 ] || printf ','
  first=0
  escaped_name="$(json_escape "$name")"
  escaped_first="$(json_escape "$first_seen")"
  escaped_last="$(json_escape "$last_seen")"
  printf '{"id":"%s","name":"%s","size":%s,"lines":%s,"estimated":%s,"modified":%s,"firstSeen":"%s","lastSeen":"%s","centroid":' "$escaped_name" "$escaped_name" "${size:-0}" "${rows:-0}" "$estimated" "${modified:-0}" "$escaped_first" "$escaped_last"
  if [ -n "$latitude" ] && [ -n "$longitude" ]; then
    printf '{"lat":%s,"lng":%s}' "$latitude" "$longitude"
  else
    printf 'null'
  fi
  printf '}'
done
printf ']'
