"""Pin-level, cycle-accurate model of the DCIM v2 chip, written from
docs/V2_SPEC.md (never from RTL).

    sim.py     event kernel: several unrelated clocks, optional metastability
    crc.py     the link CRC and the self-test generators
    chip.py    the chip: four clock domains, the crossings between them
    fpga.py    what sits on the other side of the pins: link, SPI, JTAG drivers
    __main__   scenarios that check the spec and measure its cycle counts

Run from the repository root:  python3 -m model.chip_v2
"""
