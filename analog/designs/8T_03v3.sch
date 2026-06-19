v {xschem version=3.4.8RC file_version=1.3}
G {}
K {}
V {}
S {}
F {}
E {}
N 150 -290 190 -290 {lab=Q}
N 150 -290 150 -150 {lab=Q}
N 150 -150 190 -150 {lab=Q}
N 230 -260 230 -180 {lab=QB}
N 90 -240 230 -240 {lab=QB}
N 230 -220 350 -220 {lab=QB}
N 230 -120 230 -100 {lab=vss}
N 130 -100 230 -100 {lab=vss}
N 120 -100 130 -100 {lab=vss}
N 380 -220 380 -100 {lab=vss}
N 230 -100 380 -100 {lab=vss}
N 230 -340 230 -320 {lab=vdd}
N 120 -340 230 -340 {lab=vdd}
N 380 -390 380 -260 {lab=WL}
N 230 -150 250 -150 {lab=vss}
N 250 -150 250 -100 {lab=vss}
N 230 -340 250 -340 {lab=vdd}
N 250 -340 250 -290 {lab=vdd}
N 230 -290 250 -290 {lab=vdd}
N 50 -290 90 -290 {lab=QB}
N 90 -290 90 -150 {lab=QB}
N 50 -150 90 -150 {lab=QB}
N 10 -260 10 -180 {lab=Q}
N 10 -200 150 -200 {lab=Q}
N 10 -120 10 -100 {lab=vss}
N 10 -100 110 -100 {lab=vss}
N 110 -100 120 -100 {lab=vss}
N -140 -220 -140 -100 {lab=vss}
N -140 -100 10 -100 {lab=vss}
N 10 -340 10 -320 {lab=vdd}
N 10 -340 120 -340 {lab=vdd}
N -140 -390 -140 -260 {lab=WL}
N -10 -150 10 -150 {lab=vss}
N -10 -150 -10 -100 {lab=vss}
N -10 -340 10 -340 {lab=vdd}
N -10 -340 -10 -290 {lab=vdd}
N -10 -290 10 -290 {lab=vdd}
N 120 -100 120 -70 {lab=vss}
N 120 -370 120 -340 {lab=vdd}
N -110 -220 10 -220 {lab=Q}
N -200 -220 -170 -220 {lab=WBL}
N -220 -220 -200 -220 {lab=WBL}
N 410 -220 460 -220 {lab=WBLB}
N -220 -320 -220 -120 {lab=WBL}
N 460 -320 460 -120 {lab=WBLB}
N 150 -150 150 130 {lab=Q}
N 150 130 200 130 {lab=Q}
N 240 60 240 100 {lab=#net1}
N 240 60 430 60 {lab=#net1}
N 240 160 240 200 {lab=vss}
N 190 200 400 200 {lab=vss}
N 460 -10 460 20 {lab=A}
N 430 -10 460 -10 {lab=A}
N 490 60 540 60 {lab=RBL}
N 540 10 540 110 {lab=RBL}
N 460 60 460 110 {lab=vss}
N 240 130 460 130 {lab=vss}
N 460 110 460 130 {lab=vss}
N 400 130 400 200 {lab=vss}
N 80 200 190 200 {lab=vss}
N 80 -100 80 200 {lab=vss}
C {symbols/nfet_03v3.sym} 210 -150 0 0 {name=PD1
L=0.28u
W=0.28u
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
C {symbols/pfet_03v3.sym} 210 -290 0 0 {name=PU1
L=0.44u
W=0.22u
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
C {symbols/nfet_03v3.sym} 380 -240 1 0 {name=AX1
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
C {symbols/nfet_03v3.sym} 30 -150 0 1 {name=PD2
L=0.28u
W=0.28u
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
C {symbols/pfet_03v3.sym} 30 -290 0 1 {name=PU2
L=0.44u
W=0.22u
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
C {symbols/nfet_03v3.sym} -140 -240 3 1 {name=AX2
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
C {ipin.sym} 120 -70 3 0 {name=p1 lab=vss}
C {ipin.sym} 120 -370 1 0 {name=p3 lab=vdd}
C {ipin.sym} -140 -390 1 0 {name=p2 lab=WL}
C {ipin.sym} 380 -390 1 0 {name=p4 lab=WL}
C {ipin.sym} -220 -120 3 0 {name=p5 lab=WBL}
C {ipin.sym} 460 -130 3 0 {name=p6 lab=WBLB}
C {lab_wire.sym} 230 -240 0 0 {name=p7 sig_type=std_logic lab=QB}
C {lab_wire.sym} 10 -200 0 0 {name=p8 sig_type=std_logic lab=Q}
C {symbols/nfet_03v3.sym} 220 130 0 0 {name=AX4
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
C {symbols/nfet_03v3.sym} 460 40 1 0 {name=AX3
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
C {ipin.sym} 430 -10 0 0 {name=p9 lab=A}
C {ipin.sym} 540 110 3 0 {name=p11 lab=RBL}
C {lab_wire.sym} 170 130 0 0 {name=p12 sig_type=std_logic lab=Q}
