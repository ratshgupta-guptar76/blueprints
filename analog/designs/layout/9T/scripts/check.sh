#!/bin/bash
# Magic -> GDS -> KLayout (add SRAMDEF marker) -> KLayout DRC (gf180mcu.drc, DRM section 11 included)
set -e

CELL=$1
if [ -z "$CELL" ]; then
  echo "usage: ./scripts/check.sh <cellname>" >&2
  exit 1
fi

if [ -z "$PDK_ROOT" ] || [ -z "$PDK" ]; then
  echo "ERROR: PDK_ROOT and PDK must be set (e.g. PDK_ROOT=~/vlsi/blueprints/gf180mcu PDK=gf180mcuD)" >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
DRC_DECK="$PDK_ROOT/$PDK/libs.tech/klayout/tech/drc/gf180mcu.drc"

mkdir -p "$ROOT_DIR/gds" "$ROOT_DIR/drc"

# 1. Magic: write GDS from .mag
(
  cd "$ROOT_DIR/mag"
  magic -dnull -noconsole -rcfile "$PDK_ROOT/$PDK/libs.tech/magic/$PDK.magicrc" <<EOF
load $CELL
gds write ../gds/${CELL}.gds
quit -noprompt
EOF
)

# A cell that fails to load still writes a (near-)empty GDS, which then
# passes DRC trivially -- that's the failure mode to catch here, loudly.
if [ ! -s "$ROOT_DIR/gds/${CELL}.gds" ]; then
  echo "ERROR: gds/${CELL}.gds is empty or missing -- did '$CELL' load in Magic?" >&2
  exit 1
fi

# 2. Add SRAMDEF marker (GDS 108/5) so DRM section 11 (SRAM) rules activate
klayout -b -r "$SCRIPT_DIR/add_sramdef.py" \
  -rd input_gds="$ROOT_DIR/gds/${CELL}.gds" \
  -rd output_gds="$ROOT_DIR/gds/${CELL}_marked.gds"

if [ ! -s "$ROOT_DIR/gds/${CELL}_marked.gds" ]; then
  echo "ERROR: gds/${CELL}_marked.gds is empty or missing -- add_sramdef.py failed?" >&2
  exit 1
fi

# 3. KLayout DRC on the marked GDS
# Verified against $PDK_ROOT/$PDK/libs.tech/klayout/tech/drc/gf180mcu.drc header:
# -rd names are input, report, feol, beol, conn_drc (topcell/thr/etc. are optional).
klayout -b -r "$DRC_DECK" \
  -rd input="$ROOT_DIR/gds/${CELL}_marked.gds" \
  -rd report="$ROOT_DIR/drc/${CELL}.lyrdb" \
  -rd feol=true -rd beol=true -rd conn_drc=true

# 4. Count violations, grouped by rule name
REPORT="$ROOT_DIR/drc/${CELL}.lyrdb"
TOTAL=$(grep -c "<item>" "$REPORT" || true)

echo "-----------------------------"
echo "DRC items: $TOTAL"
if [ "$TOTAL" -gt 0 ]; then
  grep -oP "<category>'\K[^']+" "$REPORT" | sort | uniq -c | sort -rn
fi
echo "Report: $REPORT"
