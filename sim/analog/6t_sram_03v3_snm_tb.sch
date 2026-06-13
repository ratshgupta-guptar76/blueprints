v {xschem version=3.4.8RC file_version=1.3}
G {}
K {}
V {}
S {}
F {}
E {}
N 580 -740 580 -700 {lab=Q}
N 580 -810 580 -800 {lab=vdd}
N 580 -590 580 -580 {lab=vss}
N 560 -620 580 -620 {lab=vss}
N 560 -620 560 -590 {lab=vss}
N 560 -770 580 -770 {lab=vdd}
N 560 -800 560 -770 {lab=vdd}
N 950 -740 950 -650 {lab=Qb}
N 950 -810 950 -800 {lab=vdd}
N 950 -590 950 -580 {lab=vss}
N 950 -620 970 -620 {lab=vss}
N 970 -620 970 -590 {lab=vss}
N 950 -770 970 -770 {lab=vdd}
N 970 -800 970 -770 {lab=vdd}
N 580 -700 580 -650 {lab=Q}
N 950 -870 950 -810 {lab=vdd}
N 580 -870 950 -870 {lab=vdd}
N 750 -900 750 -870 {lab=vdd}
N 580 -870 580 -810 {lab=vdd}
N 950 -580 950 -520 {lab=vss}
N 580 -520 950 -520 {lab=vss}
N 580 -580 580 -520 {lab=vss}
N 760 -520 760 -500 {lab=vss}
N 880 -770 910 -770 {lab=Vin}
N 880 -770 880 -620 {lab=Vin}
N 880 -620 910 -620 {lab=Vin}
N 620 -770 650 -770 {lab=Vin}
N 620 -620 650 -620 {lab=Vin}
N 560 -590 560 -520 {lab=vss}
N 970 -590 970 -520 {lab=vss}
N 560 -870 580 -870 {lab=vdd}
N 560 -870 560 -800 {lab=vdd}
N 950 -870 970 -870 {lab=vdd}
N 970 -870 970 -800 {lab=vdd}
N 1460 -820 1460 -800 {lab=vdd}
N 1460 -740 1460 -720 {lab=0}
N 1540 -820 1540 -800 {lab=vss}
N 1540 -740 1540 -720 {lab=0}
N 950 -520 970 -520 {lab=vss}
N 560 -520 580 -520 {lab=vss}
N 650 -770 650 -620 {lab=Vin}
N 1240 -810 1240 -800 {lab=Vin}
N 650 -770 690 -770 {lab=Vin}
N 310 -860 310 -510 {lab=BL}
N 310 -680 380 -680 {lab=BL}
N 410 -680 410 -660 {lab=vss}
N 410 -1000 410 -720 {lab=WL}
N 360 -1000 410 -1000 {lab=WL}
N 410 -660 410 -520 {lab=vss}
N 410 -520 560 -520 {lab=vss}
N 1160 -860 1160 -510 {lab=BLB}
N 1110 -710 1140 -710 {lab=BLB}
N 1080 -710 1080 -690 {lab=vss}
N 1080 -1000 1080 -750 {lab=WL}
N 1080 -690 1080 -520 {lab=vss}
N 1140 -710 1160 -710 {lab=BLB}
N 970 -520 1080 -520 {lab=vss}
N 410 -1000 1080 -1000 {lab=WL}
N 1680 -820 1680 -800 {lab=WL}
N 1680 -740 1680 -720 {lab=0}
N 950 -710 1050 -710 {lab=Qb}
N 440 -680 580 -680 {lab=Q}
N 1230 -620 1230 -610 {lab=E1}
N 1370 -620 1370 -610 {lab=E2}
N 1310 -810 1310 -800 {lab=Ein}
N 830 -620 880 -620 {lab=Vin}
C {symbols/nfet_03v3.sym} 600 -620 0 1 {name=M1
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
model=nfet_03v3
spiceprefix=X
}
C {symbols/pfet_03v3.sym} 600 -770 0 1 {name=M2
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
model=pfet_03v3
spiceprefix=X
}
C {ipin.sym} 750 -900 3 1 {name=p1 lab=vdd
W=0.22u}
C {symbols/nfet_03v3.sym} 930 -620 0 0 {name=M3
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
model=nfet_03v3
spiceprefix=X
}
C {symbols/pfet_03v3.sym} 930 -770 0 0 {name=M4
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
model=pfet_03v3
spiceprefix=X
}
C {lab_wire.sym} 580 -680 0 1 {name=p4 sig_type=std_logic lab=Q
W=0.22u}
C {ipin.sym} 760 -500 3 0 {name=p5 lab=vss
W=0.22u}
C {lab_wire.sym} 950 -710 0 0 {name=p6 sig_type=std_logic lab=Qb
W=0.22u}
C {vsource.sym} 1460 -770 0 0 {name=VDD value=3.3 savecurrent=false}
C {opin.sym} 1460 -820 1 1 {name=p2 lab=vdd
W=0.22u}
C {gnd.sym} 1460 -720 0 0 {name=l1 lab=0}
C {vsource.sym} 1540 -770 0 0 {name=VSS value=0 savecurrent=false}
C {gnd.sym} 1540 -720 0 0 {name=l2 lab=0}
C {opin.sym} 1540 -820 3 0 {name=p3 lab=vss
W=0.22u}
C {devices/code_shown.sym} 1210 -960 0 0 {name=MODELS only_toplevel=true
format="tcleval( @value )"
value="
.include $::180MCU_MODELS/design.ngspice
.lib $::180MCU_MODELS/sm141064.ngspice typical
"}
C {devices/code_shown.sym} 1810 -930 0 0 {name=NGSPICE only_toplevel=true
value="
.control
save all

** DC analysis 
dc Vin 0 3.3 0.001

let v = v(Q)
let vb = v(Qb)
let vin = v(Vin)
** Plot the waveforms
plot v vs vin vin vs vb

write 6t_sram_03v3_snm_tb.raw
.endc

.end
"}
C {vsource.sym} 1240 -770 0 0 {name=Vin value=0 savecurrent=false}
C {gnd.sym} 1240 -740 0 0 {name=l4 lab=0}
C {opin.sym} 1240 -810 3 0 {name=p9 lab=Vin
W=0.22u}
C {ipin.sym} 690 -770 0 1 {name=p7 lab=Vin
W=0.22u}
C {iopin.sym} 310 -860 1 1 {name=p18 sig_type=std_logic lab=BL
W=0.22u}
C {symbols/nfet_03v3.sym} 410 -700 1 0 {name=M11
L=0.28u
W=0.32u
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
C {ipin.sym} 360 -1000 0 0 {name=p19 sig_type=std_logic lab=WL
W=0.22u}
C {iopin.sym} 1160 -860 3 0 {name=p20 sig_type=std_logic lab=BLB
W=0.22u}
C {symbols/nfet_03v3.sym} 1080 -730 1 0 {name=M12
L=0.28u
W=0.32u
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
C {vsource.sym} 1680 -770 0 0 {name=VWL1 value=0 savecurrent=false}
C {gnd.sym} 1680 -720 0 0 {name=l6 lab=0}
C {opin.sym} 1680 -820 3 0 {name=p17 sig_type=std_logic lab=WL
W=0.22u}
C {vsource_arith.sym} 1230 -580 0 0 {name=E1 VOL=V(Vin)/2+V(Ein)}
C {gnd.sym} 1230 -550 0 0 {name=l5 lab=0}
C {opin.sym} 1230 -620 3 0 {name=p10 lab=E1
W=0.22u}
C {vsource_arith.sym} 1370 -580 0 0 {name=E2 VOL=-V(Vin)/2+V(Ein)}
C {gnd.sym} 1370 -550 0 0 {name=l3 lab=0}
C {opin.sym} 1370 -620 3 0 {name=p12 lab=E2
W=0.22u}
C {vsource_arith.sym} 1310 -770 0 0 {name=Ein VOL=(V(Q)+V(Qb))/2}
C {gnd.sym} 1310 -740 0 0 {name=p11 lab=0
W=0.22u}
C {opin.sym} 1310 -810 3 0 {name=p8 lab=Ein
W=0.22u}
C {ipin.sym} 830 -620 2 1 {name=p13 lab=Vin
W=0.22u}
