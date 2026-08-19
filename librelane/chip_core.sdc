current_design $::env(DESIGN_NAME)
set_units -time ns

set clock_port __VIRTUAL_CLK__
if { [info exists ::env(CLOCK_PORT)] } {
    set port_count [llength $::env(CLOCK_PORT)]
    if { $port_count > "0" } {
        set ::clock_port [lindex $::env(CLOCK_PORT) 0]
    }
}

set port_args [get_ports $clock_port]

puts "\[INFO] Using clock $clock_port…"
create_clock {*}$port_args -name $clock_port -period $::env(CLOCK_PERIOD)

set input_delay_value [expr $::env(CLOCK_PERIOD) * $::env(IO_DELAY_CONSTRAINT) / 100]
set output_delay_value [expr $::env(CLOCK_PERIOD) * $::env(IO_DELAY_CONSTRAINT) / 100]

set_max_fanout $::env(MAX_FANOUT_CONSTRAINT) [current_design]
if { [info exists ::env(MAX_TRANSITION_CONSTRAINT)] } {
    set_max_transition $::env(MAX_TRANSITION_CONSTRAINT) [current_design]
}
if { [info exists ::env(MAX_CAPACITANCE_CONSTRAINT)] } {
    set_max_capacitance $::env(MAX_CAPACITANCE_CONSTRAINT) [current_design]
}

set clocks [get_clocks $clock_port]

# Direct Core Signal Ports
# bidir_in is the only actual input in the bidir group; bidir_out/oe/cs/sl/ie/pu/pd
# are all outputs (pad control/config driven by the core -- see chip_core.sv), so
# input and output delay must be applied to disjoint sets, not the same bundle.
set core_bidir_in_ports [get_ports {
    a_bit
    w_bit
    start
    cont
    P_minus1[*]
}]

set core_bidir_out_ports [get_ports {
    y_bit
    done
    busy
}]

set_input_delay -min 0 -clock $clocks $core_bidir_in_ports
set_input_delay -max $input_delay_value -clock $clocks $core_bidir_in_ports
set_output_delay $output_delay_value -clock $clocks $core_bidir_out_ports

set core_input_ports [get_ports {
    rst_n
    a_bit
    w_bit
    start
    cont
    P_minus1[*]
}]

set_input_delay -min 0 -clock $clocks $core_input_ports
set_input_delay -max $input_delay_value -clock $clocks $core_input_ports

set cap_load [expr $::env(OUTPUT_CAP_LOAD) / 1000.0]
set_load $cap_load [all_outputs]

set_clock_uncertainty $::env(CLOCK_UNCERTAINTY_CONSTRAINT) $clocks
set_clock_transition $::env(CLOCK_TRANSITION_CONSTRAINT) $clocks

set_timing_derate -early [expr 1-[expr $::env(TIME_DERATING_CONSTRAINT) / 100]]
set_timing_derate -late [expr 1+[expr $::env(TIME_DERATING_CONSTRAINT) / 100]]

if { [info exists ::env(OPENLANE_SDC_IDEAL_CLOCKS)] && $::env(OPENLANE_SDC_IDEAL_CLOCKS) } {
    unset_propagated_clock [all_clocks]
} else {
    set_propagated_clock [all_clocks]
}
