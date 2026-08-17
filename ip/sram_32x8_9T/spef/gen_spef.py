#!/usr/bin/env python3
"""Convert the Magic ext2spice extraction of sram_32x8_9T into a SPEF file.

Magic's extraction (../pex/run_ex.sh: extract + extresist + ext2spice
cthresh 0 extresist on) produced ../pex/sram_32x8_9T.spice. Inspection of
that netlist shows:
  - All *R* elements sit exclusively between VDD/VSS power-mesh nodes
    (no resistance was extracted along the RBL/WL/A/WBL/WBLB signal
    routes, so each signal pin is a single lumped node).
  - All *C* elements are pairwise coupling capacitances (cthresh 0 keeps
    every pair, not just grounded lumps): signal-to-signal (e.g.
    RBL[0]-RBL[1]), signal-to-internal-bitcell-node (e.g. A[0] to an
    anonymous "a_x_y#" node -- the real charge-domain MAC coupling this
    9T DCIM cell depends on), and signal/internal-to-VDD/VSS.

This script keeps every non-zero coupling cap that touches at least one
named signal pin (RBL/WL/A/WBL/WBLB) and doesn't touch VDD/VSS (power
nets are excluded -- IR drop is handled separately, not via STA SPEF),
and emits it as a SPEF coupling *CAP entry under the owning signal net's
*D_NET section. Every R element is power-mesh only, so no *RES section
is needed for any signal net (verified at runtime, not assumed).

Run from this directory: python3 gen_spef.py
"""
import re
import sys
from pathlib import Path
from collections import defaultdict

HERE = Path(__file__).resolve().parent
SPICE = HERE / "../pex/sram_32x8_9T.spice"
OUT = HERE / "sram_32x8_9T.spef"

POWER = {"VDD", "VSS"}


def parse_value_ff(tok):
    """Parse a magic ext2spice cap value (bare, 'f'-suffixed, or 'p'-suffixed) to femtofarads."""
    if tok.endswith("p"):
        return float(tok[:-1]) * 1000.0
    if tok.endswith("f"):
        return float(tok[:-1])
    return float(tok)


def main():
    text = SPICE.read_text()
    lines = text.splitlines()

    # --- 1. Parse the .subckt port list (continuation lines start with '+') ---
    ports = []
    in_subckt = False
    for line in lines:
        if line.startswith(".subckt"):
            in_subckt = True
            ports.extend(line.split()[2:])
            continue
        if in_subckt:
            if line.startswith("+"):
                ports.extend(line[1:].split())
                continue
            break

    signal_ports = [p for p in ports if p not in POWER]
    port_dir = {p: ("O" if p.startswith("RBL[") else "I") for p in signal_ports}

    print(f"Parsed {len(ports)} subckt ports ({len(signal_ports)} signal, "
          f"{len(ports) - len(signal_ports)} power)", file=sys.stderr)

    # --- 2. Parse C lines, keep non-zero, non-power, at-least-one-named-signal-pin ---
    is_named_signal = lambda n: n in port_dir
    kept = []  # (n1, n2, value_ff)
    c_re = re.compile(r"^C\d+\s+(\S+)\s+(\S+)\s+(\S+)")
    n_total = n_kept = 0
    for line in lines:
        m = c_re.match(line)
        if not m:
            continue
        n_total += 1
        n1, n2, valtok = m.groups()
        if n1 in POWER or n2 in POWER:
            continue
        if not (is_named_signal(n1) or is_named_signal(n2)):
            continue
        val = parse_value_ff(valtok)
        if val == 0.0:
            continue
        kept.append((n1, n2, val))
        n_kept += 1

    print(f"C lines: {n_total} total -> {n_kept} kept "
          f"(signal-touching, non-zero, non-power)", file=sys.stderr)

    # --- 3. Confirm no R element touches a signal pin (sanity check) ---
    r_re = re.compile(r"^R\d+\s+(\S+)\s+(\S+)\s+(\S+)")
    stray_r = 0
    for line in lines:
        m = r_re.match(line)
        if not m:
            continue
        n1, n2, _ = m.groups()
        if is_named_signal(n1) or is_named_signal(n2):
            stray_r += 1
    if stray_r:
        print(f"WARNING: {stray_r} R elements touch a signal pin -- "
              f"*RES sections are needed but this script doesn't emit them!",
              file=sys.stderr)
        sys.exit(1)
    print("Confirmed: no R elements touch signal pins (power-mesh only); "
          "no *RES sections required.", file=sys.stderr)

    # --- 4. Assign each cap entry to its owning net (first named side; if both
    #         named, owned by whichever comes first in port order, to avoid
    #         double-counting a coupling cap under both nets) ---
    port_index = {p: i for i, p in enumerate(signal_ports)}
    net_caps = defaultdict(list)  # net -> [(other_node, value)]
    for n1, n2, val in kept:
        n1_named = n1 in port_index
        n2_named = n2 in port_index
        if n1_named and n2_named:
            owner, other = (n1, n2) if port_index[n1] <= port_index[n2] else (n2, n1)
        elif n1_named:
            owner, other = n1, n2
        else:
            owner, other = n2, n1
        net_caps[owner].append((other, val))

    # --- 5. Build a compact NAME_MAP over every identifier referenced ---
    all_names = set(signal_ports)
    for entries in net_caps.values():
        for other, _ in entries:
            all_names.add(other)
    name_list = sorted(all_names)
    name_idx = {name: i + 1 for i, name in enumerate(name_list)}

    # --- 6. Emit SPEF ---
    out_lines = []
    a = out_lines.append
    a('*SPEF "IEEE 1481-1998"')
    a('*DESIGN "sram_32x8_9T"')
    a('*DATE "generated by gen_spef.py"')
    a('*VENDOR "Magic VLSI 8.3 (gf180mcuD ext2spice, cthresh 0, extresist on)"')
    a('*PROGRAM "gen_spef.py"')
    a('*VERSION "1.0"')
    a('*DESIGN_FLOW "NAME_SCOPE LOCAL" "PIN_CAP NONE" "NO_SLEW"')
    a('*DIVIDER /')
    a('*DELIMITER :')
    a('*BUS_DELIMITER [ ]')
    a('*T_UNIT 1 NS')
    a('*C_UNIT 1 FF')
    a('*R_UNIT 1 OHM')
    a('*L_UNIT 1 HENRY')
    a('')
    a('*NAME_MAP')
    for name in name_list:
        a(f'*{name_idx[name]} {name}')
    a('')
    a('*PORTS')
    for p in signal_ports:
        a(f'*{name_idx[p]} {port_dir[p]}')
    a('')

    cap_idx = 1
    for p in signal_ports:
        entries = net_caps.get(p, [])
        total = sum(v for _, v in entries)
        a(f'*D_NET *{name_idx[p]} {total:.6f}')
        a('*CONN')
        a(f'*P *{name_idx[p]} {port_dir[p]}')
        if entries:
            a('*CAP')
            for other, val in entries:
                a(f'{cap_idx} *{name_idx[p]} *{name_idx[other]} {val:.6f}')
                cap_idx += 1
        a('*END')
        a('')

    OUT.write_text("\n".join(out_lines) + "\n")
    print(f"Wrote {OUT} ({len(out_lines)} lines, {cap_idx - 1} *CAP entries, "
          f"{len(signal_ports)} nets, {len(name_list)} named nodes)", file=sys.stderr)


if __name__ == "__main__":
    main()
