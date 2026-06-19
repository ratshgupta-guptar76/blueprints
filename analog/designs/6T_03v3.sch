v {xschem version=3.4.8RC file_version=1.3}
G {}
K {}
V {}
S {}
F {}
E {}
N 610 -440 650 -440 {lab=QBIN}
N 610 -440 610 -300 {lab=QBIN}
N 610 -300 650 -300 {lab=QBIN}
N 690 -410 690 -330 {lab=QB}
N 690 -370 810 -370 {lab=QB}
N 690 -270 690 -250 {lab=VSS}
N 590 -250 690 -250 {lab=VSS}
N 580 -250 590 -250 {lab=VSS}
N 840 -370 840 -250 {lab=VSS}
N 690 -250 840 -250 {lab=VSS}
N 690 -490 690 -470 {lab=VDD}
N 580 -490 690 -490 {lab=VDD}
N 840 -600 840 -410 {lab=WL}
N 690 -300 710 -300 {lab=VSS}
N 710 -300 710 -250 {lab=VSS}
N 690 -490 710 -490 {lab=VDD}
N 710 -490 710 -440 {lab=VDD}
N 690 -440 710 -440 {lab=VDD}
N 510 -440 550 -440 {lab=QIN}
N 550 -440 550 -300 {lab=QIN}
N 510 -300 550 -300 {lab=QIN}
N 470 -410 470 -330 {lab=Q}
N 470 -270 470 -250 {lab=VSS}
N 470 -250 570 -250 {lab=VSS}
N 570 -250 580 -250 {lab=VSS}
N 320 -370 320 -250 {lab=VSS}
N 320 -250 470 -250 {lab=VSS}
N 470 -490 470 -470 {lab=VDD}
N 470 -490 580 -490 {lab=VDD}
N 320 -540 320 -410 {lab=WL}
N 450 -300 470 -300 {lab=VSS}
N 450 -300 450 -250 {lab=VSS}
N 450 -490 470 -490 {lab=VDD}
N 450 -490 450 -440 {lab=VDD}
N 450 -440 470 -440 {lab=VDD}
N 580 -250 580 -220 {lab=VSS}
N 580 -520 580 -490 {lab=VDD}
N 350 -370 470 -370 {lab=Q}
N 260 -370 290 -370 {lab=BL}
N 240 -370 260 -370 {lab=BL}
N 870 -370 920 -370 {lab=BLB}
N 240 -470 240 -270 {lab=BL}
N 920 -470 920 -270 {lab=BLB}
N 320 -620 320 -540 {lab=WL}
N 320 -600 840 -600 {lab=WL}
N 600 -360 610 -360 {lab=QBIN}
N 590 -360 600 -360 {lab=QBIN}
N 590 -360 590 -350 {lab=QBIN}
N 550 -370 560 -370 {lab=QIN}
N 560 -370 570 -370 {lab=QIN}
N 570 -380 570 -370 {lab=QIN}
C {symbols/nfet_03v3.sym} 670 -300 0 0 {name=PD1
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
C {symbols/pfet_03v3.sym} 670 -440 0 0 {name=PU1
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
C {symbols/nfet_03v3.sym} 840 -390 1 0 {name=AX1
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
C {ipin.sym} 580 -220 3 0 {name=p1 lab=VSS}
C {ipin.sym} 580 -520 1 0 {name=p3 lab=VDD}
C {ipin.sym} 320 -620 1 0 {name=p2 lab=WL}
C {ipin.sym} 240 -470 1 0 {name=p5 lab=BL}
C {ipin.sym} 920 -470 1 0 {name=p6 lab=BLB}
C {title.sym} 180 -50 0 0 {name=l1 author="Ratish V. Gupta"}
C {devices/code_shown.sym} 20 -750 0 0 {name=PARAMS only_toplevel=true
format="tcleval( @value )"
value="
.include /workspace/analog/designs/params.spice
"}
C {devices/code_shown.sym} 20 -160 0 0 {name=MODELS only_toplevel=true
format="tcleval( @value )"
value="
.include $::180MCU_MODELS/design.ngspice
.lib $::180MCU_MODELS/sm141064.ngspice typical
"}
C {symbols/pfet_03v3.sym} 490 -440 0 1 {name=PU2
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
C {symbols/nfet_03v3.sym} 490 -300 0 1 {name=PD2
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
C {symbols/nfet_03v3.sym} 320 -390 3 1 {name=AX2
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
C {ipin.sym} 590 -350 3 0 {name=p4 lab=QBIN}
C {ipin.sym} 570 -380 1 0 {name=p9 lab=QIN}
C {opin.sym} 470 -370 2 1 {name=p10 lab=Q}
C {opin.sym} 690 -370 2 0 {name=p8 lab=QB}
