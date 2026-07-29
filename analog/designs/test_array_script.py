#!/usr/bin/env python3
"""
gen_col_tb.py — generate a col_64 compute testbench.

Loads a known weight pattern via .ic, then drives 3 activation phases
(all-high, all-low, alternating) and measures each per-cell rbl[i].

Weights held constant (WL off => storage isolated). Product[i] = weight[i] AND act[i].

Phase 1 (act=1): rbl[i] should track weight[i].
Phase 2 (act=0): rbl[i] should be product-0 for all i.
Phase 3 (act=~weight): product 0 everywhere (opposite-phase) -> no spurious 1s.

Usage: python3 gen_col_tb.py --rows 64 > col_64_tb.spice
"""

import argparse

PVT_INC = "/workspace/analog/designs/pvt.spice"
PH = 20        # ns per phase
VDD = "{VDD_CORNER}"


def weight(i: int) -> int:
    return i & 1                       # alternating


def act_phase1(i: int) -> int:
    return 1                           # all high


def act_phase2(i: int) -> int:
    return 0                           # all low


def act_phase3(i: int) -> int:
    return (i & 1) ^ 1                 # opposite phase to weight => product all 0


def gen_tb(rows: int) -> str:
    L = []
    L.append(f"* col_{rows} compute testbench — 3 activation phases vs known weights")
    L.append(f".include {PVT_INC}")
    L.append(f".include /workspace/analog/designs/col_{rows}.spice")
    L.append("")
    L.append(f"VVDD vdd 0 {VDD}")
    L.append("VVSS vss 0 0")
    L.append("VWBL  wbl  0 0")
    L.append("VWBLB wblb 0 0")
    L.append("")

    # WL all off (isolate storage during compute)
    L.append("* --- WL off (no access; storage held) ---")
    for i in range(rows):
        L.append(f"VWL{i} wl_{i} 0 0")
    L.append("")

    # weights via .ic
    L.append("* --- weights via .ic (alternating) ---")
    for i in range(rows):
        if weight(i):
            L.append(f".ic v(q_{i})={VDD} v(qb_{i})=0")
        else:
            L.append(f".ic v(q_{i})=0 v(qb_{i})={VDD}")
    L.append("")

    # activation PWL: phase1 [0,PH], phase2 [PH,2PH], phase3 [2PH,3PH]
    t1, t2, t3 = PH, 2 * PH, 3 * PH
    L.append("* --- activations: PWL through 3 phases ---")
    for i in range(rows):
        v1 = VDD if act_phase1(i) else "0"
        v2 = VDD if act_phase2(i) else "0"
        v3 = VDD if act_phase3(i) else "0"
        # step at each phase boundary (fast edges)
        L.append(
            f"VA{i} a_{i} 0 PWL("
            f"0 {v1}  {t1-1}n {v1}  {t1}n {v2}  {t2-1}n {v2}  {t2}n {v3}  {t3}n {v3})"
        )
    L.append("")

    # sim + measurements
    L.append(".control")
    L.append(f"  tran 0.01n {t3}n uic")
    L.append("")
    for ph, tend in ((1, t1), (2, t2), (3, t3)):
        L.append(f"  * --- phase {ph} rbl levels (measure near end of window) ---")
        for i in range(rows):
            L.append(f"  meas tran rbl{i}_p{ph} FIND v(rbl_{i}) AT={tend-1}n")
        L.append("")
    L.append(".endc")
    L.append(".end")
    return "\n".join(L) + "\n"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--rows", type=int, default=64)
    args = p.parse_args()
    print(gen_tb(args.rows), end="")


if __name__ == "__main__":
    main()