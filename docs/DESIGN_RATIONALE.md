# DCIM v2: Design Rationale

## Purpose of this document

`HANDOFF.md` lists what is changing in v2. This document explains why. It is written so that anyone picking up the project, human or Claude Code, understands the reasoning behind each decision well enough to defend it, and to recognize when a proposed change would undermine it. When a decision here seems inconvenient during implementation, the reasoning below is the thing to argue with, not the decision itself.

The short version is this: v1 proved that the compute-in-memory core works and taught us, through measurement, that the core is not the bottleneck. Everything around it is. v2 keeps the proven core exactly as it is and rebuilds the architecture around it so that the core's energy advantage can actually show up in a real system, can be measured cleanly, and can be tested properly. The photonics work sits alongside this as a measured experiment about where light beats electronics, not as a part the chip depends on.

## Where v1 stands, and what it taught us

v1 is a digital compute-in-memory macro on GF180MCU that computes y = W^T * a for INT8 weights and activations. It uses a custom 9T SRAM bitcell: a 6T storage cell plus a compute port that ANDs the stored weight bit with an incoming activation bit. Four 32 x 8 macros sit side by side to form a 32 x 32 array of bitcells. Because weights are stored bit-parallel, each INT8 weight occupies 8 bit-columns, so the array holds 128 weights arranged as 32 inputs by 4 outputs. Activations arrive bit-serially, one bit-plane per cycle, least significant bit first. Each bit-column has a popcount adder tree that counts how many of its 32 cells produced a 1, the per-lane logic combines the 8 column counts with their binary weights (subtracting the sign column), and a shift-accumulate stage builds up the full result across activation bit-planes.

The architecture's claim has always been energy, not speed. A bit-serial design is inherently slower than a fully parallel multiplier array at INT8, so speed claims would be false. The argument for compute-in-memory is that weights never move: they sit in the bitcells where the multiplication happens, and moving data is where most of an accelerator's energy goes.

When we instrumented v1 with a cycle-accurate test (`cocotb/functional/dcim_top_tb.py`, checked against the golden model on every pass), the result was striking. A single matrix-vector multiply at INT8 takes 350 cycles: 256 to stream activations in, 8 to compute, 1 for the done state, and 85 to stream results out. Compute is 2.3% of the time. At binary precision (P = 1), it is 343 cycles, and compute is 0.3% of the time, because v1 still streams all 8 bits of every activation even though only one bit-plane is used. Loading the weights takes another 1,025 cycles, but that happens once per weight set.

So v1 is I/O-bound. The compute-in-memory core, the part that embodies the whole idea, does useful work less than 3% of the time, and spends the rest waiting for single-pin serial interfaces to feed it and drain it. It is not electrically idle while it waits. The activation chain drives the array directly, so the partial products and adder trees switch on every load cycle: in simulation of the v1 RTL with random data, more than 90% of their signal transitions per vector happen during the activation load, when the result is not used (see `docs/V2_DESIGN_GUIDE.md`, section 1.6). Any energy advantage the core has gets buried under the cost of the time spent moving data through one pin at a time.

The area numbers told a complementary story. The core area is about 823,500 square microns, but only about a third of it holds real cells; the rest is fill. Of the real cells, the four SRAM macros take only about 32,000 square microns combined. Standard-cell logic takes about 246,000, and combinational logic, dominated by the column adder trees, is the largest share. The synthesized netlist maps those trees reasonably efficiently (around 740 full-adder equivalents), so the area is not wasted. It is simply that adder trees, not bitcells, are what cost area in this design, and that there is plenty of free room on the die. One caution: the final netlist is flattened and no per-module area report has been run, so the adder trees' share is inferred from the cell mix (740 majority cells, 740 XOR2, 1,457 XNOR2 out of 5,181 combinational cells), not measured.

These two findings, measured rather than assumed, drive almost every v2 decision.

## What the capstone is trying to show

The larger project is a capstone and thesis built around a question that matters to the industry: AI's energy cost is dominated by moving data, and photonics is widely promised as part of the answer. In practice, photonics has succeeded commercially for moving data between chips and racks, while photonic computing is still largely at the demonstration stage. The thesis builds a small system that measures both roles against electronics on the same hardware, and uses those measurements to project where optical computing would start to win.

This framing has a direct consequence for the DCIM: it must be measurable on its own terms. Energy per MAC, throughput, and correctness need to come from the DCIM itself, not from whatever is attached to it. It also means the DCIM must work perfectly without any photonic hardware. The photonics is an experiment that runs on top of a working system. It is never a dependency of that system.

## Why v1 is frozen and v2 lives on a branch

v1 is the frozen baseline design (as of 2026-10-13 it has not been taped out: the shuttle deadline was extended to 2026-12-14 because of fab issues, and v2 is planned for that submission). Its value as a baseline depends entirely on our ability to point at exactly what was submitted and reproduce it. If v1's source drifts after submission, every "v2 versus v1" comparison becomes questionable, because nobody can be sure which v1 is being compared. So v1 is tagged as `v1.0` and that tag is protected against moving or deletion.

v2 is developed on a separate `v2-dev` branch in the same public repository, with feature work on short-lived branches merged by pull request. `main` stays at v1 until v2 passes all of its merge gates. We considered putting v2 in a private repository, because of a possible conflict of interest, and concluded it was not needed. The repository is Apache-2.0, which permits a public derivative as long as the license, notice, and per-file license headers are kept.

## Why v2 keeps the same compute array

v2 uses exactly the same four macros in exactly the same 32 x 4 arrangement as v1. We considered growing the array to 4 or 8 times v1's capacity and decided against it, for three reasons.

First, this is a proof of concept. The goal is to demonstrate and measure an architecture, not to run large networks. Layers larger than 32 inputs can be processed in chunks, with the FPGA adding partial sums, which is slower but entirely adequate for a demonstration. The demo network is shaped to avoid chunking where it can (see "How a network actually runs").

Second, an identical array means identical layout risk. The v1 array is known to pass DRC, LVS, and antenna checks, and its physical behavior will be characterized when silicon returns. Changing it would reopen all of that.

Third, and most important for the thesis, keeping the array fixed makes the comparison clean. If v2 used a different array, any measured difference in energy or throughput could come from the array change or from the architectural changes, and there would be no way to separate them. With an identical array, every difference between v1 and v2 is attributable to the v2 architecture.

The area findings support this. With two thirds of the core free, there is room for all of v2's new logic without touching the array.

## Why the v2 headline is I/O, not compute

Earlier planning made "2 activation bits per cycle" the v2 headline, on the reasoning that bit-serial computation was v1's main weakness. The cycle measurements showed that this was wrong. Processing 2 bits per cycle would cut COMPUTE from 8 cycles to 4, saving 4 cycles out of 350, an improvement of about 1%. Nobody would ever see it. That change was dropped.

The real bottleneck is moving data in and out, so v2 rebalances the I/O. Each change attacks a specific measured cost.

### Parallel activation lanes

v1 loads every activation bit through a single pin, through one long shift chain of 256 bits. v2 splits that chain into four sub-chains of eight rows each and loads them in parallel from the four link lanes, cutting the load time by a factor of four. That gain exists only over the link. SPI has a single data-in pin, so at best it loads activations at v1's rate of one bit per cycle. Every throughput number therefore has to state which interface it was measured on, and should be reported in wall time as well as core cycles.

### Two load modes, selected by P

The optical first layer, when it is used, and the bring-up network both produce 1-bit features, so P = 1 is an important operating mode, and v1 wastes seven eighths of the load in it by streaming 8 bits per row. v2 supports exactly two load modes: full 8-bit, and 1-bit. P = 1 selects the 1-bit load; every other P value computes correctly but loads at full width. There is no separate mode bit, so the load mode and the precision cannot disagree.

The 1-bit mode is small to build. Each row's cell is DW bits deep and its least significant flop is the compute tap. In 1-bit mode the load path runs through only that flop in each row, which is one multiplexer per row. This replaces the earlier open question about a general precision-aware chain.

### Overlapped drain, and the drain as the new bound

`stream_out` captures the results into its own register when the computation finishes, so the state machine can return to loading while the previous results are still streaming out. That overlap hides the drain for one vector. In steady state, though, the next result can be ready before the previous one has finished draining, so the state machine must stall before overwriting `stream_out` until the drain completes (drain backpressure). Steady-state throughput is set by the slowest of load, compute, and drain. At P = 1 the drain is the slowest. At P = 8 it is the activation chain, which is occupied through the load, the wait for the CRC, and the compute, and cannot take the next payload until all three are done.

Two things attack the drain bound. The first is more return lanes: v2 has four, one per output (see the pinout section). The second is draining fewer bits per result, which the next two subsections cover.

### Precision-aware drain

A raw result does not need all 21 accumulator bits unless P = 8. The result width is derived from P the same way the load mode is: width = DW + P + clog2(ROWS), which is 14 bits at P = 1 and 21 bits at P = 8. `stream_out` stops after that many bits per lane, and the receiver sign-extends. No separate mode bit exists, so width and precision cannot mismatch. This rests on the accumulator holding a P < 8 result right-aligned and sign-extended, which was checked in simulation on the v1 RTL: at P = 1 the worst case (every weight -128, every activation bit set) gives -4,096, which fits in 14 bits, and at P = 8 the worst case gives -1,044,480, which fits in 21.

### On-chip bias, ReLU, and requantization

When the next layer only needs an 8-bit activation, the chip can shrink each result from 21 bits to 8 itself. The order is: add a per-output bias, apply ReLU, shift right by a programmable amount, saturate. The details:

- The bias add is 22 bits wide and saturating. The largest raw sum (32 x 255 x 128 = 1,044,480) nearly fills the 21-bit accumulator, so a 21-bit add could overflow.
- The shift truncates. That is the simplest behavior to match in the golden model and in training.
- Activations are unsigned in this design (A_SIGN = 0), so saturation is to 0..255, not to signed INT8's 127.
- The bias must be added before ReLU, which is why v2 has a per-output bias register rather than relying on bias-free training.
- It is only valid for layers that fit in a single pass of 32 inputs or fewer. For chunked layers, ReLU of a partial sum is mathematically wrong, so the chip outputs raw partial sums and the FPGA sums them before applying bias and ReLU.
- It is configurable, so raw sums remain available for verification and analysis.

The photograph demo can use this feature on every layer. In its one-pass candidate network no layer needs chunking, so the chip could do bias, ReLU, and scaling for the whole network and leave the FPGA only max pooling and picking the largest score. Across the trained demo networks the shifts are 5 to 11 and the largest bias needs 17 bits including sign, so the 22-bit add has ample room. Two limits are stated plainly. At P = 8 a requantized drain is no faster, because the activation chain already bounds the period at 75 cycles; the gain is arithmetic moved off the FPGA, not speed. And the system model does not yet model the on-chip version: there the FPGA does this arithmetic, which gives the same integers.

### Gating the activations outside compute

In v1 the activation chain drives the array directly, so the array outputs and adder trees switch on every load cycle, not only during compute. v2 holds the macros' activation input at zero except during compute: one AND gate per row, merged with the multiplexer that memory BIST needs at the same place. The gate is driven straight from a register so that it cannot glitch open. With the input at zero every partial product is zero and the trees see constant inputs. This is what makes "energy per compute cycle" mean what it says on v2, and the compute-gate configuration bit is simply a second condition on the same gate.

### Ping-pong activation banks: deferred

Ping-pong banks would let the next vector load while the current one computes. They were planned and then moved to a stretch goal, by the same standard that dropped 2 bits per cycle. At P = 1 the design is drain-bound, so they gain nothing. At P = 8 they would let the next payload start as soon as the previous one ends, shortening the period from about 75 cycles to the 69-cycle frame length, roughly 8%, for double the activation storage (which is already the largest sequential block). If the async FIFO on the link receiver is made deep enough to hold a frame, it buffers the next frame while the core computes, which recovers part of the same benefit.

### Estimated cycles per vector

These are estimates to be measured, not assumed. They rest on assumptions that are still open and must be verified:

- The lane rate equals the core clock. This depends on pad and PCB limits. The PDK timing library gives the output pad, at its lowest drive setting and the slow corner (125 C, 2.97 V), about 10 ns of delay and an 11 ns rise time into 15 pF. That fits a 40 ns bit at 25 MHz and does not fit a 20 ns bit at 50 MHz. At the highest drive setting the same figures are about 6 ns and 3 ns. The board and link module add their own limits, which are not known yet.
- Inbound frame on four lanes: 1 sync cycle, 2 header cycles (8 bits), the payload, 2 CRC cycles.
- Return frame on four lanes: a 4-bit sync word on every lane (4 cycles), the echoed 6-bit sequence number (2 cycles), the payload (one result per lane, so as many cycles as the result is wide), and CRC-8 (2 cycles). That is 8 cycles of overhead.
- One cycle for done, bias, and requantize. The FIFO crossing adds about 3 cycles of latency but no steady-state cost.
- The CRC comparison is registered, so compute starts one cycle after the last CRC symbol. The activation chain is occupied from the first payload symbol until compute ends (payload, 2 CRC symbols, 1 compare, compute): 12 cycles at P = 1 and 75 at P = 8. The next frame's sync and header may overlap that, but its payload may not.

| Mode | Inbound frame | Chain occupied | Drain | Per vector | v1 |
|---|---|---|---|---|---|
| P = 1, raw (14-bit) | 13 | 12 | 22 | 22 | 343 |
| P = 1, requantized | 13 | 12 | 16 | 16 | 343 |
| P = 8, raw (21-bit) | 69 | 75 | 29 | 75 | 350 |
| P = 8, requantized | 69 | 75 | 16 | 75 | 350 |

Per-pass speedup over v1: about 16x at P = 1 raw, about 21x at P = 1 requantized (single-pass layers only), and about 4.7x at P = 8.

Which feature gives which gain:

| Feature | P = 1 | P = 8 |
|---|---|---|
| 1-bit load mode | load 256 bits to 32 | none |
| Four input lanes | 32 cycles to 8, hidden behind the drain | 256 cycles to 64, the main gain |
| Overlapped drain | removes the drain from the sum | removes the drain from the sum |
| Precision-aware drain | raw drain 84 bits to 56, sets the bound | none |
| Requantize | drain to 32 bits, single-pass layers only | none (load-bound) |
| Four return lanes | drain payload 56 cycles to 14 (raw) | none |

### How a network actually runs: batch by weight set

The array holds one weight set: 32 inputs by 4 outputs. A layer change, a new group of 4 outputs, or a new chunk of a layer wider than 32 inputs all need different weights, and that means a weight reload. So the system runs batch by weight set: load one weight set, run every image in the batch through it, reload, repeat. P is written once, alongside the weights.

The demo is photograph recognition: colour photographs in ten classes, shrunk to 64 x 64 and run through a convolutional network. The training set is Imagenette, ten classes taken from ImageNet (9,469 training photographs, 3,925 validation photographs). An earlier version of the demo used CIFAR-10, which is 32 x 32; the move was made because the same network scored about 5 points higher on 64 x 64 input than on 32 x 32. A convolution applies one small weight set to every window of the image, so it suits a weight-stationary chip: load a weight set once, then send every window of every image through it.

The network is chosen with a system model in `model/`. It trains under the hardware's rules (8-bit weights, unsigned activations, ReLU, power-of-two scaling) and then runs the trained integers through a bit-exact model of the chip. Three convolution-only candidates came out of it. The first, one-pass, is the demo's reference network; the other two were not chosen, because their gain on the validation photographs does not show on independent ones:

| Candidate | Shape | Weights | Weight sets | Chip passes per image | Accuracy, validation photographs |
|---|---|---|---|---|---|
| One-pass | A 3 x 3 convolution that halves the image, to 16 feature maps, then seven pairs of depthwise 3 x 3 and 1 x 1 convolution at 32 maps, with three poolings and a global maximum, then 10 outputs | 7,968 | 116 | 30,899 | 81.7% (three runs, 81.3 to 82.0) |
| Wide | The same shape at 32, 64, and 128 maps | 70,528 | 700 | 96,316 | 84.2% (one run) |
| One-pass at full resolution | The one-pass shape with a first layer that keeps the image size and one more pooling stage | 10,592 | 154 | 125,107 | 84.6% (one run) |

Accuracy is measured in the model, in integer arithmetic, on the 3,925 validation photographs, which the network never trains on. On every network trained at 8 bits, integer accuracy was within 0.4 points of floating point, so the chip's arithmetic costs nothing measurable. Three runs of the same network span 0.7 points, so single-run differences under about 1.5 points mean little. Photographs from other sources score lower. On 458 independent photographs of the ten classes (208 from the ImageNetV2 test set and 250 from Wikimedia Commons, taken as they come) the three candidates scored 73.4%, 72.9%, and 74.5%, which is not a real difference at about 2 points of uncertainty: the larger networks' gain on the validation photographs does not show on independent ones. The earlier CIFAR-10 versions of the one-pass and wide shapes dropped further: 83.7% and 91.0% on held-out images fell to 72.5% and 81.7% on an independent dataset of the same classes (CIFAR-10.1, 2,000 images), and to 58% for both on 100 photographs taken from the web as they came.

In the one-pass candidate no layer has more than 32 inputs per output. The first layer sees 27 (a 3 x 3 window of three colours). A depthwise layer sees 9 per output, and three of its feature maps share one weight set. A 1 x 1 layer sees at most 32. Nothing is chunked, so the FPGA adds no partial sums and every layer can use on-chip requantize. The same holds at full resolution. The wide candidate's later 1 x 1 layers have 64 or 128 inputs and are chunked.

Every pass in these networks is 8-bit, so the gain per pass is the P = 8 one. Per image, as an estimate:

| | One-pass | Wide | One-pass at full resolution |
|---|---|---|---|
| v1, passes | 30,899 x 350 = 10,814,650 | 96,316 x 350 = 33,710,600 | 125,107 x 350 = 43,787,450 |
| v2, passes | 30,899 x 75 = 2,317,425 | 96,316 x 75 = 7,223,700 | 125,107 x 75 = 9,383,025 |
| v2, weight reloads | 116 x 1,024 = 118,784 | 700 x 1,024 = 716,800 | 154 x 1,024 = 157,696 |
| v1 total, one image | 10,933,550 (about 437 ms at 25 MHz) | 34,428,100 (about 1.38 s) | 43,945,300 (about 1.76 s) |
| v2 total, one image | 2,436,209 (about 97 ms) | 7,940,500 (about 318 ms) | 9,540,721 (about 382 ms) |
| Speedup, one image | about 4.5x | about 4.3x | about 4.6x |

The honest headline for the photograph demo is therefore about 4.7x per pass and about 4.5x per image, not 9.5x. The 9.5x figure belongs to the earlier digits network, most of whose passes are 1-bit, where v2 gains the most. Lower precision does not recover it as the design stands. v2 loads the full 8 bits per row at every precision except P = 1, so a 4-bit pass is 64 + 2 + 1 + 4 = 71 cycles, hardly better than 75. Only a 1-bit pass (22 cycles) is much cheaper. A load that takes only P bits per row would make a 4-bit pass 39 cycles, but in the model (one-pass shape on CIFAR-10) 4-bit pixels and activations cost about 3 points on held-out images and 5 on an independent dataset; that would be a change to the two-load-mode decision and is not proposed here.

Running self-attention is a goal for this chip, and it runs on the chip unchanged. Attention multiplies data by data, and the array multiplies data by stored weights, so one operand is written into the weight array: each image's keys, then its values, with the queries and then the attention rows sent as activations. ReLU and a power-of-two scale stand in for softmax. The chip stays weight-stationary within an image (a written set serves all of that image's vectors, 64 on an 8 x 8 map, before it is replaced), but those sets cannot be shared across a batch. Measured over three training runs each on Imagenette: attention can replace every convolution after the 8 x 8 map with no measurable loss (82.0% against 81.2% on the validation photographs, 70.8% against 71.7% on independent ones), for about 20% more cycles per image. It does not improve accuracy at this size, and neither does textbook attention in floating point (softmax, several heads, layer normalisation), so the simplifications made for the chip are not the limit; the small network and the 9,469 training photographs are. Convolution gives more accuracy per cycle at every point measured. The demo therefore runs two networks on the same chip (decided 2026-10-09): the attention network as the headline and the one-pass convolution network as the reference. Nothing in the hardware differs between them, only the weights and the FPGA's schedule, which is the point of the demonstration: one weight-stationary array runs a convolutional network and a self-attention network at the same accuracy. The figures are in design guide sections 7.2 and 7.7.

Weight reloads matter far less than they did. A convolution reuses a weight set across hundreds of windows, so reloads are about 5% of v2's time for a single image with the one-pass candidate, about 9% with the wide one, and about 2% at full resolution, and less with a batch. A v2 weight set over SPI is 1,024 bits; with SCLK at the core clock rate that is at least 1,024 core cycles before any command overhead, essentially the same as v1's 1,025.

The earlier digits network (8 x 8 binarized digits, 2 x 2 patches giving 64 binary features, 16 hidden units, 10 classes) is kept as a small bring-up test. It takes 8 passes at P = 1 and 3 at P = 8: 8 x 343 + 3 x 350 = 3,794 cycles on v1 and 8 x 22 + 3 x 75 = 401 on v2 with weights loaded, about 9.5x. It is the case that exercises the 1-bit load mode and the precision-aware drain. For a single image it is dominated by its 11 weight reloads: 11,665 cycles on v2 against 15,069 on v1, about 1.3x. That must be said plainly wherever its single-image latency is reported.

Weight loading over the link would cut a reload from about 1,024 cycles to about 261. It was considered again and deliberately kept as a stretch goal. The photonic module computes the first layer on data as it passes through, so it may not be a transparent path for raw weight bits, and the system must work with that module plugged in. Weights therefore load over SPI, which is independent of whichever link module is fitted, and SPI was made faster instead (see the SPI section). The inbound frame header still reserves a frame type, so the faster route can be added later without changing the frame format.

Two energy metrics follow from the batch model, and both are reported:

- Steady-state energy per vector: weights already loaded, reloads excluded, with P, drain mode, and interface stated.
- End-to-end energy per inference: includes weight reloads, reported for a stated batch size.

## Why activation precision control stays

Activation precision, from 1 to 8 bits, stays in v2. At one point there was a plan to remove precision features, but that applied to weight precision modes, which are not needed. Activation precision is a different matter: the bring-up network runs its first layer at P = 1 and its second at P = 8, a network behind an optical first layer starts from 1-bit features, and the v1 energy method depends on comparing the two precisions.

What changes is how it is set. The `P_minus1` pins are removed. P becomes a configuration register, written over SPI or JTAG, alongside the weights it belongs to. The value travels with the vector: one copy is latched when its load begins and used for the load mode and the compute, and a second is taken when its result is captured and used for the drain width. A single copy would be wrong, because v2 drains one result while the next vector loads. A write in the middle of a vector therefore takes effect on the next one. P also selects the load mode (1-bit at P = 1, full width otherwise) and the raw drain width, so those three can never disagree.

An earlier idea put a P field in the link frame header, so the FPGA could switch precision between frames with no SPI write. It was dropped: a precision change always comes with a layer change, a layer change always needs a weight reload over SPI, and so the register is enough.

## Why adder tree sharing is deferred

Adder tree sharing, where one set of trees is time-multiplexed across several output lanes, was designed in some detail. It would replace 32 column trees with 8, fed through a 4:1 multiplexer, at the cost of making compute take four times as many cycles. In v1 that slowdown would barely matter, because compute is 8 of 350 cycles. In v2 it would: at P = 8 compute would grow from 8 cycles to 32 and the period from 75 to 99 (64 + 2 + 1 + 32), about a third slower on every pass of the demo networks, which would take the per-pass gain over v1 from about 4.7x to about 3.5x. By cell count it would remove about 555 of the 740 full adders and add 256 four-input multiplexers at the array outputs.

It was still deferred, because the only thing it saves is area, and v2 is not short of area. It does not meaningfully save energy, since the same additions still happen, just one lane at a time, plus a little extra switching in the multiplexer. And it is not free in risk: it adds a lane counter, gated shifting in the activation chain so the same bit-plane is held across all four lanes, per-lane accumulator enables, and a new cycle ordering that every trace-level test would need to learn. That is verification effort and bug surface with no measurable benefit. It comes back only if synthesis of the full v2 design shows area is actually tight.

A related concern was that the adder trees are the most power-hungry and glitch-prone part of the design. Sharing does not address that. If it becomes a goal, the levers are pipelining the trees or restructuring them as explicit balanced compressor trees. With about 20 nanoseconds of timing slack at 25 MHz, neither is required, so they would be a power experiment rather than a necessity. The same measurement rules out a faster clock without them: the worst path, from an activation chain flop through a bitcell, the adder tree, and the output combine into an accumulator, arrives at 19.95 ns at the slow corner, so a 20 ns clock would have no room for the logic v2 adds to that path.

## Why these interfaces

v1's interface is a handful of single-bit serial pins. That was adequate for a first chip but makes the chip hard to drive, hard to debug, and impossible to connect to anything faster. In v2 every one of those pins is gone: `a_bit`, `w_bit`, `start`, `cont`, `P_minus1`, `y_bit`, `done`, and `busy` are replaced by the interfaces below, each with a specific job.

### The link is the data path

It has four inbound data lanes, matching the four feature bits per patch that the photonic first layer produces when it is used, and four return lanes, one per output.

The inbound direction is source-synchronous: the sender forwards its clock on a dedicated lane, and the receiver samples data on that clock. This decision came from an earlier plan that used oversampling clock recovery, which caps the link rate at a quarter to an eighth of the core clock and makes the link slower than the chip it feeds. A forwarded clock lets the link run at the full lane rate. The receive logic runs in its own clock domain, deserializes the lanes, and passes data into the core domain through an asynchronous FIFO, which is a standard clock-domain-crossing structure and must be built carefully.

Inbound frame format:

- A sync symbol.
- An 8-bit header: a 2-bit frame type and a 6-bit sequence number. One frame type is the activation frame. The other values are reserved, one of them for weight loading over the link if that stretch goal is ever built.
- The payload: 32 bits at P = 1, 256 bits otherwise.
- A CRC-8 covering the header and the payload.

A valid activation frame starts a computation by itself. There is no start pin and no `cont`: each frame is one vector, and weights persist until an explicit weight write. The CRC gates the start, not the load: the payload is already in the activation chain when the CRC arrives, so a bad frame is simply never computed, the CRC error counter increments, and the next frame overwrites the chain.

Result tracking uses the sequence number. Each return frame echoes the sequence number of the frame it answers. A bad inbound frame produces no result, so the FPGA sees a gap and resends. Three rules make that safe:

- Results may return out of order after a resend, and are matched by sequence number. This is sound because vectors are independent of each other.
- After a CRC failure, the receiver requires N idle cycles before accepting a new sync, so that it cannot lock onto payload data that happens to look like a sync symbol. N is at least one maximum frame length, and its exact value is an open question to tune.
- A corrupted return frame also shows up as a gap and causes a recompute. The link error rate is therefore two numbers, both reported: inbound errors from the chip's counter, and outbound errors counted by the FPGA.

The return lanes are plain NRZ, one bit per core cycle, with a sync word on each lane. This rests on an invariant: the return lanes are clocked from core CLK specifically, which originates at the FPGA, so return data is mesochronous with the FPGA. The FPGA does a one-time phase alignment on each lane's sync word, plus periodic resync from the sync word in every frame. There is no clock recovery. LINK_CLK is not used for the return lanes, because a forwarded clock may only toggle during inbound frames and the results live in the core domain. If anything ever clocks the return lanes from a chip-local source, this breaks. An earlier draft used Manchester encoding here; it was dropped because it halves the rate of the lane that bounds throughput, to solve a frequency-recovery problem that does not exist when the FPGA supplies the clock.

LINK_CLK and LINK_D have their pad pull-downs enabled, so an unplugged link module cannot clock garbage into the receiver.

### SPI is for control, configuration, and functional fallback

Through SPI the FPGA can load weights, write configuration (including P, bias, and shift), start a computation by a register write, read status, read results, and read back stored weights for debugging. The chip must be completely usable over SPI alone in the functional sense. It is not a throughput path.

SPI is clocked by SCLK, in its own clock domain. An earlier decision had the core clock sample SCLK instead, which saved a domain but capped SCLK at a quarter of the core clock. That made every weight reload about four times slower than v1's, and with eleven reloads per inference it made v2 about three times slower than v1 for a single image. Clocking the SPI logic directly removes the cap, at the cost of a fourth clock domain and a crossing between SPI and the register file. Speeding up SPI was chosen over loading weights through the link because SPI does not pass through the link module, so it behaves the same whichever module is fitted. The crossing follows three proposed rules, explained in the design guide: whole words cross and never single bits, SCLK is never faster than the core clock, and SPI_CS_N going high resets the SPI bit counter. The highest SCLK the pads and board allow is still open, and the reload figures here assume it reaches the core clock rate. SPI_CS_N has its pad pull-up enabled.

### Clock domains

There are four: core (CLK), link receive (LINK_CLK), JTAG (TCK), and SPI (SPI_SCLK). Nearly all of the design runs on CLK; the other three are small islands, each with one crossing into the core.

### Configuration bits the measurements depend on

An activation source multiplexer selects whether activations come from SPI or from the link. A compute-gate bit runs the identical I/O sequence with compute suppressed. A return-lane silence bit stops the return lanes from toggling. The last two exist for the energy method.

### Decisions that close the remaining gaps

These were found while writing `docs/V2_DESIGN_GUIDE.md`, which explains each one.

- **Input lanes map to rows contiguously.** Input lane k feeds rows 8k to 8k + 7. That leaves every v1 chain connection as it is and lets SPI re-join the four sub-chains into the one v1 chain. Which row holds which feature is a software convention, documented once and shared by the FPGA and the training script.
- **One output per return lane.** Return lane j carries output j.
- **A frame that cannot be accepted is dropped and counted.** If a frame arrives while the chain still holds an uncomputed vector, the chip drops it and increments an overrun counter. The resend rule recovers it. The link is never stalled.
- **The link clock domain only samples the lanes and writes the FIFO.** Finding sync, counting, the CRC, and the decision to start are all in the core domain, because the frame length depends on P and P lives there. This rests on an interface contract: LINK_CLK runs continuously while the link is enabled, and is never faster than CLK.
- **The CRC is computed over symbols in arrival order.** On the return lanes the FPGA deskews each lane by its own sync word before it checks the CRC.
- **Writes while busy are ignored and flagged.** Weights, P, bias, and shift are written only when the chip is idle.
- **Over SPI, weights load as one burst and activations load through the re-joined single chain.**

### Why the link exists at all

The reason is the swappable module. The off-chip link hardware sits on a plug-in board, and that board can be a photonic module, a copper LVDS module, or plain direct wires. All three present the same digital lanes at the same connector. The DCIM never knows which is plugged in. This is what makes the interconnect experiments fair: the same chip, the same network, and the same data, with only the transport changed. It is also what makes the photonics safe. If the photonic chip arrives late or does not work, the copper and wire modules still run the full system. And because the link logic is on v2 from the start, a photonic module can be plugged in after v2 is fabricated, with no respin.

## Why design for test

v1 left several things unverified that matter a great deal: the RBL index mapping was never traced through the physical ports, functional verification was never run against the real macro, and the timing library values are placeholders. Some of those will be closed for v2 through the merge gates. But they also taught a general lesson: the first time silicon is powered on, it is much better to have ways to see inside it than to discover it has no observable behavior and no way to find out why.

JTAG provides a second way into the chip. For that to be a real fallback rather than just observability, its DEBUG instruction has read and write access to the same register file SPI uses, so JTAG alone can load weights and activations, start a computation, and read results. That matters because SPI is itself new in v2. The TAP runs on its own TCK, so IDCODE still answers if the core clock is dead, which is the cheapest check that the chip is alive. Alongside DEBUG sit BYPASS and IDCODE, and MBIST and CBIST to run the self-tests. TMS has its pad pull-up enabled. Boundary scan is deliberately left out; for a 22-pin test chip on a simple board, its area and design effort are not justified.

The two fallbacks are not fully independent. Both reach the chip through one register file in the core clock domain, so a fault there, or a dead core clock, takes out SPI and JTAG DEBUG together.

Memory BIST runs a march test over the bitcell array, writing and reading patterns that catch stuck cells and coupling between neighbors. The 9T macro has no ordinary read port, because its only output is the AND of the stored bit with the activation. So BIST reads each row through the compute port by applying a one-hot activation to that row, which requires multiplexers on the activation path and on the write path at the macro boundary. With a one-hot activation, each column's popcount equals that row's cell bit, so the existing adder tree outputs serve as the read path and no extra read multiplexer is needed. This tests the AND compute port and the trees as well as the storage. The trade-off is that a tree fault looks like a memory fault; compute BIST and DEBUG readback separate the two. Memory BIST matters especially because the 9T cell is custom and has never been proven in silicon.

Compute BIST loads known weights and activations, runs the computation, and compresses the results into a signature register (a MISR) that is compared against the expected signature. One run exercises the adder trees, the lane combine, the shift-accumulate, and the accumulators together.

Both self-tests run automatically out of reset, under rules that keep them harmless:

- BIST never gates normal operation. A failed or unfinished BIST does not stop the chip from being used.
- The first write over SPI or JTAG, or the first valid link frame, aborts a running BIST. Reads pass through with no effect, so the result can be polled while the test runs.
- A timeout aborts a hung BIST and releases the multiplexers at the macro boundary.
- The result is a four-state status field, readable over SPI and JTAG at any time: running, pass, fail, aborted.

The STATUS pin replaces separate DONE and BIST_PASS pins. From reset it shows the self-test result as a heartbeat: low while running, a slow square wave on pass, held high on fail or on a timeout abort. A single static level would be ambiguous, because low could mean failed or not finished and a pad stuck high would read as a pass; a toggling signal cannot be faked by a stuck pad. On the first write or first valid link frame, the pin switches to DONE and pulses once per completed compute. A command-caused abort is therefore visible only in the status register, never on the pin. Switching also stops the heartbeat, so it does not toggle a pad during energy measurements.

Scan chains were planned and then dropped from v2's scope. Scan across four clock domains needs test-clock multiplexing in each, and the open flow's support for scan insertion and test-pattern generation is still unconfirmed. That makes scan the riskiest test feature for the least marginal value, given that the self-tests plus read-write JTAG already cover most of what is needed. Without scan there is no fault coverage figure, and the project does not claim one. Scan of the core domain alone remains a stretch goal if the flow supports it.

## Why this pinout, and how energy is measured with one supply

The shuttle allows 22 pads including power, and the chip has a single supply net and a single ground net.

### The 22 pads

| Pins | Count |
|---|---|
| VDD | 1 |
| VSS | 1 |
| CLK, RST_N | 2 |
| SPI_SCLK, SPI_CS_N, SPI_MOSI, SPI_MISO | 4 |
| TCK, TMS, TDI, TDO | 4 |
| LINK_CLK | 1 |
| LINK_D[3:0] | 4 |
| LINK_TX[3:0] | 4 |
| STATUS | 1 |
| Total | 22 |

That is 2 supply pads, 13 inputs, and 7 outputs. The return lanes are kept at four, one per output. At P = 1 the drain bounds throughput even with four lanes. At P = 8, which is every pass of the photograph demo, four lanes keep the drain (29 cycles) well under the 75-cycle chain period, where a single lane (92 cycles) would become the bound. An earlier draft spent two of these pads on a second VDD and a second VSS and kept only two return lanes; that is now the order in which extra pads would be spent, not the plan.

The cost of four return lanes is supply bounce. Up to seven outputs switch through one supply pair, four of them together on every drain cycle, where v1 has three outputs. The defenses are a low output drive setting (the PDRV pins on the output pad cells; the lowest is PDRV0 = PDRV1 = 0, and v1's three outputs are set one step above that, at PDRV0 = 1, PDRV1 = 0, with fast slew) and staggering the return lanes by half a cycle, which the per-lane sync words tolerate. By the pad timing data quoted earlier, the lowest drive supports one bit per cycle at 25 MHz and not at 50 MHz, so a 50 MHz clock target forces a choice between drive strength and lane rate.

The v2 slot may differ from v1's: the pad count may rise and the area may shrink. If the pad count rises above 22, the first extra pads go to a second VDD and then a second VSS, if the shuttle allows two pads on one supply net. If the area shrinks, the room for new logic has to be rechecked, and adder tree sharing is the lever already identified for that case.

If pins ever need to be cut, the order is: return lanes from four to two, then STATUS (its information is available by polling the status register), then input lanes from four to two.

### What the repo shows about the shuttle, and what to ask

Three facts come from the v1 integration files (`info.yaml`, `def/A07/project_defs/A/`, and the padring netlist and pin list inside `integration/SSCS_2026_02.tar.xz`):

- The pad map is generated by the organizers' tooling from the `pins:` list in `info.yaml`. It is not edited by hand. Pad cells are assigned from each pin's `io_type`, and outputs get the `bi_t` cell, which exposes drive strength, slew, and pull-up or pull-down to the design.
- Every team on that shuttle used exactly one power pad and one ground pad. Nothing in the repo forbids two, and nothing confirms it is allowed.
- In the shuttle padring netlist, the ground pins of every pad on the die are on one net, while our core's VSS port connects to our own ground pad. Our core's VDD, and our pads' VDD and DVDD (the pad driver supply), are all on the net of our own power pad.
- The same netlist shows our design driving each pad's control pins itself: output enable, drive strength, slew, input enable, and pull-up or pull-down.

Three questions go to the organizers together, since the v2 shuttle may differ and the netlist may not tell the whole story:

1. May one team use more than one pad on the same supply net?
2. Is VSS shared chip-wide?
3. Is the pad driver supply on our private VDD, or shared?

The answers decide how any extra pads are spent. If VSS is chip-wide, a second VSS pad is worth less than a second VDD pad.

### How energy is measured

An earlier plan gave the macro its own supply pin so its energy could be measured in isolation. That plan was wrong on two counts. The array is identical in v1 and v2, so the macro's own energy per operation should be about the same in both, while everything v2 actually changes (adder trees, accumulators, I/O, control) sits elsewhere. And v1 has a single supply, so there would be no v1 macro-only number to compare against. Splitting the pad supply from the core supply was also considered, and is not possible: the pad library has no separate core supply pad.

Energy is therefore measured differentially on total chip current, the same way on both chips. It is measured on the VDD side, because VDD is private to the team and ground may not be. As far as the netlist shows, that current includes the pad drivers, exactly as it does in v1.

Because pad drivers are included, and an output pad driving a board trace costs far more per transition than internal logic, pad activity is removed from the comparison rather than assumed to cancel:

- An idle baseline is taken with the clock running and nothing active.
- On v2, measurement loops run with the return lanes silenced and results unread. With the pads quiet, the compute-gate bit on versus off differs only in compute energy.
- On v1, the drain always runs, so compute energy is isolated with crafted data: P = 1 versus P = 8 on inputs chosen (for example paired positive and negative weights) so that the upper bit-planes toggle the partial products and adder trees but leave the result, and so the drain, unchanged. This was checked in simulation on the v1 RTL: with paired weights and every row carrying upper activation bits, the P = 1 and P = 8 results and drained bit streams were identical.
- On v1, every measured run must start from reset, not from a `cont` loop. The comparison only works if the activation load switches the same amount in both runs, and in a `cont` loop it does not: a P = 8 compute leaves the chain empty, while a P = 1 compute leaves seven bits in every row that the next load pushes through the rest of the chain. In simulation with the same data, one load made 30,916 partial-product transitions in a P = 8 loop and 65,647 in a P = 1 loop, a gap about twenty times larger than the compute difference being measured. With a reset before each run the two loads were identical (30,916 each), and the remaining difference was about six compute cycles of array and adder tree switching plus seven accumulator updates. The cost is that each run then includes the 1,025-cycle weight load, so the compute difference is a small fraction of the run and needs long averaging.
- Comparing all-zero activations with random ones estimates the data-dependent part. This comparison also changes the toggling in the activation chain during load, so it is an upper bound on the AND and adder tree contribution, not an isolated figure.
- Total chip energy gives the two system-level metrics defined earlier: steady-state energy per vector, and end-to-end energy per inference at a stated batch size. This is where v2's I/O changes show up.

Each measurement uses long repeated loops and averaged readings, and reports its method and uncertainty. The stated limitation is that absolute per-block energy cannot be isolated on a single supply.

## Why the cleanup work

The four macro instances in `dcim_array.sv` are written out by hand, with literal bit slices for each one and hardcoded counts. That is exactly the pattern behind the most common bug in this project's history: duplicating logic, renaming it, and getting an index subtly wrong. A past bug in this repository also showed how dangerous these are, when a test claimed to be exhaustive while iterating over the wrong range and silently checked only 5 of 32 addresses. Converting the array to a generate loop removes the hand-written indexing entirely, and a dedicated test proves the column mapping is unchanged after the refactor. This must be done before any other change to that file.

Many module header comments describe an older 64 x 64, 8-lane configuration, with numbers like 512-bit loads, 176-bit drains, and 7-bit column sums. At v1's actual 32 x 32 size, they are wrong. They mislead reviewers, and they would mislead an automated assistant reading the code. They are fixed deliberately against `dcim_pkg.sv`, which is the single source of truth for every parameter.

## Why the photonics plays the role it does

The photonic chip went through many proposed roles before settling, and the reasons for rejecting the others are as important as the final choice.

The first idea was to use photonics to replace the DCIM's adder tree, since a photodiode naturally sums the light that falls on it. This does not work, and the reason is fundamental. The adder tree lives inside the GF180 chip, and its inputs are electrical bits produced by neighboring bitcells every clock cycle. GF180 cannot generate or guide light, so using photonics would mean sending every partial product off the chip, converting it to light, summing it on a separate die, converting it back with a photodiode and an ADC, and bringing it back on chip, every cycle. Each of those conversions costs far more energy than the digital adder it replaces. It would reverse the energy advantage the DCIM exists to provide. The same reasoning rules out photonic MAC units inside the DCIM, and swapping the DCIM for a systolic array changes nothing, because the problem is the electrical-to-optical round trip, not the compute architecture.

The rule that came out of this is that photonics replaces adders only where the data is already light. That is where the final roles come from.

The first role is interconnect. The photonic chip separates multiple data lanes carried on different wavelengths in one fiber, using ring resonators that each pick out one wavelength. This is the role photonics plays successfully in real data centers. At lab scale it does not beat copper on energy, but it clearly wins on lane density (many lanes in one fiber), distance (a long fiber spool versus a long copper cable), and immunity to electrical noise. All three are measured against the copper module on the same system.

The second role is a fixed first network layer computed in transit. Because the data is already light as it passes through the link, the rings can multiply it by fixed weights and the photodiodes can sum it, computing a binary convolution (for example 2 x 2 or 3 x 3 patches with four kernels) before the data is converted back to electrical form. This gives the DCIM its 1-bit input features and makes the two chips genuinely depend on each other in the data flow. It also reduces conversions on the receive side: a patch of many inputs becomes a few feature outputs, so fewer photodiodes and receivers are needed than a plain link would require. The transmit side gains nothing, since every input still needs its own modulated wavelength. The kernels are chosen as general-purpose features (strokes and ink presence), trained under the physical constraints before tapeout, and stress-tested against fabrication error. They are all-positive, because a photodiode sums light intensity and cannot subtract; kernels with negative weights, such as true edge detectors, would need balanced detection with two photodiodes per output. In practice, passive rings will not land exactly on the laser wavelengths after fabrication. A thermoelectric cooler can shift the whole chip, but not individual rings within a bank, so the effective kernels are whatever was actually fabricated rather than the designed values. That is precisely why the DCIM is trained on the features the real chip produces: the reprogrammable part adapts to the fixed one. A few rings can optionally carry heaters to demonstrate reprogrammable optical weights, limited by the bond pads each heater needs.

The system model measures what the restrictions on this layer cost on photographs (CIFAR-10, the demo's earlier dataset; not repeated on Imagenette). With the same network behind it (a 3 x 3 window at every pixel, then three convolution and pooling stages), integer accuracy on held-out images was 83.2% with the first layer on the DCIM and 83.6% with an unrestricted optical layer (16 kernels, signed weights, 8-bit output). Restricting one thing at a time gave 78.8% with non-negative weights, 78.1% with a 1-bit output, and 79.2% with 4 kernels. Non-negative weights and a 1-bit output together gave 71.3%, and all three gave 64.5%. The layer as described above (2 x 2 patches, 4 non-negative kernels, 1-bit output) gave 67.1%, and 74.0% with 16 kernels. So each restriction costs about 4 to 5 points and together they cost about 16. These are model results under ideal optics with 8-bit weight resolution, one training run each. Repeated on Imagenette with the attention candidate behind the first layer (three runs each), an unrestricted optical layer matched the DCIM (81.3% against 82.0% on the validation photographs) and saved about 11% of the cycles. Non-negative weights alone cost about 1.5 points, a 1-bit output about 3.5, both about 9, and 13 to 15 with only 4 kernels. So the 1-bit output, not the sign of the weights, is the restriction to relax first. The candidate demo networks therefore keep every layer on the DCIM, and the optical first layer is measured as a variant. Which restrictions the photonic design can relax (two photodiodes per output for signed weights, a converter in place of the comparator, more kernels than link lanes) is open.

The deeper justification is the scaling argument. In optical compute, the multiplies and additions are nearly free, and the cost is in the conversions: one per input and one per output. For a layer with N inputs and M outputs, there are N times M operations but only N plus M conversions, so the conversion cost per operation falls as the layer grows. At the small sizes a student chip can build, electronics wins easily. At large sizes, optics can win, and recent industrial demonstrations are far larger than anything a student chip can build. Two photonic processor papers appeared together in Nature in April 2025 (volume 640, issue 8058): Hua et al. of Lightelligence, "An integrated large-scale photonic accelerator with ultralow latency" (pages 361 to 367), reporting more than 16,000 photonic components, and Ahmed et al. of Lightmatter, "Universal photonic artificial intelligence acceleration" (pages 368 to 374), reporting a processor that runs ResNet and BERT. Their matrix dimensions are not stated in the abstracts and must be taken from the full text before any size is quoted here. The photonic chip includes kernel banks of several sizes (2 x 2, 3 x 3, and 4 x 4) so that the trend can be measured from real hardware, rather than extrapolated from a single point. The thesis result is two crossover analyses from measured data: the interconnect crossover, which is reachable at lab scale, and the compute crossover, which requires industrial scale. Together they explain, with the project's own measurements, why the industry adopted photonic interconnect first.

None of this touches the DCIM die. The photonic chip is a passive part on a plug-in module, and v2 is complete without it.

## What we decided not to do, and why

Several directions were considered and rejected, and it is worth recording why so they are not reopened by accident. An analog front-end on the DCIM die (transimpedance amplifiers and ADCs to read photodiodes directly) was rejected as overkill, since off-chip parts on the link module do the same job with far less risk. Replacing the DCIM with a systolic array was rejected because it would throw away the submitted baseline, the verified bitcell work, and the most distinctive part of the project, without making the photonics any more useful; the existing FPGA systolic array instead serves as a comparison point. Other capstone directions (batteryless computing, radiation tolerance for space, encrypted computing) were explored and set aside mainly on cost and scope. Photonic in-memory computing with rewritable phase-change materials was recognized as the natural long-term direction, but those materials are not available on open or student fabrication runs, so it appears as future work.

## How the plan contains risk

The project is structured so that each risky piece can fail without taking down anything beneath it. v1, frozen for submission, is the foundation, and its silicon measurements become the baseline once it returns. v2 adds architectural improvements but is functionally usable over SPI alone, and over JTAG alone, so a failure in any one new interface still leaves a working chip. The one shared point is the register file in the core clock domain, which both fallbacks depend on. The interconnect experiments work with copper and wires, so the photonic chip is never required. If the photonic die is late or does not work, commercial optical parts can stand in for it in the same module, and the photonic chip's own measured data still supports the scaling analysis. A decision date, set a couple of months before the capstone demonstration, forces a clean switch to the fallback rather than a last-minute scramble.

## What success looks like

At the end, the project should be able to show, with measurements from its own hardware: that v1 and v2 both compute correctly, checked against the golden model; v2's throughput improvement over v1 and where it comes from, per pass and weighted over the demo network, with the interface and batch size stated; energy for both, measured differentially on total chip current by the same method (idle baseline, compute energy per cycle, data-dependent energy, steady-state energy per vector, and end-to-end energy per inference at a stated batch size); self-test results; link error rates in both directions for the copper and wire modules, and for the photonic module if present; the fixed optical first layer computed both optically and digitally, compared on energy, latency, and accuracy; measured photonic parameters (coupling loss, laser power, detector sensitivity, fabrication error versus design) across several kernel sizes; and the two projected crossover points built from those measurements.

Every claim the project makes should be backed by a number from this hardware, compared against a baseline running on the same system. That discipline, more than any single feature, is what turns this from a chip build into a thesis.

## Open decisions and unverified assumptions

Terminology first, because one word is doing three jobs. In the v1 RTL a "lane" is one of the N_WEIGHTS = 4 outputs (`lane_shift_accum`). In this document "input lanes" are the four LINK_D pins and "return lanes" are the LINK_TX pins. Any new text should say which it means.

`docs/V2_DESIGN_GUIDE.md` section 9.1 lists nine gaps that were found while writing the guide and are now closed. Their decisions are recorded in this document under "Decisions that close the remaining gaps".

`docs/V2_FLOW_AUDIT.md` walks the flow from specification to bring-up, records what the v1 run showed at each step, and holds the risk register. Its proposed mitigations are not decisions until accepted.

Still to be decided:

- Frame details: the sync patterns and their lengths, the CRC polynomial, the async FIFO depth, and the idle count N after a CRC failure.
- The register map for SPI and JTAG DEBUG, and the JTAG IDCODE value.
- Whether the photonic module can give a multi-bit output, which decides whether its first layer is used with the demo networks or the module serves as a link only.
- Which restrictions on the photonic first layer can be relaxed: signed weights, a multi-bit output, more kernels than link lanes.
- The target clock frequency. The pad drive data and the measured worst path both point to staying at 25 MHz.
- The three questions for the shuttle organizers in the pinout section.
- Whether the photonic module passes data through unchanged when it is not computing the first layer. Later-layer activations come from the FPGA and must reach the chip over the link for the P = 8 estimates to hold with that module fitted. In the photograph demo nearly all link traffic is such data, so this is the main path, not a side case. A related question: a frame whose payload is computed on in transit cannot carry a CRC the FPGA worked out beforehand, unless the FPGA also computes the features it expects.

Stated here but not verified from this repository:

- The cycle estimates for v2. Their assumptions are listed with the tables. The v1 figures are measured.
- Any v1 silicon result. Nothing has been taped out (the shuttle deadline was extended to 2026-12-14); nothing here is a silicon measurement until it is fabricated and returns.
- Everything in the photonics sections about device behavior, fabrication runs, and what is commercially deployed. None of it can be checked from this repository.
- The limits the board and the link module place on the lane rate.
- The accuracy figures for the demo network. They come from the system model in `model/`, one training run each, so differences under about a point are not meaningful.

