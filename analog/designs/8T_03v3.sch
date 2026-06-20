v {xschem version=3.4.8RC file_version=1.3}
G {}
K {}
V {}
S {}
F {}
E {}
N 430 -300 490 -300 {lab=qb}
N 530 -370 530 -330 {lab=#net1}
N 530 -370 650 -370 {lab=#net1}
N 530 -270 530 -230 {lab=vss}
N 480 -230 580 -230 {lab=vss}
N 680 -440 680 -410 {lab=A}
N 650 -440 680 -440 {lab=A}
N 710 -370 760 -370 {lab=WBL}
N 760 -420 760 -320 {lab=WBL}
N 430 -320 430 -280 {lab=qb}
N 210 -320 220 -320 {lab=q}
N 210 -320 210 -280 {lab=q}
N 210 -280 220 -280 {lab=q}
N 420 -320 430 -320 {lab=qb}
N 420 -280 430 -280 {lab=qb}
C {symbols/nfet_03v3.sym} 510 -300 0 0 {name=AX4
L=0.28u
W=0.25u
nf=1
m=1
ad="'int((nf+1)/2) * W/nf * 0.18u'"
pd="'2*int((nf+1)/2) * (W/nf + 0.18u)'"
as="'int((nf+2)/2) * W/nf * 0.18u'"
ps="'2*int((nf+2)/2) * (W/nf + 0.18u)'"
nrd="'0.18u / W'" nrs="'0.18u / W'"
sa=0 sb=0 sd=0
model=nfet_03v3
spiceprefix=X
}
C {symbols/nfet_03v3.sym} 680 -390 1 0 {name=AX3
L=0.28u
W=0.25u
nf=1
m=1
ad="'int((nf+1)/2) * W/nf * 0.18u'"
pd="'2*int((nf+1)/2) * (W/nf + 0.18u)'"
as="'int((nf+2)/2) * W/nf * 0.18u'"
ps="'2*int((nf+2)/2) * (W/nf + 0.18u)'"
nrd="'0.18u / W'" nrs="'0.18u / W'"
sa=0 sb=0 sd=0
model=nfet_03v3
spiceprefix=X
}
C {ipin.sym} 650 -440 0 0 {name=p9 lab=A}
C {ipin.sym} 760 -320 3 0 {name=p11 lab=WBL}
C {analog/designs/6T_03v3.sym} 110 -320 0 0 {name=x1}
C {ipin.sym} 430 -280 2 0 {name=p6 lab=qb
}
C {ipin.sym} 210 -320 2 1 {name=p7 lab=q}
C {ipin.sym} 280 -390 1 0 {name=p1 lab=wl}
C {ipin.sym} 350 -390 1 0 {name=p2 lab=vss}
C {ipin.sym} 370 -390 1 0 {name=p3 lab=vdd}
C {ipin.sym} 370 -210 3 0 {name=p4 lab=wblb}
C {ipin.sym} 270 -210 3 0 {name=p5 lab=wbl}
C {lab_pin.sym} 480 -230 0 0 {name=p8 sig_type=std_logic lab=vss}
C {devices/code_shown.sym} 20 -500 0 0 {name=PARAMS only_toplevel=true
format="tcleval( @value )"
value="
.include /workspace/analog/designs/params_6T.spice
.include /workspace/analog/designs/params_8T.spice
"}
C {devices/code_shown.sym} 20 -150 0 0 {name=MODELS only_toplevel=true
format="tcleval( @value )"
value="
.include $::180MCU_MODELS/design.ngspice
.lib $::180MCU_MODELS/sm141064.ngspice typical
"}
C {title.sym} 180 -40 0 0 {name=l1 author="Ratish V. Gupta"}
