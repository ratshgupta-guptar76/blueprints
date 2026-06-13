v {xschem version=3.4.8RC file_version=1.3}
G {}
K {}
V {}
S {}
F {}
E {}
N 650 -500 650 -460 {lab=Q}
N 650 -570 650 -560 {lab=vdd}
N 650 -350 650 -340 {lab=vss}
N 630 -380 650 -380 {lab=vss}
N 630 -380 630 -350 {lab=vss}
N 630 -530 650 -530 {lab=vdd}
N 630 -560 630 -530 {lab=vdd}
N 1020 -500 1020 -410 {lab=Qb}
N 1020 -570 1020 -560 {lab=vdd}
N 1020 -350 1020 -340 {lab=vss}
N 1020 -380 1040 -380 {lab=vss}
N 1040 -380 1040 -350 {lab=vss}
N 1020 -530 1040 -530 {lab=vdd}
N 1040 -560 1040 -530 {lab=vdd}
N 650 -460 650 -410 {lab=Q}
N 1020 -630 1020 -570 {lab=vdd}
N 650 -630 1020 -630 {lab=vdd}
N 820 -660 820 -630 {lab=vdd}
N 650 -630 650 -570 {lab=vdd}
N 1020 -340 1020 -280 {lab=vss}
N 650 -280 1020 -280 {lab=vss}
N 650 -340 650 -280 {lab=vss}
N 830 -280 830 -260 {lab=vss}
N 950 -530 980 -530 {lab=Vin}
N 950 -530 950 -380 {lab=Vin}
N 950 -380 980 -380 {lab=Vin}
N 690 -530 720 -530 {lab=Vin}
N 690 -380 720 -380 {lab=Vin}
N 630 -350 630 -280 {lab=vss}
N 1040 -350 1040 -280 {lab=vss}
N 630 -630 650 -630 {lab=vdd}
N 630 -630 630 -560 {lab=vdd}
N 1020 -630 1040 -630 {lab=vdd}
N 1040 -630 1040 -560 {lab=vdd}
N 1530 -580 1530 -560 {lab=vdd}
N 1530 -500 1530 -480 {lab=0}
N 1610 -580 1610 -560 {lab=vss}
N 1610 -500 1610 -480 {lab=0}
N 1020 -280 1040 -280 {lab=vss}
N 630 -280 650 -280 {lab=vss}
N 720 -530 720 -380 {lab=Vin}
N 1380 -570 1380 -560 {lab=Vin}
N 720 -530 760 -530 {lab=Vin}
N 380 -620 380 -270 {lab=BL}
N 380 -440 450 -440 {lab=BL}
N 480 -440 480 -420 {lab=vss}
N 480 -760 480 -480 {lab=WL}
N 430 -760 480 -760 {lab=WL}
N 480 -420 480 -280 {lab=vss}
N 480 -280 630 -280 {lab=vss}
N 1230 -620 1230 -270 {lab=BLB}
N 1180 -470 1210 -470 {lab=BLB}
N 1150 -470 1150 -450 {lab=vss}
N 1150 -760 1150 -510 {lab=WL}
N 1150 -450 1150 -280 {lab=vss}
N 1210 -470 1230 -470 {lab=BLB}
N 1040 -280 1150 -280 {lab=vss}
N 480 -760 1150 -760 {lab=WL}
N 1750 -580 1750 -560 {lab=WL}
N 1750 -500 1750 -480 {lab=0}
N 1020 -470 1120 -470 {lab=Qb}
N 510 -440 650 -440 {lab=Q}
N 900 -380 950 -380 {lab=Vin}
N 380 -290 400 -290 {lab=BL}
N 460 -290 480 -290 {lab=vss}
N 1220 -300 1230 -300 {lab=BLB}
N 1150 -300 1160 -300 {lab=vss}
C {symbols/nfet_03v3.sym} 670 -380 0 1 {name=M1
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
C {symbols/pfet_03v3.sym} 670 -530 0 1 {name=M2
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
C {ipin.sym} 820 -660 3 1 {name=p1 lab=vdd
W=0.22u}
C {symbols/nfet_03v3.sym} 1000 -380 0 0 {name=M3
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
C {symbols/pfet_03v3.sym} 1000 -530 0 0 {name=M4
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
C {lab_wire.sym} 650 -440 0 1 {name=p4 sig_type=std_logic lab=Q
W=0.22u}
C {ipin.sym} 830 -260 3 0 {name=p5 lab=vss
W=0.22u}
C {lab_wire.sym} 1020 -470 0 0 {name=p6 sig_type=std_logic lab=Qb
W=0.22u}
C {vsource.sym} 1530 -530 0 0 {name=VDD value=3.3 savecurrent=false}
C {opin.sym} 1530 -580 1 1 {name=p2 lab=vdd
W=0.22u}
C {gnd.sym} 1530 -480 0 0 {name=l1 lab=0}
C {vsource.sym} 1610 -530 0 0 {name=VSS value=0 savecurrent=false}
C {gnd.sym} 1610 -480 0 0 {name=l2 lab=0}
C {opin.sym} 1610 -580 3 0 {name=p3 lab=vss
W=0.22u}
C {devices/code_shown.sym} 1280 -720 0 0 {name=MODELS only_toplevel=true
format="tcleval( @value )"
value="
.include $::180MCU_MODELS/design.ngspice
.lib $::180MCU_MODELS/sm141064.ngspice typical
"}
C {devices/code_shown.sym} 1880 -690 0 0 {name=NGSPICE only_toplevel=true
value="
.options savecurrents
.control
save all

** DC analysis 
dc Vin 0 3.3 0.1

let v = v(Q)
let vb = v(Qb)
let vin = v(Vin)
** Plot the waveforms
plot v vs vin vin vs vb

write 6t_sram_03v3_snm_tb.raw
.endc

.end
"}
C {vsource.sym} 1380 -530 0 0 {name=Vin value=0 savecurrent=false}
C {gnd.sym} 1380 -500 0 0 {name=l4 lab=0}
C {opin.sym} 1380 -570 3 0 {name=p9 lab=Vin
W=0.22u}
C {ipin.sym} 760 -530 0 1 {name=p7 lab=Vin
W=0.22u}
C {iopin.sym} 380 -620 1 1 {name=p18 sig_type=std_logic lab=BL
W=0.22u}
C {symbols/nfet_03v3.sym} 480 -460 1 0 {name=M11
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
C {ipin.sym} 430 -760 0 0 {name=p19 sig_type=std_logic lab=WL
W=0.22u}
C {iopin.sym} 1230 -620 3 0 {name=p20 sig_type=std_logic lab=BLB
W=0.22u}
C {symbols/nfet_03v3.sym} 1150 -490 1 0 {name=M12
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
C {vsource.sym} 1750 -530 0 0 {name=VWL value=3.3 savecurrent=false}
C {gnd.sym} 1750 -480 0 0 {name=l6 lab=0}
C {opin.sym} 1750 -580 3 0 {name=p17 sig_type=std_logic lab=WL
W=0.22u}
C {ipin.sym} 900 -380 2 1 {name=p13 lab=Vin
W=0.22u}
C {capa.sym} 1190 -300 1 0 {name=C1
m=1
value=20f
footprint=1206
device="ceramic capacitor"}
C {capa.sym} 430 -290 1 0 {name=C2
m=1
value=20f
footprint=1206
device="ceramic capacitor"}
