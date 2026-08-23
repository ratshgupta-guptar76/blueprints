#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
#
# Overlays a finished config_core.yaml GDS (default: final/gds/A07_dcim_top.gds)
# onto the real A07_A padframe (def/A07/project_defs/A/A07_A_padring.def) so
# you can see it sitting inside the actual padring, and renders a PNG.
#
# This is a visualization aid only -- config_core.yaml never produces this
# merged view itself, and this is not a submission artifact. The padring GDS
# is generated from the organizers' own DEF via LibreLane's KLayout
# stream_out.py helper (same LEF/GDS library paths LibreLane already uses for
# this design -- see any run's 57-klayout-streamout/COMMANDS) and cached,
# since the padring itself never changes between reruns of the core flow.

import argparse
import subprocess
import sys
import yaml
from pathlib import Path

import klayout.db as db

REPO_ROOT = Path(__file__).resolve().parent.parent
LIBRELANE_SCRIPTS = None  # resolved lazily, see find_stream_out_script()

PADRING_DEF = REPO_ROOT / "def/A07/project_defs/A/A07_A_padring.def"
INTERFACE_YAML = REPO_ROOT / "def/A07/project_defs/A/A07_A_interface.yaml"


def find_stream_out_script() -> Path:
    import librelane

    return Path(librelane.__file__).parent / "scripts" / "klayout" / "stream_out.py"


def io_lef_gds_args(pdk_root: Path, pdk: str, scl: str) -> list[str]:
    gf180 = pdk_root / pdk
    io_dir = gf180 / "libs.ref" / "gf180mcu_fd_io"
    lefs = sorted((io_dir / "lef").glob("*.lef"))
    gds_files = [
        io_dir / "gds" / "gf180mcu_fd_io.gds",
        io_dir / "gds" / "gf180mcu_ef_io.gds",
        io_dir / "gds" / "gf180mcu_ws_io.gds",
    ]
    args = []
    for lef in lefs:
        args += ["--input-lef", str(lef)]
    for gds in gds_files:
        args += ["--with-gds-file", str(gds)]
    return args


def build_padring_gds(pdk_root: Path, pdk: str, scl: str, out_gds: Path, force: bool):
    if out_gds.exists() and not force:
        print(f"[render_full_chip] reusing cached padring GDS: {out_gds}")
        return

    gf180 = pdk_root / pdk
    tech = gf180 / "libs.tech" / "klayout" / "tech"
    out_gds.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable,
        str(find_stream_out_script()),
        str(PADRING_DEF),
        "--output", str(out_gds),
        "--top", "A07_A_padring",
        "--conflict-resolution", "RenameCell",
        "--lyp", str(tech / "gf180mcu.lyp"),
        "--lyt", str(tech / "gf180mcu.lyt"),
        "--lym", str(tech / "gf180mcu.map"),
    ] + io_lef_gds_args(pdk_root, pdk, scl)

    print(f"[render_full_chip] streaming padring DEF -> GDS: {out_gds}")
    subprocess.run(cmd, check=True)


def merge(core_gds: Path, padring_gds: Path, out_gds: Path, offset_um: tuple[float, float]):
    merged = db.Layout()
    merged.dbu = 0.001

    merged.read(str(padring_gds))
    pad_idx = merged.cell_by_name("A07_A_padring")

    core_ly = db.Layout()
    core_ly.read(str(core_gds))
    core_top_name = core_ly.top_cell().name

    merged.read(str(core_gds))
    core_idx = merged.cell_by_name(core_top_name)

    full = merged.create_cell("A07_full_chip")
    full.insert(db.CellInstArray(pad_idx, db.Trans(db.Vector(0, 0))))

    ox = int(round(offset_um[0] / merged.dbu))
    oy = int(round(offset_um[1] / merged.dbu))
    full.insert(db.CellInstArray(core_idx, db.Trans(db.Vector(ox, oy))))

    opts = db.SaveLayoutOptions()
    opts.gds2_write_timestamps = False
    merged.write(str(out_gds), opts)
    print(f"[render_full_chip] wrote merged GDS: {out_gds}")


def render(gds: Path, out_png_base: Path, pdk_root: Path, pdk: str, width: int, oversampling: int):
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    import lay2img

    lay2img.main(str(gds), str(out_png_base), width, None, oversampling, str(pdk_root), pdk)
    print(f"[render_full_chip] wrote {out_png_base.with_name(out_png_base.stem + '_white.png')}")
    print(f"[render_full_chip] wrote {out_png_base.with_name(out_png_base.stem + '_black.png')}")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--core-gds", default=str(REPO_ROOT / "final/gds/A07_dcim_top.gds"))
    ap.add_argument("--out-dir", default=str(REPO_ROOT / "def/A07/render"))
    ap.add_argument("--pdk-root", default=str(REPO_ROOT / "gf180mcu"))
    ap.add_argument("--pdk", default="gf180mcuD")
    ap.add_argument("--scl", default="gf180mcu_as_sc_mcu7t3v3")
    ap.add_argument("--force-padring", action="store_true", help="regenerate the cached padring GDS")
    ap.add_argument("--width", type=int, default=2048)
    ap.add_argument("--oversampling", type=int, default=4)
    args = ap.parse_args()

    core_gds = Path(args.core_gds)
    if not core_gds.exists():
        sys.exit(f"core GDS not found: {core_gds} (did the flow reach KLayout.StreamOut?)")

    out_dir = Path(args.out_dir)
    pdk_root = Path(args.pdk_root)

    interface = yaml.safe_load(INTERFACE_YAML.read_text())
    offset_um = tuple(float(v) for v in interface["origin_microns"])
    print(f"[render_full_chip] core origin inside padframe: {offset_um} um (from {INTERFACE_YAML.name})")

    padring_gds = out_dir / "A07_A_padring.klayout.gds"
    build_padring_gds(pdk_root, args.pdk, args.scl, padring_gds, args.force_padring)

    merged_gds = out_dir / "A07_full_chip.gds"
    merge(core_gds, padring_gds, merged_gds, offset_um)

    render(merged_gds, out_dir / "A07_full_chip", pdk_root, args.pdk, args.width, args.oversampling)


if __name__ == "__main__":
    main()
