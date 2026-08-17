#!/usr/bin/env python3
"""Generate sram_bitcell_9T's Liberty timing model.

sram_32x8_9T.lib (gen_lib.py) characterizes the *macro's* top-level pins as
a flat black box, which is all a lib-only view can offer LibreLane. But
LibreLane's per-macro `nl` (netlist) + `spef` fields exist specifically to
enable *hierarchical* SPEF-based STA (see librelane/config/variable.py's
Macro.nl docstring) -- which needs a structural netlist made of instances
that themselves have known timing, i.e. Liberty models. sram_32x8_9T has no
internal standard cells (it's a full-custom 9T bitcell array), but it IS a
real tiled array of one physical cell (ip/sram_32x8_9T/mag/9T_tileable.mag,
instantiated 256 times per ../nl/gen_nl.py) -- so the correct granularity
for hierarchical STA is a per-bitcell Liberty model, not a per-macro one.

Conveniently, analog/sim/9t/read_delay_tt_025C_3v30.spice already measured
exactly this: it simulates ONE extracted bitcell (analog/tb/9T_tb.spice's
9T_03v3 subckt), so its A -> RBL numbers are already bitcell-granularity,
not macro-granularity -- gen_lib.py just applied them uniformly across the
macro's 256 output pins as an approximation. Here they're used directly,
unapproximated. Pin capacitances and area also come from real data: the
single cell's own intrinsic parasitic caps (9T_tb.spice's C0-C28) and the
real 9T_tileable.mag bounding box (3.110 x 5.480um, from Magic) -- distinct
from (smaller than) sram_32x8_9T.lib's per-column RBL SPEF caps, which
include coupling from the other 31 cells sharing that bitline.

WL -> Q write timing is not modeled here for the same reason gen_lib.py
excludes it: the existing write_delay testbench has an unresolved protocol
bug (see gen_lib.py's docstring). Q/QB aren't used at the array level
either way (see ../nl/gen_nl.py -- they're left unconnected per instance).
"""
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
CELL = "sram_bitcell_9T"
OUT = HERE / f"{CELL}__tt_025C_3v30.lib"
BITCELL_SPICE = HERE / "../../../analog/tb/9T_tb.spice"

# Real Magic bounding box of ip/sram_32x8_9T/mag/9T_tileable.mag: 3.110 x 5.480um
AREA_UM2 = 3.110 * 5.480

# Same measured values as gen_lib.py -- see that file's docstring for the
# read_delay_tt_025C_3v30.spice methodology. Reused here at their native
# (bitcell) granularity instead of being applied macro-wide.
CELL_RISE_NS = "0.0416063"
CELL_FALL_NS = "0.0467786"
RISE_TRANSITION_NS = "0.0995452"
FALL_TRANSITION_NS = "0.0805173"


def load_bitcell_pin_caps_pf():
    """Sum every C-line touching each pin of 9T_tb.spice's 9T_03v3 subckt."""
    text = BITCELL_SPICE.read_text()
    totals_ff = {}
    for line in text.splitlines():
        if not line.startswith("C"):
            continue
        _, n1, n2, valtok = line.split()
        val = float(valtok[:-1]) if valtok.endswith("f") else float(valtok)
        totals_ff[n1] = totals_ff.get(n1, 0.0) + val
        totals_ff[n2] = totals_ff.get(n2, 0.0) + val
    return {pin: totals_ff[pin] / 1000.0 for pin in ("A", "WL", "WBL", "WBLB", "RBL")}


pin_cap_pf = load_bitcell_pin_caps_pf()

with open(OUT, "w") as f:
    f.write(f'library ({CELL}) {{\n')
    f.write('  technology (cmos);\n')
    f.write('  delay_model : table_lookup;\n')
    f.write('  time_unit : "1ns";\n')
    f.write('  voltage_unit : "1V";\n')
    f.write('  current_unit : "1mA";\n')
    f.write('  pulling_resistance_unit : "1kohm";\n')
    f.write('  leakage_power_unit : "1nW";\n')
    f.write('  capacitive_load_unit (1, pf);\n')
    f.write('  input_threshold_pct_rise : 50.0;\n')
    f.write('  input_threshold_pct_fall : 50.0;\n')
    f.write('  output_threshold_pct_rise : 50.0;\n')
    f.write('  output_threshold_pct_fall : 50.0;\n')
    f.write('  slew_lower_threshold_pct_rise : 20.0;\n')
    f.write('  slew_upper_threshold_pct_rise : 80.0;\n')
    f.write('  slew_lower_threshold_pct_fall : 20.0;\n')
    f.write('  slew_upper_threshold_pct_fall : 80.0;\n')
    f.write('  slew_derate_from_library : 1.0;\n')
    f.write('  nom_process : 1.0;\n')
    f.write('  nom_temperature : 25.0;\n')
    f.write('  nom_voltage : 3.3;\n')
    f.write('  default_max_transition : 1.5;\n')
    f.write('  operating_conditions (tt_025C_3v30) {\n')
    f.write('    process : 1.0;\n    temperature : 25.0;\n    voltage : 3.3;\n  }\n')
    f.write('  default_operating_conditions : tt_025C_3v30;\n\n')

    f.write(f'  cell ({CELL}) {{\n')
    f.write(f'    area : {AREA_UM2:.4f}; /* 9T_tileable.mag bbox, um^2 */\n')
    f.write('    dont_use : TRUE;\n')
    f.write('    dont_touch : TRUE;\n')
    f.write('    interface_timing : TRUE;\n\n')

    f.write('    pg_pin (VDD) { voltage_name : VDD; pg_type : primary_power; }\n')
    f.write('    pg_pin (VSS) { voltage_name : VSS; pg_type : primary_ground; }\n\n')

    for pin in ("A", "WL", "WBL", "WBLB"):
        f.write(f'    pin ({pin}) {{\n')
        f.write('      direction   : input;\n')
        f.write(f'      capacitance : {pin_cap_pf[pin]:.6f}; /* real, from 9T_tb.spice extraction */\n')
        f.write('      related_power_pin  : VDD;\n')
        f.write('      related_ground_pin : VSS;\n')
        f.write('    }\n')

    f.write('    pin (RBL) {\n')
    f.write('      direction   : output;\n')
    f.write(f'      capacitance : {pin_cap_pf["RBL"]:.6f}; /* real, from 9T_tb.spice extraction */\n')
    f.write('      related_power_pin  : VDD;\n')
    f.write('      related_ground_pin : VSS;\n')
    f.write('      timing () {\n')
    f.write('        related_pin  : "A";\n')
    f.write('        timing_sense : positive_unate;\n')
    f.write(f'        cell_rise (scalar) {{ values("{CELL_RISE_NS}"); }}\n')
    f.write(f'        cell_fall (scalar) {{ values("{CELL_FALL_NS}"); }}\n')
    f.write(f'        rise_transition (scalar) {{ values("{RISE_TRANSITION_NS}"); }}\n')
    f.write(f'        fall_transition (scalar) {{ values("{FALL_TRANSITION_NS}"); }}\n')
    f.write('      }\n    }\n')

    f.write('  }\n}\n')

print(f"wrote {OUT}")
print(f"area: {AREA_UM2:.4f} um^2 (real, from Magic bbox of 9T_tileable.mag)")
print(f"pin capacitance: real (from 9T_tb.spice single-cell extraction): {pin_cap_pf}")
print(f"RBL timing: real (measured, same read_delay_tt_025C_3v30.spice run as gen_lib.py)")
