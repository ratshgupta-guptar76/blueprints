v {xschem version=3.4.8RC file_version=1.3}
G {}
K {}
V {}
S {}
F {}
E {}
T {Simple CMOS Inverter} 250 -850 0 0 0.4 0.4 {}
N 620 -650 620 -570 {lab=vdd}
N 620 -510 620 -400 {lab=vo}
N 620 -460 800 -460 {lab=vo}
N 410 -460 490 -460 {lab=vi}
N 490 -540 580 -540 {lab=vi}
N 490 -460 490 -370 {lab=vi}
N 490 -370 580 -370 {lab=vi}
N 490 -540 490 -460 {lab=vi}
N 620 -340 620 -270 {lab=vss}
N 620 -370 660 -370 {lab=vss}
N 620 -540 660 -540 {lab=vdd}
N 660 -590 660 -540 {lab=vdd}
N 660 -370 660 -320 {lab=vss}
N 620 -320 660 -320 {lab=vss}
N 650 -590 660 -590 {lab=vdd}
N 620 -590 650 -590 {lab=vdd}
C {title.sym} 220 -70 0 0 {name=l1 author="Ratish Gupta"}
C {symbols/nfet_03v3.sym} 600 -370 0 0 {name=M1
L=0.28u
W=1u
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
C {symbols/pfet_03v3.sym} 600 -540 0 0 {name=M2
L=0.28u
W=1u
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
C {ipin.sym} 410 -460 0 0 {name=p4 lab=vi}
C {opin.sym} 800 -460 0 0 {name=p1 lab=vo}
C {iopin.sym} 620 -650 3 0 {name=p2 lab=vdd}
C {iopin.sym} 620 -270 1 0 {name=p3 lab=vss}
