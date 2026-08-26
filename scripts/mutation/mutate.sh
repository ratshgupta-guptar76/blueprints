#!/usr/bin/env bash
# =============================================================================
# mutate.sh — mutation testing harness
#
# Deliberately breaks an RTL module one mutation at a time and confirms the
# cocotb suite CATCHES it. A mutation that survives is a hole: the tests pass
# whether or not the logic is correct, so they prove nothing about that class
# of bug. Mutation testing measures whether the CHECKS are adequate — it is
# orthogonal to stimulus coverage.
#
# NOTE: the result is inverted. A mutation is "caught" when `make func` FAILS.
#
# Usage:  ./scripts/mutation/mutate.sh <module>  # from the repo root
# Exit:   0 = every mutation caught;  1 = at least one survived
#
# Mutations live in scripts/mutation/tables/<module>.txt, one per line:
#     description|sed expression
# Blank lines and lines starting with # are ignored. The sed expression is
# passed to `sed -i` verbatim — no shell escaping needed, so SystemVerilog
# literals like 1'b1 and '0 can be written as-is.
#
# The original RTL is restored on exit, including on Ctrl-C or error.
# =============================================================================
set -uo pipefail

MODULE="${1:-}"
if [ -z "$MODULE" ]; then
    echo "Usage: $0 <module>"
    echo "Available:"
    for f in scripts/mutation/tables/*.txt; do
        [ -e "$f" ] || continue
        b="${f##*/}"; echo "  ${b%.txt}"
    done
    exit 2
fi

RTL="src/${MODULE}.sv"
TABLE="scripts/mutation/tables/${MODULE}.txt"

[ -f "$RTL" ]   || { echo "No such RTL file: $RTL"; exit 2; }
[ -f "$TABLE" ] || { echo "No mutation table: $TABLE"; exit 2; }

if command -v git >/dev/null && git rev-parse --git-dir >/dev/null 2>&1; then
    if ! git diff --quiet "$RTL" 2>/dev/null; then
        echo "ERROR: $RTL has uncommitted changes — a prior mutation may not have been restored."
        echo "Restore first:  git checkout $RTL"
        exit 2
    fi
fi

BACKUP="$(mktemp)"
cp "$RTL" "$BACKUP"
restore() { cp "$BACKUP" "$RTL"; rm -f "$BACKUP"; }
trap restore EXIT INT TERM

echo "=== mutation testing: $MODULE ==="
echo

survived=0
caught=0
skipped=0

while IFS='|' read -r desc expr; do
    # skip blanks and comments
    case "${desc## }" in ''|'#'*) continue ;; esac
    [ -n "${expr:-}" ] || { echo "  SKIP  $desc  (no sed expression)"; skipped=$((skipped+1)); continue; }

    cp "$BACKUP" "$RTL"
    if ! sed -i "$expr" "$RTL" 2>/dev/null; then
        echo "  SKIP  $desc  (sed expression rejected)"
        skipped=$((skipped+1)); continue
    fi

    # A sed that matches nothing silently reports "caught" for a mutation that
    # was never applied — the failure mode that makes mutation testing useless.
    if diff -q "$BACKUP" "$RTL" >/dev/null; then
        echo "  SKIP  $desc  (pattern did not match — mutation not applied)"
        skipped=$((skipped+1)); continue
    fi

    # Verilator will not recompile for a source change it considers current.
    rm -rf "cocotb/sim_build/${MODULE}"

    if make func="$MODULE" >/dev/null 2>&1; then
        echo "  SURVIVED  $desc"
        echo "            ^ tests passed on broken RTL — no check covers this"
        survived=$((survived+1))
    else
        echo "  caught    $desc"
        caught=$((caught+1))
    fi
done < "$TABLE"

echo
echo "caught: $caught   survived: $survived   skipped: $skipped"

if [ "$skipped" -gt 0 ]; then
    echo "WARNING: $skipped mutation(s) never applied — fix the patterns in $TABLE"
fi

if [ "$survived" -gt 0 ]; then
    echo "RESULT: FAIL — $survived mutation(s) escaped detection"
    exit 1
fi
echo "RESULT: PASS — every applied mutation was caught"

expected=$(grep -vc -e '^[[:space:]]*#' -e '^[[:space:]]*$' "$TABLE")
processed=$((caught + survived + skipped))
if [ "$processed" -ne "$expected" ]; then
    echo "ERROR: table has $expected mutations but $processed were processed"
    exit 1
fi