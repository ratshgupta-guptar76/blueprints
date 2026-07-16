v {xschem version=3.4.8RC file_version=1.3}
G {}
K {}
V {}
S {}
F {}
E {}
N 830 -240 870 -240 {lab=QB}
N 940 -160 940 -120 {lab=VSS}
N 450 -350 490 -350 {lab=QBIN}
N 450 -270 450 -210 {lab=QBIN}
N 450 -210 490 -210 {lab=QBIN}
N 530 -280 530 -240 {lab=QB}
N 530 -280 650 -280 {lab=QB}
N 530 -180 530 -160 {lab=VSS}
N 420 -160 530 -160 {lab=VSS}
N 680 -280 680 -160 {lab=VSS}
N 550 -160 680 -160 {lab=VSS}
N 530 -400 530 -380 {lab=VDD}
N 420 -400 530 -400 {lab=VDD}
N 680 -510 680 -320 {lab=WL}
N 530 -210 550 -210 {lab=VSS}
N 550 -210 550 -160 {lab=VSS}
N 530 -400 550 -400 {lab=VDD}
N 550 -400 550 -350 {lab=VDD}
N 530 -350 550 -350 {lab=VDD}
N 350 -350 390 -350 {lab=QIN}
N 390 -280 390 -210 {lab=QIN}
N 350 -210 390 -210 {lab=QIN}
N 310 -280 310 -240 {lab=Q}
N 310 -180 310 -160 {lab=VSS}
N 310 -160 420 -160 {lab=VSS}
N 160 -280 160 -160 {lab=VSS}
N 290 -160 310 -160 {lab=VSS}
N 310 -400 310 -380 {lab=VDD}
N 310 -400 420 -400 {lab=VDD}
N 290 -210 310 -210 {lab=VSS}
N 290 -210 290 -160 {lab=VSS}
N 290 -400 310 -400 {lab=VDD}
N 290 -400 290 -350 {lab=VDD}
N 290 -350 310 -350 {lab=VDD}
N 420 -160 420 -130 {lab=VSS}
N 420 -430 420 -400 {lab=VDD}
N 190 -280 310 -280 {lab=Q}
N 80 -280 130 -280 {lab=WBL}
N 710 -280 760 -280 {lab=WBLB}
N 80 -280 80 -180 {lab=WBL}
N 760 -280 760 -180 {lab=WBLB}
N 160 -510 160 -320 {lab=WL}
N 160 -510 680 -510 {lab=WL}
N 430 -270 450 -270 {lab=QBIN}
N 430 -270 430 -260 {lab=QBIN}
N 390 -280 410 -280 {lab=QIN}
N 410 -290 410 -280 {lab=QIN}
N 940 -390 940 -320 {lab=A}
N 920 -390 940 -390 {lab=A}
N 870 -190 900 -190 {lab=QB}
N 870 -240 870 -190 {lab=QB}
N 870 -290 900 -290 {lab=QB}
N 940 -260 940 -220 {lab=RBL}
N 870 -290 870 -240 {lab=QB}
N 530 -320 530 -280 {lab=QB}
N 530 -160 550 -160 {lab=VSS}
N 160 -160 290 -160 {lab=VSS}
N 310 -320 310 -280 {lab=Q}
N 80 -380 80 -280 {lab=WBL}
N 760 -380 760 -280 {lab=WBLB}
N 160 -530 160 -510 {lab=WL}
N 450 -350 450 -270 {lab=QBIN}
N 390 -350 390 -280 {lab=QIN}
N 940 -290 980 -290 {lab=VSS}
N 940 -190 980 -190 {lab=VSS}
N 940 -140 980 -140 {lab=VSS}
N 940 -240 1080 -240 {lab=RBL}
N 980 -190 980 -140 {lab=VSS}
N 980 -330 980 -290 {lab=VSS}
C {symbols/nfet_03v3.sym} 920 -190 0 0 {name=M1
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
C {opin.sym} 1080 -240 0 0 {name=p11 lab=RBL}
C {devices/code_shown.sym} 35.625 -711.875 0 0 {name=PARAMS only_toplevel=true
format="tcleval( @value )"
value="
.include /workspace/analog/designs/params_6T.spice
.include /workspace/analog/designs/params_8T.spice
"}
C {title.sym} 180 -40 0 0 {name=l1 author="Ratish V. Gupta"}
C {symbols/nfet_03v3.sym} 510 -210 0 0 {name=PD1
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
C {symbols/pfet_03v3.sym} 510 -350 0 0 {name=PU1
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
C {symbols/nfet_03v3.sym} 680 -300 1 0 {name=AX1
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
C {ipin.sym} 420 -130 3 0 {name=p10 lab=VSS}
C {ipin.sym} 420 -430 1 0 {name=p12 lab=VDD}
C {ipin.sym} 160 -530 0 0 {name=p13 lab=WL}
C {ipin.sym} 80 -380 0 0 {name=p14 lab=WBL}
C {ipin.sym} 760 -380 0 0 {name=p15 lab=WBLB}
C {symbols/pfet_03v3.sym} 330 -350 0 1 {name=PU2
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
C {symbols/nfet_03v3.sym} 330 -210 0 1 {name=PD2
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
C {symbols/nfet_03v3.sym} 160 -300 3 1 {name=AX2
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
C {ipin.sym} 430 -260 3 0 {name=p16 lab=QBIN}
C {ipin.sym} 410 -290 1 0 {name=p17 lab=QIN}
C {opin.sym} 310 -280 2 1 {name=p18 lab=Q}
C {opin.sym} 530 -280 2 0 {name=p19 lab=QB}
C {lab_pin.sym} 830 -240 0 0 {name=p1 sig_type=std_logic lab=QB}
C {ipin.sym} 920 -390 0 0 {name=p9 lab=A}
C {lab_pin.sym} 940 -120 3 0 {name=p3 sig_type=std_logic lab=VSS}
C {symbols/pfet_03v3.sym} 920 -290 0 0 {name=M2
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
model=pfet_03v3
spiceprefix=X
}
C {lab_pin.sym} 980 -330 1 0 {name=p2 sig_type=std_logic lab=VDD}
