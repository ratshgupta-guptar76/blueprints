#!/bin/bash
# mag/<cell>.mag -> gds -> +SRAMDEF marker -> mag/<cell>_sram.mag
#
# Diffusion under the marker reads back in as sramndiff/srampdiff/sramndc/
# srampdc, so Magic's interactive DRC applies the relaxed SRAM rules while
# editing the result.
set -e

CELL=$1
FORCE=0
for arg in "$@"; do
  [ "$arg" = "--force" ] && FORCE=1
done

if [ -z "$CELL" ] || [ "$CELL" = "--force" ]; then
  echo "usage: ./scripts/to_sram.sh <cellname> [--force]" >&2
  exit 1
fi

if [ -z "$PDK_ROOT" ] || [ -z "$PDK" ]; then
  echo "ERROR: PDK_ROOT and PDK must be set (e.g. PDK_ROOT=~/vlsi/blueprints/gf180mcu PDK=gf180mcuD)" >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
MAGICRC="$PDK_ROOT/$PDK/libs.tech/magic/$PDK.magicrc"

IN_MAG="$ROOT_DIR/mag/${CELL}.mag"
OUT_MAG="$ROOT_DIR/mag/${CELL}.mag"

if [ ! -f "$IN_MAG" ]; then
  echo "ERROR: $IN_MAG not found" >&2
  exit 1
fi

if [ -f "$OUT_MAG" ] && [ "$FORCE" -ne 1 ]; then
  echo "ERROR: $OUT_MAG already exists -- pass --force to overwrite" >&2
  exit 1
fi

mkdir -p "$ROOT_DIR/gds"

# 1. Magic: write GDS from the standard-type .mag
(
  cd "$ROOT_DIR/mag"
  magic -dnull -noconsole -rcfile "$MAGICRC" <<EOF
load $CELL
gds warning default
gds rescale no
gds unique yes
gds readonly yes
gds write ../gds/${CELL}.gds
quit -noprompt
EOF
)


if [ ! -s "$ROOT_DIR/gds/${CELL}.gds" ]; then
  echo "ERROR: gds/${CELL}.gds is empty or missing -- did '$CELL' load in Magic?" >&2
  exit 1
fi

# 2. Add the SRAMDEF marker (GDS 108/5)
klayout -b -r "$SCRIPT_DIR/add_sramdef.py" \
  -rd input_gds="$ROOT_DIR/gds/${CELL}.gds" \
  -rd output_gds="$ROOT_DIR/gds/${CELL}.gds"

if [ ! -s "$ROOT_DIR/gds/${CELL}.gds" ]; then
  echo "ERROR: gds/${CELL}.gds is empty or missing -- add_sramdef.py failed?" >&2
  exit 1
fi

# 3. Magic: read the marked GDS back in -- diffusion under SRAMDEF now reads
# in as sramndiff/srampdiff/sramndc/srampdc -- and save under the new name.
(
  cd "$ROOT_DIR/mag"
  magic -dnull -noconsole -rcfile "$MAGICRC" <<EOF
gds read ../gds/${CELL}.gds
save ${CELL}
quit -noprompt
EOF
)

if [ ! -s "$OUT_MAG" ]; then
  echo "ERROR: $OUT_MAG was not written" >&2
  exit 1
fi

echo "Wrote $OUT_MAG (sram-typed)"
