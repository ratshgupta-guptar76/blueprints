# Analog Workspace

Full-custom design of the CIM 8T bitcell macro. This folder is **mounted into
the IIC-OSIC-TOOLS container** — it is not a container image itself. The Nix
shell at the repo root is the *digital* (LibreLane) environment and does **not**
ship Xschem or ngspice, so all schematic + SPICE work happens here in the
container.

## Layout

```
scripts/start_vnc.sh  # launcher (at repo root): IIC-OSIC-TOOLS + GF180 PDK
analog/               # this folder — mounted to /foss/designs in the container
  xschem/       # schematics (.sch) and symbols (.sym): 8T cell, array, WL/BL drivers
  spice/        # extracted netlists + SPICE testbenches (.spice, .meas)
  magic/        # layout (.mag) + .magicrc
  sim/          # ngspice outputs / waveforms (raw data — safe to delete/regenerate)
```

## Start the environment

Run from the repo root:

```bash
scripts/start_vnc.sh                 # docker (default)
ENGINE=podman scripts/start_vnc.sh   # podman instead
```

Then open **http://localhost:80** (password `abc123`) in a browser, or connect a
VNC client to `vnc://localhost:5901`. Stop with `scripts/start_vnc.sh stop`.

### Display options

Override via environment variables (set at launch; restart to change):

| Var | Default | Effect |
|-----|---------|--------|
| `VNC_RESOLUTION` | `1920x1080` | Desktop resolution, `WIDTHxHEIGHT`. |
| `SCALE` | `1` | Pixel scale: framebuffer = `VNC_RESOLUTION * SCALE`. Smaller = bigger UI. Must be > 0. |
| `VNC_PW` | `abc123` | VNC password. |
| `ENGINE` | `docker` | Container engine (`docker` or `podman`). |

```bash
VNC_RESOLUTION=2560x1440 scripts/start_vnc.sh            # higher resolution
SCALE=0.5 scripts/start_vnc.sh                           # 2x bigger UI
VNC_RESOLUTION=2560x1440 SCALE=0.5 scripts/start_vnc.sh  # -> 1280x720
```

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
