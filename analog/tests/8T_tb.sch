v {xschem version=3.4.8RC file_version=1.3}
G {}
K {}
V {}
S {}
F {}
E {}
N 740 -280 740 -240 {lab=qb}
N 730 -240 740 -240 {lab=qb}
N 730 -280 740 -280 {lab=qb}
N 530 -280 530 -240 {lab=q}
N 530 -240 540 -240 {lab=q}
N 530 -280 540 -280 {lab=q}
C {analog/designs/8T_03v3.sym} 635 -260 0 0 {name=x1}
C {ipin.sym} 650 -370 1 0 {name=p1 lab=vdd}
C {ipin.sym} 630 -370 1 0 {name=p2 lab=vss}
C {ipin.sym} 530 -330 0 0 {name=p4 lab=wl}
C {ipin.sym} 530 -260 0 0 {name=p5 lab=q}
C {ipin.sym} 740 -260 2 0 {name=p6 lab=qb}
C {ipin.sym} 570 -160 3 0 {name=p7 lab=a}
C {ipin.sym} 610 -160 3 0 {name=p8 lab=rbl}
C {ipin.sym} 740 -330 2 0 {name=p3 lab=wlb}
C {ipin.sym} 740 -200 2 0 {name=p9 lab=blb}
C {title.sym} 180 -40 0 0 {name=l1 author="Ratish V. Gupta"}
C {devices/code_shown.sym} 40 -460 0 0 {name=PARAMS only_toplevel=true
format="tcleval( @value )"
value="
.include /workspace/analog/designs/params.spice
"}
C {devices/code_shown.sym} 20 -140 0 0 {name=MODELS only_toplevel=true
format="tcleval( @value )"
value="
.include $::180MCU_MODELS/design.ngspice
.lib $::180MCU_MODELS/sm141064.ngspice typical
"}
