# Bundled third-party software

NetRider includes these dependencies unchanged except for selecting the
required runtime files. No Hak5 firmware binaries or private configuration
are redistributed. The runtime relies on libraries already shipped in Pager
firmware 1.1.2.

| Component | Version/source | License notice |
| --- | --- | --- |
| CPython and selected standard-library modules | OpenWrt 24.10.1 mipsel_24kc feed; exact version in DEPENDENCIES.json | licenses/PYTHON-LICENSE.txt (PSF/Python-2.0.1 and included third-party terms) |
| uhttpd | OpenWrt 24.10.1 mipsel_24kc feed; exact revision in DEPENDENCIES.json | licenses/UHTTPD-LICENSE.txt (ISC) |
| MapLibre GL JS | 5.14.0 | www/vendor/MAPLIBRE-LICENSE.txt (BSD-3-Clause and included dependencies) |
| DM Mono / Space Grotesk | Google Fonts | www/vendor/DM-MONO-OFL.txt and SPACE-GROTESK-OFL.txt (SIL OFL 1.1) |
| Native bitmap fonts | DejaVu / Bitstream Vera | native/assets/FONT-LICENSE.txt |

Upstream source: https://github.com/python/cpython,
https://github.com/openwrt/packages/tree/openwrt-24.10/lang/python,
https://github.com/openwrt/uhttpd,
https://github.com/maplibre/maplibre-gl-js,
https://github.com/google/fonts.

Map data © OpenStreetMap contributors (https://www.openstreetmap.org/copyright),
available under the Open Database License. OpenFreeMap provides the online
basemap (https://openfreemap.org/). No captured WiGLE records or offline map
dataset is included in this distribution.
