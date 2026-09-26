# MeshCore for WiFi Pineapple Pager

Release **0.2.0-pager-27**. One standalone payload with a native full-screen
interface, local messaging, contact/adverts management, and independent sound
and vibration settings for new adverts and messages.

## Requirements

- WiFi Pineapple Pager, firmware **1.1.2 or newer**, stock MIPS `mipsel_24kc`
  environment. Native UI and notification hardware were verified on 1.1.2;
  later firmware is not yet hardware-qualified.
- A compatible Glytch Mesh Mod (USB ID `1a86:5512`) with an appropriate antenna
  for LoRa communication. Without the mod the UI can still open offline.
- Root access for the initial package installation. The stock Pager tools are
  checked before installation; no Internet, package feed, compiler, Python,
  NetRider, or previously installed MeshCore server is required.

## Install

Copy this **entire `MeshCore` folder**, including `assets`, to:

```text
/root/payloads/user/general/MeshCore/
```

The result must contain `general/MeshCore/payload.sh`, not a `payload.sh`
directly under `user`. Alternatively, extract the release archive from
`/root/payloads/user`; it already contains the `general/MeshCore/` directory.

1. Open **Payloads → General → MeshCore** on the Pager.
2. Approve installation of the bundled, checksummed package.
3. Choose your region in the first-run picker. A valid selection applies its
   radio profile and sets `enabled=1`. Cancelling leaves a fresh install disabled
   with region `UNSET`; run the payload again to finish setup.
4. Choose whether MeshCore should start automatically at boot, then whether to
   start it now. Boot startup is optional, not silently enabled.
5. The native UI opens. With the mod missing, a started service waits for it;
   attach it and allow the watchdog to bring the radio online.

If the copy method loses executable permissions, run:

```sh
chmod +x /root/payloads/user/general/MeshCore/payload.sh
```

Select the correct region and antenna for your use. Both radios must use the
same compatible frequency, bandwidth, spreading factor, and coding rate to
communicate. Do not run another application that owns the Mesh Mod at the same
time. Pager boot/reboot can take several minutes.

## Use

Navigate with the directional buttons; **A** selects and **B** returns. The UI
includes its own message keyboard. The power button opens/closes Display
settings; any button wakes a sleeping screen without activating a menu item.
Dimming, brightness, and sleep timing are in **Settings → Display**.
Exiting the payload releases the display but does **not** stop a running server.
Use **Settings → Stop server** when you want it stopped.

- **Contacts**: choose a contact to write a message or send a preset.
- **New adverts**: accept or deny discovered identities. Denied adverts can be
  reviewed and cleared later.
- **Send advert**: announce this Pager's identity and display name.
- **Settings → Notifications → Adverts / Messages**: separate silent,
  sound-only, vibration-only, or combined modes, native ringtone/pattern
  selection, and a test action. The Pager's master volume still applies.

Notifications apply while the UI is open, asleep, or closed, provided the
server is running. Message notifications include the sender and message text.
GPS/location is not supported by this release.

Edit `messages.txt` in this folder to change canned replies: one message per
line, at most 160 UTF-8 bytes each. Blank lines and lines beginning with `#`
are ignored.

### Test two Pagers without infrastructure

Install on each Pager and select the same region/profile. Give them distinct
display names in Settings. On each Pager, send an advert and accept the other
Pager's advert under New adverts. Then send a direct message in each direction
and check the received text and acknowledgement. No repeater or Internet is
needed when the radios are within range. This two-way acceptance workflow
ensures both Pagers know the peer before the test.

### Connect a phone

Join the Pager's management AP, then use the MeshCore app's **TCP** connection
to the Pager's management address, normally **172.16.52.1, port 5000**. USB
networking can reach the same address when available. This is a raw MeshCore
companion connection, **not a web page**. If you changed the management subnet,
update `bind_address` in `/etc/config/meshcore` to that interface's address.
Keep the companion port on a trusted management network; it is not a
public-facing authenticated service.

## Updates, state, and integrity

The launcher offers to upgrade older installs or repair an incomplete install,
and will not downgrade an installed newer version. Upgrades preserve the UCI
configuration and per-device state; back them up before updating. Preserve your
custom `messages.txt` when copying a newer release folder.

- Configuration: `/etc/config/meshcore`
- Identity, contacts, messages, and UI preferences: `/root/.meshcore`
- Bundled installer: `assets/meshcore-server.ipk`

A fresh Pager generates its own identity when the daemon first starts. This
folder contains no paired contacts, device identities, demo messages, host
passwords, or saved device configuration. Deleting the payload folder does not
uninstall the package or delete its state.

`SHA256SUMS` covers the original release files. You can check it with
`sha256sum -c SHA256SUMS` from this folder (or `shasum -a 256 -c SHA256SUMS` on
macOS). Editing presets intentionally changes their release checksum. The
installer separately validates the immutable IPK and version against
`assets/SHA256SUMS`; these checks detect corruption, not publisher authenticity.
Redistribution notices are included in `assets/licenses/` and installed with
the runtime. No development documentation or source tree is needed on the Pager.
