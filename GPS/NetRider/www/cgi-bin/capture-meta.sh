#!/bin/sh
# Detailed metadata for a single selected WiGLE capture. Its result is cached
# so the catalogue remains instant on later opens.
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

url_decode() {
  printf '%b' "$(printf '%s' "$1" | sed 's/+/ /g; s/%/\\x/g')"
}

name="$(url_decode "${QUERY_STRING#file=}")"
case "$name" in
  *.csv) ;;
  *) printf 'Status: 400 Bad Request\r\nContent-Type: application/json\r\n\r\n{"ok":false,"message":"INVALID CAPTURE NAME"}'; exit 0 ;;
esac
case "$name" in
  *'/'*|*'\\'*|*'..'*) printf 'Status: 400 Bad Request\r\nContent-Type: application/json\r\n\r\n{"ok":false,"message":"INVALID CAPTURE NAME"}'; exit 0 ;;
esac

file="$WIGLE_DIR/$name"
if [ ! -f "$file" ]; then
  printf 'Status: 404 Not Found\r\nContent-Type: application/json\r\n\r\n{"ok":false,"message":"CAPTURE NOT FOUND"}'
  exit 0
fi

# WiGLE rows are intentionally scanned with awk's native CSV field splitting:
# this route is informational (not the actual CSV importer) and must complete
# quickly on the Pager CPU. SSIDs containing commas are ignored if their shifted
# latitude/longitude values fail numeric validation, preserving centroid safety.
metadata="$(awk -F ',' '
  $1 == "MAC" {
    for (i=1; i<=NF; i++) {
      if ($i == "CurrentLatitude") latitude=i
      if ($i == "CurrentLongitude") longitude=i
      if ($i == "FirstSeen") first_seen=i
    }
    header_found=(latitude && longitude)
    next
  }
  header_found {
    rows++
    lat=$(latitude)+0; lng=$(longitude)+0
    if (lat >= -90 && lat <= 90 && lng >= -180 && lng <= 180 && !(lat == 0 && lng == 0)) {
      latitude_total+=lat; longitude_total+=lng; coordinates++
    }
    seen=$(first_seen)
    if (seen ~ /^[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9][[:space:]][0-9][0-9]:[0-9][0-9]:[0-9][0-9]$/) {
      if (first == "" || seen < first) first=seen
      if (last == "" || seen > last) last=seen
    }
  }
  END {
    if (coordinates) printf "%d|%.6f|%.6f|%s|%s", rows, latitude_total/coordinates, longitude_total/coordinates, first, last
    else printf "%d|||%s|%s", rows, first, last
  }
' "$file" 2>/dev/null)"

rows="${metadata%%|*}"
remainder="${metadata#*|}"
latitude="${remainder%%|*}"
remainder="${remainder#*|}"
longitude="${remainder%%|*}"
remainder="${remainder#*|}"
first_seen="${remainder%%|*}"
last_seen="${remainder#*|}"
size="$(file_size "$file")"
modified="$(file_modified "$file")"
signature="${size:-0}:${modified:-0}"
mkdir -p "$CACHE_DIR" 2>/dev/null || CACHE_DIR=''
if [ -n "$CACHE_DIR" ] && [ -n "$metadata" ]; then
  chmod 700 "$CACHE_DIR" 2>/dev/null || true
  cache_file="$CACHE_DIR/$name.meta"
  cache_tmp="$cache_file.$$"
  printf '%s\n%s\n' "$signature" "$metadata" > "$cache_tmp" 2>/dev/null && mv -f "$cache_tmp" "$cache_file" 2>/dev/null
fi

printf 'Content-Type: application/json\r\nCache-Control: no-store\r\n\r\n'
escaped_name="$(json_escape "$name")"
escaped_first="$(json_escape "$first_seen")"
escaped_last="$(json_escape "$last_seen")"
printf '{"ok":true,"id":"%s","name":"%s","size":%s,"lines":%s,"estimated":false,"modified":%s,"firstSeen":"%s","lastSeen":"%s","centroid":' "$escaped_name" "$escaped_name" "${size:-0}" "${rows:-0}" "${modified:-0}" "$escaped_first" "$escaped_last"
if [ -n "$latitude" ] && [ -n "$longitude" ]; then
  printf '{"lat":%s,"lng":%s}' "$latitude" "$longitude"
else
  printf 'null'
fi
printf '}'
