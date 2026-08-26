#!/usr/bin/env python3
"""Generate sram_32x8_9T's Liberty timing model, for all 3 signoff corners.

Pin capacitances and cell area are pulled from real extracted/layout data
(../spef/sram_32x8_9T.spef and ../lef/sram_32x8_9T.lef) rather than being
hand-picked placeholders. Both are geometric extraction results, so they
are corner-independent and reused as-is for tt/ff/ss.

RBL's cell_rise/cell_fall/rise_transition/fall_transition arcs come from
transient SPICE measurements of the A -> RBL propagation path (measured
in analog/characterization/9t/read_delay_<corner>.spice, one run per corner) -- NOT
from the SPEF, which only carries capacitance: Magic's extraction found
zero resistance along the signal routes (see spef/gen_spef.py's
docstring), so there was never any RC data to derive delay from.

Methodology / what this does and doesn't represent:
  - The sim uses the single already-extracted 9T bitcell netlist
    (analog/testbench/9T_tb.spice's 9T_03v3 subckt, itself a real Magic
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
  - The values are a single (no-load-table) characterization point per
    corner, same structure the placeholder scalars used, just measured
    instead of guessed.
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

Run from this directory: python3 gen_lib.py
"""
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
CELL = "sram_32x8_9T"
SPEF = HERE / "../spef/sram_32x8_9T.spef"
LEF = HERE / "../lef/sram_32x8_9T.lef"

# Temperature/voltage taken from each corner's own operating_conditions
# block in gf180mcu_as_sc_mcu7t3v3__<corner>.lib, not guessed. cell_rise/
# cell_fall/rise_transition/fall_transition are ngspice `meas tran`
# results (t_read_rise/t_read_fall/trans_rbl_rise/trans_rbl_fall) from
# analog/characterization/9t/read_delay_<corner>.spice, converted s -> ns.
CORNERS = {
    "tt_025C_3v30": dict(
        temperature=25.0, voltage=3.3,
        cell_rise="0.0416063", cell_fall="0.0467786",
        rise_transition="0.0995452", fall_transition="0.0805173",
    ),
    "ff_n40C_3v60": dict(
        temperature=-40.0, voltage=3.6,
        cell_rise="0.0279951", cell_fall="0.0322755",
        rise_transition="0.0799470", fall_transition="0.0663005",
    ),
    "ss_125C_3v00": dict(
        temperature=125.0, voltage=3.0,
        cell_rise="0.0633163", cell_fall="0.0698808",
        rise_transition="0.137845", fall_transition="0.113007",
    ),
}


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


def write_corner_lib(corner, params, pin_cap_pf, area_um2):
    out = HERE / f"{CELL}__{corner}.lib"
    temperature = params["temperature"]
    voltage = params["voltage"]
    cell_rise_ns = params["cell_rise"]
    cell_fall_ns = params["cell_fall"]
    rise_transition_ns = params["rise_transition"]
    fall_transition_ns = params["fall_transition"]

    with open(out, "w") as f:
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
        f.write(f'  nom_temperature : {temperature};\n')
        f.write(f'  nom_voltage : {voltage};\n')
        f.write('  default_max_transition : 1.5;\n')
        f.write(f'  operating_conditions ({corner}) {{\n')
        f.write(f'    process : 1.0;\n    temperature : {temperature};\n    voltage : {voltage};\n  }}\n')
        f.write(f'  default_operating_conditions : {corner};\n\n')

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
            f.write(f'          cell_rise (scalar) {{ values("{cell_rise_ns}"); }}\n')
            f.write(f'          cell_fall (scalar) {{ values("{cell_fall_ns}"); }}\n')
            f.write(f'          rise_transition (scalar) {{ values("{rise_transition_ns}"); }}\n')
            f.write(f'          fall_transition (scalar) {{ values("{fall_transition_ns}"); }}\n')
            f.write('        }\n      }\n')
        f.write('    }\n')

        f.write('  }\n}\n')

    print(f"wrote {out}")
    print(f"  area: {area_um2:.4f} um^2 (from LEF)")
    print(f"  RBL cell_rise/cell_fall/rise_transition/fall_transition (ns): "
          f"{cell_rise_ns}/{cell_fall_ns}/{rise_transition_ns}/{fall_transition_ns}")


pin_cap_pf = load_pin_caps_pf()
area_um2 = load_area_um2()

for corner, params in CORNERS.items():
    write_corner_lib(corner, params, pin_cap_pf, area_um2)

print("WL -> Q write delay: NOT included in any corner -- existing testbench "
      "needs a real protocol fix first, see module docstring")
