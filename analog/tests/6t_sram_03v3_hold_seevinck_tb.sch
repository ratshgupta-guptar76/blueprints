v {xschem version=3.4.8RC file_version=1.3}
G {}
K {}
V {}
S {}
F {}
E {}
N -400 -220 -400 -180 {lab=Q}
N -400 -290 -400 -280 {lab=vdd}
N -400 -70 -400 -60 {lab=vss}
N -420 -100 -400 -100 {lab=vss}
N -420 -100 -420 -70 {lab=vss}
N -420 -250 -400 -250 {lab=vdd}
N -420 -280 -420 -250 {lab=vdd}
N -30 -220 -30 -130 {lab=Qb}
N -30 -290 -30 -280 {lab=vdd}
N -30 -70 -30 -60 {lab=vss}
N -30 -100 -10 -100 {lab=vss}
N -10 -100 -10 -70 {lab=vss}
N -30 -250 -10 -250 {lab=vdd}
N -10 -280 -10 -250 {lab=vdd}
N -400 -180 -400 -130 {lab=Q}
N -30 -350 -30 -290 {lab=vdd}
N -400 -350 -30 -350 {lab=vdd}
N -230 -380 -230 -350 {lab=vdd}
N -400 -350 -400 -290 {lab=vdd}
N -30 -60 -30 0 {lab=vss}
N -400 0 -30 0 {lab=vss}
N -400 -60 -400 0 {lab=vss}
N -220 0 -220 20 {lab=vss}
N -100 -250 -70 -250 {lab=Ein2}
N -100 -250 -100 -100 {lab=Ein2}
N -100 -100 -70 -100 {lab=Ein2}
N -360 -250 -330 -250 {lab=Ein1}
N -360 -100 -330 -100 {lab=Ein1}
N -420 -70 -420 0 {lab=vss}
N -10 -70 -10 0 {lab=vss}
N -420 -350 -400 -350 {lab=vdd}
N -420 -350 -420 -280 {lab=vdd}
N -30 -350 -10 -350 {lab=vdd}
N -10 -350 -10 -280 {lab=vdd}
N 260 -300 260 -280 {lab=vdd}
N 260 -220 260 -200 {lab=0}
N 340 -300 340 -280 {lab=vss}
N 340 -220 340 -200 {lab=0}
N -30 0 -10 0 {lab=vss}
N -420 0 -400 0 {lab=vss}
N -330 -250 -330 -100 {lab=Ein1}
N 260 -70 260 -60 {lab=Vu}
N -330 -250 -290 -250 {lab=Ein1}
N -670 -340 -670 10 {lab=BL}
N -670 -160 -600 -160 {lab=BL}
N -570 -160 -570 -140 {lab=vss}
N -570 -480 -570 -200 {lab=WL}
N -620 -480 -570 -480 {lab=WL}
N -570 -140 -570 0 {lab=vss}
N -570 0 -420 0 {lab=vss}
N 180 -340 180 10 {lab=BLB}
N 130 -190 160 -190 {lab=BLB}
N 100 -190 100 -170 {lab=vss}
N 100 -480 100 -230 {lab=WL}
N 100 -170 100 0 {lab=vss}
N 160 -190 180 -190 {lab=BLB}
N -10 0 100 0 {lab=vss}
N -570 -480 100 -480 {lab=WL}
N 480 -300 480 -280 {lab=WL}
N 480 -220 480 -200 {lab=0}
N -30 -190 70 -190 {lab=Qb}
N -540 -160 -400 -160 {lab=Q}
N 340 -60 340 -50 {lab=E_v1}
N 480 -60 480 -50 {lab=E_v2}
N -150 -100 -100 -100 {lab=Ein2}
N 340 130 340 140 {lab=Ein1}
N 510 130 510 140 {lab=Ein2}
C {symbols/nfet_03v3.sym} -380 -100 0 1 {name=M1
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
C {symbols/pfet_03v3.sym} -380 -250 0 1 {name=M2
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
C {ipin.sym} -230 -380 3 1 {name=p1 lab=vdd
W=0.22u}
C {symbols/nfet_03v3.sym} -50 -100 0 0 {name=M3
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
C {symbols/pfet_03v3.sym} -50 -250 0 0 {name=M4
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
C {lab_wire.sym} -400 -160 0 1 {name=p4 sig_type=std_logic lab=Q
W=0.22u}
C {ipin.sym} -220 20 3 0 {name=p5 lab=vss
W=0.22u}
C {lab_wire.sym} -30 -190 0 0 {name=p6 sig_type=std_logic lab=Qb
W=0.22u}
C {vsource.sym} 260 -250 0 0 {name=VDD value=3.3 savecurrent=false}
C {opin.sym} 260 -300 1 1 {name=p2 lab=vdd
W=0.22u}
C {gnd.sym} 260 -200 0 0 {name=l1 lab=0}
C {vsource.sym} 340 -250 0 0 {name=VSS value=0 savecurrent=false}
C {gnd.sym} 340 -200 0 0 {name=l2 lab=0}
C {opin.sym} 340 -300 3 0 {name=p3 lab=vss
W=0.22u}
C {devices/code_shown.sym} 230 -440 0 0 {name=MODELS only_toplevel=true
format="tcleval( @value )"
value="
.include $::180MCU_MODELS/design.ngspice
.lib $::180MCU_MODELS/sm141064.ngspice typical
"}
C {devices/code_shown.sym} 830 -410 0 0 {name=NGSPICE only_toplevel=true
value="
.control
save all

** DC analysis 
dc Vu -1.65 1.65 0.001
let diff = (v(E_v1) - v(E_v2))/sqrt(2)
plot diff vs v(Vu)

meas DC snm MAX diff

write 6t_sram_03v3_snm_tb.raw
.endc

.end
"}
C {vsource.sym} 260 -30 0 0 {name=Vu value=DC savecurrent=false}
C {gnd.sym} 260 0 0 0 {name=l4 lab=0}
C {opin.sym} 260 -70 3 0 {name=p9 lab=Vu
W=0.22u}
C {iopin.sym} -670 -340 1 1 {name=p18 sig_type=std_logic lab=BL
W=0.22u}
C {symbols/nfet_03v3.sym} -570 -180 1 0 {name=M11
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
C {ipin.sym} -620 -480 0 0 {name=p19 sig_type=std_logic lab=WL
W=0.22u}
C {iopin.sym} 180 -340 3 0 {name=p20 sig_type=std_logic lab=BLB
W=0.22u}
C {symbols/nfet_03v3.sym} 100 -210 1 0 {name=M12
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
C {vsource.sym} 480 -250 0 0 {name=VWL1 value=0 savecurrent=false}
C {gnd.sym} 480 -200 0 0 {name=l6 lab=0}
C {opin.sym} 480 -300 3 0 {name=p17 sig_type=std_logic lab=WL
W=0.22u}
C {vsource_arith.sym} 340 -20 0 0 {name=E_v1 VOL=sqrt(2)*V(Q)+V(Vu)}
C {gnd.sym} 340 10 0 0 {name=l5 lab=0}
C {opin.sym} 340 -60 3 0 {name=p10 lab=E_v1
W=0.22u}
C {vsource_arith.sym} 480 -20 0 0 {name=E_v2 VOL=sqrt(2)*V(Qb)-V(Vu)}
C {gnd.sym} 480 10 0 0 {name=l3 lab=0}
C {opin.sym} 480 -60 3 0 {name=p12 lab=E_v2
W=0.22u}
C {vsource_arith.sym} 340 170 0 0 {name=Ein1 VOL=(V(E_v1)+V(Vu))/sqrt(2)}
C {gnd.sym} 340 200 0 0 {name=l7 lab=0}
C {opin.sym} 340 130 3 0 {name=p7 lab=Ein1
W=0.22u}
C {vsource_arith.sym} 510 170 0 0 {name=Ein2 VOL=(V(E_v2)-V(Vu))/sqrt(2)}
C {gnd.sym} 510 200 0 0 {name=l8 lab=0}
C {opin.sym} 510 130 3 0 {name=p8 lab=Ein2
W=0.22u}
C {ipin.sym} -290 -250 0 1 {name=p11 lab=Ein1
W=0.22u}
C {ipin.sym} -150 -100 2 1 {name=p13 lab=Ein2
W=0.22u}
