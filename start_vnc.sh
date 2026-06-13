#!/usr/bin/env bash
#
# Launch the IIC-OSIC-TOOLS analog environment (Xschem, ngspice, Magic,
# KLayout, Netgen + GF180 PDK) with this analog/ folder mounted as the
# working directory, GUIs served over VNC.
#
# Engine-agnostic: defaults to docker, set ENGINE=podman to use podman.
#   ./start_vnc.sh            # start (docker)
#   ENGINE=podman ./start_vnc.sh
#   ./start_vnc.sh stop       # stop the container
#
set -euo pipefail

ENGINE="${ENGINE:-docker}"
IMAGE="${IMAGE:-hpretl/iic-osic-tools:chipathon26}"
NAME="${NAME:-iic-analog}"
VNC_PW="${VNC_PW:-abc123}"
# The folder mounted to /foss/designs. Defaults to ./analog next to this
# script (which lives at the repo root); override with ANALOG_DIR=/path.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ANALOG_DIR="${ANALOG_DIR:-$SCRIPT_DIR/analog}"

if [ "${1:-start}" = "stop" ]; then
    "$ENGINE" stop "$NAME"
    exit 0
fi

# :Z relabels the bind mount for SELinux (needed on Fedora for docker & podman)
"$ENGINE" run -d --rm \
    --name "$NAME" \
    -p 80:80 -p 5901:5901 \
    -e VNC_PW="$VNC_PW" \
    -v "$ANALOG_DIR:/foss/designs:Z" \
    "$IMAGE"

echo "Started '$NAME' via $ENGINE."
echo "  VNC (browser): http://localhost:80   (password: $VNC_PW)"
echo "  VNC (client) : vnc://localhost:5901"
echo "  Workspace    : analog/ -> /foss/designs inside the container"
echo "Stop with: ./start_vnc.sh stop   (or: $ENGINE stop $NAME)"
