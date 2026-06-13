# Analog Workspace

Full-custom design of the CIM 8T bitcell macro. This folder is **mounted into
the IIC-OSIC-TOOLS container** — it is not a container image itself. The Nix
shell at the repo root is the *digital* (LibreLane) environment and does **not**
ship Xschem or ngspice, so all schematic + SPICE work happens here in the
container.

## Layout

```
analog/
  start_vnc.sh        # launch IIC-OSIC-TOOLS (Xschem/ngspice/Magic/KLayout/Netgen + GF180 PDK)
  xschem/       # schematics (.sch) and symbols (.sym): 8T cell, array, WL/BL drivers
  spice/        # extracted netlists + SPICE testbenches (.spice, .meas)
  magic/        # layout (.mag) + .magicrc
  sim/          # ngspice outputs / waveforms (raw data — safe to delete/regenerate)
```

## Start the environment

```bash
./start_vnc.sh                 # docker (default)
ENGINE=podman ./start_vnc.sh   # podman instead
```

Then open **http://localhost:80** (password `abc123`) in a browser, or connect a
VNC client to `vnc://localhost:5901`. Stop with `./start_vnc.sh stop`.

Inside the container this folder is mounted directly at `/foss/designs`.

> **Always use VNC for the GUIs**, not host X11: Xwayland breaks Xschem's Tk
> right-click menus, and KLayout falls back to slow software rendering under X11.
> Set the `asusctl` profile to Performance on AC before long SPICE/DRC runs.

## Tool flow

| Step | Tool | Output |
|------|------|--------|
| Schematic | `xschem` | `xschem/*.sch`, exported netlist → `spice/` |
| Characterize | `ngspice` | read/write margins, stability (Seevinck), `sim/` |
| Layout | `magic` | `magic/*.mag` |
| DRC | `magic` / `klayout` | clean layout |
| Extract + LVS | `magic` (PEX) + `netgen` | schematic-vs-layout match |

## Handoff to the digital flow

The **hardened views** the LibreLane flow consumes do **not** live here — once the
macro is laid out and signed off, export its `.gds`, `.lef`, and `.lib` into the
IP directory:

```
ip/cim8t_64x64/{gds,lef,lib,vh}/
```

and declare it in `librelane/macros/*.yaml`. Keep this `analog/` folder for the
*sources* (schematic/layout/spice); keep `ip/cim8t_64x64/` for the *built views*.
Pin the macro's port/interface contract so the analog and digital halves agree on
the boundary.
