v {xschem version=3.4.8RC file_version=1.3}
G {}
K {}
V {}
S {}
F {}
E {}
N 480 -480 480 -440 {lab=Q}
N 480 -550 480 -540 {lab=vdd}
N 480 -330 480 -320 {lab=vss}
N 460 -360 480 -360 {lab=vss}
N 460 -360 460 -330 {lab=vss}
N 460 -510 480 -510 {lab=vdd}
N 460 -540 460 -510 {lab=vdd}
N 850 -480 850 -390 {lab=Qb}
N 850 -550 850 -540 {lab=vdd}
N 850 -330 850 -320 {lab=vss}
N 850 -360 870 -360 {lab=vss}
N 870 -360 870 -330 {lab=vss}
N 850 -510 870 -510 {lab=vdd}
N 870 -540 870 -510 {lab=vdd}
N 480 -440 480 -390 {lab=Q}
N 850 -610 850 -550 {lab=vdd}
N 480 -610 850 -610 {lab=vdd}
N 650 -640 650 -610 {lab=vdd}
N 480 -610 480 -550 {lab=vdd}
N 850 -320 850 -260 {lab=vss}
N 480 -260 850 -260 {lab=vss}
N 480 -320 480 -260 {lab=vss}
N 660 -260 660 -240 {lab=vss}
N 780 -510 810 -510 {lab=Q}
N 780 -510 780 -360 {lab=Q}
N 780 -360 810 -360 {lab=Q}
N 520 -510 550 -510 {lab=Qb}
N 550 -510 550 -360 {lab=Qb}
N 520 -360 550 -360 {lab=Qb}
N 550 -450 850 -450 {lab=Qb}
N 480 -420 780 -420 {lab=Q}
N 240 -600 240 -250 {lab=BL}
N 1080 -600 1080 -250 {lab=BLB}
N 370 -420 480 -420 {lab=Q}
N 240 -420 310 -420 {lab=BL}
N 340 -420 340 -400 {lab=vss}
N 850 -450 970 -450 {lab=Qb}
N 1030 -450 1060 -450 {lab=BLB}
N 1000 -450 1000 -430 {lab=vss}
N 340 -740 340 -460 {lab=WL}
N 340 -740 1000 -740 {lab=WL}
N 1000 -740 1000 -490 {lab=WL}
N 290 -740 340 -740 {lab=WL}
N 1000 -430 1000 -260 {lab=vss}
N 850 -260 1000 -260 {lab=vss}
N 340 -400 340 -260 {lab=vss}
N 340 -260 480 -260 {lab=vss}
N 460 -330 460 -260 {lab=vss}
N 870 -330 870 -260 {lab=vss}
N 460 -610 480 -610 {lab=vdd}
N 460 -610 460 -540 {lab=vdd}
N 850 -610 870 -610 {lab=vdd}
N 870 -610 870 -540 {lab=vdd}
N 1060 -450 1080 -450 {lab=BLB}
N 90 -150 90 -130 {lab=vdd}
N 90 -70 90 -50 {lab=0}
N 170 -150 170 -130 {lab=vss}
N 170 -70 170 -50 {lab=0}
N 340 -150 340 -130 {lab=WL}
N 340 -70 340 -50 {lab=0}
C {symbols/nfet_03v3.sym} 500 -360 0 1 {name=M1
L=0.28u
W=0.22u
nf=4
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
C {symbols/pfet_03v3.sym} 500 -510 0 1 {name=M2
L=0.28u
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
C {ipin.sym} 650 -640 3 1 {name=p1 lab=vdd
W=0.22u}
C {symbols/nfet_03v3.sym} 830 -360 0 0 {name=M3
L=0.28u
W=0.22u
nf=4
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
C {symbols/pfet_03v3.sym} 830 -510 0 0 {name=M4
L=0.28u
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
C {lab_wire.sym} 480 -420 0 1 {name=p4 sig_type=std_logic lab=Q
W=0.22u}
C {ipin.sym} 660 -240 3 0 {name=p5 lab=vss
W=0.22u}
C {lab_wire.sym} 850 -450 0 0 {name=p6 sig_type=std_logic lab=Qb
W=0.22u}
C {iopin.sym} 1080 -600 3 0 {name=p7 sig_type=std_logic lab=BLB
W=0.22u}
C {iopin.sym} 240 -600 1 1 {name=p8 sig_type=std_logic lab=BL
W=0.22u}
C {symbols/nfet_03v3.sym} 340 -440 1 0 {name=M5
L=0.28u
W=0.22u
nf=2
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
C {symbols/nfet_03v3.sym} 1000 -470 1 0 {name=M6
L=0.28u
W=0.22u
nf=2
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
C {ipin.sym} 290 -740 0 0 {name=p9 sig_type=std_logic lab=WL
W=0.22u}
C {vsource.sym} 90 -100 0 0 {name=VDD value=3.3 savecurrent=false}
C {opin.sym} 90 -150 1 1 {name=p2 lab=vdd
W=0.22u}
C {gnd.sym} 90 -50 0 0 {name=l1 lab=0}
C {vsource.sym} 170 -100 0 0 {name=VSS value=0 savecurrent=false}
C {gnd.sym} 170 -50 0 0 {name=l2 lab=0}
C {opin.sym} 170 -150 3 0 {name=p3 lab=vss
W=0.22u}
C {vsource.sym} 340 -100 0 0 {name=VWL value="PULSE(0 3.3 5n 0.1n 0.1n 10n 50n)" savecurrent=false}
C {gnd.sym} 340 -50 0 0 {name=l3 lab=0}
C {opin.sym} 340 -150 3 0 {name=p11 sig_type=std_logic lab=WL
W=0.22u}
C {devices/code_shown.sym} 1690 -340 0 0 {name=MODELS only_toplevel=true
format="tcleval( @value )"
value="
.include $::180MCU_MODELS/design.ngspice
.lib $::180MCU_MODELS/sm141064.ngspice typical
"}
C {devices/code_shown.sym} 1680 -860 0 0 {name=NGSPICE only_toplevel=true
value="

** Initial Conditions -- Set BL to '1' and BLB to '0'
.ic v(Q)=0 v(Qb)=3.3 v(BL)=3.3 v(BLB)=0

.control
save all

** Define Write Line Pulse signal
let fsig_w = 100M
let tper_w = 1/fsig_w
let tfr_w = 0.01*tper_w
let ton_w = 0.5*tper_w-2*tfr_w

** Transient analysis 
tran 0.01n 50n uic

** Plot the waveforms
plot q qb wl
plot bl blb wl

write 6t_sram_03v3_tb.raw
.endc

"}
