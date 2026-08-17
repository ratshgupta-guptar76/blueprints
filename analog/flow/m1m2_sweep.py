#!/usr/bin/env python3
"""2D sizing sweep for the 8T DCIM bitcell's read/compute port (M1/M2) --
finds the smallest-area (W_M1, W_M2) that computes the AND-multiply
correctly across all SS/TT/FF x PVT corners, at the 6T core sizing already
committed in params_6T.spice (W_PD=0.22, W_AX=0.32, W_PU=0.44 -- see
BASE_W_PD/BASE_W_AX/BASE_W_PU below).

RBL = W AND A, where W is the stored bit (Q) and A is the activation input
(confirmed against mult_w0a0/w0a1/w1a0/w1a1_test.spice): M1 (NMOS, gate=QB)
pulls RBL low when Q=0; M2 (PMOS, gate=QB, source=A) pulls RBL to A when
Q=1. That only gives RBL a low-impedance driver in 3 of the 4 (W,A) cases --
when W=1 and A=0, QB=0 turns M1 off AND leaves M2 at Vgs=0 (also off), so
RBL floats. Confirmed by direct simulation: at the current sizing RBL
settles to 1.11V (neither rail) with a real 12.6uA crowbar spike into
whatever reads it -- not a bug, just how this topology behaves for that
input combination. There's no "correct digital level" to gate on there, so:

Two-phase design:
  Phase 1 (hard gate): mult_w0a0_test, mult_w0a1_test, mult_w1a1_test (the
  3 cases with a real digital answer) across the full (W_M1, W_M2) grid x
  all 27 corners. RBL must land within 10% of VDD of the correct rail
  (matching the margin convention already used by hold_run/write_run/
  read_run elsewhere in this repo) at every corner for a sizing point to
  count as correct.
  Phase 2 (informational, gate-passing points only): read_delay (A->RBL
  propagation), access_energy's energy_read, and mult_w1a0_test's crowbar
  current/energy for the floating-RBL case. No numeric spec exists for any
  of these, so -- same as sizing_sweep.py's perf/power phase -- they're
  reported and plotted, never gated on.

Same docker-exec-into-the-IIC-container / per-thread-scratch-dir / resumable
JSONL cache machinery as sizing_sweep.py; see that file's docstring for why.

Usage:
    python3 m1m2_sweep.py --dry-run
    python3 m1m2_sweep.py --jobs 8
    python3 m1m2_sweep.py --w-m1-step 0.04 --w-m2-step 0.04   # coarse pass first
"""
from __future__ import annotations

import argparse
import itertools
import json
import os
import re
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TypedDict, cast

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# --------------------------------------------------------------------------
# Paths
# --------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent          # .../analog
SIM8T = ROOT / "sim" / "8t"
RESULTS = ROOT / "flow" / "results"
SWEEP_WORK = RESULTS / "_m1m2_sweep_work"               # gitignored under analog/flow/results
CACHE_PATH = RESULTS / "m1m2_sweep_cache.jsonl"
SUMMARY_CSV = RESULTS / "m1m2_sweep_summary.csv"

CONTAINER_NAME = "chipathon-2026-iic"
LAUNCH_SCRIPT = ROOT.parent / "scripts" / "run_docker_iic.sh"
CONTAINER_WORKSPACE = "/workspace/analog"
GF180 = "/foss/pdks/gf180mcuD/libs.tech/ngspice"


class Corner(TypedDict):
    name: str
    lib: str
    temp: int
    vdd: float


LIBS = {"tt": "typical", "ss": "ss", "ff": "ff"}
TEMPS = [-40, 25, 125]
VOLTS = [2.97, 3.30, 3.63]

CORNERS: list[Corner] = [
    Corner(
        name=f"{lib.upper()}_{'m' + str(abs(t)) if t < 0 else t}_{str(v).replace('.', 'p')}",
        lib=lib_name, temp=t, vdd=v,
    )
    for (lib, lib_name), t, v in itertools.product(LIBS.items(), TEMPS, VOLTS)
]

# the 3 (W,A) cases with a real digital answer -- the hard gate
GATE_TESTS = ["mult_w0a0_test", "mult_w0a1_test", "mult_w1a1_test"]
# informational only, gate-passing points only -- no spec, never excludes a point
INFO_TESTS = ["read_delay", "access_energy", "mult_w1a0_test"]

# fixed 6T core sizing -- the sizing_sweep.py result the user chose to build against
BASE_W_PD = 0.22
BASE_W_AX = 0.32
BASE_W_PU = 0.44
L_FIXED = 0.28

LOGIC_MARGIN = 0.10   # clean-digital-level margin, matches hold_run/write_run/read_run

NUM = r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?"

PVT_TEMPLATE = """* AUTO-GENERATED scratch file -- m1m2_sweep.py (do not hand-edit)
.include {gf180}/design.ngspice
.lib {gf180}/sm141064.ngspice {lib}
.temp {temp}
.param VDD_CORNER={vdd}
"""

PARAMS_6T_TEMPLATE = """* AUTO-GENERATED scratch file -- m1m2_sweep.py (fixed 6T core, do not hand-edit)
.param W_PU={w_pu}u\tL_PU={l}u
.param W_PD={w_pd}u\tL_PD={l}u
.param W_AX={w_ax}u\tL_AX={l}u
"""

PARAMS_8T_TEMPLATE = """* AUTO-GENERATED scratch file -- m1m2_sweep.py (do not hand-edit)
.param W_M1={w_m1}u\tL_M1={l}u
.param W_M2={w_m2}u\tL_M2={l}u
"""


# --------------------------------------------------------------------------
# docker exec plumbing (same pattern as sizing_sweep.py / pvt_sweep.ipynb)
# --------------------------------------------------------------------------
def docker_exec(*args, cwd=None, **kwargs):
    docker_args = ["docker", "exec"]
    if cwd:
        docker_args += ["-w", cwd]
    docker_args += [CONTAINER_NAME, "bash", "-lc", " ".join(args)]
    kwargs.setdefault("check", False)
    return subprocess.run(docker_args, **kwargs)  # noqa: PLW1510 -- check= set via setdefault above


def ensure_container_running() -> None:
    up = subprocess.run(
        ["docker", "ps", "-q", "--filter", f"name=^{CONTAINER_NAME}$"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    if up:
        return
    print(f"[setup] {CONTAINER_NAME} not running -- launching via {LAUNCH_SCRIPT}")
    subprocess.run(["bash", str(LAUNCH_SCRIPT)], env={**os.environ, "IIC_DETACH": "1"}, check=True)


def to_container_path(path: Path) -> str:
    return f"{CONTAINER_WORKSPACE}/{path.relative_to(ROOT).as_posix()}"


def had_error(proc: subprocess.CompletedProcess) -> bool:
    blob = proc.stdout + proc.stderr
    return proc.returncode != 0 or re.search(
        r"(?im)^\s*(fatal|undefined parameter|can't find|error on line|syntax error)", blob
    ) is not None


def meas_last(out: str, name: str) -> float | None:
    m = re.findall(rf"^\s*{re.escape(name)}\s*=\s*({NUM})", out, re.MULTILINE)
    return float(m[-1]) if m else None


# --------------------------------------------------------------------------
# per-worker scratch dirs -- one per thread, reused across all its tasks
# --------------------------------------------------------------------------
_thread_local = threading.local()
_slot_counter = itertools.count()
_slot_lock = threading.Lock()


def scratch_dir_for_thread() -> Path:
    if not hasattr(_thread_local, "dir"):
        with _slot_lock:
            slot = next(_slot_counter)
        d = SWEEP_WORK / f"slot_{slot}"
        d.mkdir(parents=True, exist_ok=True)
        _thread_local.dir = d
    return _thread_local.dir


ALL_DECK_TESTS = GATE_TESTS + INFO_TESTS
_BASE_DECKS = {test: (SIM8T / f"{test}.spice").read_text() for test in ALL_DECK_TESTS}


def render_deck(test: str, params6_path: Path, params8_path: Path, pvt_path: Path,
                 raw_path: Path | None) -> str:
    """Base deck, but its params_6T.spice / params_8T.spice / pvt.spice includes
    point at this task's private scratch files, and the .raw waveform dump is
    dropped so thousands of runs don't collide on / thrash a shared file."""
    text = _BASE_DECKS[test]
    text = re.sub(r"^\.include\s+\S*params_6T\.spice\s*$",
                  f".include {to_container_path(params6_path)}", text, flags=re.MULTILINE)
    text = re.sub(r"^\.include\s+\S*params_8T\.spice\s*$",
                  f".include {to_container_path(params8_path)}", text, flags=re.MULTILINE)
    text = re.sub(r"^\.include\s+\S*/pvt\.spice\s*$",
                  f".include {to_container_path(pvt_path)}", text, flags=re.MULTILINE)
    if raw_path is None:
        text = re.sub(r"^write\s+\S+\.raw\s+all\s*$", "* (raw dump skipped for sweep)", text, flags=re.MULTILINE)
    else:
        text = re.sub(r"^write\s+\S+\.raw\s+all\s*$",
                       f"write {to_container_path(raw_path)} all", text, flags=re.MULTILINE)
    return text


# --------------------------------------------------------------------------
# cache -- JSONL, one line per (W_M1, W_M2, corner, cache-test) result.
# --------------------------------------------------------------------------
def cache_key(w_m1: float, w_m2: float, corner_name: str, cache_test: str) -> str:
    return f"{w_m1:.3f}|{w_m2:.3f}|{corner_name}|{cache_test}"


class Cache:
    def __init__(self, path: Path):
        self.path = path
        self.records: dict[str, dict] = {}
        self._lock = threading.Lock()
        if path.exists():
            n_bad = 0
            for line in path.read_text().splitlines():
                if not line.strip():
                    continue
                try:
                    rec = json.loads(line)
                    self.records[rec["key"]] = rec
                except (json.JSONDecodeError, KeyError):
                    n_bad += 1
            if n_bad:
                print(f"[cache] skipped {n_bad} malformed line(s) in {path.name}")
        self._fh = open(path, "a")  # noqa: SIM115 -- deliberately long-lived, closed in close()

    def get(self, key: str) -> dict | None:
        return self.records.get(key)

    def put(self, rec: dict) -> None:
        with self._lock:
            self.records[rec["key"]] = rec
            self._fh.write(json.dumps(rec) + "\n")
            self._fh.flush()

    def close(self) -> None:
        self._fh.close()


def _cache_hit_is_done(cache: Cache, key: str) -> bool:
    """Only counts as done if the ngspice run actually completed (ran_ok=True)
    -- ran_ok=False means docker/ngspice itself failed and is worth retrying."""
    rec = cache.get(key)
    return rec is not None and bool(rec.get("ran_ok", False))


# --------------------------------------------------------------------------
# one (W_M1, W_M2, corner, test) run
# --------------------------------------------------------------------------
@dataclass
class Task:
    w_m1: float
    w_m2: float
    corner: Corner
    test: str


def cache_tests_for(test: str) -> list[str]:
    if test == "access_energy":
        return ["access_energy_read"]
    if test == "mult_w1a0_test":
        return ["mult_w1a0_energy", "mult_w1a0_crowbar"]
    return [test]


def run_task(task: Task, timeout: float, keep_raw: bool) -> list[dict]:
    d = scratch_dir_for_thread()
    params6_path = d / "params_6T.spice"
    params8_path = d / "params_8T.spice"
    pvt_path = d / "pvt.spice"
    deck_path = d / f"{task.test}.spice"
    raw_path = (d / f"{task.test}.raw") if keep_raw else None

    params6_path.write_text(PARAMS_6T_TEMPLATE.format(w_pu=BASE_W_PU, w_pd=BASE_W_PD, w_ax=BASE_W_AX, l=L_FIXED))
    params8_path.write_text(PARAMS_8T_TEMPLATE.format(w_m1=task.w_m1, w_m2=task.w_m2, l=L_FIXED))
    pvt_path.write_text(PVT_TEMPLATE.format(gf180=GF180, lib=task.corner["lib"], temp=task.corner["temp"], vdd=task.corner["vdd"]))
    deck_path.write_text(render_deck(task.test, params6_path, params8_path, pvt_path, raw_path))

    proc = docker_exec("ngspice", "-b", to_container_path(deck_path), cwd=CONTAINER_WORKSPACE,
                        capture_output=True, text=True, timeout=timeout)
    err = had_error(proc)
    out = proc.stdout + proc.stderr
    vdd = task.corner["vdd"]

    def rec(cache_test: str, metric: str, value: float | None, ok: bool) -> dict:
        return {
            "key": cache_key(task.w_m1, task.w_m2, task.corner["name"], cache_test),
            "w_m1": task.w_m1, "w_m2": task.w_m2,
            "corner": task.corner["name"], "vdd": vdd,
            "test": cache_test, "metric": metric, "value": value,
            "ran_ok": not err, "pass": bool(ok), "ts": time.time(),
            "returncode": proc.returncode,
            "error_tail": out[-500:] if err else None,
        }

    if task.test in ("mult_w0a0_test", "mult_w0a1_test"):
        value = meas_last(out, "o_final")
        ok = (not err) and value is not None and value <= LOGIC_MARGIN * vdd
        return [rec(task.test, "o_final_low", value, ok)]

    if task.test == "mult_w1a1_test":
        value = meas_last(out, "o_final")
        ok = (not err) and value is not None and value >= (1 - LOGIC_MARGIN) * vdd
        return [rec(task.test, "o_final_high", value, ok)]

    if task.test == "read_delay":
        value = meas_last(out, "t_read")
        return [rec("read_delay", "read_delay_s", value, (not err) and value is not None)]

    if task.test == "access_energy":
        er = meas_last(out, "energy_read")
        # energy_write also printed by this deck but irrelevant here -- 6T core is fixed
        return [rec("access_energy_read", "energy_read_J", er, (not err) and er is not None)]

    if task.test == "mult_w1a0_test":
        energy = meas_last(out, "total_energy")
        crowbar = meas_last(out, "max_crowbar_current")
        return [
            rec("mult_w1a0_energy", "crowbar_energy_J", energy, (not err) and energy is not None),
            rec("mult_w1a0_crowbar", "max_crowbar_current_A", crowbar, (not err) and crowbar is not None),
        ]

    raise ValueError(f"unknown test {task.test!r}")


# --------------------------------------------------------------------------
# sweep driver
# --------------------------------------------------------------------------
def frange(lo: float, hi: float, step: float) -> list[float]:
    return [round(float(x), 2) for x in np.arange(lo, hi + step / 2, step)]


def build_tasks(sizing_points: list[tuple[float, float]], tests: list[str], cache: Cache) -> list[Task]:
    tasks = []
    for w_m1, w_m2 in sizing_points:
        for corner in CORNERS:
            for test in tests:
                cts = cache_tests_for(test)
                if all(_cache_hit_is_done(cache, cache_key(w_m1, w_m2, corner["name"], ct)) for ct in cts):
                    continue
                tasks.append(Task(w_m1, w_m2, corner, test))
    return tasks


def run_sweep(tasks: list[Task], cache: Cache, jobs: int, timeout: float, keep_raw: bool) -> None:
    from concurrent.futures import ThreadPoolExecutor, as_completed

    if not tasks:
        print("[sweep] nothing to do -- everything already cached")
        return

    print(f"[sweep] {len(tasks)} simulations to run across {jobs} worker(s)")
    t0 = time.time()
    done = 0
    failed = 0
    with ThreadPoolExecutor(max_workers=jobs) as ex:
        futures = {ex.submit(run_task, t, timeout, keep_raw): t for t in tasks}
        for fut in as_completed(futures):
            task = futures[fut]
            try:
                for r in fut.result():
                    cache.put(r)
                    if not r["ran_ok"]:
                        failed += 1
            except Exception as e:  # noqa: BLE001 -- one bad sim must not kill the whole sweep
                failed += 1
                print(f"[!] {task.test} @ W_M1={task.w_m1} W_M2={task.w_m2} {task.corner['name']}: {e}")
            done += 1
            if done % 25 == 0 or done == len(tasks):
                elapsed = time.time() - t0
                rate = done / elapsed if elapsed > 0 else 0
                eta = (len(tasks) - done) / rate if rate > 0 else float("inf")
                fail_flag = f"  [{failed} FAILED -- check container health]" if failed else ""
                print(f"[sweep] {done}/{len(tasks)} ({100*done/len(tasks):.1f}%) "
                      f"-- {rate:.1f} sim/s -- ETA {eta/60:.1f} min{fail_flag}", flush=True)
    if failed:
        print(f"[sweep] {failed}/{len(tasks)} run(s) failed (ran_ok=False) -- they'll retry automatically "
              f"next run; inspect 'error_tail' in {CACHE_PATH.name} if they keep failing")


# --------------------------------------------------------------------------
# aggregation
# --------------------------------------------------------------------------
def gate_status(cache: Cache, w_m1: float, w_m2: float, cache_test: str) -> tuple[bool, int]:
    """(all 27 corners passed, number that didn't)."""
    n_bad = 0
    for corner in CORNERS:
        r = cache.get(cache_key(w_m1, w_m2, corner["name"], cache_test))
        if r is None or not r["ran_ok"] or not r["pass"]:
            n_bad += 1
    return n_bad == 0, n_bad


def worst_over_corners(cache: Cache, w_m1: float, w_m2: float, cache_test: str, reducer=max) -> tuple[float, int]:
    vals, missing = [], 0
    for corner in CORNERS:
        r = cache.get(cache_key(w_m1, w_m2, corner["name"], cache_test))
        if r is None or not r["ran_ok"] or r["value"] is None:
            missing += 1
        else:
            vals.append(r["value"])
    worst = reducer(vals) if vals else float("nan")
    return worst, missing


def aggregate_gate(cache: Cache, sizing_points: list[tuple[float, float]]) -> pd.DataFrame:
    rows = []
    for w_m1, w_m2 in sizing_points:
        row = {"W_M1": w_m1, "W_M2": w_m2, "total_width_um": w_m1 + w_m2}  # single M1, single M2 -- no x2
        all_pass = True
        for test in GATE_TESTS:
            ok, n_bad = gate_status(cache, w_m1, w_m2, test)
            row[f"{test}_pass"] = ok
            row[f"{test}_n_bad"] = n_bad
            all_pass = all_pass and ok
        row["pass_correctness"] = all_pass
        rows.append(row)
    return pd.DataFrame(rows)


def add_info_metrics(df: pd.DataFrame, cache: Cache) -> pd.DataFrame:
    cols = {
        "worst_read_delay_s": [], "worst_read_energy_J": [],
        "worst_crowbar_energy_J": [], "worst_max_crowbar_current_A": [],
    }
    for _, r in df.iterrows():
        if not bool(r["pass_correctness"]):
            for v in cols.values():
                v.append(float("nan"))
            continue
        w_m1, w_m2 = float(r["W_M1"]), float(r["W_M2"])
        cols["worst_read_delay_s"].append(worst_over_corners(cache, w_m1, w_m2, "read_delay", max)[0])
        cols["worst_read_energy_J"].append(worst_over_corners(cache, w_m1, w_m2, "access_energy_read", max)[0])
        cols["worst_crowbar_energy_J"].append(worst_over_corners(cache, w_m1, w_m2, "mult_w1a0_energy", max)[0])
        cols["worst_max_crowbar_current_A"].append(worst_over_corners(cache, w_m1, w_m2, "mult_w1a0_crowbar", max)[0])
    for k, v in cols.items():
        df[k] = v
    return df


# --------------------------------------------------------------------------
# plotting
# --------------------------------------------------------------------------
def _panel(ax, sub: pd.DataFrame, col: str, title: str, cmap: str = "viridis") -> None:
    piv = sub.pivot_table(index="W_M2", columns="W_M1", values=col)
    X, Y = np.meshgrid(np.asarray(piv.columns.values), np.asarray(piv.index.values))
    Z = piv.values
    finite = Z[np.isfinite(Z)]
    if finite.size == 0:
        ax.set_title(f"{title}\n(no data)")
        return
    cf = ax.contourf(X, Y, Z, levels=21, cmap=cmap)
    ax.figure.colorbar(cf, ax=ax)
    ax.set_title(title)
    ax.set_xlabel("W_M1 (um)")
    ax.set_ylabel("W_M2 (um)")


def plot_gate(df: pd.DataFrame, out_dir: Path) -> Path:
    fig, ax = plt.subplots(figsize=(8, 6))
    piv = df.pivot_table(index="W_M2", columns="W_M1", values="pass_correctness")
    X, Y = np.meshgrid(np.asarray(piv.columns.values), np.asarray(piv.index.values))
    ax.contourf(X, Y, piv.values.astype(float), levels=[-0.5, 0.5, 1.5], colors=["#b2182b", "#2166ac"])
    ax.set_title("AND-multiply correctness (w0a0, w0a1, w1a1)\nblue = passes all 27 corners, red = fails")
    ax.set_xlabel("W_M1 (um)")
    ax.set_ylabel("W_M2 (um)")
    fig.suptitle(f"M1/M2 read-port sweep -- 6T core fixed at W_PD={BASE_W_PD}, W_AX={BASE_W_AX}, "
                 f"W_PU={BASE_W_PU}, L={L_FIXED} um", fontsize=10)
    fig.tight_layout()
    out_path = out_dir / "m1m2_gate_contour.png"
    fig.savefig(out_path, dpi=130)
    plt.close(fig)
    return out_path


def plot_info(df: pd.DataFrame, out_dir: Path) -> Path | None:
    sub = cast(pd.DataFrame, df[df["pass_correctness"]])
    if sub.empty:
        return None
    sub = sub.assign(worst_crowbar_energy_fJ=sub["worst_crowbar_energy_J"] * 1e15)

    fig, axes = plt.subplots(2, 2, figsize=(11, 9))
    _panel(axes[0, 0], sub, "worst_read_delay_s", "Worst-case read/compute delay (s)")
    _panel(axes[0, 1], sub, "worst_read_energy_J", "Worst-case read energy (J)")
    _panel(axes[1, 0], sub, "worst_crowbar_energy_fJ", "W=1,A=0 floating-RBL energy (fJ)", cmap="magma")
    _panel(axes[1, 1], sub, "worst_max_crowbar_current_A", "W=1,A=0 peak crowbar current (A)", cmap="magma")
    fig.suptitle("M1/M2 perf/power (correctness-passing points only) -- no numeric spec, lower is better\n"
                 "bottom row: the W=1,A=0 floating-RBL case (informational, not gated -- see script docstring)")
    fig.tight_layout()
    out_path = out_dir / "m1m2_info_contours.png"
    fig.savefig(out_path, dpi=130)
    plt.close(fig)
    return out_path


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--w-m1-min", type=float, default=0.22)
    ap.add_argument("--w-m1-max", type=float, default=0.60)
    ap.add_argument("--w-m1-step", type=float, default=0.02)
    ap.add_argument("--w-m2-min", type=float, default=0.22)
    ap.add_argument("--w-m2-max", type=float, default=0.60)
    ap.add_argument("--w-m2-step", type=float, default=0.02)
    ap.add_argument("--jobs", type=int, default=min(16, os.cpu_count() or 8))
    ap.add_argument("--timeout", type=float, default=60.0)
    ap.add_argument("--keep-raw", action="store_true")
    ap.add_argument("--skip-info", action="store_true", help="phase 1 only (correctness), skip delay/power/crowbar")
    ap.add_argument("--top-n", type=int, default=10)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    w_m1_vals = frange(args.w_m1_min, args.w_m1_max, args.w_m1_step)
    w_m2_vals = frange(args.w_m2_min, args.w_m2_max, args.w_m2_step)
    sizing_points = list(itertools.product(w_m1_vals, w_m2_vals))

    n_points = len(sizing_points)
    n_phase1 = n_points * len(CORNERS) * len(GATE_TESTS)
    print(f"[sweep] fixed 6T core: W_PD={BASE_W_PD} W_AX={BASE_W_AX} W_PU={BASE_W_PU} L={L_FIXED} um")
    print(f"[sweep] W_M1: {len(w_m1_vals)} values [{w_m1_vals[0]}..{w_m1_vals[-1]}]")
    print(f"[sweep] W_M2: {len(w_m2_vals)} values [{w_m2_vals[0]}..{w_m2_vals[-1]}]")
    print(f"[sweep] phase 1 (correctness, hard gate): {n_points} points x {len(CORNERS)} corners "
          f"x {len(GATE_TESTS)} tests = {n_phase1} simulations")
    print(f"[sweep] phase 2 (delay/power/crowbar, informational): up to {n_points} points x {len(CORNERS)} "
          f"corners x {len(INFO_TESTS)} tests -- actual count depends on how many points pass phase 1")

    if args.dry_run:
        return

    RESULTS.mkdir(parents=True, exist_ok=True)
    SWEEP_WORK.mkdir(parents=True, exist_ok=True)
    ensure_container_running()

    cache = Cache(CACHE_PATH)
    print(f"[cache] {len(cache.records)} result(s) already cached in {CACHE_PATH.name}")

    print("\n=== phase 1: AND-multiply correctness (hard gate) ===")
    tasks = build_tasks(sizing_points, GATE_TESTS, cache)
    run_sweep(tasks, cache, args.jobs, args.timeout, args.keep_raw)

    df = aggregate_gate(cache, sizing_points)
    n_pass = int(df["pass_correctness"].sum())
    print(f"[phase 1] {n_pass}/{len(df)} sizing point(s) compute correctly across all corners")

    if not args.skip_info and n_pass > 0:
        print("\n=== phase 2: read delay/energy + W=1,A=0 crowbar (informational, passing points only) ===")
        pass_sub = cast(pd.DataFrame, df[df["pass_correctness"]])
        passing_points = list(zip(pass_sub["W_M1"], pass_sub["W_M2"]))
        tasks = build_tasks(passing_points, INFO_TESTS, cache)
        run_sweep(tasks, cache, args.jobs, args.timeout, args.keep_raw)
        df = add_info_metrics(df, cache)

    cache.close()

    df.to_csv(SUMMARY_CSV, index=False)
    print(f"\n[out] {len(df)} sizing point(s) -> {SUMMARY_CSV}")

    gate_path = plot_gate(df, RESULTS)
    print(f"[out] correctness gate plot -> {gate_path}")
    if "worst_read_delay_s" in df.columns:
        info_path = plot_info(df, RESULTS)
        if info_path:
            print(f"[out] perf/power/crowbar plot -> {info_path}")

    passing = cast(pd.DataFrame, cast(pd.DataFrame, df[df["pass_correctness"]]).sort_values("total_width_um"))
    print("\n=== smallest-total-width points computing correctly (all corners) ===")
    if passing.empty:
        print("  none -- no (W_M1, W_M2) cleared AND-multiply correctness across all corners")
    else:
        have_info = "worst_read_delay_s" in df.columns
        for _, r in passing.head(args.top_n).iterrows():
            line = f"    W_M1={r.W_M1:.2f}  W_M2={r.W_M2:.2f}  total_width={r.total_width_um:.2f}um"
            if have_info and bool(pd.notna(r.get("worst_read_delay_s"))):
                line += (f"  |  t_read={r.worst_read_delay_s*1e12:.1f}ps"
                         f"  E_read={r.worst_read_energy_J*1e15:.2f}fJ"
                         f"  E_crowbar(w1a0)={r.worst_crowbar_energy_J*1e15:.2f}fJ"
                         f"  I_crowbar_pk(w1a0)={r.worst_max_crowbar_current_A*1e9:.2f}nA")
            print(line)


if __name__ == "__main__":
    main()
