# NetRider 2.1.2-beta.2

Self-contained WiFi Pineapple Pager beta for Glytch Loader. Three files to upload:

```
GPS/NetRider/payload.sh
GPS/NetRider/netrider-bundle.tar.gz
GPS/NetRider/README.md
```

Extract the **outer ZIP** on your computer, then upload its `GPS` folder at the
root of GlytchModPayloads. If `GPS/NetRider` already exists, upload these three
files into that folder instead. **Do not extract netrider-bundle.tar.gz.** It
must stay beside the matching `payload.sh`. You do not need to upload the old
expanded `runtime`, `native`, or `www` folders. No Git LFS is needed.

The Loader installs this as `Payloads > User > General > NetRider`. On first
use, the launcher checks the archive's SHA-256, unpacks it with the Pager's
stock tools, and opens the normal menu. Later starts reuse the unpacked copy.
No package installation, runtime downloads, or system-library replacement.
Allow roughly 25 MB free for the archive plus unpacked app (additional space
is used by captured logs and the native map cache).

## Included

Native green map/display controls, browser dashboard, Python/uhttpd runtimes,
MapLibre, fonts, documentation and license notices. The default view is LVCC,
Las Vegas. No captures, personal locations, saved account data or keys are
included. Requires stock **Pager firmware 1.1.2 or later**; 1.1.2 is the tested
runtime baseline. A GPS receiver/fix is needed for live positioning.

**New map tiles and online lookups still need internet.** This bundle is a
self-contained software install, not an offline map pack. Browser maps use the
viewer's connection; native maps use the Pager's connection/cache. WiGLE login
and upload use the Pager's connection.

## Controls

- Open Pager Map: A cycles Follow/Pan/Zoom; D-pad navigates; B exits.
- Double A starts WiGLE logging. Double Power opens display settings.
- Start Server opens the dashboard at `https://<Pager-IP>:8443` (normally
  `https://172.16.52.1:8443` over USB). Accept the device-local certificate.
- Use only on a trusted management network; the dashboard is not an
  authenticated multi-user service. Do not expose its ports publicly.

Unpacked code lives under `.netrider/<bundle-hash>/`. Settings, certificates
and map cache live under `data/`, so a new code bundle does not replace them.
WiGLE logs remain in `/root/loot/wigle`, and account configuration stays under
the firmware's control. Older unpacked code versions are retained on updates;
they are safe to remove when NetRider is stopped. Do not upload `.netrider/`
or `data/` back into the repository.

The archive includes `BETA.md`, `VALIDATION-BETA.md`, `THIRD-PARTY-NOTICES.md`,
`DEPENDENCIES.json`, and a per-file `SHA256SUMS` inventory. Map data ©
OpenStreetMap contributors (ODbL); basemap served by OpenFreeMap.
