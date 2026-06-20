v {xschem version=3.4.8RC file_version=1.3}
G {}
K {}
V {}
S {}
F {}
E {}
N 840 -310 900 -310 {lab=Q}
N 940 -380 940 -340 {lab=#net1}
N 940 -380 1060 -380 {lab=#net1}
N 940 -280 940 -240 {lab=VSS}
N 890 -240 990 -240 {lab=VSS}
N 1090 -450 1090 -420 {lab=A}
N 1060 -450 1090 -450 {lab=A}
N 1120 -380 1170 -380 {lab=RBL}
N 1170 -430 1170 -330 {lab=RBL}
N 470 -410 510 -410 {lab=QBIN}
N 470 -410 470 -270 {lab=QBIN}
N 470 -270 510 -270 {lab=QBIN}
N 550 -380 550 -300 {lab=QB}
N 550 -340 670 -340 {lab=QB}
N 550 -240 550 -220 {lab=VSS}
N 450 -220 550 -220 {lab=VSS}
N 440 -220 450 -220 {lab=VSS}
N 700 -340 700 -220 {lab=VSS}
N 550 -220 700 -220 {lab=VSS}
N 550 -460 550 -440 {lab=VDD}
N 440 -460 550 -460 {lab=VDD}
N 700 -570 700 -380 {lab=WL}
N 550 -270 570 -270 {lab=VSS}
N 570 -270 570 -220 {lab=VSS}
N 550 -460 570 -460 {lab=VDD}
N 570 -460 570 -410 {lab=VDD}
N 550 -410 570 -410 {lab=VDD}
N 370 -410 410 -410 {lab=QIN}
N 410 -410 410 -270 {lab=QIN}
N 370 -270 410 -270 {lab=QIN}
N 330 -380 330 -300 {lab=Q}
N 330 -240 330 -220 {lab=VSS}
N 330 -220 430 -220 {lab=VSS}
N 430 -220 440 -220 {lab=VSS}
N 180 -340 180 -220 {lab=VSS}
N 180 -220 330 -220 {lab=VSS}
N 330 -460 330 -440 {lab=VDD}
N 330 -460 440 -460 {lab=VDD}
N 180 -510 180 -380 {lab=WL}
N 310 -270 330 -270 {lab=VSS}
N 310 -270 310 -220 {lab=VSS}
N 310 -460 330 -460 {lab=VDD}
N 310 -460 310 -410 {lab=VDD}
N 310 -410 330 -410 {lab=VDD}
N 440 -220 440 -190 {lab=VSS}
N 440 -490 440 -460 {lab=VDD}
N 210 -340 330 -340 {lab=Q}
N 120 -340 150 -340 {lab=WBL}
N 100 -340 120 -340 {lab=WBL}
N 730 -340 780 -340 {lab=WBLB}
N 100 -440 100 -240 {lab=WBL}
N 780 -440 780 -240 {lab=WBLB}
N 180 -590 180 -510 {lab=WL}
N 180 -570 700 -570 {lab=WL}
N 460 -330 470 -330 {lab=QBIN}
N 450 -330 460 -330 {lab=QBIN}
N 450 -330 450 -320 {lab=QBIN}
N 410 -340 420 -340 {lab=QIN}
N 420 -340 430 -340 {lab=QIN}
N 430 -350 430 -340 {lab=QIN}
N 940 -310 1090 -310 {lab=VSS}
N 1090 -380 1090 -280 {lab=VSS}
C {symbols/nfet_03v3.sym} 920 -310 0 0 {name=M1
L='L_M1'
W='W_M1'
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
C {symbols/nfet_03v3.sym} 1090 -400 1 0 {name=M2
L='L_M2'
W='W_M2'
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
C {ipin.sym} 1060 -450 0 0 {name=p9 lab=A}
C {opin.sym} 1170 -330 1 0 {name=p11 lab=RBL}
C {lab_pin.sym} 890 -240 0 0 {name=p8 sig_type=std_logic lab=VSS}
C {devices/code_shown.sym} 595.625 -141.875 0 0 {name=PARAMS only_toplevel=true
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
C {symbols/nfet_03v3.sym} 530 -270 0 0 {name=PD1
L='L_PD'
W='W_PD'
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
C {symbols/pfet_03v3.sym} 530 -410 0 0 {name=PU1
L='L_PU'
W='W_PU'
nf=1
m=1
ad="'int((nf+1)/2) * W/nf * 0.18u'"
pd="'2*int((nf+1)/2) * (W/nf + 0.18u)'"
as="'int((nf+2)/2) * W/nf * 0.18u'"
ps="'2*int((nf+2)/2) * (W/nf + 0.18u)'"
nrd="'0.18u / W'" nrs="'0.18u / W'"
sa=0 sb=0 sd=0
model=pfet_03v3
spiceprefix=X
}
C {symbols/nfet_03v3.sym} 700 -360 1 0 {name=AX1
L='L_AX'
W='W_AX'
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
C {ipin.sym} 440 -190 3 0 {name=p10 lab=VSS}
C {ipin.sym} 440 -490 1 0 {name=p12 lab=VDD}
C {ipin.sym} 180 -590 1 0 {name=p13 lab=WL}
C {ipin.sym} 100 -440 1 0 {name=p14 lab=WBL}
C {ipin.sym} 780 -440 1 0 {name=p15 lab=WBLB}
C {symbols/pfet_03v3.sym} 350 -410 0 1 {name=PU2
L='L_PU'
W='W_PU'
nf=1
m=1
ad="'int((nf+1)/2) * W/nf * 0.18u'"
pd="'2*int((nf+1)/2) * (W/nf + 0.18u)'"
as="'int((nf+2)/2) * W/nf * 0.18u'"
ps="'2*int((nf+2)/2) * (W/nf + 0.18u)'"
nrd="'0.18u / W'" nrs="'0.18u / W'"
sa=0 sb=0 sd=0
model=pfet_03v3
spiceprefix=X
}
C {symbols/nfet_03v3.sym} 350 -270 0 1 {name=PD2
L='L_PD'
W='W_PD'
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
C {symbols/nfet_03v3.sym} 180 -360 3 1 {name=AX2
L='L_AX'
W='W_AX'
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
C {ipin.sym} 450 -320 3 0 {name=p16 lab=QBIN}
C {ipin.sym} 430 -350 1 0 {name=p17 lab=QIN}
C {opin.sym} 330 -340 2 1 {name=p18 lab=Q}
C {opin.sym} 550 -340 2 0 {name=p19 lab=QB}
C {lab_pin.sym} 840 -310 0 0 {name=p1 sig_type=std_logic lab=Q}
C {lab_pin.sym} 1090 -280 3 0 {name=p2 sig_type=std_logic lab=VSS}
