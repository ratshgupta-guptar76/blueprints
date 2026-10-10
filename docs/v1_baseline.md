# v1 baseline

This is the reference that v2 is compared against for merge gate 1: "all golden-model tests pass, coverage at or above v1". Everything here is **Measured** on the v1 RTL, on 2026-10-10, unless a line says otherwise.

## What was measured

| Item | Value |
|---|---|
| Commit | `7e92f16` on `v2-dev`, plus the column-mapping walk test added the same day |
| RTL | The same logic as tag `v1.0` (`d879b31`). The only differences in `src/` and `ip/` are two pairs of comment-only Verilator lint pragmas (`src/dcim_top.sv`, `ip/sram_32x8_9T/vh/sram_32x8_9T.v`). |
| Verilator | 5.044 |
| Icarus Verilog | 13.0 (devel) |
| cocotb | 2.0.1 |

## 1. Lint

| Check | Result |
|---|---|
| `make lint` (Verilator `-Wall`, top `dcim_top`) | Clean, exit 0 |
| The tapeout top `A07_dcim_top`, linted inside the LibreLane flow | 109 warnings, 102 of them `TIMESCALEMOD` (from the last v1 flow run, see `docs/V2_FLOW_AUDIT.md` finding F5) |

## 2. Functional tests

`make func-all` on Icarus: 11 modules, 69 tests, all pass, about 45 seconds. Tag `v1.0` had 68; the 69th is `test_column_mapping_walk`, added for v2 build step 1.

| Module | Tests (Icarus) | Tests run on Verilator | Skipped on Verilator |
|---|---|---|---|
| `act_shift_chain` | 7 | 6 | 1 |
| `adder_tree` | 3 | 2 | 1 |
| `col_adder` | 3 | 2 | 1 |
| `control_fsm` | 7 | 7 | 0 |
| `dcim_array` | 10 | 9 | 1 |
| `lane_shift_accum` | 7 | 6 | 1 |
| `row_decoder` | 4 | 3 | 1 |
| `shift_accum` | 6 | 5 | 1 |
| `shift_reg` | 7 | 6 | 1 |
| `stream_out` | 8 | 7 | 1 |
| `weight_load` | 7 | 6 | 1 |
| **Total** | **69** | **59** | **10** |

The tests skipped on Verilator are the X-propagation tests. Verilator is a two-state simulator, so they run on Icarus only.

## 3. Coverage

`make func-all SIM=verilator`, which builds with `--coverage-line --coverage-user`. This is **line coverage** plus any user coverage points, per module testbench. It is not toggle, branch, or expression coverage.

| Module | Points hit | Points | Coverage |
|---|---|---|---|
| `act_shift_chain` | 10 | 10 | 100% |
| `adder_tree` | 4 | 4 | 100% |
| `col_adder` | 4 | 4 | 100% |
| `control_fsm` | 57 | 57 | 100% |
| `dcim_array` | 7 | 7 | 100% |
| `lane_shift_accum` | 15 | 19 | 78% |
| `row_decoder` | 4 | 4 | 100% |
| `shift_accum` | 15 | 19 | 78% |
| `shift_reg` | 10 | 10 | 100% |
| `stream_out` | 15 | 15 | 100% |
| `weight_load` | 16 | 16 | 100% |

The two 78% rows are the same source file, `lane_shift_accum.sv`, reached by two testbenches. The four points never hit are two lines:

- line 68, the branch taken when `W_SIGN` is 0 (the MSB column is added, not subtracted);
- line 85, the branch taken when `A_SIGN` is 1 (the last plane is subtracted).

Both depend on compile-time parameters, and v1 is built with `W_SIGN = 1` and `A_SIGN = 0`, so no test at these parameters can reach them. Multi-parameter test sweeps are deliberately deferred (see `CLAUDE.md`). Every line that can be reached at the v1 parameters is covered.

## 4. Mutation tests

`make func-mut-all` on Icarus, about 2.5 minutes. A mutation is a realistic typo applied to the RTL; it is "caught" when the module's tests fail on it.

| Module | Caught | Survived | Not applied |
|---|---|---|---|
| `act_shift_chain` | 7 | 0 | 0 |
| `adder_tree` | 6 | 0 | 0 |
| `col_adder` | 9 | 0 | 0 |
| `control_fsm` | 14 | 0 | 1 |
| `dcim_array` | 7 | 0 | 0 |
| `lane_shift_accum` | 9 | 0 | 0 |
| `row_decoder` | 5 | 0 | 0 |
| `shift_accum` | 5 | 0 | 0 |
| `shift_reg` | 10 | 0 | 0 |
| `stream_out` | 9 | 0 | 0 |
| `weight_load` | 11 | 0 | 0 |
| **Total** | **92** | **0** | **1** |

- **The one not applied** is `control_fsm`, "SHIFT_OUT exit inverted": its pattern no longer matches the RTL text, so the mutation was never made. The table entry is stale and should be rewritten.
- **`dcim_array` had no mutation table before 2026-10-10.** Its seven mutations are index mistakes in the macro wiring (a slice not updated, two macros crossed, an index reversed or off by one). `test_column_mapping_walk` catches all seven on its own. The older `test_column_mapping` misses one of them: a bit order that is wrong only in rows 16 to 31, because it looks at row 0 only.

## 5. Cycle counts

From design guide section 1, measured on the v1 RTL by simulation:

| | Cycles |
|---|---|
| One weight set (`WRITE_W`) | 1,025 |
| One vector at P = 8 | 256 + 8 + 1 + 85 = 350 |
| One vector at P = 1 | 256 + 1 + 1 + 85 = 343 |

## 6. Physical results

The last v1 flow run is tabulated in `docs/V2_FLOW_AUDIT.md` section 2 and is not repeated here. The figures most often needed: 14,323 standard cells excluding fill, 492 flops, 33.8% utilization, worst setup arrival 19.95 ns against a 40 ns clock, and DRC, LVS, antenna, and XOR all at zero.

## 7. What this baseline does not cover

- **No top-level test.** `dcim_top_tb.py` is not in the repository, so everything above is per module. The cycle counts in section 5 come from a separate top-level probe.
- **Line coverage only.** A line can be executed without its values being checked. The mutation tests are what show the checks are meaningful.
- **X-propagation on Icarus only.**
- **Gate-level simulation has no timing,** so it cannot show a glitch or a clock-domain crossing fault.

## 8. How to reproduce

All from the repository root, in the nix shell.

| Result | Command |
|---|---|
| Lint | `make lint` |
| Functional tests | `make func-all` |
| Coverage | `make func-all SIM=verilator` (remove `cocotb/sim_build/<module>` first if it was last built with Icarus) |
| Mutation tests | `make func-mut-all` |

## 9. What gate 1 asks of v2

For every module that v2 keeps, and for each new one:

1. All tests pass on Icarus and on Verilator.
2. Line coverage is 100% of the lines reachable at the build's parameters. For `lane_shift_accum` that means the two parameter branches above stay the only exceptions, unless v2 makes `A_SIGN` a run-time setting, in which case line 85 must then be covered.
3. No mutation survives, and none is left "not applied".
4. An exhaustive test asserts its own iteration count.
