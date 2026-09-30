# NetRider native map (2.1.2 beta)

Choose **OPEN PAGER MAP** in the payload menu. Pager firmware 1.1.2 or later,
the existing framebuffer and GPIO buttons are required. The beta includes its
own Python runtime; no packages need installing. The web dashboard remains
available independently. Before a valid GPS fix or local capture is available,
the map defaults to the Las Vegas Convention Center (36.1319, -115.1515).

Green GlytchTech boot animation, native 480×222 map, battery/charging,
satellites used in fix, GPS fix, clock, live log age and observation count.
Unknown GPS telemetry is shown as `--`. Satellite counts come from gpsd SKY
reports; no serial GPS port is opened exclusively by this app. Battery data
comes from the kernel power-supply interface. WiGLE updates follow the newest
CSV and retain at most 4000 recent valid coordinates; a fresh GPS fix takes
priority for centering, then the newest logged coordinate. The trail is the
observation path, not an estimated location of each access point.

- A/Enter cycles **FOLLOW → PAN → ZOOM**. Returning to FOLLOW recenters.
- Double-tap A within 350 ms to start WiGLE logging with the native
  `WIGLE_START` command. A single tap waits briefly to distinguish the gesture.
  Double-tapping never changes map mode or restarts an already-active log.
- The lower bar reports **LOGGING: ACTIVE** only when the firmware's
  `logwigle` state confirms logging is enabled. `OFF`, `UNKNOWN`, and `ERROR`
  distinguish stopped logging, unavailable status, and a failed start.
  Active logging still needs GPS coordinates to produce plotted observations.
  Logging continues when you exit the map; stop it from the Pager's normal UI.
- D-pad pans in PAN; up/right zoom in and down/left zoom out in the other modes.
  Pan/zoom immediately reprojects the last completed map while a separate worker
  loads or generates static map tiles. Repeated moves are coalesced; road rendering no
  longer blocks button handling. Detail may take a moment to fill newly exposed
  areas, particularly at wide zoom levels or when tiles are not cached.
- Double-tap Power opens **DISPLAY // SETTINGS**. Up/Down selects Brightness,
  Dim after, or Sleep after; Left/Right changes the value. A or B closes it.
  Single Power is ignored while awake. B/Back exits from the map itself.
- Dim/sleep timers offer Off, 15 seconds, 30 seconds, 1/2/5/10/30 minutes.
  Both default to Off to preserve the previous always-on behavior. Timers are
  measured from the last button press; GPS, log arrivals, and map redraws do not
  reset them. Sleep takes precedence if its timeout is earlier than dimming.
  Dimming lowers brightness to at most 3/16. Sleep blanks the framebuffer and
  uses the stock Pager sleep backlight level (1/16); this is display sleep, not
  system suspend. WiGLE logging and the web server continue.
- Press any button to wake the screen. That wake gesture is consumed rather
  than navigating, exiting, or starting logging. Dim/sleep choices are saved
  automatically in `display-settings.json` at the payload root and apply only
  to NetRider. Brightness remains session-only. System-wide UCI preferences are
  not changed.
- Startup restores the system-configured full brightness rather than inheriting
  a dimmed backlight. Brightness changes are session-only; saved Pager settings
  are untouched. The recovery guardian restores the system-configured brightness
  before releasing the display, including after a renderer crash.
  While the map owns the display, the firmware's wake API suppresses its separate
  system-wide idle policy every five seconds; NetRider's guardian applies the
  selected local idle settings. This stops on exit; no saved system timeouts are changed and
  brightness is not repeatedly forced over firmware thermal protection.

Roads are real OpenStreetMap/OpenMapTiles vectors retrieved through OpenFreeMap on the Pager's
internet connection, using the same source as the web dashboard. The visible tile coordinates are sent to OpenFreeMap. Responses are
bounded and fetched in a background thread. The native map uses a shared Web
Mercator projection for roads, GPS and observations. Static roads/labels are
rendered once into 256×256 RGB565 tiles in `cache/raster/green-v1`, with a
512 MiB disk quota (4096 tiles) and 12 rendered tiles in RAM. Disk hits are used
even online and do not decode source geometry or contact a tile server. Cache
files are atomic, size-validated and versioned by style/projection; the oldest
access timestamps are pruned (access touches are limited to hourly).
The bottom-right readout shows `TILE CACHE: 100MB/512MB` (binary MiB, labeled
MB for compactness). It counts committed rendered tile files, not RAM, source
JSON, or logs, and updates after tile writes/pruning. Startup totals are read
by the cache worker, never by the input/render loop. Map-source credit is shown
on the startup splash and in these docs.

Up to four source vector tiles are decoded in RAM; a maximum of 96 JSON tiles
is retained in `cache/roads`. Existing source caches remain usable. First-time
rendering and uncached downloads still take time; visible tiles are prioritized
over other work, and obsolete tile renders are cancelled. Zoomed-out maps omit
tiny roads and simplify curves to screen resolution. The last completed frame
provides an immediate pan/zoom preview while missing detail loads.

Live observations, their trail, GPS and HUD are never saved into raster tiles.
New captures redraw only the live overlay, not roads. Without internet or a
cached region, observations/trail still work on black, with a `PARTIAL / TILES`
status. No offline miss is persisted as an empty map. `TILE CACHE` means all
visible static tiles are available. Map data © OpenStreetMap contributors,
ODbL. A native device view cannot use a phone's cellular connection unless
that connection is shared with the Pager. The existing browser view continues
to fetch its own map data. Tile detail follows zoom; uncached regions require
an internet connection before they can be used offline.

`UI_TAKEOVER`/`UI_RELEASE` are owned by an independent watchdog, with command
timeouts and release after partial failure. A missed renderer heartbeat kills
that exact process before releasing the UI. The native service and PineAP
remain running. NetRider respects PagerScribe's display lock; do not overlap
other custom framebuffer payloads. Logging starts only on the explicit double-A
gesture; no radio configuration or channel-hopping settings are changed.

Read-only check from the payload folder: `./runtime/python3 -B native/main.py --check`

Bounded display test: `./runtime/python3 -B native/main.py --duration 15 --offline`

Workstation build: `tools/build-native-assets.py` (Pillow required only for
building/reviewing assets). `output/native/map-demo.png` is synthetic review
data, never part of the device's live map.

Display/input helpers, bounded handoff adapter, bitmap renderer/fonts and
GlytchTech logo are reused from the user's PagerScribe project. Font license
is included under `assets/FONT-LICENSE.txt`.

Sources: https://downloads.hak5.org/pineapple/pager (1.1.2 commands), shipped
`/usr/bin/UI_TAKEOVER`, `/usr/bin/UI_RELEASE`, `/usr/bin/GPS_GET`,
https://gpsd.io/gpsd_json.html, https://openfreemap.org/quick_start/,
https://github.com/mapbox/vector-tile-spec/blob/master/2.1/README.md
