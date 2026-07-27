v {xschem version=3.4.8RC file_version=1.3}
G {}
K {}
V {}
S {}
F {}
E {}
N 690 -310 690 -270 {lab=qb}
N 490 -310 490 -270 {lab=q}
C {title.sym} 180 -40 0 0 {name=l1 author="Ratish V. Gupta"}
C {devices/code_shown.sym} 40 -490 0 0 {name=PARAMS only_toplevel=true
format="tcleval( @value )"
value="
.include /workspace/analog/designs/params_6T.spice
"}
C {analog/designs/6T_03v3.sym} 380 -310 0 0 {name=x1}
C {ipin.sym} 550 -380 1 0 {name=p1 lab=wl}
C {ipin.sym} 620 -380 1 0 {name=p2 lab=vss}
C {ipin.sym} 640 -380 1 0 {name=p3 lab=vdd}
C {ipin.sym} 640 -200 3 0 {name=p4 lab=blb}
C {ipin.sym} 540 -200 3 0 {name=p5 lab=bl}
C {opin.sym} 690 -290 0 0 {name=p6 lab=qb
}
C {opin.sym} 490 -290 0 1 {name=p7 lab=q}
C {devices/code_shown.sym} 20 -170 0 0 {name=MODELS only_toplevel=true
format="tcleval( @value )"
value="
.include $::180MCU_MODELS/design.ngspice
.lib $::180MCU_MODELS/sm141064.ngspice typical
"}
