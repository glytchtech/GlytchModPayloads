# NetRider WiGLE Map — 2.1.2-beta.1

This payload hosts the current NetRider dashboard directly from the Pager and reads only WiGLE CSV loot at `/root/loot/wigle`.

See [BETA.md](BETA.md) for the self-contained Glytch Loader package, firmware
requirements, clean LVCC defaults, online-map limitations, and installation.

## Pager menu

The `LIST_PICKER` exposes:

- `OPEN PAGER MAP` — green native map and status bar on the Pager display (firmware 1.1.2+). A cycles follow/pan/zoom, D-pad navigates, Back exits. Includes the green GlytchTech startup splash and guarded `UI_TAKEOVER`/`UI_RELEASE`. See [native setup and controls](native/README.md).
- `START SERVER` — uses the bundled `uhttpd`, creates a per-Pager local TLS certificate, and starts the dashboard in the background on HTTPS port `8443` (HTTP `8090` redirects to HTTPS). No packages are installed or downloaded.
- `STOP SERVER` — stops only this dashboard process.
- `SERVER STATUS` — reports the running state, port, and newest WiGLE CSV.
- `EXIT` — if NetRider is running, asks whether to leave the dashboard server running or stop it first.

On a client connected to the Pager, open `https://<PAGER-IP>:8443`. The USB Ethernet address is normally `https://172.16.52.1:8443`. Accept the Pager's self-signed local certificate once; this is required before the dashboard will send WiGLE credentials to the Pager-native sign-in command.

## Live mode

The Pager page starts its Live WiGLE Feed automatically. It polls the newest `*.csv` in `/root/loot/wigle` every 1.8 seconds, follows the newest valid coordinate written to that log, and never requests location permission from the viewing device. Dragging the map pauses automatic following; use the map-panel `FOLLOW LIVE` control to resume.

In the native map, double-tap A to start WiGLE logging with the Pager's `WIGLE_START` command. The lower bar shows firmware-confirmed logging status. Logging is never started automatically, existing sessions are not restarted, and radio settings are unchanged. Logging continues after leaving the map; use the Pager’s normal controls to stop it. A GPS fix is required for useful mapped observations.

The WiGLE log selector can combine multiple logs, show each capture's approximate size, line count, capture range, and nearest town, and upload selected files. The town lookup runs in the viewing browser against OpenStreetMap only after a log is selected; it is rate-limited, cached for the browser session, and does not require Pager internet access. Sign-in delegates to the Pager's `WIGLE_LOGIN` command and uploads delegate to `WIGLE_UPLOAD`; NetRider never calls WiGLE directly and does not store browser credentials.

## Payload contents

The `www/` directory contains the same dashboard assets as the desktop version plus Pager CGI routes:

- `captures.sh` lists Pager WiGLE CSV files.
- `capture.sh` serves one validated WiGLE CSV filename.
- `live.sh` serves the bounded tail of the most recently modified WiGLE CSV.

The selector can also delete selected WiGLE CSVs after an explicit browser confirmation. Deletion is accepted only from the dashboard's same-origin HTTPS connection and only for validated filenames inside `/root/loot/wigle`.

The payload resolves its own directory from the Pager-native `$_PAYLOAD_HOME` variable, so it can run from any Pager payload folder. The complete folder, including `runtime/` and `www/vendor/`, is required. The beta release contains no saved capture data or map cache.
