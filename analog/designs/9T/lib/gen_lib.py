#!/usr/bin/env python3
CELL = "sram_32x8_9T"
OUT  = f"{CELL}__tt_025C_3v30.lib"

def bus_type(name, width):
    return (f'  type ({name}) {{\n'
            f'    base_type : array;\n'
            f'    data_type : bit;\n'
            f'    bit_width : {width};\n'
            f'    bit_from  : {width-1};\n'
            f'    bit_to    : 0;\n'
            f'    downto    : true;\n'
            f'  }}\n')

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
    f.write('    area : 4891;\n')
    f.write('    dont_use : TRUE;\n')
    f.write('    dont_touch : TRUE;\n')
    f.write('    interface_timing : TRUE;\n\n')

    f.write('    pg_pin (VDD) { voltage_name : VDD; pg_type : primary_power; }\n')
    f.write('    pg_pin (VSS) { voltage_name : VSS; pg_type : primary_ground; }\n\n')

    for name, btype in (('WL','BUS32'), ('A','BUS32'),
                        ('WBL','BUS8'), ('WBLB','BUS8')):
        f.write(f'    bus ({name}) {{\n')
        f.write(f'      bus_type    : {btype};\n')
        f.write('      direction   : input;\n')
        f.write('      capacitance : 0.05;\n')
        f.write('      related_power_pin  : VDD;\n')
        f.write('      related_ground_pin : VSS;\n')
        f.write('    }\n')

    f.write('\n    bus (RBL) {\n')
    f.write('      bus_type        : BUS256;\n')
    f.write('      direction       : output;\n')
    f.write('      max_capacitance : 0.10;\n')
    f.write('      related_power_pin  : VDD;\n')
    f.write('      related_ground_pin : VSS;\n')
    for k in range(256):
        f.write(f'      pin (RBL[{k}]) {{\n')
        f.write('        timing () {\n')
        f.write(f'          related_pin  : "A[{k//8}]";\n')
        f.write('          timing_sense : positive_unate;\n')
        f.write('          cell_rise (scalar) { values("1.0"); }\n')
        f.write('          cell_fall (scalar) { values("1.0"); }\n')
        f.write('          rise_transition (scalar) { values("0.2"); }\n')
        f.write('          fall_transition (scalar) { values("0.2"); }\n')
        f.write('        }\n      }\n')
    f.write('    }\n')

    f.write('  }\n}\n')

print(f"wrote {OUT}")