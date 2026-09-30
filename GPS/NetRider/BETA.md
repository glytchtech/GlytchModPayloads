# NetRider 2.1.2-beta.1

This is the current NetRider native Pager map and browser dashboard, packaged
for beta testing. It does not include the proposed offline map-pack builder.

## Requirements and bundled software

- WiFi Pineapple Pager, firmware **1.1.2 or later** (1.1.2 is the compatibility
  baseline; future firmware versions may need retesting).
- The Pager's stock Bash, OpenSSL, TLS/JSON libraries, curl, gpsd and Hak5
  commands remain in use. No firmware libraries are replaced.
- Payload-local Python 3.11 and uhttpd are included. MapLibre GL JS and dashboard
  fonts are included. No `opkg`, npm, pip, CDN scripts, or package downloads are
  needed when installing or launching this release.
- GPS hardware/fix is needed for live positioning. Only authorized collection
  should be performed; no captures or radio changes start merely by opening it.

**Self-contained installation does not mean offline maps.** New basemap tiles,
styles and map labels still come from OpenFreeMap. The native view uses the
Pager's internet connection and its on-disk tile cache; the browser view uses
the viewing device's internet connection. Place/town lookups use browser-side
OpenStreetMap Nominatim. WiGLE login and upload require the Pager to reach
WiGLE. No map pack is bundled. The native map can show observations on black
and reuse cached tiles without internet.

## Clean release defaults

The default location is **LVCC, Las Vegas: 36.1319, -115.1515**. The dashboard
starts with zero observations. No WiGLE CSVs, SSIDs/BSSIDs, past fixes, saved
address lookups, rendered map cache, usernames/passwords, WiGLE tokens,
display preferences, device backups, or development screenshots are included.

Each Pager generates its own HTTPS certificate on first server start. Private
keys are never shared in the release. Existing logs and account configuration
on the receiving Pager are not erased, so its own latest log/GPS fix may move
the map away from the default. The Loader also preserves existing runtime
cache/settings when updating an already-installed copy.

## Glytch Loader repository layout

Copy the archive's `GPS/NetRider` directory into the root of
`GlytchModPayloads`, keeping all files and subdirectories:

```
GPS/NetRider/payload.sh
GPS/NetRider/native/
GPS/NetRider/runtime/
GPS/NetRider/www/
```

The Loader discovers `GPS > NetRider` and reads `Category: general` from
`payload.sh`, installing the complete folder to
`/root/payloads/user/general/NetRider`. No Loader manifest or post-install step
is needed. Do not commit only the launcher or omit the bundled runtime/vendor
files. The launcher restores required executable permissions and uses
`$_PAYLOAD_HOME`, so it also works from other payload categories.

For manual installation, copy the entire `NetRider` folder into an existing
`/root/payloads/user/<category>/` directory and make `payload.sh` executable.

## Use

- **OPEN PAGER MAP:** A cycles Follow/Pan/Zoom; D-pad navigates; B exits.
- **Double A:** start WiGLE logging; the lower bar confirms the logging state.
  Logging continues after leaving the map. Stop it in the normal Pager UI.
- **Double Power:** brightness and display dim/sleep settings.
- **START SERVER:** host the browser dashboard at `https://<Pager-IP>:8443`
  (`https://172.16.52.1:8443` over USB Ethernet). Port 8090 redirects to HTTPS.
  Accept the new Pager-specific self-signed certificate once.
- **STOP SERVER / SERVER STATUS / EXIT:** manage the dashboard; exiting asks
  whether to keep it running if it is active.

Use the dashboard only on a trusted management network. It can read, upload,
and—with confirmation—delete local captures, and is not an authenticated
multi-user service. Do not expose its ports to the public internet.

## Attribution and validation

Map data © OpenStreetMap contributors, ODbL; tiles served by OpenFreeMap.
See `THIRD-PARTY-NOTICES.md`, `licenses/`, `www/vendor/`, and the native font
license. Dependency origins, versions and download hashes are recorded in
`DEPENDENCIES.json`. `SHA256SUMS` inventories the release files.

This beta preserves the current map/trace rendering and UI. It is not a promise
of full offline coverage, a triangulated access-point location estimate, or
production reliability. See `VALIDATION-BETA.md` for this build's actual checks.

Device packaging guidance: https://documentation.hak5.org/wifi-pineapple-pager/payloads-1/advanced-payloads
