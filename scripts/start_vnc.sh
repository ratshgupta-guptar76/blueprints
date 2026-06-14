#!/usr/bin/env bash
#
# Launch the IIC-OSIC-TOOLS analog environment (Xschem, ngspice, Magic,
# KLayout, Netgen + GF180 PDK) with this analog/ folder mounted as the
# working directory, GUIs served over VNC.
#
# Engine-agnostic: defaults to docker, set ENGINE=podman to use podman.
#   ./start_vnc.sh                       # start (docker)
#   ENGINE=podman ./start_vnc.sh
#   VNC_RESOLUTION=2560x1440 ./start_vnc.sh   # custom desktop resolution
#   SCALE=0.5 ./start_vnc.sh             # 2x bigger UI (halve the framebuffer)
#   ./start_vnc.sh stop                  # stop the container
#
set -euo pipefail

ENGINE="${ENGINE:-docker}"
IMAGE="${IMAGE:-hpretl/iic-osic-tools:chipathon26}"
NAME="${NAME:-iic-analog}"
VNC_PW="${VNC_PW:-abc123}"
# VNC desktop resolution (WIDTHxHEIGHT). Override with VNC_RESOLUTION=...
VNC_RESOLUTION="${VNC_RESOLUTION:-2560x1440}"
# Pixel scale factor: container framebuffer = VNC_RESOLUTION * SCALE. A smaller
# framebuffer makes everything appear larger. e.g. SCALE=0.5 turns 2560x1440
# into 1280x720 (2x bigger UI). Override with SCALE=...
SCALE="${SCALE:-1}"
# Reject zero or negative scale
if ! awk -v s="$SCALE" 'BEGIN { exit !(s > 0) }'; then
    echo "Error: SCALE must be greater than 0 (got '$SCALE')" >&2
    exit 1
fi
_base_w="${VNC_RESOLUTION%x*}"
_base_h="${VNC_RESOLUTION#*x}"
EFFECTIVE_RESOLUTION="$(awk -v w="$_base_w" -v h="$_base_h" -v s="$SCALE" \
    'BEGIN { printf "%dx%d", int(w * s + 0.5), int(h * s + 0.5) }')"
# The folder mounted to /foss/designs. Defaults to <repo root>/analog,
# located via git so it works wherever this script lives. Override with
# ANALOG_DIR=/path.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel 2>/dev/null || dirname "$SCRIPT_DIR")"
ANALOG_DIR="${ANALOG_DIR:-$REPO_ROOT/analog}"

if [ "${1:-start}" = "stop" ]; then
    "$ENGINE" stop "$NAME"
    exit 0
fi

# :Z relabels the bind mount for SELinux (needed on Fedora for docker & podman)
"$ENGINE" run -d --rm \
    --name "$NAME" \
    -p 80:80 -p 5901:5901 \
    -e VNC_PW="$VNC_PW" \
    -e VNC_RESOLUTION="$EFFECTIVE_RESOLUTION" \
    -v "$ANALOG_DIR:/foss/designs:Z" \
    "$IMAGE"

echo "Started '$NAME' via $ENGINE."
echo "  VNC (browser): http://localhost:80   (password: $VNC_PW)"
echo "  VNC (client) : vnc://localhost:5901"
echo "  Resolution   : $EFFECTIVE_RESOLUTION  (base $VNC_RESOLUTION x scale $SCALE)"
echo "  Workspace    : analog/ -> /foss/designs inside the container"
echo "Stop with: ./start_vnc.sh stop   (or: $ENGINE stop $NAME)"
