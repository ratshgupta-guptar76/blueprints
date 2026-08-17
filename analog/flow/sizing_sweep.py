#!/usr/bin/env python3
"""2D sizing sweep for the 8T DCIM bitcell -- finds the smallest-area (W_PD, W_AX)
at a given W_PU that clears WLWM and hold-SNM across all SS/TT/FF x PVT corners,
then reports read/write delay and hold/dynamic power for the sizings that pass.

Two-phase design:
  Phase 1 (hard gates): write_margin + hold_snm across the full (W_PD, W_AX,
  W_PU) grid x all 27 corners. A sizing point must clear WLWM > 0.912V and
  hold SNM > 0.755V at every corner to be a candidate at all -- this is what
  "smallest cell" is minimized over.
  Phase 2 (informational): write_delay, read_delay, hold_power, access_energy
  -- run ONLY on sizing points that passed phase 1, still across all 27
  corners. There's no numeric spec for these (none was given), so they never
  exclude a sizing point; they're reported and plotted so you can pick the
  final tradeoff among the phase-1 survivors by eye.

Mirrors the conventions of pvt_sweep.ipynb: ngspice + the GF180 PDK only exist
inside the IIC-OSIC-TOOLS container (chipathon-2026-iic), reached via `docker
exec ... bash -lc`. That notebook rewrites the single shared designs/pvt.spice
file per corner and runs sequentially -- fine for ~45 runs. This sweep is
orders of magnitude larger, so instead of sharing files it gives each worker
thread its own scratch directory (analog/flow/results/_sweep_work/slot_N/)
holding a private params_6T.spice, pvt.spice, and deck copy, so N threads can
drive N `docker exec` calls concurrently without racing on the same include file.

Usage:
    python3 sizing_sweep.py --dry-run
    python3 sizing_sweep.py --w-pu 0.44 0.52 --jobs 16
    python3 sizing_sweep.py --w-pd-step 0.04 --w-ax-step 0.04   # coarse pass first
    python3 sizing_sweep.py --skip-perf-power                   # phase 1 only
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
from matplotlib.colors import TwoSlopeNorm

# --------------------------------------------------------------------------
# Paths (host side) -- mirrors pvt_sweep.ipynb's HOST_WORKSPACE / ROOT split
# --------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent          # .../analog
SIM8T = ROOT / "sim" / "8t"
RESULTS = ROOT / "flow" / "results"
SWEEP_WORK = RESULTS / "_sweep_work"                    # gitignored under analog/flow/results
CACHE_PATH = RESULTS / "sizing_sweep_cache.jsonl"
SUMMARY_CSV = RESULTS / "sizing_sweep_summary.csv"

# -- paths: CONTAINER_* -- ngspice + PDK only exist inside the container
CONTAINER_NAME = "chipathon-2026-iic"          # fixed by scripts/run_docker_iic.sh --name
LAUNCH_SCRIPT = ROOT.parent / "scripts" / "run_docker_iic.sh"
CONTAINER_WORKSPACE = "/workspace/analog"
GF180 = "/foss/pdks/gf180mcuD/libs.tech/ngspice"

# --------------------------------------------------------------------------
# Corners: SS/TT/FF x {-40, 25, 125} C x {2.97, 3.30, 3.63} V  (27 total)
# lib name must match a .LIB section in sm141064.ngspice (no "tt" -- typical)
# --------------------------------------------------------------------------
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

# phase 1: hard pass/fail gates that define "smallest cell"
STABILITY_TESTS = ["write_margin", "hold_snm"]
# phase 2: informational only -- no spec, never excludes a sizing point
PERF_POWER_TESTS = ["write_delay", "read_delay", "hold_power", "access_energy"]

# -- signoff specs (fixed absolute floors, not proportional to VDD) --
WLWM_MIN = 0.912   # V, strict >
SNM_MIN = 0.755    # V, strict >

L_FIXED = 0.28      # um, applies to PD/PU/AX for the whole sweep

NUM = r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?"

PVT_TEMPLATE = """* AUTO-GENERATED scratch file -- sizing_sweep.py (do not hand-edit)
.include {gf180}/design.ngspice
.lib {gf180}/sm141064.ngspice {lib}
.temp {temp}
.param VDD_CORNER={vdd}
"""

PARAMS_TEMPLATE = """* AUTO-GENERATED scratch file -- sizing_sweep.py (do not hand-edit)
.param W_PU={w_pu}u\tL_PU={l}u
.param W_PD={w_pd}u\tL_PD={l}u
.param W_AX={w_ax}u\tL_AX={l}u
"""


# --------------------------------------------------------------------------
# docker exec plumbing (same pattern as pvt_sweep.ipynb)
# --------------------------------------------------------------------------
def docker_exec(*args, cwd=None, **kwargs):
    """docker exec via a login shell -- ngspice only lands on PATH through the
    container's profile scripts, not the bare docker-exec PATH."""
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
# per-worker scratch dirs -- one per thread, reused across all its tasks so
# thousands of runs don't leave thousands of files behind
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


_BASE_DECKS = {test: (SIM8T / f"{test}.spice").read_text()
               for test in STABILITY_TESTS + PERF_POWER_TESTS}


def render_deck(test: str, params_path: Path, pvt_path: Path, raw_path: Path | None) -> str:
    """Base deck, but its params_6T.spice / pvt.spice includes point at this
    task's private scratch files instead of the shared designs/ copies, and
    the .raw waveform dump is dropped (or redirected) so thousands of runs
    don't collide on / thrash the shared sim/8t/results/*.raw file."""
    text = _BASE_DECKS[test]
    text = re.sub(
        r"^\.include\s+\S*params_6T\.spice\s*$",
        f".include {to_container_path(params_path)}",
        text, flags=re.MULTILINE,
    )
    text = re.sub(
        r"^\.include\s+\S*/pvt\.spice\s*$",
        f".include {to_container_path(pvt_path)}",
        text, flags=re.MULTILINE,
    )
    if raw_path is None:
        text = re.sub(r"^write\s+\S+\.raw\s+all\s*$", "* (raw dump skipped for sweep)", text, flags=re.MULTILINE)
    else:
        text = re.sub(
            r"^write\s+\S+\.raw\s+all\s*$",
            f"write {to_container_path(raw_path)} all",
            text, flags=re.MULTILINE,
        )
    return text


# --------------------------------------------------------------------------
# cache -- JSONL, one line per (sizing point, corner, cache-test) result.
# access_energy's single ngspice run yields two metrics (energy_write,
# energy_read); those get two cache entries under synthetic cache-test names
# "access_energy_write" / "access_energy_read" so each is independently
# resumable, even though both come from one deck invocation.
# Loaded at startup so a re-run skips whatever already ran; appended to as we
# go so a killed sweep can resume from wherever it stopped.
# --------------------------------------------------------------------------
def cache_key(w_pd: float, w_ax: float, w_pu: float, corner_name: str, cache_test: str) -> str:
    return f"{w_pd:.3f}|{w_ax:.3f}|{w_pu:.3f}|{corner_name}|{cache_test}"


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


# --------------------------------------------------------------------------
# one (sizing point, corner, test) run -- may yield >1 cache record
# (access_energy yields two: energy_write and energy_read)
# --------------------------------------------------------------------------
@dataclass
class Task:
    w_pd: float
    w_ax: float
    w_pu: float
    corner: Corner
    test: str


def cache_tests_for(test: str) -> list[str]:
    """The cache-test name(s) a given deck's run produces."""
    if test == "access_energy":
        return ["access_energy_write", "access_energy_read"]
    return [test]


def run_task(task: Task, timeout: float, keep_raw: bool) -> list[dict]:
    d = scratch_dir_for_thread()
    params_path = d / "params_6T.spice"
    pvt_path = d / "pvt.spice"
    deck_path = d / f"{task.test}.spice"
    raw_path = (d / f"{task.test}.raw") if keep_raw else None

    params_path.write_text(PARAMS_TEMPLATE.format(w_pu=task.w_pu, w_pd=task.w_pd, w_ax=task.w_ax, l=L_FIXED))
    pvt_path.write_text(PVT_TEMPLATE.format(gf180=GF180, lib=task.corner["lib"], temp=task.corner["temp"], vdd=task.corner["vdd"]))
    deck_path.write_text(render_deck(task.test, params_path, pvt_path, raw_path))

    proc = docker_exec("ngspice", "-b", to_container_path(deck_path), cwd=CONTAINER_WORKSPACE,
                        capture_output=True, text=True, timeout=timeout)
    err = had_error(proc)
    out = proc.stdout + proc.stderr

    def rec(cache_test: str, metric: str, value: float | None, ok: bool) -> dict:
        return {
            "key": cache_key(task.w_pd, task.w_ax, task.w_pu, task.corner["name"], cache_test),
            "w_pd": task.w_pd, "w_ax": task.w_ax, "w_pu": task.w_pu,
            "corner": task.corner["name"], "vdd": task.corner["vdd"],
            "test": cache_test, "metric": metric, "value": value,
            "ran_ok": not err, "pass": bool(ok), "ts": time.time(),
            # diagnostic only, so a batch failure (e.g. container died mid-sweep)
            # can be root-caused later without having to reproduce it
            "returncode": proc.returncode,
            "error_tail": out[-500:] if err else None,
        }

    if task.test == "write_margin":
        m = re.search(rf"WLWM_RESULT\s*:\s*({NUM})", out)
        endpoints_ok = "[FAIL]" not in out
        value = float(m.group(1)) if (m and endpoints_ok) else None
        ok = (not err) and endpoints_ok and value is not None and value > WLWM_MIN
        return [rec("write_margin", "wlwm", value, ok)]

    if task.test == "hold_snm":
        value = meas_last(out, "hold_snm")
        ok = (not err) and value is not None and value > SNM_MIN
        return [rec("hold_snm", "snm", value, ok)]

    if task.test == "write_delay":
        value = meas_last(out, "t_write")
        return [rec("write_delay", "write_delay_s", value, (not err) and value is not None)]

    if task.test == "read_delay":
        value = meas_last(out, "t_read")
        return [rec("read_delay", "read_delay_s", value, (not err) and value is not None)]

    if task.test == "hold_power":
        value = meas_last(out, "p_hold")
        return [rec("hold_power", "hold_power_W", value, (not err) and value is not None)]

    if task.test == "access_energy":
        ew = meas_last(out, "energy_write")
        er = meas_last(out, "energy_read")
        return [
            rec("access_energy_write", "energy_write_J", ew, (not err) and ew is not None),
            rec("access_energy_read", "energy_read_J", er, (not err) and er is not None),
        ]

    raise ValueError(f"unknown test {task.test!r}")


# --------------------------------------------------------------------------
# sweep driver
# --------------------------------------------------------------------------
def frange(lo: float, hi: float, step: float) -> list[float]:
    return [round(float(x), 2) for x in np.arange(lo, hi + step / 2, step)]


def _cache_hit_is_done(cache: Cache, key: str) -> bool:
    """A cache entry only counts as 'done' if the underlying ngspice run
    actually completed (ran_ok=True) -- ran_ok=False means docker/ngspice
    itself failed (container down, timeout, transient error), which is worth
    retrying on resume. A legitimate simulated result (e.g. write_margin's
    bisection endpoints genuinely failing, value=None) still has ran_ok=True
    and correctly stays cached rather than being retried forever."""
    rec = cache.get(key)
    return rec is not None and bool(rec.get("ran_ok", False))


def build_tasks(sizing_points: list[tuple[float, float, float]], tests: list[str], cache: Cache) -> list[Task]:
    tasks = []
    for w_pd, w_ax, w_pu in sizing_points:
        for corner in CORNERS:
            for test in tests:
                cts = cache_tests_for(test)
                if all(_cache_hit_is_done(cache, cache_key(w_pd, w_ax, w_pu, corner["name"], ct)) for ct in cts):
                    continue
                tasks.append(Task(w_pd, w_ax, w_pu, corner, test))
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
                print(f"[!] {task.test} @ W_PD={task.w_pd} W_AX={task.w_ax} W_PU={task.w_pu} "
                      f"{task.corner['name']}: {e}")
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
def worst_over_corners(cache: Cache, w_pd: float, w_ax: float, w_pu: float, cache_test: str,
                        reducer=min) -> tuple[float, int]:
    """reducer=min for specs with a floor (WLWM, SNM); reducer=max for
    delay/power, where the worst case is the largest value."""
    vals, missing = [], 0
    for corner in CORNERS:
        r = cache.get(cache_key(w_pd, w_ax, w_pu, corner["name"], cache_test))
        if r is None or not r["ran_ok"] or r["value"] is None:
            missing += 1
        else:
            vals.append(r["value"])
    worst = reducer(vals) if vals else float("nan")
    return worst, missing


def aggregate_stability(cache: Cache, sizing_points) -> pd.DataFrame:
    rows = []
    for w_pd, w_ax, w_pu in sizing_points:
        worst_wlwm, wlwm_bad = worst_over_corners(cache, w_pd, w_ax, w_pu, "write_margin", min)
        worst_snm, snm_bad = worst_over_corners(cache, w_pd, w_ax, w_pu, "hold_snm", min)
        # any missing/endpoint-failed corner invalidates the point outright
        pass_wlwm = wlwm_bad == 0 and worst_wlwm > WLWM_MIN
        pass_snm = snm_bad == 0 and worst_snm > SNM_MIN

        rows.append({
            "W_PD": w_pd, "W_AX": w_ax, "W_PU": w_pu,
            "total_width_um": 2 * (w_pd + w_pu + w_ax),  # 2x each: PD1/2, PU1/2, AX1/2 in the 6T core
            "worst_wlwm_V": worst_wlwm, "wlwm_missing": wlwm_bad, "pass_wlwm": pass_wlwm,
            "worst_snm_V": worst_snm, "snm_missing": snm_bad, "pass_snm": pass_snm,
            "pass_both": pass_wlwm and pass_snm,
            "n_corners": len(CORNERS),
        })
    return pd.DataFrame(rows)


def add_perf_power(df: pd.DataFrame, cache: Cache) -> pd.DataFrame:
    """Fills in delay/power columns for rows where pass_both is True; NaN
    elsewhere (phase 2 was never run on those points)."""
    cols = {
        "worst_write_delay_s": [], "worst_read_delay_s": [],
        "worst_hold_power_W": [], "worst_energy_write_J": [], "worst_energy_read_J": [],
    }
    for _, r in df.iterrows():
        if not bool(r["pass_both"]):
            for v in cols.values():
                v.append(float("nan"))
            continue
        w_pd, w_ax, w_pu = float(r["W_PD"]), float(r["W_AX"]), float(r["W_PU"])
        cols["worst_write_delay_s"].append(worst_over_corners(cache, w_pd, w_ax, w_pu, "write_delay", max)[0])
        cols["worst_read_delay_s"].append(worst_over_corners(cache, w_pd, w_ax, w_pu, "read_delay", max)[0])
        cols["worst_hold_power_W"].append(worst_over_corners(cache, w_pd, w_ax, w_pu, "hold_power", max)[0])
        cols["worst_energy_write_J"].append(worst_over_corners(cache, w_pd, w_ax, w_pu, "access_energy_write", max)[0])
        cols["worst_energy_read_J"].append(worst_over_corners(cache, w_pd, w_ax, w_pu, "access_energy_read", max)[0])
    for k, v in cols.items():
        df[k] = v
    return df


# --------------------------------------------------------------------------
# plotting
# --------------------------------------------------------------------------
def _contour_panel(ax, sub: pd.DataFrame, col: str, title: str, thresh: float | None,
                    cmap: str = "RdBu") -> None:
    piv = sub.pivot_table(index="W_AX", columns="W_PD", values=col)
    X, Y = np.meshgrid(np.asarray(piv.columns.values), np.asarray(piv.index.values))
    Z = piv.values

    finite = Z[np.isfinite(Z)]
    if finite.size == 0:
        ax.set_title(f"{title}\n(no data)")
        return

    if thresh is not None:
        span = max(finite.max() - finite.min(), 1e-12)
        vmin = min(finite.min(), thresh - 0.02 * span)
        vmax = max(finite.max(), thresh + 0.02 * span)
        norm = TwoSlopeNorm(vmin=vmin, vcenter=thresh, vmax=vmax)
        cf = ax.contourf(X, Y, Z, levels=21, cmap=cmap, norm=norm, extend="both")
        ax.contour(X, Y, Z, levels=[thresh], colors="black", linewidths=2)
        ax.set_title(f"{title}\nspec: > {thresh} (black line)")
    else:
        # no spec for this metric -- plain sequential scale, light = low/good
        cf = ax.contourf(X, Y, Z, levels=21, cmap=cmap)
        ax.set_title(title)

    fig = ax.figure
    fig.colorbar(cf, ax=ax)
    ax.set_xlabel("W_PD (um)")
    ax.set_ylabel("W_AX (um)")


def plot_stability_contours(df: pd.DataFrame, w_pu: float, out_dir: Path) -> Path:
    sub = cast(pd.DataFrame, df[df["W_PU"] == w_pu])
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    _contour_panel(axes[0], sub, "worst_wlwm_V", "Worst-case WLWM (V)", WLWM_MIN)
    _contour_panel(axes[1], sub, "worst_snm_V", "Worst-case hold SNM (V)", SNM_MIN)
    fig.suptitle(f"8T bitcell stability sweep -- W_PU = {w_pu} um, L = {L_FIXED} um  "
                 f"(worst case over {len(CORNERS)} SS/TT/FF x PVT corners)")
    fig.tight_layout()
    out_path = out_dir / f"sizing_contours_wpu_{str(w_pu).replace('.', 'p')}.png"
    fig.savefig(out_path, dpi=130)
    plt.close(fig)
    return out_path


def plot_perf_power_contours(df: pd.DataFrame, w_pu: float, out_dir: Path) -> Path | None:
    """Delay + power over the region that already passed WLWM/SNM. Points that
    failed stability were never run in phase 2 and show as gaps (NaN)."""
    sub = cast(pd.DataFrame, df[(df["W_PU"] == w_pu) & df["pass_both"]])
    if sub.empty:
        return None
    fig, axes = plt.subplots(2, 3, figsize=(16, 9))
    _contour_panel(axes[0, 0], sub, "worst_write_delay_s", "Worst-case write delay (s)", None, cmap="viridis")
    _contour_panel(axes[0, 1], sub, "worst_read_delay_s", "Worst-case read/compute delay (s)", None, cmap="viridis")
    axes[0, 2].axis("off")
    _contour_panel(axes[1, 0], sub, "worst_hold_power_W", "Worst-case hold (leakage) power (W)", None, cmap="magma")
    _contour_panel(axes[1, 1], sub, "worst_energy_write_J", "Worst-case write energy (J)", None, cmap="magma")
    _contour_panel(axes[1, 2], sub, "worst_energy_read_J", "Worst-case read energy (J)", None, cmap="magma")
    fig.suptitle(f"8T bitcell perf/power (WLWM+SNM-passing points only) -- W_PU = {w_pu} um, L = {L_FIXED} um\n"
                 f"no numeric spec for these -- lower is better, use to pick among the smallest-width survivors")
    fig.tight_layout()
    out_path = out_dir / f"perf_power_contours_wpu_{str(w_pu).replace('.', 'p')}.png"
    fig.savefig(out_path, dpi=130)
    plt.close(fig)
    return out_path


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--w-pd-min", type=float, default=0.22)
    ap.add_argument("--w-pd-max", type=float, default=0.60)
    ap.add_argument("--w-pd-step", type=float, default=0.02)
    ap.add_argument("--w-ax-min", type=float, default=0.22)
    ap.add_argument("--w-ax-max", type=float, default=0.60)
    ap.add_argument("--w-ax-step", type=float, default=0.02)
    ap.add_argument("--w-pu", type=float, nargs="+", default=[0.44],
                     help="one or more fixed W_PU values (um) to sweep W_PD/W_AX at")
    ap.add_argument("--jobs", type=int, default=min(16, os.cpu_count() or 8))
    ap.add_argument("--timeout", type=float, default=60.0, help="per-simulation ngspice timeout, seconds")
    ap.add_argument("--keep-raw", action="store_true", help="keep each run's .raw waveform (slow, for debugging)")
    ap.add_argument("--skip-perf-power", action="store_true", help="phase 1 only (WLWM/SNM), skip delay/power")
    ap.add_argument("--top-n", type=int, default=10)
    ap.add_argument("--dry-run", action="store_true", help="print the task count/estimate and exit")
    args = ap.parse_args()

    w_pd_vals = frange(args.w_pd_min, args.w_pd_max, args.w_pd_step)
    w_ax_vals = frange(args.w_ax_min, args.w_ax_max, args.w_ax_step)
    w_pu_vals = [round(v, 2) for v in args.w_pu]
    sizing_points = [(w_pd, w_ax, w_pu)
                      for w_pu, w_pd, w_ax in itertools.product(w_pu_vals, w_pd_vals, w_ax_vals)]

    n_points = len(sizing_points)
    n_phase1 = n_points * len(CORNERS) * len(STABILITY_TESTS)
    print(f"[sweep] W_PD: {len(w_pd_vals)} values [{w_pd_vals[0]}..{w_pd_vals[-1]}]")
    print(f"[sweep] W_AX: {len(w_ax_vals)} values [{w_ax_vals[0]}..{w_ax_vals[-1]}]")
    print(f"[sweep] W_PU: {w_pu_vals}")
    print(f"[sweep] phase 1 (WLWM/SNM, hard gate): {n_points} sizing points x {len(CORNERS)} corners "
          f"x {len(STABILITY_TESTS)} tests = {n_phase1} simulations")
    print(f"[sweep] phase 2 (delay/power, informational): up to {n_points} points x {len(CORNERS)} corners "
          f"x {len(PERF_POWER_TESTS)} tests = up to {n_points * len(CORNERS) * len(PERF_POWER_TESTS)} more "
          f"-- actual count depends on how many points pass phase 1")

    if args.dry_run:
        return

    RESULTS.mkdir(parents=True, exist_ok=True)
    SWEEP_WORK.mkdir(parents=True, exist_ok=True)
    ensure_container_running()

    cache = Cache(CACHE_PATH)
    print(f"[cache] {len(cache.records)} result(s) already cached in {CACHE_PATH.name}")

    print("\n=== phase 1: WLWM + hold SNM (hard gates) ===")
    tasks = build_tasks(sizing_points, STABILITY_TESTS, cache)
    run_sweep(tasks, cache, args.jobs, args.timeout, args.keep_raw)

    df = aggregate_stability(cache, sizing_points)
    n_pass = int(df["pass_both"].sum())
    print(f"[phase 1] {n_pass}/{len(df)} sizing point(s) passed WLWM & hold SNM across all corners")

    if not args.skip_perf_power and n_pass > 0:
        print("\n=== phase 2: write/read delay + hold/dynamic power (informational, passing points only) ===")
        pass_sub = cast(pd.DataFrame, df[df["pass_both"]])
        passing_points = list(zip(pass_sub["W_PD"], pass_sub["W_AX"], pass_sub["W_PU"]))
        tasks = build_tasks(passing_points, PERF_POWER_TESTS, cache)
        run_sweep(tasks, cache, args.jobs, args.timeout, args.keep_raw)
        df = add_perf_power(df, cache)

    cache.close()

    df.to_csv(SUMMARY_CSV, index=False)
    print(f"\n[out] {len(df)} sizing point(s) -> {SUMMARY_CSV}")

    for w_pu in w_pu_vals:
        out_path = plot_stability_contours(df, w_pu, RESULTS)
        print(f"[out] stability contour plot -> {out_path}")
        if "worst_write_delay_s" in df.columns:
            pp_path = plot_perf_power_contours(df, w_pu, RESULTS)
            if pp_path:
                print(f"[out] perf/power contour plot -> {pp_path}")

    passing = cast(pd.DataFrame, df[df["pass_both"]]).sort_values("total_width_um")
    print("\n=== smallest-total-width points passing WLWM & hold SNM (all corners) ===")
    if passing.empty:
        print("  none -- no sizing point cleared both specs across all corners")
    else:
        have_pp = "worst_write_delay_s" in df.columns
        for w_pu in w_pu_vals:
            sub = passing[passing["W_PU"] == w_pu].head(args.top_n)
            if sub.empty:
                continue
            print(f"\n  -- W_PU = {w_pu} um --")
            for _, r in sub.iterrows():
                line = (f"    W_PD={r.W_PD:.2f}  W_AX={r.W_AX:.2f}  "
                        f"total_width={r.total_width_um:.2f}um  "
                        f"WLWM={r.worst_wlwm_V:.3f}V  SNM={r.worst_snm_V:.3f}V")
                if have_pp and bool(pd.notna(r.get("worst_write_delay_s"))):
                    line += (f"  |  t_write={r.worst_write_delay_s*1e12:.1f}ps"
                             f"  t_read={r.worst_read_delay_s*1e12:.1f}ps"
                             f"  P_hold={r.worst_hold_power_W*1e9:.2f}nW"
                             f"  E_write={r.worst_energy_write_J*1e15:.2f}fJ"
                             f"  E_read={r.worst_energy_read_J*1e15:.2f}fJ")
                print(line)


if __name__ == "__main__":
    main()
