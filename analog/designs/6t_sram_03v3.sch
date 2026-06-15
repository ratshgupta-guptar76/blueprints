v {xschem version=3.4.8RC file_version=1.3}
G {}
K {}
V {}
S {}
F {}
E {}
N 90 -150 90 -130 {lab=vdd}
N 90 -70 90 -50 {lab=0}
N 170 -150 170 -130 {lab=vss}
N 170 -70 170 -50 {lab=0}
N 340 -150 340 -130 {lab=WL}
N 340 -70 340 -50 {lab=0}
N 530 -560 530 -520 {lab=Q}
N 530 -630 530 -620 {lab=vdd}
N 530 -410 530 -400 {lab=vss}
N 510 -440 530 -440 {lab=vss}
N 510 -440 510 -410 {lab=vss}
N 510 -590 530 -590 {lab=vdd}
N 510 -620 510 -590 {lab=vdd}
N 900 -560 900 -470 {lab=Qb}
N 900 -630 900 -620 {lab=vdd}
N 900 -410 900 -400 {lab=vss}
N 900 -440 920 -440 {lab=vss}
N 920 -440 920 -410 {lab=vss}
N 900 -590 920 -590 {lab=vdd}
N 920 -620 920 -590 {lab=vdd}
N 530 -520 530 -470 {lab=Q}
N 900 -690 900 -630 {lab=vdd}
N 530 -690 900 -690 {lab=vdd}
N 700 -720 700 -690 {lab=vdd}
N 530 -690 530 -630 {lab=vdd}
N 900 -400 900 -340 {lab=vss}
N 530 -340 900 -340 {lab=vss}
N 530 -400 530 -340 {lab=vss}
N 710 -340 710 -320 {lab=vss}
N 830 -590 860 -590 {lab=Q}
N 830 -590 830 -440 {lab=Q}
N 830 -440 860 -440 {lab=Q}
N 570 -590 600 -590 {lab=Qb}
N 570 -440 600 -440 {lab=Qb}
N 510 -410 510 -340 {lab=vss}
N 920 -410 920 -340 {lab=vss}
N 510 -690 530 -690 {lab=vdd}
N 510 -690 510 -620 {lab=vdd}
N 900 -690 920 -690 {lab=vdd}
N 920 -690 920 -620 {lab=vdd}
N 900 -340 920 -340 {lab=vss}
N 510 -340 530 -340 {lab=vss}
N 600 -590 600 -440 {lab=Qb}
N 530 -500 830 -500 {lab=Q}
N 260 -680 260 -330 {lab=vdd}
N 260 -500 330 -500 {lab=vdd}
N 360 -500 360 -480 {lab=vss}
N 360 -820 360 -540 {lab=WL}
N 310 -820 360 -820 {lab=WL}
N 360 -480 360 -340 {lab=vss}
N 360 -340 510 -340 {lab=vss}
N 1110 -680 1110 -330 {lab=vss}
N 1060 -530 1090 -530 {lab=vss}
N 1030 -530 1030 -510 {lab=vss}
N 1030 -820 1030 -570 {lab=WL}
N 1030 -510 1030 -340 {lab=vss}
N 1090 -530 1110 -530 {lab=vss}
N 920 -340 1030 -340 {lab=vss}
N 360 -820 1030 -820 {lab=WL}
N 900 -530 1000 -530 {lab=Qb}
N 390 -500 530 -500 {lab=Q}
N 1030 -360 1110 -360 {lab=vss}
N 260 -670 510 -670 {lab=vdd}
N 600 -530 900 -530 {lab=Qb}
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
C {devices/code_shown.sym} 1240 -290 0 0 {name=MODELS only_toplevel=true
format="tcleval( @value )"
value="
.include $::180MCU_MODELS/design.ngspice
.lib $::180MCU_MODELS/sm141064.ngspice typical
"}
C {devices/code_shown.sym} 1230 -810 0 0 {name=NGSPICE only_toplevel=true
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
C {symbols/nfet_03v3.sym} 550 -440 0 1 {name=M7
L=0.28u
W=0.66u
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
C {symbols/pfet_03v3.sym} 550 -590 0 1 {name=M8
L=0.28u
W=0.72u
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
C {ipin.sym} 700 -720 3 1 {name=p10 lab=vdd
W=0.22u}
C {symbols/nfet_03v3.sym} 880 -440 0 0 {name=M9
L=0.28u
W=0.61u
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
C {symbols/pfet_03v3.sym} 880 -590 0 0 {name=M10
L=0.28u
W=0.72u
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
C {lab_wire.sym} 530 -500 0 1 {name=p12 sig_type=std_logic lab=Q
W=0.22u}
C {ipin.sym} 710 -320 3 0 {name=p13 lab=vss
W=0.22u}
C {lab_wire.sym} 900 -530 0 0 {name=p14 sig_type=std_logic lab=Qb
W=0.22u}
C {iopin.sym} 260 -680 1 1 {name=p18 sig_type=std_logic lab=BL
W=0.22u}
C {symbols/nfet_03v3.sym} 360 -520 1 0 {name=M11
L=0.28u
W=0.44u
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
C {ipin.sym} 310 -820 0 0 {name=p19 sig_type=std_logic lab=WL
W=0.22u}
C {iopin.sym} 1110 -680 3 0 {name=p20 sig_type=std_logic lab=BLB
W=0.22u}
C {symbols/nfet_03v3.sym} 1030 -550 1 0 {name=M12
L=0.28u
W=0.44u
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
v {xschem version=3.4.8RC file_version=1.3}
G {}
K {}
V {}
S {}
F {}
E {}
N 90 -150 90 -130 {lab=vdd}
N 90 -70 90 -50 {lab=0}
N 170 -150 170 -130 {lab=vss}
N 170 -70 170 -50 {lab=0}
N 340 -150 340 -130 {lab=WL}
N 340 -70 340 -50 {lab=0}
N 530 -560 530 -520 {lab=Q}
N 530 -630 530 -620 {lab=vdd}
N 530 -410 530 -400 {lab=vss}
N 510 -440 530 -440 {lab=vss}
N 510 -440 510 -410 {lab=vss}
N 510 -590 530 -590 {lab=vdd}
N 510 -620 510 -590 {lab=vdd}
N 900 -560 900 -470 {lab=Qb}
N 900 -630 900 -620 {lab=vdd}
N 900 -410 900 -400 {lab=vss}
N 900 -440 920 -440 {lab=vss}
N 920 -440 920 -410 {lab=vss}
N 900 -590 920 -590 {lab=vdd}
N 920 -620 920 -590 {lab=vdd}
N 530 -520 530 -470 {lab=Q}
N 900 -690 900 -630 {lab=vdd}
N 530 -690 900 -690 {lab=vdd}
N 700 -720 700 -690 {lab=vdd}
N 530 -690 530 -630 {lab=vdd}
N 900 -400 900 -340 {lab=vss}
N 530 -340 900 -340 {lab=vss}
N 530 -400 530 -340 {lab=vss}
N 710 -340 710 -320 {lab=vss}
N 830 -590 860 -590 {lab=Q}
N 830 -590 830 -440 {lab=Q}
N 830 -440 860 -440 {lab=Q}
N 570 -590 600 -590 {lab=Qb}
N 570 -440 600 -440 {lab=Qb}
N 510 -410 510 -340 {lab=vss}
N 920 -410 920 -340 {lab=vss}
N 510 -690 530 -690 {lab=vdd}
N 510 -690 510 -620 {lab=vdd}
N 900 -690 920 -690 {lab=vdd}
N 920 -690 920 -620 {lab=vdd}
N 900 -340 920 -340 {lab=vss}
N 510 -340 530 -340 {lab=vss}
N 600 -590 600 -440 {lab=Qb}
N 530 -500 830 -500 {lab=Q}
N 260 -680 260 -330 {lab=vdd}
N 260 -500 330 -500 {lab=vdd}
N 360 -500 360 -480 {lab=vss}
N 360 -820 360 -540 {lab=WL}
N 310 -820 360 -820 {lab=WL}
N 360 -480 360 -340 {lab=vss}
N 360 -340 510 -340 {lab=vss}
N 1110 -680 1110 -330 {lab=vss}
N 1060 -530 1090 -530 {lab=vss}
N 1030 -530 1030 -510 {lab=vss}
N 1030 -820 1030 -570 {lab=WL}
N 1030 -510 1030 -340 {lab=vss}
N 1090 -530 1110 -530 {lab=vss}
N 920 -340 1030 -340 {lab=vss}
N 360 -820 1030 -820 {lab=WL}
N 900 -530 1000 -530 {lab=Qb}
N 390 -500 530 -500 {lab=Q}
N 1030 -360 1110 -360 {lab=vss}
N 260 -670 510 -670 {lab=vdd}
N 600 -530 900 -530 {lab=Qb}
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
C {devices/code_shown.sym} 1240 -290 0 0 {name=MODELS only_toplevel=true
format="tcleval( @value )"
value="
.include $::180MCU_MODELS/design.ngspice
.lib $::180MCU_MODELS/sm141064.ngspice typical
"}
C {devices/code_shown.sym} 1230 -810 0 0 {name=NGSPICE only_toplevel=true
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
C {symbols/nfet_03v3.sym} 550 -440 0 1 {name=M7
L=0.28u
W=0.66u
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
C {symbols/pfet_03v3.sym} 550 -590 0 1 {name=M8
L=0.28u
W=0.72u
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
C {ipin.sym} 700 -720 3 1 {name=p10 lab=vdd
W=0.22u}
C {symbols/nfet_03v3.sym} 880 -440 0 0 {name=M9
L=0.28u
W=0.61u
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
C {symbols/pfet_03v3.sym} 880 -590 0 0 {name=M10
L=0.28u
W=0.72u
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
C {lab_wire.sym} 530 -500 0 1 {name=p12 sig_type=std_logic lab=Q
W=0.22u}
C {ipin.sym} 710 -320 3 0 {name=p13 lab=vss
W=0.22u}
C {lab_wire.sym} 900 -530 0 0 {name=p14 sig_type=std_logic lab=Qb
W=0.22u}
C {iopin.sym} 260 -680 1 1 {name=p18 sig_type=std_logic lab=BL
W=0.22u}
C {symbols/nfet_03v3.sym} 360 -520 1 0 {name=M11
L=0.28u
W=0.44u
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
C {ipin.sym} 310 -820 0 0 {name=p19 sig_type=std_logic lab=WL
W=0.22u}
C {iopin.sym} 1110 -680 3 0 {name=p20 sig_type=std_logic lab=BLB
W=0.22u}
C {symbols/nfet_03v3.sym} 1030 -550 1 0 {name=M12
L=0.28u
W=0.44u
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
