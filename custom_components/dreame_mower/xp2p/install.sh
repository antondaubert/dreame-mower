#!/usr/bin/env bash
#
# Installs the live video helper for the Dreame Mower integration.
#
# It can be run straight from the repository, with no checkout:
#
#   curl -fsSL https://raw.githubusercontent.com/antondaubert/dreame-mower/main/custom_components/dreame_mower/xp2p/install.sh | bash
#
# With no arguments it finds the Home Assistant containers on this machine
# that have the integration installed and offers to install into them:
#
#   ./install.sh
#
# Pass a configuration directory to skip discovery:
#
#   ./install.sh /path/to/homeassistant/config
#
# The build runs in a throwaway Ubuntu 24.04 container, so no compiler or
# library is installed on the host. See README.md for what gets downloaded.
#
# Set DREAME_XP2P_PLATFORM to build for an architecture other than this
# host's, which is only useful on a development machine whose Home Assistant
# container is emulated:
#
#   DREAME_XP2P_PLATFORM=linux/amd64 ./install.sh
#
# SPDX-License-Identifier: MIT
set -euo pipefail

# Piped through curl there is no script file, so fall back to the working
# directory; the sources are then taken from the installed integration.
SELF="${BASH_SOURCE[0]:-$0}"
SRC_DIR="$(cd "$(dirname "$SELF")" 2>/dev/null && pwd || pwd)"
ISSUES_URL="https://github.com/antondaubert/dreame-mower/issues"
CONFIG_DIR="${1:-}"

echo "Dreame Mower live video helper"
echo "Live video currently runs on x86_64 Linux hosts only."
echo

# --- architecture -----------------------------------------------------------

PLATFORM_ARGS=()
if [ -n "${DREAME_XP2P_PLATFORM:-}" ]; then
  PLATFORM_ARGS=(--platform "$DREAME_XP2P_PLATFORM")
  echo "Building for ${DREAME_XP2P_PLATFORM} rather than this host's architecture."
  echo "The result only runs where that architecture does."
  echo
fi

ARCH="$(uname -m)"
if [ -z "${DREAME_XP2P_PLATFORM:-}" ] && [ "$ARCH" != "x86_64" ] && [ "$ARCH" != "amd64" ]; then
  cat >&2 <<MSG
This host is ${ARCH}, and live video is only available on x86_64.

The camera transport relies on a vendor-supplied library that is published
for x86_64 Linux only. There is no build for arm64, so Raspberry Pi,
Home Assistant Green and Home Assistant Yellow cannot run it. The rest of
the integration is unaffected.

On a development machine whose Home Assistant container runs an emulated
x86_64, set DREAME_XP2P_PLATFORM=linux/amd64 to build anyway.
MSG
  exit 70
fi

# --- docker -----------------------------------------------------------------

if ! command -v docker >/dev/null 2>&1; then
  cat >&2 <<MSG
Docker was not found on this host, and the helper is built inside a container.

If your Home Assistant runs some other way, we would like to support it.
Please open an issue describing your setup — how Home Assistant is installed,
and the output of "uname -m" — at:

  ${ISSUES_URL}

Note that live video needs an x86_64 host in any case.
MSG
  exit 69
fi

# --- pick targets -----------------------------------------------------------

# Each target is "<container>|<label>", or "|<host path>" when a directory was
# given explicitly. Installing through the container covers bind mounts and
# named volumes alike.
TARGETS=()

if [ -n "$CONFIG_DIR" ]; then
  if [ ! -d "$CONFIG_DIR" ]; then
    echo "error: $CONFIG_DIR is not a directory." >&2
    exit 66
  fi
  TARGETS=("|${CONFIG_DIR%/}")
else
  echo "Looking for Home Assistant containers with the integration installed..."
  CANDIDATES=()
  while IFS= read -r container; do
    [ -n "$container" ] || continue
    if docker exec "$container" test -d /config/custom_components/dreame_mower >/dev/null 2>&1; then
      CANDIDATES+=("$container")
    fi
  done < <(docker ps --format '{{.Names}}')

  case "${#CANDIDATES[@]}" in
    0)
      cat >&2 <<MSG

No running Home Assistant container has the Dreame Mower integration
installed.

If Home Assistant is running elsewhere, pass its configuration directory:

  $0 /path/to/homeassistant/config

If it is running in Docker and should have been found, please open an issue
with the output of "docker ps" at:

  ${ISSUES_URL}
MSG
      exit 66
      ;;
    1)
      echo "Found: ${CANDIDATES[0]}"
      TARGETS=("${CANDIDATES[0]}|${CANDIDATES[0]}")
      ;;
    *)
      echo "Found several:"
      for i in "${!CANDIDATES[@]}"; do
        echo "  $((i + 1))) ${CANDIDATES[$i]}"
      done
      echo "  a) all of them"
      echo
      # stdin may be the pipe when this is run through curl, so ask the
      # terminal directly.
      if [ -e /dev/tty ] && { : >/dev/tty; } 2>/dev/null; then
        printf 'Install into which? [1-%s/a] ' "${#CANDIDATES[@]}" >/dev/tty
        read -r choice </dev/tty
      else
        echo "error: several instances found and no terminal to ask." >&2
        echo "       Re-run with a configuration directory to choose one." >&2
        exit 65
      fi
      if [ "$choice" = "a" ] || [ "$choice" = "A" ]; then
        for container in "${CANDIDATES[@]}"; do
          TARGETS+=("${container}|${container}")
        done
      elif [[ "$choice" =~ ^[0-9]+$ ]] && [ "$choice" -ge 1 ] \
        && [ "$choice" -le "${#CANDIDATES[@]}" ]; then
        container="${CANDIDATES[$((choice - 1))]}"
        TARGETS=("${container}|${container}")
      else
        echo "error: '$choice' is not one of the options." >&2
        exit 65
      fi
      ;;
  esac
fi

# --- resolve the sources ----------------------------------------------------

# Run from a checkout the sources sit next to this script. Run through curl
# they do not, so take them from the integration we are installing into, which
# also guarantees the helper matches the version in use.
BUILD_DIR="$(mktemp -d)"
SOURCE_DIR="$SRC_DIR"
trap 'rm -rf "$BUILD_DIR" "${FETCHED_DIR:-}"' EXIT

if [ ! -f "${SRC_DIR}/runner.c" ] || [ ! -f "${SRC_DIR}/build.sh" ]; then
  FETCHED_DIR="$(mktemp -d)"
  SOURCE_DIR="$FETCHED_DIR"
  first_container="${TARGETS[0]%%|*}"
  first_label="${TARGETS[0]#*|}"
  installed="custom_components/dreame_mower/xp2p"
  echo "Taking the helper sources from the installed integration..."
  if [ -n "$first_container" ]; then
    for file in runner.c build.sh; do
      docker cp "${first_container}:/config/${installed}/${file}" \
        "${FETCHED_DIR}/${file}" >/dev/null 2>&1 || {
          echo "error: ${file} is missing from ${first_label}." >&2
          echo "       Update the integration and try again." >&2
          exit 66
        }
    done
  else
    for file in runner.c build.sh; do
      cp "${first_label}/${installed}/${file}" "${FETCHED_DIR}/${file}" 2>/dev/null || {
        echo "error: ${first_label}/${installed}/${file} is missing." >&2
        echo "       Update the integration and try again." >&2
        exit 66
      }
    done
  fi
fi

# --- build once -------------------------------------------------------------

echo
docker run --rm "${PLATFORM_ARGS[@]}" \
  -v "${SOURCE_DIR}:/src:ro" \
  -v "${BUILD_DIR}:/out" \
  ubuntu:24.04 \
  bash /src/build.sh

# --- install into each target ----------------------------------------------

echo
for target in "${TARGETS[@]}"; do
  container="${target%%|*}"
  label="${target#*|}"
  if [ -n "$container" ]; then
    docker exec "$container" rm -rf /config/dreame_mower/xp2p
    docker exec "$container" mkdir -p /config/dreame_mower/xp2p
    docker cp "${BUILD_DIR}/." "${container}:/config/dreame_mower/xp2p"
    echo "Installed into ${label} at /config/dreame_mower/xp2p"
  else
    rm -rf "${label}/dreame_mower/xp2p"
    mkdir -p "${label}/dreame_mower/xp2p"
    cp -R "${BUILD_DIR}/." "${label}/dreame_mower/xp2p/"
    echo "Installed into ${label}/dreame_mower/xp2p"
  fi
done

cat <<MSG

Reload the integration to pick it up: Settings -> Devices & services ->
Dreame Mower -> the three-dot menu -> Reload. The camera then appears on
mowers that support it.
MSG
