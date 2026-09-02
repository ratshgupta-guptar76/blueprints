#!/usr/bin/env python3
from reader import click, click_odb


@click.group()
def cli():
    pass


DBU_PER_UM = 2000

# Ring geometry is otherwise deterministic (fixed by CORE_AREA/
# PDN_CORE_RING_V/HOFFSET math in config_core.yaml, not by placement), so
# the ring's *position* can stay hardcoded -- only its Y-extent (west
# side) / X-extent (north side) is queried live.
VSS_RING_X_CENTER = 110080
VDD_RING_Y_CENTER = 2051880
RING_HALF_WIDTH = 25000  # PDN_CORE_RING_V/HWIDTH = 25um

VSS_BRIDGE_X = (0, 144000)  # die edge (x=0) out past the ring's inner edge
VDD_STUB_Y = (2030000, 2220000)  # ring's inner edge up to the die edge (y=1110um)
VDD_VIA_Y_OFFSETS = (10000, 35000)  # two via rows, relative to the stub's y0

# Width of the tie-bar that shorts all of a pad's fingers together. Kept narrow
# deliberately: at ~3.8mA total supply current this is far more metal than the
# current needs, so the only thing extra width would buy is capacitance.
SPINE_WIDTH = 6000  # 3um

# Each strap overhangs its finger by this much. It has to clear two opposing
# constraints: large enough that any step it forms against the ring edge stays
# over the 0.28um min width (an exact-width strap left an 0.08um step), but
# small enough to stay out of the neighbouring finger -- the smallest gap
# between fingers is 1.6um, and the original 3um overhang punched 0.1um into
# the neighbour, which is what caused the M2.1 errors.
STRAP_OVERHANG = 2000  # 1um

# Extra crossbars laid perpendicular to the straps, in addition to the tie-bar
# at the die edge, turning the comb into a mesh. Fractions of the straps' own
# length, so they stay inside whatever extent the straps actually reached.
GRID_CROSSBAR_FRACTIONS = (0.35, 0.60, 0.85)

# The PDK's DRC checks every vertex against a 0.005um grid (`ongrid(0.005)` in
# geom.drc), which is 10 DBU here. Anything computed rather than taken straight
# from the finger table has to be snapped or it trips *_OFFGRID.
MFG_GRID = 10


def snap(v):
    return int(round(v / MFG_GRID)) * MFG_GRID

# A07_A.def's real VSS/VDD pin finger positions (the actual padframe pad
# geometry, in that file's own DBU scale: UNITS DISTANCE MICRONS 200).
# THIS design's DBU scale is 2000/um, so *10 converts template DBU to ours.
_TEMPLATE_DBU_TO_OURS = 10
VSS_PAD_FINGERS_UM200 = [
    (13828, 15728), (11198, 13248), (8828, 10878),
    (6122, 8172), (3752, 5802), (1272, 3172),
]
VDD_PAD_FINGERS_UM200 = [
    (58828, 60728), (56198, 58248), (53828, 55878),
    (51122, 53172), (48752, 50802), (46272, 48172),
]
VSS_PAD_FINGERS = [(lo * _TEMPLATE_DBU_TO_OURS, hi * _TEMPLATE_DBU_TO_OURS) for lo, hi in VSS_PAD_FINGERS_UM200]
VDD_PAD_FINGERS = [(lo * _TEMPLATE_DBU_TO_OURS, hi * _TEMPLATE_DBU_TO_OURS) for lo, hi in VDD_PAD_FINGERS_UM200]


def merge_ranges(ranges):
    ranges = sorted(ranges)
    merged = []
    for lo, hi in ranges:
        if merged and lo <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], hi))
        else:
            merged.append((lo, hi))
    return merged


def find_ring_segments(net, layer_name, fixed_axis, fixed_center, half_width, tol=2000):
    """Collect this net's SBox shapes on `layer_name` whose position along
    the fixed axis matches the ring (not straps/vias elsewhere), and return
    the merged contiguous ranges along the other (varying) axis."""
    ranges = []
    for swire in net.getSWires():
        for box in swire.getWires():
            if box.isVia():
                continue
            if box.getTechLayer() is None or box.getTechLayer().getName() != layer_name:
                continue
            if fixed_axis == "x":
                center = (box.xMin() + box.xMax()) // 2
                width = box.xMax() - box.xMin()
                if abs(center - fixed_center) <= tol and abs(width - 2 * half_width) <= tol:
                    ranges.append((box.yMin(), box.yMax()))
            else:
                center = (box.yMin() + box.yMax()) // 2
                width = box.yMax() - box.yMin()
                if abs(center - fixed_center) <= tol and abs(width - 2 * half_width) <= tol:
                    ranges.append((box.xMin(), box.xMax()))
    return merge_ranges(ranges)


def other_net_boxes(net, layer_name):
    boxes = []
    for swire in net.getSWires():
        for b in swire.getWires():
            if b.isVia():
                continue
            if b.getTechLayer() and b.getTechLayer().getName() == layer_name:
                boxes.append((b.xMin(), b.yMin(), b.xMax(), b.yMax()))
    return boxes


def clip_x1_to_avoid(x0, x1, y0, y1, obstruction_boxes, clearance):
    """Shrink a box's far (x1) edge just short of the nearest obstruction it
    would otherwise overlap, given the box's y-range already overlaps."""
    for ox0, oy0, ox1, oy1 in obstruction_boxes:
        if y1 <= oy0 or oy1 <= y0:
            continue  # no y-overlap, not a real obstruction for this strip
        if ox0 < x1 and ox0 > x0:
            x1 = min(x1, ox0 - clearance)
    return x1


def pick_target_finger(segments, fingers, margin_um=1.25):
    """Pick a real padframe pin finger that's fully contained (with margin)
    in one continuous ring segment, so the bridge both reaches the actual
    pad location AND stays connected to our own ring with no gap."""
    margin = round(margin_um * DBU_PER_UM)
    for lo, hi in fingers:
        want_lo, want_hi = lo - margin, hi + margin
        for seg_lo, seg_hi in segments:
            if seg_lo <= want_lo and want_hi <= seg_hi:
                return want_lo, want_hi, True
    best = None
    for lo, hi in fingers:
        for seg_lo, seg_hi in segments:
            ov_lo, ov_hi = max(lo, seg_lo), min(hi, seg_hi)
            if ov_hi > ov_lo and (best is None or ov_hi - ov_lo > best[1] - best[0]):
                best = (ov_lo, ov_hi)
    if best is None:
        raise RuntimeError("No padframe pin finger overlaps any ring segment at all")
    return best[0], best[1], False


@click.command()
@click_odb
def add_padframe_power_bridge(reader):
    import odb

    block = reader.chip.getBlock()
    tech = reader.tech
    m2 = tech.findLayer("Metal2")
    via = tech.findVia("Via2_4X4H_HH_DEFAULT")

    vss = block.findNet("VSS")
    vdd = block.findNet("VDD")

    # --- VSS: west ring, vary Y, fixed X ---
    vss_segments = find_ring_segments(vss, "Metal2", "x", VSS_RING_X_CENTER, RING_HALF_WIDTH)
    print(f"VSS west ring segments (DBU): {vss_segments}")
    _, _, clean_fit = pick_target_finger(vss_segments, VSS_PAD_FINGERS)
    print(f"VSS ring coverage: at least one finger fits a ring segment={clean_fit}")
    if not clean_fit:
        print("WARNING: no VSS pad finger fully fit inside one continuous ring "
              "segment -- used the best partial overlap instead.")

    vss_x0, _ = VSS_BRIDGE_X
    vdd_m2_boxes = other_net_boxes(vdd, "Metal2")

    vss_swire = odb.dbSWire.create(vss, "ROUTED")

    # One strap per finger. Fingers whose y-range falls inside a ring segment
    # get their own independent path to the ring; the rest still reach it via
    # the tie-bar below, so every finger ends up connected either way.
    vss_strap_x1s = []
    for i, (f_lo, f_hi) in enumerate(VSS_PAD_FINGERS):
        s_lo, s_hi = f_lo - STRAP_OVERHANG, f_hi + STRAP_OVERHANG
        s_x1 = clip_x1_to_avoid(vss_x0, VSS_BRIDGE_X[1], s_lo, s_hi, vdd_m2_boxes, clearance=5000)
        odb.dbSBox.create(vss_swire, m2, vss_x0, s_lo, s_x1, s_hi, "STRIPE")
        vss_strap_x1s.append(s_x1)
        on_ring = any(seg_lo <= s_lo and s_hi <= seg_hi for seg_lo, seg_hi in vss_segments)
        print(f"VSS strap {i}: x=[{vss_x0},{s_x1}] y=[{s_lo},{s_hi}] reaches_ring={on_ring}")

    # Crossbars perpendicular to the straps, turning the comb into a mesh. The
    # first hugs the die edge; the rest are spaced along the straps' shared
    # length, so every crossbar lands on every strap.
    vss_spine_lo = min(lo for lo, _ in VSS_PAD_FINGERS) - STRAP_OVERHANG
    vss_spine_hi = max(hi for _, hi in VSS_PAD_FINGERS) + STRAP_OVERHANG
    vss_reach = min(vss_strap_x1s)
    vss_bar_x = [vss_x0] + [
        snap(vss_x0 + f * (vss_reach - vss_x0 - SPINE_WIDTH))
        for f in GRID_CROSSBAR_FRACTIONS
    ]
    for bx in vss_bar_x:
        odb.dbSBox.create(vss_swire, m2, bx, vss_spine_lo, bx + SPINE_WIDTH, vss_spine_hi, "STRIPE")
    print(f"VSS crossbars at x={vss_bar_x} y=[{vss_spine_lo},{vss_spine_hi}] "
          f"({len(vss_bar_x)} bars x {len(VSS_PAD_FINGERS)} straps)")

    # --- VDD: north ring, vary X, fixed Y ---
    vdd_segments = find_ring_segments(vdd, "Metal3", "y", VDD_RING_Y_CENTER, RING_HALF_WIDTH)
    print(f"VDD north ring segments (DBU): {vdd_segments}")
    _, _, clean_fit = pick_target_finger(vdd_segments, VDD_PAD_FINGERS)
    print(f"VDD ring coverage: at least one finger fits a ring segment={clean_fit}")
    if not clean_fit:
        print("WARNING: no VDD pad finger fully fit inside one continuous ring "
              "segment -- used the best partial overlap instead.")

    vdd_swire = odb.dbSWire.create(vdd, "ROUTED")

    for i, (f_lo, f_hi) in enumerate(VDD_PAD_FINGERS):
        s_lo, s_hi = f_lo - STRAP_OVERHANG, f_hi + STRAP_OVERHANG
        odb.dbSBox.create(vdd_swire, m2, s_lo, VDD_STUB_Y[0], s_hi, VDD_STUB_Y[1], "STRIPE")
        on_ring = any(seg_lo <= s_lo and s_hi <= seg_hi for seg_lo, seg_hi in vdd_segments)
        print(f"VDD strap {i}: x=[{s_lo},{s_hi}] y=[{VDD_STUB_Y[0]},{VDD_STUB_Y[1]}] reaches_ring={on_ring}")

    # Same mesh on the north side: fingers run vertically here, so the crossbars
    # run horizontally. The first hugs the die edge, the rest step down the
    # straps' length.
    vdd_spine_lo = min(lo for lo, _ in VDD_PAD_FINGERS) - STRAP_OVERHANG
    vdd_spine_hi = max(hi for _, hi in VDD_PAD_FINGERS) + STRAP_OVERHANG
    vdd_span = VDD_STUB_Y[1] - VDD_STUB_Y[0]
    vdd_bar_y = [VDD_STUB_Y[1] - SPINE_WIDTH] + [
        snap(VDD_STUB_Y[1] - SPINE_WIDTH - f * (vdd_span - SPINE_WIDTH))
        for f in GRID_CROSSBAR_FRACTIONS
    ]
    for by in vdd_bar_y:
        odb.dbSBox.create(vdd_swire, m2, vdd_spine_lo, by, vdd_spine_hi, by + SPINE_WIDTH, "STRIPE")
    print(f"VDD crossbars at y={vdd_bar_y} x=[{vdd_spine_lo},{vdd_spine_hi}] "
          f"({len(vdd_bar_y)} bars x {len(VDD_PAD_FINGERS)} straps)")

    # The straps are Metal2 but this ring is Metal3, so each strap needs its own
    # vias -- without them only the strap that happens to sit under a via would
    # actually be tied to the ring.
    for i, (f_lo, f_hi) in enumerate(VDD_PAD_FINGERS):
        via_x_center = (f_lo + f_hi) // 2
        half_width = (f_hi - f_lo) // 2
        via_offset = max(0, half_width - 3000)  # keep >=1.5um clear of the strap's own edges
        for dy in VDD_VIA_Y_OFFSETS:
            vy = VDD_STUB_Y[0] + dy
            odb.dbSBox.create(vdd_swire, via, via_x_center - via_offset, vy, "STRIPE")
            odb.dbSBox.create(vdd_swire, via, via_x_center + via_offset, vy, "STRIPE")

    # Final sanity check: confirm neither bridge actually shorts VDD to VSS.
    for layer in ("Metal1", "Metal2", "Metal3", "Metal4", "Metal5"):
        vss_boxes = other_net_boxes(vss, layer)
        vdd_boxes = other_net_boxes(vdd, layer)
        for a in vss_boxes:
            for b in vdd_boxes:
                if not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1]):
                    raise RuntimeError(
                        f"VDD/VSS overlap on {layer} after adding bridges: {a} vs {b}"
                    )
    print("Sanity check passed: no VDD/VSS overlap on any layer.")


cli.add_command(add_padframe_power_bridge)

if __name__ == "__main__":
    cli()
