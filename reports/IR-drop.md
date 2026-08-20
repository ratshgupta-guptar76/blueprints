# IRDrop Report

> rpt

```rst
[INFO PSM-0040] All shapes on net VDD are connected.
[INFO PSM-0073] Using bump pattern with x-pitch 140.0000um, y-pitch 140.0000um, and size 70.0000um with an reduction factor of 3x.
########## IR report #################
########## IR report #################
Net              : VDD
Corner           : nom_tt_025C_3v30
Total power      : 1.26e-02 W
Supply voltage   : 3.30e+00 V
Worstcase voltage: 3.30e+00 V
Average voltage  : 3.30e+00 V
Average IR drop  : 4.80e-05 V
Worstcase IR drop: 2.27e-04 V
Percentage drop  : 0.01 %
######################################
+ analyze_power_grid -net VSS -voltage_file /home/ratishgupta/vlsi/blueprints/librelane/runs/RUN_2026-08-20_10-36-25/55-openroad-irdropreport/net-VSS.csv
[INFO PSM-0040] All shapes on net VSS are connected.
[INFO PSM-0073] Using bump pattern with x-pitch 140.0000um, y-pitch 140.0000um, and size 70.0000um with an reduction factor of 3x.
########## IR report #################
Net              : VSS
Corner           : nom_tt_025C_3v30
Total power      : 1.26e-02 W
Supply voltage   : 0.00e+00 V
Worstcase voltage: 2.57e-04 V
Average voltage  : 4.89e-05 V
Average IR drop  : 4.89e-05 V
Worstcase IR drop: 2.57e-04 V
Percentage drop  : 0.01 %
######################################
%OL_END_REPORT

```