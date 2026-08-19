#!/usr/bin/env python3
"""Generate sram_32x8_9T's Liberty timing model.

Pin capacitances and cell area are pulled from real extracted/layout data
(../spef/sram_32x8_9T.spef and ../lef/sram_32x8_9T.lef) rather than being
hand-picked placeholders.

RBL's cell_rise/cell_fall/rise_transition/fall_transition arcs come from
transient SPICE measurements of the A -> RBL propagation path (measured
in analog/sim/9t/read_delay_tt_025C_3v30.spice, tt/25C/3.3V corner) --
NOT from the SPEF, which only carries capacitance: Magic's extraction
found zero resistance along the signal routes (see spef/gen_spef.py's
docstring), so there was never any RC data to derive delay from.

Methodology / what this does and doesn't represent:
  - The sim uses the single already-extracted 9T bitcell netlist
    (analog/tb/9T_tb.spice's 9T_03v3 subckt, itself a real Magic
    extraction of one cell) driving a lumped CRBL equal to the real
    worst-case RBL net capacitance from the full 32x8 macro's SPEF
    (3.52894fF, the max over all 256 RBL[i] nets) -- not the full
    2304-device macro netlist. Since the macro's signal routing has no
    extracted resistance, RBL's load really is well-approximated as a
    single lumped cap, so this is a legitimate stand-in for "one bitcell
    driving the real worst-case load" -- but it is not a full-array
    transient simulation (that would additionally need the real
    multi-row read/write addressing protocol, which isn't reverse-
    engineered here).
  - The values are a single (no-load-table) characterization point, same
    structure the placeholder scalars used, just measured instead of
    guessed.
  - WL -> Q "write" propagation delay was also attempted
    (write_delay_tt_025C_3v30.spice) but the existing testbench (never
    actually run before this) holds A=VDD constant throughout, which
    destabilizes the stored bit via the read/compute path before the
    write pulse even arrives (Q drifts to a nonphysical ~0.45V midpoint
    by t=1ns, well before WL fires at t=5ns) -- this needs the real
    idle/read protocol (is A supposed to sit low between operations?)
    confirmed against the digital control logic before it can be
    trusted, so it's left out of this file. Q isn't an exposed macro pin
    anyway, so it wouldn't map to a Liberty arc even once fixed.
"""
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
CELL = "sram_32x8_9T"
OUT = HERE / f"{CELL}__tt_025C_3v30.lib"
SPEF = HERE / "../spef/sram_32x8_9T.spef"
LEF = HERE / "../lef/sram_32x8_9T.lef"

# From analog/sim/9t/read_delay_tt_025C_3v30.spice (ngspice tran, tt/25C/3.3V,
# CRBL = 3.52894fF real extracted worst-case RBL load):
#   t_read_rise (A rise -> RBL rise)        = 4.16063e-11 s
#   t_read_fall (A fall -> RBL fall)        = 4.67786e-11 s
#   trans_rbl_rise (RBL 20%-80%, rising)    = 9.95452e-11 s
#   trans_rbl_fall (RBL 80%-20%, falling)   = 8.05173e-11 s
CELL_RISE_NS = "0.0416063"
CELL_FALL_NS = "0.0467786"
RISE_TRANSITION_NS = "0.0995452"
FALL_TRANSITION_NS = "0.0805173"


def load_pin_caps_pf():
    """*D_NET *<idx> <total_fF> + *NAME_MAP *<idx> <name> -> {name: total_pF}."""
    text = SPEF.read_text()
    name_map_block = text.split('*NAME_MAP', 1)[1].split('*PORTS', 1)[0]
    idx_to_name = dict(re.findall(r'^\*(\d+) (\S+)$', name_map_block, re.M))
    idx_to_total_ff = dict(re.findall(r'^\*D_NET \*(\d+) (\S+)$', text, re.M))
    return {
        idx_to_name[idx]: float(total_ff) / 1000.0
        for idx, total_ff in idx_to_total_ff.items()
    }


def load_area_um2():
    """LEF SIZE <w> BY <h> ; -> w * h."""
    m = re.search(r'SIZE\s+([\d.]+)\s+BY\s+([\d.]+)\s*;', LEF.read_text())
    w, h = float(m.group(1)), float(m.group(2))
    return w * h


def bus_type(name, width):
    return (f'  type ({name}) {{\n'
            f'    base_type : array;\n'
            f'    data_type : bit;\n'
            f'    bit_width : {width};\n'
            f'    bit_from  : {width-1};\n'
            f'    bit_to    : 0;\n'
            f'    downto    : true;\n'
            f'  }}\n')


pin_cap_pf = load_pin_caps_pf()
area_um2 = load_area_um2()

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

    f.write(bus_type('BUS32', 32))
    f.write(bus_type('BUS8', 8))
    f.write(bus_type('BUS256', 256))
    f.write('\n')

    f.write(f'  cell ({CELL}) {{\n')
    f.write(f'    area : {area_um2:.4f}; /* {LEF.name} SIZE, um^2 */\n')
    f.write('    dont_use : TRUE;\n')
    f.write('    dont_touch : TRUE;\n')
    f.write('    interface_timing : TRUE;\n\n')

    f.write('    pg_pin (VDD) { voltage_name : VDD; pg_type : primary_power; }\n')
    f.write('    pg_pin (VSS) { voltage_name : VSS; pg_type : primary_ground; }\n\n')

    for name, btype, width in (('WL', 'BUS32', 32), ('A', 'BUS32', 32),
                                ('WBL', 'BUS8', 8), ('WBLB', 'BUS8', 8)):
        bit_caps = [pin_cap_pf[f'{name}[{k}]'] for k in range(width)]
        avg_cap = sum(bit_caps) / len(bit_caps)
        f.write(f'    bus ({name}) {{\n')
        f.write(f'      bus_type    : {btype};\n')
        f.write('      direction   : input;\n')
        f.write(f'      capacitance : {avg_cap:.6f}; /* mean of {width} extracted per-bit values */\n')
        f.write('      related_power_pin  : VDD;\n')
        f.write('      related_ground_pin : VSS;\n')
        for k in range(width):
            f.write(f'      pin ({name}[{k}]) {{ capacitance : {bit_caps[k]:.6f}; }}\n')
        f.write('    }\n')

    rbl_caps = [pin_cap_pf[f'RBL[{k}]'] for k in range(256)]
    f.write('\n    bus (RBL) {\n')
    f.write('      bus_type        : BUS256;\n')
    f.write('      direction       : output;\n')
    # No max_capacitance here: it's an output-pin *drive-capability* constraint
    # (how much load this pin is allowed to drive), not something a SPEF net
    # extraction can tell you -- the SPEF only reports the capacitance one
    # physical net happens to have. Setting it to the extracted value
    # (previously done here) made it smaller than a single min-size buffer's
    # input pin cap, so every downstream RBL net looked like an unfixable
    # max_capacitance violation and OpenROAD's repair_design looped forever
    # trying to buffer it away.
    f.write('      related_power_pin  : VDD;\n')
    f.write('      related_ground_pin : VSS;\n')
    for k in range(256):
        f.write(f'      pin (RBL[{k}]) {{\n')
        f.write(f'        capacitance : {rbl_caps[k]:.6f};\n')
        f.write('        timing () {\n')
        f.write(f'          related_pin  : "A[{k//8}]";\n')
        f.write('          timing_sense : positive_unate;\n')
        # Measured, not guessed -- see module docstring for methodology.
        f.write(f'          cell_rise (scalar) {{ values("{CELL_RISE_NS}"); }}\n')
        f.write(f'          cell_fall (scalar) {{ values("{CELL_FALL_NS}"); }}\n')
        f.write(f'          rise_transition (scalar) {{ values("{RISE_TRANSITION_NS}"); }}\n')
        f.write(f'          fall_transition (scalar) {{ values("{FALL_TRANSITION_NS}"); }}\n')
        f.write('        }\n      }\n')
    f.write('    }\n')

    f.write('  }\n}\n')

print(f"wrote {OUT}")
print(f"area: {area_um2:.4f} um^2 (from LEF)")
print(f"WL/A/WBL/WBLB/RBL per-bit capacitance: real (from SPEF)")
print(f"RBL cell_rise/cell_fall/rise_transition/fall_transition: real "
      f"(measured, tt_025C_3v30, see module docstring) = "
      f"{CELL_RISE_NS}/{CELL_FALL_NS}/{RISE_TRANSITION_NS}/{FALL_TRANSITION_NS} ns")
print("WL -> Q write delay: NOT included -- existing testbench needs a real "
      "protocol fix first, see module docstring")
