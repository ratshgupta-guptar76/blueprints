v {xschem version=3.4.8RC file_version=1.3}
G {}
K {}
V {}
S {}
F {}
E {}
C {title.sym} 200 -40 0 0 {name=l1 author="Ratish V. Gupta"}
C {devices/code_shown.sym} 60 -490 0 0 {name=PARAMS only_toplevel=true
format="tcleval( @value )"
value="
.include /workspace/analog/designs/params_6T.spice
"}
C {analog/designs/6T_03v3.sym} 400 -310 0 0 {name=x1}
C {ipin.sym} 570 -380 1 0 {name=p1 lab=wl}
C {ipin.sym} 640 -380 1 0 {name=p2 lab=vss}
C {ipin.sym} 660 -380 1 0 {name=p3 lab=vdd}
C {ipin.sym} 660 -200 3 0 {name=p4 lab=blb}
C {ipin.sym} 560 -200 3 0 {name=p5 lab=bl}
C {ipin.sym} 710 -310 2 0 {name=p6 lab=qb
}
C {ipin.sym} 510 -270 2 1 {name=p7 lab=q}
C {devices/code_shown.sym} 40 -170 0 0 {name=MODELS only_toplevel=true
format="tcleval( @value )"
value="
.include $::180MCU_MODELS/design.ngspice
.lib $::180MCU_MODELS/sm141064.ngspice typical
"}
C {ipin.sym} 510 -310 2 1 {name=p8 lab=qbin}
C {ipin.sym} 710 -270 2 0 {name=p9 lab=qin
}
