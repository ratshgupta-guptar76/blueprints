v {xschem version=3.4.8RC file_version=1.3}
G {}
K {}
V {}
S {}
F {}
E {}
N 665 -370 685 -370 {lab=qb[63:0]}
N 665 -330 685 -330 {lab=qb[63:0]}
N 685 -370 685 -330 {lab=qb[63:0]}
N 455 -370 475 -370 {lab=q[63:0]}
N 455 -370 455 -330 {lab=q[63:0]}
N 455 -330 475 -330 {lab=q[63:0]}
C {analog/designs/8T_03v3.sym} 570 -350 0 0 {name=x[63:0]}
C {ipin.sym} 585 -460 1 0 {name=p1 lab=vdd}
C {ipin.sym} 675 -420 0 1 {name=p2 lab=wbl}
C {ipin.sym} 675 -290 0 1 {name=p3 lab=wblb}
C {ipin.sym} 565 -460 1 0 {name=p4 lab=vss}
C {opin.sym} 545 -250 1 0 {name=p5 lab=rbl}
C {ipin.sym} 465 -420 0 0 {name=p6 lab=wl[63:0]}
C {ipin.sym} 505 -250 3 0 {name=p7 lab=a[63:0]}
C {lab_pin.sym} 455 -350 0 0 {name=p9 lab=q[63:0]}
C {lab_pin.sym} 685 -350 0 1 {name=p10 lab=qb[63:0]}
C {devices/code_shown.sym} 35.625 -711.875 0 0 {name=PARAMS only_toplevel=true
format="tcleval( @value )"
value="
.include /workspace/analog/designs/params_6T.spice
.include /workspace/analog/designs/params_8T.spice
"}
C {title.sym} 180 -40 0 0 {name=l1 author="Ratish V. Gupta"}
