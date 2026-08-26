# SPDX-FileCopyrightText: 2026 Chipathon 2026 -- Team A07 Blueprints
# SPDX-License-Identifier: Apache-2.0
"""Drive/compute helpers shared by A07_dcim_top_tb.py's tests."""
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, ReadOnly, ReadWrite, RisingEdge, Timer

from golden_model import ACC_WIDTH, DW, N_WEIGHTS, ROWS


def _drive_control(dut, *, a_bit=0, w_bit=0, start=0, cont=0, p_minus1=DW - 1) -> None:
    dut.a_bit.value = a_bit
    dut.w_bit.value = w_bit
    dut.start.value = start
    dut.cont.value = cont
    dut.P_minus1.value = p_minus1


async def _drive_and_edge(dut, **kwargs) -> None:
    """Drive control signals, wait for the clock edge that captures them, then
    settle into the ReadWrite (reactive) phase before returning.

    GL-mode hazard: a synthesized netlist replaces a handful of RTL
    always_ff blocks with one always@(posedge clk) per gate-level DFF cell.
    Driving the *next* cycle's stimulus immediately upon waking from
    RisingEdge races those blocks' evaluation of *this* edge's D input --
    unspecified relative ordering between cocotb's callback and the
    simulator's own event queue, invisible in RTL (few always_ff blocks,
    ordering happens to work out) but real in GL. Ending every edge-wait in
    ReadWrite (which fires only after all of this edge's Active/NBA updates
    have settled) guarantees any write a caller makes next lands strictly
    after the DUT's own captures for that edge are done."""
    _drive_control(dut, **kwargs)
    await RisingEdge(dut.clk)
    await ReadWrite()


async def _start_up(dut):
    # Pad-side receiver inputs: unused (A07_dcim_top only XORs these into an
    # otherwise-unused signal, see src/A07_dcim_top.sv), driven 0 so nothing
    # floating feeds into the netlist.
    dut.y_bit_IN.value = 0
    dut.done_IN.value = 0
    dut.busy_IN.value = 0

    _drive_control(dut)
    cocotb.start_soon(Clock(dut.clk, 20, unit="ns").start())
    dut.rst_n.value = 0
    await Timer(100, unit="ns")
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 2)
    await ReadWrite()


async def _pulse_start(dut, p_minus1):
    """IDLE -> WRITE_W is unregistered (gated only on `start`), so the very next
    edge after the start pulse already has WRITE_W's w_bit capture active."""
    await _drive_and_edge(dut, start=1, p_minus1=p_minus1)
    _drive_control(dut, p_minus1=p_minus1)


async def _load_weights(dut, W, p_minus1):
    """WRITE_W: ROWS*COLS bits (COLS = N_WEIGHTS*DW). Column c holds bit (c % DW)
    of weight (c // DW) -- weight 0 first, LSB-first within each weight (see
    dcim_array.sv's WBL wiring / weight_load.sv's shift direction)."""
    for row in range(ROWS):
        for w_idx in range(N_WEIGHTS):
            value = int(W[row, w_idx]) & ((1 << DW) - 1)
            for bit in range(DW):
                await _drive_and_edge(dut, w_bit=(value >> bit) & 1, p_minus1=p_minus1)


def _activation_bits(a):
    """The DW*ROWS activation bitstream in wire order: reversed(range(ROWS)),
    each row's DW bits LSB-first (see _load_activations)."""
    bits = []
    for row in reversed(range(ROWS)):
        value = int(a[row]) & ((1 << DW) - 1)
        for bit in range(DW):
            bits.append((value >> bit) & 1)
    return bits


async def _load_activations(dut, a, p_minus1):
    """WRITE_A: DW*ROWS bits, rows in reverse order (act_shift_chain.sv is a
    head-to-tail daisy chain; the row sent last travels least and lands in
    the head cell/row 0), each row's bits LSB-first.

    Loads the full bit stream on every pass, including cont-continuation
    passes: a_en is gated on the *current* (pre-edge) state, so the
    SHIFT_OUT->WRITE_A transition edge itself never has a_en high -- nothing
    is captured until the first cycle where state has actually settled to
    WRITE_A, one cycle later than a naive reading of the FSM diagram
    suggests. There is no bit that's already "captured" for a continuation
    pass to skip."""
    for value in _activation_bits(a):
        await _drive_and_edge(dut, a_bit=value, p_minus1=p_minus1)


async def _start_weights(dut, W, p_minus1):
    """IDLE -> WRITE_W -> WRITE_A boundary: pulse start, load ROWS*COLS weight
    bits, then cross the wfull registration bubble. Leaves the DUT ready for
    _compute_and_drain's activation load on the very next edge.

    Unlike chip_top_tb.py's caution note, this function IS exercised a
    second time without an intervening hard reset by
    test_second_fresh_weight_load_without_reset -- that's the scenario
    under test there, not something being avoided here."""
    await _pulse_start(dut, p_minus1)
    await _load_weights(dut, W, p_minus1)

    # WRITE_W -> WRITE_A is gated on `wfull`, which weight_load.sv registers one
    # cycle after the 32nd (COLS-th) weight bit -- so there is exactly one bubble
    # cycle here where a_en is still 0 and no activation bit is captured.
    await _drive_and_edge(dut, p_minus1=p_minus1)


async def _compute_and_drain(dut, a, p_minus1, cont):
    """WRITE_A -> COMPUTE -> DONE -> SHIFT_OUT for one activation vector, and
    return the N_WEIGHTS signed accumulator lanes (two's-complement, ACC_WIDTH
    bits each). Works identically for a fresh weight load or a cont-reuse
    pass -- see _load_activations for why cont passes don't skip anything."""
    await _load_activations(dut, a, p_minus1)

    await ClockCycles(dut.clk, p_minus1 + 1)
    await ReadOnly()
    assert int(dut.done_OUT.value) == 1, "expected DONE high after COMPUTE finished"

    # DONE -> SHIFT_OUT: this edge captures y into stream_out's PISO, so y_bit is
    # already valid (lane 0, bit 0) the instant we land in SHIFT_OUT.
    await RisingEdge(dut.clk)
    await ReadWrite()

    lanes = [0] * N_WEIGHTS
    for lane in range(N_WEIGHTS):
        for bit in range(ACC_WIDTH):
            _drive_control(dut, cont=cont, p_minus1=p_minus1)
            await ReadOnly()
            lanes[lane] |= int(dut.y_bit_OUT.value) << bit
            await RisingEdge(dut.clk)
            await ReadWrite()

    # SHIFT_OUT -> WRITE_A (cont) or -> IDLE: a_en is gated on the pre-edge
    # state, so nothing is captured on this edge regardless of what's driven
    # here -- the next pass's _load_activations starts clean on the cycle
    # after this one.
    await _drive_and_edge(dut, cont=cont, p_minus1=p_minus1)

    sign_bit = 1 << (ACC_WIDTH - 1)
    return [v - (1 << ACC_WIDTH) if v & sign_bit else v for v in lanes]


async def _run_matvec(dut, W, a, p_minus1):
    """One full START..SHIFT_OUT pass (fresh weight load, cont=0)."""
    await _start_weights(dut, W, p_minus1)
    return await _compute_and_drain(dut, a, p_minus1, cont=0)


async def _run_weight_stationary(dut, W, passes):
    """Load weights once, then run one _compute_and_drain per (a, p_minus1)
    pair in `passes` via the `cont` reuse path."""
    await _start_weights(dut, W, passes[0][1])

    results = []
    for i, (a, p_minus1) in enumerate(passes):
        cont = i < len(passes) - 1
        results.append(await _compute_and_drain(dut, a, p_minus1, cont=cont))
    return results
