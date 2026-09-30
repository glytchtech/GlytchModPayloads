# NetRider beta validation

Release: 2.1.2-beta.1. Baseline: Pager firmware 1.1.2 (MIPSel, OpenWrt 24.10.1).

Local validation: 46 automated native/rendering and release-boundary tests pass.
Dashboard JavaScript and launcher shell syntax pass. The release builder checks
LVCC/empty-capture defaults, local browser assets, dependency presence and an
explicit allowlist excluding development data, keys and caches.

## Clean-device smoke test

Tested on a stock-runtime Pager running firmware 1.1.2, with neither system
Python nor system uhttpd installed. The payload was unpacked into a separate
test folder; no existing payload or firmware package was replaced.

- Bundled Python 3.11.16 starts and imports SSL, CSV, JSON, sockets, urllib,
  array, fcntl and threading. It uses its payload-local standard library and
  the firmware's OpenSSL 3.0.16.
- Native read-only preflight passes: firmware version, 480×222 RGB565
  framebuffer, GPIO buttons, UI handoff commands and assets.
- Bundled uhttpd serves the dashboard, local MapLibre and font files, capture
  catalogue and live CGI endpoints over a loopback-only HTTPS listener. HTTP
  redirects to HTTPS. A new local certificate is generated and its private key
  has mode 0600.
- An eight-second offline native-map session renders and exits normally;
  the guardian reports successful `UI_RELEASE`.
- Stock `WIGLE_START`, `WIGLE_LOGIN`, `WIGLE_UPLOAD`, `GPS_GET`, `UI_TAKEOVER`,
  `UI_RELEASE`, curl, OpenSSL and Bash are present. System Python/uhttpd remain
  absent after the tests. No WiGLE logging or upload was initiated.

## Browser smoke test

Headless Chromium, desktop 1440×900 and portrait 390×844: no uncaught script
errors; zero records/networks, NO CAPTURE, LVCC center (-115.1515, 36.1319),
zoom 11.3, locally loaded DM Mono/Space Grotesk, working log-selector opening
and palette selection, and portrait layout detection.

This deterministic browser test stubs the external basemap with an empty
style. It verifies the packaged app, not live tile-provider availability.
The only external map request in the test is the expected OpenFreeMap style;
no JavaScript/CSS/font CDN is required.

Not exercised in this release pass: real-world moving GPS collection,
third-party WiGLE login/upload, live reverse geocoding, large-log stress
testing, or firmware newer than 1.1.2. These features retain their existing
implementation; this is a packaging beta, not a new feature-validation cycle.
