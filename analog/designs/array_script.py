#!/usr/bin/env python3
"""gen_tb.py — 8T_tb-format wrapper, cell inherited from 8T_03v3.spice."""

import argparse
import re

SCH = "/workspace/analog/tb/{name}.sch"
SYM = "/workspace/analog/designs/8T_03v3.sym"


def load_cell_subckt(path: str) -> tuple[str, str]:
    """Read the cell file; activate **.subckt/**.ends, strip .end and the
    user-architecture include block. Returns (cell_name, active_subckt_text)."""
    lines = open(path).read().splitlines()
    out, name, in_arch = [], None, False
    for ln in lines:
        s = ln.strip()
        if s.startswith("**** begin user architecture"):
            in_arch = True
            continue
        if s.startswith("**** end user architecture"):
            in_arch = False
            continue
        if in_arch:
            continue
        m = re.match(r"^\*\*\.subckt\s+(\S+)", ln)
        if m:
            name = m.group(1)
            out.append(ln.replace("**.subckt", ".subckt", 1))
            continue
        if s.startswith("**.ends"):
            out.append(ln.replace("**.ends", ".ends", 1))
            continue
        if s == ".end":
            continue
        if s.startswith("** sch_path:"):
            continue
        out.append(ln)
    return name or "8T_03v3", "\n".join(out).strip("\n")


def gen(rows: int, name: str, cell_name: str, cell_text: str) -> str:
    L = [f"** sch_path: {SCH.format(name=name)}"]
    if rows == 1:
        L.append(f"**.subckt {name} vdd vss wl q qb a rbl wbl wblb")
        for p in ("vdd", "vss", "wl"):
            L.append(f"*.ipin {p}")
        L += ["*.opin q", "*.opin qb", "*.ipin a", "*.opin rbl",
              "*.ipin wbl", "*.ipin wblb"]
        L.append(f"x1 vdd wbl wblb vss wl a qb q qb rbl q {cell_name}")
    else:
        L.append(f"**.subckt {name} vdd vss wbl wblb")
        L += ["*.ipin vdd", "*.ipin vss", "*.ipin wbl", "*.ipin wblb"]
        for i in range(rows - 1, -1, -1):
            L += [f"*.ipin wl_{i}", f"*.ipin a_{i}", f"*.opin rbl_{i}"]
        for i in range(rows - 1, -1, -1):
            L.append(f"x_{i} vdd wbl wblb vss wl_{i} a_{i} "
                     f"qb_{i} q_{i} qb_{i} rbl_{i} q_{i} {cell_name}")
    L += ["**.ends", "",
          "**** begin user architecture code", "",
          ".include /workspace/analog/designs/params_6T.spice",
          ".include /workspace/analog/designs/params_8T.spice", "",
          "**** end user architecture code",
          f"* expanding   symbol:  {SYM} # of pins=11",
          f"** sym_path: {SYM}",
          cell_text, "", ".end"]
    return "\n".join(L) + "\n"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--cell", required=True, help="path to 8T_03v3.spice")
    p.add_argument("--rows", type=int, default=1)
    p.add_argument("--name", type=str, default="8T_tb")
    a = p.parse_args()
    cell_name, cell_text = load_cell_subckt(a.cell)
    print(gen(a.rows, a.name, cell_name, cell_text), end="")


if __name__ == "__main__":
    main()