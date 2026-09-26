#!/bin/bash
# SPDX-License-Identifier: MIT
# Title: MeshCore
# Description: Install and operate the native MeshCore Pager companion.
# Author: Pager MeshCore contributors
# Version: 0.2.0-pager-27
# Category: Network
# Dependencies: WiFi Pineapple Pager firmware 1.1.2+; Glytch Mesh Mod for LoRa

set -u

RELEASE_VERSION=0.2.0-pager-27
if [ -n "${MESHCORE_PAYLOAD_DIR:-}" ]; then
    PAYLOAD_DIR=$MESHCORE_PAYLOAD_DIR
else
    PAYLOAD_DIR=$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
fi
ASSETS="$PAYLOAD_DIR/assets"
DAEMON=/usr/bin/meshcore-server
UI=/usr/bin/meshcore-ui
SERVICE=/etc/init.d/meshcore
CONFIG=/etc/config/meshcore
WRAPPER=/usr/lib/meshcore/meshcore-server-wrapper.sh
WATCHDOG=/usr/lib/meshcore/meshcore-watchdog.sh
FIRMWARE=/etc/pineapplepager/version
HAK5_BIN=/usr/bin
SYSTEM_BASH=/bin/bash
USB_DEVICES=/sys/bus/usb/devices

say() {
    if command -v LOG >/dev/null 2>&1; then LOG "[MeshCore] $*"
    else printf '[MeshCore] %s\n' "$*"; fi
}
fail() {
    say "ERROR: $*"
    if command -v ERROR_DIALOG >/dev/null 2>&1; then ERROR_DIALOG "$*" || true
    else printf '%s\n' "$*" >&2; fi
    return 1
}
confirmed() {
    local response
    response=$(CONFIRMATION_DIALOG "$1") || return 1
    [ "$response" = "${DUCKYSCRIPT_USER_CONFIRMED:-CONFIRMED}" ]
}

preflight() {
    local command version= major minor patch
    [ "$(id -u)" = 0 ] || { fail 'Run this payload from the Pager as root.'; return 1; }
    [ -x "$SYSTEM_BASH" ] || { fail 'The Pager Bash interpreter is missing.'; return 1; }
    for command in opkg uci curl pidof sha256sum LOG ALERT ERROR_DIALOG CONFIRMATION_DIALOG LIST_PICKER; do
        command -v "$command" >/dev/null 2>&1 || {
            fail "Required Pager command is missing: $command"
            return 1
        }
    done
    for command in UI_TAKEOVER UI_RELEASE RINGTONE VIBRATE; do
        [ -x "$HAK5_BIN/$command" ] || {
            fail "Required firmware command is missing: $command. Install Pager firmware 1.1.2 or newer."
            return 1
        }
    done
    [ -r "$FIRMWARE" ] || { fail 'Cannot identify Pager firmware.'; return 1; }
    IFS= read -r version < "$FIRMWARE" || true
    if [[ "$version" =~ ^([0-9]+)\.([0-9]+)\.([0-9]+)([-+].*)?$ ]]; then
        major=$((10#${BASH_REMATCH[1]}))
        minor=$((10#${BASH_REMATCH[2]}))
        patch=$((10#${BASH_REMATCH[3]}))
    else
        fail 'Unrecognized Pager firmware version.'
        return 1
    fi
    if (( major < 1 || (major == 1 && minor < 1) || (major == 1 && minor == 1 && patch < 2) )); then
        fail 'MeshCore requires Pager firmware 1.1.2 or newer.'
        return 1
    fi
    opkg print-architecture 2>/dev/null | grep -q '[[:space:]]mipsel_24kc[[:space:]]' || {
        fail 'This release supports only the Pager mipsel_24kc target.'
        return 1
    }
}

check_install_assets() {
    local file line count=0 seen_ipk=0 seen_version=0
    local pattern='^([0-9a-fA-F]{64})  (meshcore-server\.ipk|VERSION)$'
    for file in meshcore-server.ipk VERSION SHA256SUMS; do
        [ -f "$ASSETS/$file" ] && [ ! -L "$ASSETS/$file" ] || {
            fail "Missing installation asset: $file. Copy the complete MeshCore folder again."
            return 1
        }
    done
    [ "$(<"$ASSETS/VERSION")" = "$RELEASE_VERSION" ] || {
        fail 'The payload and bundled package versions do not match. Copy the complete release again.'
        return 1
    }
    while IFS= read -r line || [ -n "$line" ]; do
        [[ "$line" =~ $pattern ]] || {
            fail 'Invalid installation checksum manifest.'
            return 1
        }
        case "${BASH_REMATCH[2]}" in
            meshcore-server.ipk) seen_ipk=$((seen_ipk + 1)) ;;
            VERSION) seen_version=$((seen_version + 1)) ;;
        esac
        count=$((count + 1))
    done < "$ASSETS/SHA256SUMS"
    [ "$count:$seen_ipk:$seen_version" = 2:1:1 ] || {
        fail 'The checksum manifest must list the package and VERSION exactly once.'
        return 1
    }
    (cd "$ASSETS" && sha256sum -c SHA256SUMS) >/dev/null 2>&1 || {
        fail 'MeshCore asset verification failed. Copy the complete release again.'
        return 1
    }
}

installed() {
    [ -x "$DAEMON" ] && [ -x "$UI" ] && [ -x "$SERVICE" ] &&
        [ -x "$WRAPPER" ] && [ -x "$WATCHDOG" ] && [ -f "$CONFIG" ]
}
installed_version() {
    local info line version= status=
    info=$(opkg status meshcore-server 2>/dev/null) || return 0
    while IFS= read -r line; do
        case "$line" in
            'Version: '*) version=${line#Version: } ;;
            'Status: '*) status=${line#Status: } ;;
        esac
    done <<< "$info"
    case "$status" in *' installed') printf '%s\n' "$version" ;; esac
}
service_ready() { [ -x "$DAEMON" ] && "$DAEMON" --config "$CONFIG" --control contacts >/dev/null 2>&1; }
service_running() { [ -x "$SERVICE" ] && "$SERVICE" status >/dev/null 2>&1; }

install_server() {
    local force=${1:-0} was_running=0 attempts=0 result
    if pidof meshcore-ui >/dev/null 2>&1; then
        fail 'Exit the running MeshCore UI before installing or upgrading it.'
        return 1
    fi
    service_running && was_running=1
    service_ready && was_running=1
    if [ "$was_running" = 1 ]; then
        "$SERVICE" stop || { fail 'Could not stop MeshCore safely for the upgrade.'; return 1; }
        while service_running || service_ready; do
            [ "$attempts" -lt 10 ] || { fail 'MeshCore did not stop; no package was installed.'; return 1; }
            sleep 1
            attempts=$((attempts + 1))
        done
    fi
    say "Installing verified local package $RELEASE_VERSION; no download is needed."
    if [ "$force" = 1 ]; then
        opkg install --force-reinstall "$ASSETS/meshcore-server.ipk"
        result=$?
    else
        opkg install "$ASSETS/meshcore-server.ipk"
        result=$?
    fi
    if [ "$result" != 0 ] || ! installed || [ "$(installed_version)" != "$RELEASE_VERSION" ]; then
        if [ "$was_running" = 1 ] && installed; then "$SERVICE" start >/dev/null 2>&1 || true; fi
        fail 'MeshCore installation did not complete. Existing state was not removed. See the payload log for opkg output.'
        return 1
    fi
    if [ "$was_running" = 1 ]; then
        "$SERVICE" start || { fail 'MeshCore was upgraded, but its service could not be restarted.'; return 1; }
    fi
    ALERT "MeshCore $RELEASE_VERSION installed. Existing configuration and data were retained."
}

ensure_runtime() {
    local version force=0
    version=$(installed_version)
    if [ -n "$version" ] && opkg compare-versions "$version" '>' "$RELEASE_VERSION"; then
        installed || { fail 'A newer MeshCore package is incomplete. Repair it with its matching or newer release; this payload will not downgrade it.'; return 1; }
        say "Keeping newer installed MeshCore $version."
        return 0
    fi
    if installed && [ "$version" = "$RELEASE_VERSION" ]; then return 0; fi
    if installed && [ -n "$version" ]; then
        opkg compare-versions "$version" '<' "$RELEASE_VERSION" || {
            fail "Cannot compare installed MeshCore version $version."
            return 1
        }
        confirmed "Upgrade MeshCore $version to $RELEASE_VERSION? Existing data and settings will be kept." || return 0
    elif [ -n "$version" ]; then
        confirmed "MeshCore $version is incomplete. Repair it using this $RELEASE_VERSION package?" || return 2
        [ "$version" = "$RELEASE_VERSION" ] && force=1
    else
        confirmed "MeshCore is not installed. Install the bundled $RELEASE_VERSION package now?" || return 2
    fi
    install_server "$force"
}

select_region_profile() {
    local choice region frequency bandwidth spreading_factor coding_rate
    choice=$(LIST_PICKER 'Select Region' \
        'USA / Canada' 'EU / UK (868 MHz)' 'Australia (915 MHz)' \
        'New Zealand (917 MHz)' CANCEL 'USA / Canada') || return 2
    case "$choice" in
        'USA / Canada') region=US; frequency=910525000; bandwidth=62500; spreading_factor=7; coding_rate=5 ;;
        'EU / UK (868 MHz)') region=EU_868; frequency=869618000; bandwidth=62500; spreading_factor=8; coding_rate=8 ;;
        'Australia (915 MHz)') region=AU_915; frequency=916575000; bandwidth=62500; spreading_factor=7; coding_rate=8 ;;
        'New Zealand (917 MHz)') region=NZ_915; frequency=917375000; bandwidth=62500; spreading_factor=7; coding_rate=5 ;;
        *) return 2 ;;
    esac
    if ! uci set meshcore.main.region="$region" ||
       ! uci set meshcore.main.frequency="$frequency" ||
       ! uci set meshcore.main.bandwidth="$bandwidth" ||
       ! uci set meshcore.main.spreading_factor="$spreading_factor" ||
       ! uci set meshcore.main.coding_rate="$coding_rate" ||
       ! uci set meshcore.main.enabled=1 || ! uci commit meshcore; then
        # Remove only this action's pending fields. A failed commit must not
        # look configured/enabled on the next launch; unrelated UCI stays put.
        local field
        for field in region frequency bandwidth spreading_factor coding_rate enabled; do
            uci -q revert "meshcore.main.$field" >/dev/null 2>&1 || true
        done
        fail 'MeshCore could not save the selected regional radio profile.'
        return 1
    fi
    ALERT "MeshCore configured for $choice and enabled."
}

configure_service() {
    local region enabled fresh=0 result
    region=$(uci -q get meshcore.main.region 2>/dev/null || printf UNSET)
    enabled=$(uci -q get meshcore.main.enabled 2>/dev/null || printf 0)
    case "$region" in
        US|EU_868|EU_433|AU_915|NZ_915|NZ_865|AS_923|IN_865) ;;
        ''|UNSET)
            select_region_profile
            result=$?
            [ "$result" = 0 ] || return "$result"
            fresh=1
            ;;
        *) fail "Unsupported configured region '$region'. Correct the configuration before starting."; return 1 ;;
    esac
    if [ "$fresh" = 0 ] && [ "$enabled" != 1 ]; then
        confirmed "MeshCore is configured for $region but disabled. Enable it now?" || return 2
        if ! uci set meshcore.main.enabled=1 || ! uci commit meshcore; then
            uci -q revert meshcore.main.enabled >/dev/null 2>&1 || true
            fail 'Could not save MeshCore enablement.'
            return 1
        fi
    fi
    if [ "$fresh" = 1 ] && ! "$SERVICE" enabled >/dev/null 2>&1; then
        if confirmed 'Start MeshCore automatically on future Pager boots? It can use LoRa without opening this payload. Choose No for manual startup.'; then
            "$SERVICE" enable || { fail 'Could not enable automatic startup.'; return 1; }
        fi
    fi
    return 0
}

mesh_mod_present() {
    local path vid product
    for path in "$USB_DEVICES"/*; do
        [ -r "$path/idVendor" ] && [ -r "$path/idProduct" ] || continue
        vid=$(tr '[:upper:]' '[:lower:]' < "$path/idVendor")
        product=$(tr '[:upper:]' '[:lower:]' < "$path/idProduct")
        [ "$vid:$product" = 1a86:5512 ] && return 0
    done
    return 1
}
wait_for_service() {
    local attempts=0
    while [ "$attempts" -lt 12 ]; do
        service_ready && return 0
        sleep 1
        attempts=$((attempts + 1))
    done
    service_ready
}
start_server() {
    local attempts=0
    if pidof meshtasticd >/dev/null 2>&1; then
        fail 'meshtasticd is running and cannot share the Mesh Mod. Stop it before starting MeshCore.'
        return 1
    fi
    "$SERVICE" start || { fail 'MeshCore could not be started. Check the payload log.'; return 1; }
    if ! mesh_mod_present; then
        while ! service_running; do
            [ "$attempts" -lt 5 ] || { fail 'The MeshCore supervisor did not start. Check its configuration and payload log.'; return 1; }
            sleep 1
            attempts=$((attempts + 1))
        done
        say 'MeshCore is waiting for Mesh Mod USB 1a86:5512. The UI can be used offline.'
        return 0
    fi
    wait_for_service && return 0
    "$SERVICE" restart >/dev/null 2>&1 || true
    wait_for_service && return 0
    if ! mesh_mod_present && service_running; then
        say 'Mesh Mod was disconnected; MeshCore is waiting for reconnection.'
        return 0
    fi
    fail 'MeshCore did not become RF-ready. Check the Mesh Mod, radio settings, and payload log.'
}

main() {
    local result state_dir
    preflight || return 1
    check_install_assets || return 1
    ensure_runtime
    result=$?
    [ "$result" = 2 ] && return 0
    [ "$result" = 0 ] || return "$result"
    configure_service
    result=$?
    [ "$result" = 2 ] && return 0
    [ "$result" = 0 ] || return "$result"
    if ! service_ready; then
        if service_running && ! mesh_mod_present; then
            say 'MeshCore is waiting for the Mesh Mod; opening the offline UI.'
        elif confirmed 'MeshCore is not RF-ready. Start it now? Without a Mesh Mod it will wait for one.'; then
            start_server || return 1
        fi
    fi
    state_dir=$(uci -q get meshcore.main.state_directory 2>/dev/null || printf /root/.meshcore)
    [ -n "$state_dir" ] || state_dir=/root/.meshcore
    "$UI" --payload-dir "$PAYLOAD_DIR" --state-dir "$state_dir"
}

[ "${MESHCORE_PAYLOAD_LIB_ONLY:-0}" = 1 ] || main
