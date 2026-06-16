#!/usr/bin/env bash
# Launch hpretl/iic-osic-tools with this repo mounted at /workspace.
#
# Primary use case is interactive inspection of a pre-built GDS
# (KLayout, Magic, Netgen). The reference build path is Nix
# (`docs/reproducing-native.md`); see `docs/reproducing-docker.md` for
# why the container is not recommended for signoff-grade runs.
#
# Usage:
#   scripts/run_docker_iic.sh                         # interactive shell
#   scripts/run_docker_iic.sh klayout final/.../gds   # one-shot command
#
# GUI tools run over the container's built-in VNC server (noVNC) by default.
# This is the right choice on Wayland (Fedora/KDE): forwarding host X11 fails
# because there is no local X server, and Xwayland breaks Tk pointer grabs
# (Xschem right-click menus, KLayout). Open http://localhost:${IIC_VNC_PORT}
# after launch; default VNC password is abc123.
#
# Environment knobs:
#   IIC_IMAGE     - Docker image tag (default: hpretl/iic-osic-tools:latest)
#   IIC_MODE      - vnc (default) | x11    GUI transport
#   IIC_VNC_PORT  - host port for noVNC web UI (default: 80)
#   IIC_RFB_PORT  - host port for raw VNC/RFB, for KRDC etc. (default: 5901)
#   DISPLAY       - host X display (only used when IIC_MODE=x11)
#   EXTRA_VOLS    - extra --volume args to pass through

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE="${IIC_IMAGE:-hpretl/iic-osic-tools:latest}"
MODE="${IIC_MODE:-vnc}"
VNC_PORT="${IIC_VNC_PORT:-80}"
RFB_PORT="${IIC_RFB_PORT:-5901}"

if ! command -v docker >/dev/null 2>&1; then
    echo "docker not found in PATH" >&2
    exit 1
fi

# Build the display-transport args. In VNC mode we deliberately do NOT set
# DISPLAY or mount the X socket so the container's entrypoint starts its own
# Xvnc/noVNC stack instead of waiting on a (nonexistent) host X server. We
# also skip the --user override so the container can set up its VNC user and
# bind the web port; its default user is uid 1000, matching the host.
GUI_ARGS=()
USER_ARGS=(--user "$(id -u):$(id -g)")
case "${MODE}" in
    vnc)
        GUI_ARGS+=(-p "${VNC_PORT}:80" -p "${RFB_PORT}:5901")
        USER_ARGS=()
        echo "[run_docker_iic] VNC mode:" >&2
        echo "  browser (noVNC): http://localhost:${VNC_PORT}" >&2
        echo "  VNC viewer/KRDC: localhost:${RFB_PORT}  (password: abc123)" >&2
        ;;
    x11)
        if [[ -z "${DISPLAY:-}" ]]; then
            echo "IIC_MODE=x11 but DISPLAY is unset" >&2
            exit 1
        fi
        GUI_ARGS+=(-e "DISPLAY=${DISPLAY}")
        if [[ -S /tmp/.X11-unix ]]; then
            GUI_ARGS+=(-v /tmp/.X11-unix:/tmp/.X11-unix:rw)
        fi
        if [[ -n "${XAUTHORITY:-}" && -f "${XAUTHORITY}" ]]; then
            GUI_ARGS+=(-v "${XAUTHORITY}:/tmp/.Xauthority:ro" -e XAUTHORITY=/tmp/.Xauthority)
        fi
        ;;
    *)
        echo "Unknown IIC_MODE='${MODE}' (expected: vnc | x11)" >&2
        exit 1
        ;;
esac

EXTRA_VOL_ARGS=()
if [[ -n "${EXTRA_VOLS:-}" ]]; then
    # shellcheck disable=SC2086
    EXTRA_VOL_ARGS=(${EXTRA_VOLS})
fi

set -x
docker run --rm -it \
    --name chipathon-2026-iic \
    "${USER_ARGS[@]}" \
    -v "${REPO_ROOT}:/workspace" \
    -w /workspace \
    "${GUI_ARGS[@]}" \
    "${EXTRA_VOL_ARGS[@]}" \
    "${IMAGE}" \
    "$@"
