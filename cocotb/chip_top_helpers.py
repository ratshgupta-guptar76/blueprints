# SPDX-FileCopyrightText: 2026 Chipathon 2026 workshop
# SPDX-License-Identifier: Apache-2.0
"""Drive/compute helpers shared by chip_top_tb.py's tests."""
import os

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, RisingEdge, Timer

from golden_model import ACC_WIDTH, DW, N_WEIGHTS, ROWS

gl = os.getenv("GL") == "1"

# Input pad bit indices -- mirrors the localparams in chip_core.sv. (busy/done/
# y_bit are output pads too, but they're read via the internal RTL signal
# instead -- see _busy()/_done()/_y_bit() below.)
PAD_A_BIT = 0
PAD_W_BIT = 1
PAD_START = 2
PAD_CONT = 3
PAD_PMINUS1 = (19, 18, 17)  # P_minus1[0], [1], [2]


def _drive_control(dut, *, a_bit=0, w_bit=0, start=0, cont=0, p_minus1=DW - 1):
    """Drive the bidir pads chip_core reads as inputs (a_bit/w_bit/start/cont/
    P_minus1); every other bidir pad is a chip_core *output*, so leave it high-Z."""
    width = len(dut.bidir_PAD)
    bus = ["z"] * width

    def set_bit(bit, value):
        bus[width - 1 - bit] = "1" if value else "0"

    set_bit(PAD_A_BIT, a_bit)
    set_bit(PAD_W_BIT, w_bit)
    set_bit(PAD_START, start)
    set_bit(PAD_CONT, cont)
    for i, pad in enumerate(PAD_PMINUS1):
        set_bit(pad, (p_minus1 >> i) & 1)

    dut.bidir_PAD.value = "".join(bus)


_gl_handle_cache = {}


def _internal(dut, rtl_path):
    # bidir_PAD readback goes through real switch-level pad cells with specify-
    # block propagation delay, so it isn't valid at the same edge -- tap the
    # internal signal directly instead (as the original smoke test did).
    #
    # In GL mode there's no real hierarchy to walk: Yosys flattens submodule
    # instances but keeps the original dotted names as single, literal wire
    # names (Verilog escaped identifiers), e.g. the net named exactly
    # "i_chip_core.U_DCIM_TOP.CONTROL_FSM.busy". dut[name]/dut._id(name) both
    # fail to resolve this via icarus's VPI (vpi_handle_by_name apparently
    # doesn't accept the un-escaped dotted string the same way vpi_iterate
    # reports it), so iterate dut's children once and cache by name instead.
    if gl:
        if not _gl_handle_cache:
            for h in dut:
                _gl_handle_cache[h._name] = h
        return _gl_handle_cache[rtl_path]
    obj = dut
    for part in rtl_path.split("."):
        obj = getattr(obj, part)
    return obj


def _busy(dut):
    return int(_internal(dut, "i_chip_core.busy" if not gl else "i_chip_core.U_DCIM_TOP.CONTROL_FSM.busy").value)


def _done(dut):
    return int(_internal(dut, "i_chip_core.done" if not gl else "i_chip_core.U_DCIM_TOP.CONTROL_FSM.done").value)


def _y_bit(dut):
    # No GL path: this specific net gets optimized/renamed away during
    # synthesis (only SERIAL_STREAM_OUTPUT's acc[*] survives with a stable
    # name), so this is only ever called in RTL mode -- see the GL scoping
    # note on chip_top_smoke_runner/test skips.
    assert not gl, "_y_bit has no working GL path; don't call it in GL mode"
    return int(_internal(dut, "i_chip_core.y_bit").value)


async def _start_up(dut):
    dut.input_PAD.value = 0
    _drive_control(dut)

    cocotb.start_soon(Clock(dut.clk_PAD, 20, unit="ns").start())

    dut.rst_n_PAD.value = 0
    await Timer(100, unit="ns")
    dut.rst_n_PAD.value = 1
    await ClockCycles(dut.clk_PAD, 2)


async def _pulse_start(dut, p_minus1):
    """IDLE -> WRITE_W is unregistered (gated only on `start`), so the very next
    edge after the start pulse already has WRITE_W's w_bit capture active."""
    _drive_control(dut, start=1, p_minus1=p_minus1)
    await RisingEdge(dut.clk_PAD)
    _drive_control(dut, p_minus1=p_minus1)


async def _load_weights(dut, W, p_minus1):
    """WRITE_W: ROWS*COLS bits (COLS = N_WEIGHTS*DW). Column c holds bit (c % DW)
    of weight (c // DW) -- weight 0 first, LSB-first within each weight -- because
    weight_load.sv's shifter enters new bits at the MSB and the bit sent first ends
    up at w_buf[0] after COLS shifts (see dcim_array.sv's WBL wiring)."""
    for row in range(ROWS):
        for w_idx in range(N_WEIGHTS):
            value = int(W[row, w_idx]) & ((1 << DW) - 1)
            for bit in range(DW):
                _drive_control(dut, w_bit=(value >> bit) & 1, p_minus1=p_minus1)
                await RisingEdge(dut.clk_PAD)


def _activation_bits(a):
    """The DW*ROWS activation bitstream in wire order: reversed(range(ROWS)),
    each row's DW bits LSB-first (see _load_activations)."""
    bits = []
    for row in reversed(range(ROWS)):
        value = int(a[row]) & ((1 << DW) - 1)
        for bit in range(DW):
            bits.append((value >> bit) & 1)
    return bits


async def _load_activations(dut, a, p_minus1, skip_first=False):
    """WRITE_A: DW*ROWS bits. act_shift_chain.sv is ROWS shift_reg cells daisy-
    chained head-to-tail (row 0 = head, nearest a_bit). Because the whole chain
    keeps shifting toward the tail every cycle, the row sent *last* travels the
    least and ends up in the head cell (row 0) -- so rows must be sent in REVERSE
    order (ROWS-1 .. 0), each row's DW bits LSB-first (bit0 lands in that cell's
    sr[0], per shift_reg.sv).

    `skip_first` must be True when this pass's first bit was already driven
    and captured by the *previous* pass's cont-continuation edge -- see
    _compute_and_drain's trailing-edge handling."""
    bits = _activation_bits(a)
    for value in bits[1:] if skip_first else bits:
        _drive_control(dut, a_bit=value, p_minus1=p_minus1)
        await RisingEdge(dut.clk_PAD)


async def _start_weights(dut, W, p_minus1):
    """IDLE -> WRITE_W -> WRITE_A boundary: pulse start, load ROWS*COLS weight
    bits, then cross the wfull registration bubble. Leaves the DUT ready for
    _compute_and_drain's activation load on the very next edge.

    CAUTION: during this bubble edge, wshift_en is still active (state is still
    WRITE_W going into it) -- weight_load.sv takes one extra, unintended shift
    (of whatever w_bit=0 happens to be driven), permanently shifting wload_cnt's
    phase by one for the *next* time WRITE_W is entered (unlike stream_out's
    counter, wload_cnt has no equivalent fresh-reload each pass, only a hard
    reset). So this function must only be called right after a hard reset
    (_start_up) -- never call it twice in the same test without an intervening
    _start_up, or the second weight load will silently corrupt. Use the `cont`
    weight-stationary path (_compute_and_drain with cont=1) to reuse a loaded
    weight matrix across multiple activation vectors instead."""
    await _pulse_start(dut, p_minus1)
    await _load_weights(dut, W, p_minus1)

    # WRITE_W -> WRITE_A is gated on `wfull`, which weight_load.sv registers one
    # cycle after the 32nd (COLS-th) weight bit -- so there is exactly one bubble
    # cycle here where a_en is still 0 and no activation bit is captured.
    _drive_control(dut, p_minus1=p_minus1)
    await RisingEdge(dut.clk_PAD)


async def _compute_and_drain(
    dut, a, p_minus1, cont, first=False, skip_first_bit=False, next_a=None, next_p_minus1=None
):
    """WRITE_A -> COMPUTE -> DONE -> SHIFT_OUT for one activation vector, and
    return the N_WEIGHTS signed accumulator lanes (two's-complement, ACC_WIDTH
    bits each). `cont` is held through the whole drain (control_fsm samples it
    at SHIFT_OUT's y_done, not at DONE) -- if cont=1, the DUT is left ready for
    another _compute_and_drain call reusing the same loaded weights; if cont=0,
    it's left back in IDLE. Safe to call repeatedly (stream_out's counter is
    freshly reloaded every DONE, unlike weight_load's -- see _start_weights).

    `first` must be True only for the very first COMPUTE entry since the last
    hard reset (i.e. the call right after _start_weights): that COMPUTE phase
    empirically takes one cycle longer to reach DONE (P_minus1 + 2 edges from
    the last activation edge) than every subsequent COMPUTE entry does
    (P_minus1 + 1, matching the FSM comment) -- the same "first entry into a
    phase is one cycle slower" pattern _start_weights documents for WRITE_W.

    `skip_first_bit`/`next_a`/`next_p_minus1`: the SHIFT_OUT->WRITE_A(cont)
    boundary edge is ALREADY the first real a_en-active capture edge of the
    next pass (confirmed by comparing the actual driven a_bit sequence against
    the intended one in a waveform dump: every captured bit matched the
    *previous* intended bit, i.e. the whole 256-bit stream landed shifted by
    exactly one position, silently dropping the true last bit -- there is no
    extra "free" bubble edge here the way there is for WRITE_W->WRITE_A). So
    when `cont` is set, this call must drive `next_a`'s real first bit on its
    trailing edge (instead of a default 0), and the *next* _compute_and_drain
    call must be told `skip_first_bit=True` so _load_activations sends the
    remaining ROWS*DW-1 bits, not all ROWS*DW."""
    await _load_activations(dut, a, p_minus1, skip_first=skip_first_bit)

    # +2 (not +1) whenever _load_activations's return point sits one cycle
    # earlier than real WRITE_A progress: true for `first` (see above) and
    # also for skip_first_bit (its first bit -- and thus its first counted
    # edge -- was already consumed by the previous pass's trailing edge).
    await ClockCycles(dut.clk_PAD, p_minus1 + (2 if (first or skip_first_bit) else 1))
    assert _done(dut) == 1, "expected DONE pad high after COMPUTE finished"

    # DONE -> SHIFT_OUT: this edge captures y into stream_out's PISO, so y_bit is
    # already valid (lane 0, bit 0) the instant we land in SHIFT_OUT.
    await RisingEdge(dut.clk_PAD)

    lanes = [0] * N_WEIGHTS
    for lane in range(N_WEIGHTS):
        for bit in range(ACC_WIDTH):
            lanes[lane] |= _y_bit(dut) << bit
            _drive_control(dut, cont=cont, p_minus1=p_minus1)
            await RisingEdge(dut.clk_PAD)

    # SHIFT_OUT's exit is gated on stream_out's `y_done`, which (like wfull) is
    # registered one cycle after the last drained bit. If continuing, this
    # same edge is already the next pass's first WRITE_A capture -- see the
    # docstring above.
    if cont:
        next_bit = _activation_bits(next_a)[0]
        _drive_control(dut, a_bit=next_bit, cont=1, p_minus1=next_p_minus1)
    else:
        _drive_control(dut, cont=0, p_minus1=p_minus1)
    await RisingEdge(dut.clk_PAD)

    sign_bit = 1 << (ACC_WIDTH - 1)
    return [v - (1 << ACC_WIDTH) if v & sign_bit else v for v in lanes]


async def _run_matvec(dut, W, a, p_minus1):
    """One full START..SHIFT_OUT pass (fresh weight load, cont=0). Only call
    this once per _start_up -- see _start_weights's caution note."""
    await _start_weights(dut, W, p_minus1)
    return await _compute_and_drain(dut, a, p_minus1, cont=0, first=True)


async def _run_weight_stationary(dut, W, passes):
    """Load weights once, then run one _compute_and_drain per (a, p_minus1) pair
    in `passes`, reusing the loaded weights via `cont` (skips WRITE_W for every
    vector after the first, avoiding weight_load's re-entry corruption
    entirely -- see _start_weights). The p_minus1 used while loading weights is
    irrelevant to correctness (control_fsm only samples P_minus1 during
    COMPUTE, which each pass drives with its own value). Returns a list of
    lane-lists, one per pass."""
    await _start_weights(dut, W, passes[0][1])

    results = []
    for i, (a, p_minus1) in enumerate(passes):
        cont = i < len(passes) - 1
        next_a, next_p_minus1 = passes[i + 1] if cont else (None, None)
        results.append(
            await _compute_and_drain(
                dut,
                a,
                p_minus1,
                cont=cont,
                first=(i == 0),
                skip_first_bit=(i > 0),
                next_a=next_a,
                next_p_minus1=next_p_minus1,
            )
        )
    return results
