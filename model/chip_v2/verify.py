"""Checks on the checks, before any RTL exists. Run from the repository root:

    python3 -m model.chip_v2.verify replay     every scenario recorded as a pin trace and replayed
                                               against a fresh copy of the model: must match exactly
    python3 -m model.chip_v2.verify mutants    the same traces against every broken copy in
                                               mutants.py: each must be noticed at the pins
    python3 -m model.chip_v2.verify random N   N seeds of random traffic (random_traffic.py)
    python3 -m model.chip_v2.verify matrix     every requirement in requirements.py traced to its checks;
                                               writes docs/V2_REQUIREMENTS_MATRIX.md (--image: run the photographs too)
    python3 -m model.chip_v2.verify coverage N the functional coverage model (coverage.py) on the scenarios
                                               and N random seeds; writes docs/V2_FUNCTIONAL_COVERAGE.md

Exit status is 0 only if the command found nothing wrong.
"""
from __future__ import annotations

import sys
import time

from . import mutants as U
from . import trace as T

SCENARIOS = ["rules", "requant", "nolink", "spi", "link", "selftest", "errors", "workload", "cdc", "period",
             "recover", "linkup", "status", "modes", "jtagx", "robust", "regs", "reset", "tap", "sync", "cover", "kws"]


def record_all(names=None, quiet=True):
    from . import __main__ as M
    names = [n for n in (names or SCENARIOS) if n in M.SCENARIOS]
    traces, checks = T.record_scenarios(names, quiet=quiet)
    failed = [c for c in checks if not c[1]]
    return traces, checks, failed


def cmd_replay() -> int:
    t0 = time.time()
    traces, checks, failed = record_all()
    print(f"recorded {len(traces)} benches, {sum(t.cycles for t in traces):,} CLK cycles, "
          f"{sum(len(t) for t in traces):,} pin events; the scenarios' own checks: "
          f"{len(checks) - len(failed)} of {len(checks)} pass with the metastability model off")
    bad = 0
    for tr in traces:
        m = T.replay(tr)
        if m:
            bad += 1
            print(f"  MISMATCH {tr.label}: {m[0]}")
    print(f"{len(traces) - bad} of {len(traces)} traces replay exactly on a fresh copy of the model "
          f"({time.time() - t0:.0f} s)")
    return 1 if bad or failed else 0


def kill(mutant: U.Mutant, traces):
    """The first trace on which the mutant differs at a pin, or None."""
    cls = U.build(mutant)
    for tr in traces:
        try:
            m = T.replay(tr, cls)
        except Exception as e:                      # a broken model may also simply fall over
            return tr, f"the model raised {type(e).__name__}"
        if m:
            return tr, str(m[0])
    return None


def cmd_mutants(only: list[str]) -> int:
    t0 = time.time()
    U.check_table()
    traces, checks, failed = record_all()
    clean = sum(1 for tr in traces if not T.replay(tr))
    print(f"{len(traces)} traces, {sum(t.cycles for t in traces):,} CLK cycles; {clean} replay exactly on the unbroken model")
    if clean != len(traces) or failed:
        print("the unbroken model does not replay its own traces: fix that first")
        return 1
    survived, inside = [], []
    todo = [m for m in U.MUTANTS if not only or any(o in m.name for o in only)]
    for m in todo:
        hit = kill(m, traces)
        if hit:
            print(f"  caught   [{m.section:>3}] {m.name}: {hit[0].label}", flush=True)
        elif m.inside:
            inside.append(m)
            print(f"  inside   [{m.section:>3}] {m.name}: not visible at the pins, as expected", flush=True)
        else:
            survived.append(m)
            print(f"  SURVIVED [{m.section:>3}] {m.name}", flush=True)
    caught = len(todo) - len(survived) - len(inside)
    print(f"\n{caught} caught, {len(survived)} survived, {len(inside)} need a test inside the chip, "
          f"of {len(todo)} mutants ({time.time() - t0:.0f} s)")
    for m in survived:
        print(f"  SURVIVED [{m.section}] {m.name}")
    return 1 if survived else 0


def cmd_matrix(with_image: bool) -> int:
    """Check every requirement's evidence against the real scenarios and mutants,
    and write docs/V2_REQUIREMENTS_MATRIX.md."""
    import contextlib
    import io
    import re
    from pathlib import Path

    from . import __main__ as M
    from .requirements import REQS, RND
    names = [n for n in M.SCENARIOS if n != "image"] + (["image"] if with_image else [])
    results = {}
    for n in names:
        first = len(M.RESULTS)
        with contextlib.redirect_stdout(io.StringIO()):
            M.SCENARIOS[n]()
        results[n] = [(name, ok) for name, ok, _ in M.RESULTS[first:]]
    mutants = {m.name: m for m in U.MUTANTS}
    used_checks, used_mutants, problems, rows = set(), set(), [], []
    for r in REQS:
        hits = []
        for scen, rx in r.checks:
            if scen not in results:
                if scen == "image" and not with_image:
                    hits.append((scen, rx, True))
                    continue
                problems.append(f"{r.id}: no scenario '{scen}'")
                continue
            found = [(name, ok) for name, ok in results[scen] if re.search(rx, name)]
            if not found:
                problems.append(f"{r.id}: no check in '{scen}' matches /{rx}/")
            for name, ok in found:
                used_checks.add((scen, name))
                if not ok:
                    problems.append(f"{r.id}: check failed: {scen}: {name}")
            hits += [(scen, name, ok) for name, ok in found]
        for m in r.mutants:
            if m not in mutants:
                problems.append(f"{r.id}: no mutant '{m}'")
            used_mutants.add(m)
        for x in r.rnd:
            if x not in RND:
                problems.append(f"{r.id}: no random invariant '{x}'")
        kinds = sum(bool(v) for v in (r.checks, r.rnd, [m for m in r.mutants if not mutants.get(m, U.MUTANTS[0]).inside]))
        if r.kind in ("phys",):
            status = "flow" if r.planned else "GAP"
        elif r.kind == "inside":
            status = "needs L1" if r.planned else "GAP"
        elif kinds >= 2:
            status = "covered"
        elif kinds == 1:
            status = "one method"
        else:
            status = "GAP"
        rows.append((r, len({(s, n) for s, n, _ in hits}), status))
    orphans = [f"{s}: {n}" for s in results for n, _ in results[s] if (s, n) not in used_checks]
    orphan_mut = [m for m in mutants if m not in used_mutants]
    count = {}
    for _, _, st in rows:
        count[st] = count.get(st, 0) + 1

    out = ["# v2 requirements matrix", "",
           "**Generated** by `python3 -m model.chip_v2.verify matrix` from `model/chip_v2/requirements.py`. "
           "Do not edit by hand. The plan that explains it is `docs/V2_VERIFICATION_PLAN.md`.", "",
           f"{len(REQS)} requirements: " + ", ".join(f"{v} {k}" for k, v in sorted(count.items())) + ".", "",
           "Status: **covered** = at least two of (directed check, random invariant, fault caught at the pins); "
           "**one method** = only one of them; **needs L1** = not visible at the pins, needs a test inside the "
           "chip; **flow** = checked by the physical flow; **GAP** = nothing yet.", "",
           "| ID | Spec | Requirement | Kind | Checks | Random | Faults | Planned | Status |",
           "|---|---|---|---|---|---|---|---|---|"]
    for r, n, st in rows:
        out.append(f"| {r.id} | {r.sec} | {r.text} | {r.kind} | {n} | {len(r.rnd)} | {len(r.mutants)} | "
                   f"{len(r.planned)} | {st} |")
    out += ["", "## Planned tests", ""]
    for r in REQS:
        for p in r.planned:
            out.append(f"- **{r.id}** {p}")
    out += ["", "## Audit", "",
            f"- Checks not traced to any requirement: {len(orphans)}" + ("".join(f"\n  - {o}" for o in orphans)),
            f"- Faults not traced to any requirement: {len(orphan_mut)}" + ("".join(f"\n  - {o}" for o in orphan_mut)),
            f"- Broken references: {len(problems)}" + ("".join(f"\n  - {o}" for o in problems)),
            f"- The photographs were {'' if with_image else 'not '}run for this matrix."]
    Path("docs/V2_REQUIREMENTS_MATRIX.md").write_text("\n".join(out) + "\n")
    print(f"{len(REQS)} requirements: " + ", ".join(f"{v} {k}" for k, v in sorted(count.items())))
    print(f"{len(orphans)} untraced checks, {len(orphan_mut)} untraced faults, {len(problems)} broken references")
    for x in problems + orphans + orphan_mut:
        print("  ", x)
    return 1 if problems or orphans or orphan_mut else 0


def cmd_coverage(seeds: int) -> int:
    """The functional coverage model of the plan's section 5, collected on every scenario but the
    photographs and on seeds of random traffic; writes docs/V2_FUNCTIONAL_COVERAGE.md."""
    from pathlib import Path

    from . import __main__ as M
    from . import coverage as V
    t0 = time.time()
    names = [n for n in M.SCENARIOS if n != "image"]
    cov = V.collect(names, seeds)
    hit, total, missing = cov.report()
    out = ["# v2 functional coverage", "",
           "**Generated** by `python3 -m model.chip_v2.verify coverage` from `model/chip_v2/coverage.py`. "
           "Do not edit by hand. The coverage model is `docs/V2_VERIFICATION_PLAN.md` section 5.", "",
           f"Collected on {cov.benches} benches: every scenario but the photographs, {seeds} legal and {seeds} "
           f"hostile random seeds, and two forced self-test timeouts. {hit} of {total} reachable bins hit "
           f"({100 * hit / total:.1f}%); {sum(len(v) for v in V.IMPOSSIBLE.values())} bins are impossible by design.", "",
           "| Point | Bins | Impossible | Hit | Missing |", "|---|---|---|---|---|"]
    for k, allb in cov.all.items():
        imp = len(V.IMPOSSIBLE.get(k, {}))
        miss = len(missing.get(k, []))
        out.append(f"| {k} | {len(allb)} | {imp} | {len(allb) - imp - miss} | {miss} |")
    out += ["", "## Missing bins", ""]
    for k, m in missing.items():
        out.append(f"- **{k}** ({len(m)}): " + "; ".join(str(x) for x in m))
    out += ["", "## Impossible bins, and why", ""]
    for k, d in V.IMPOSSIBLE.items():
        for b, why in d.items():
            out.append(f"- **{k}** {b}: {why}")
    Path("docs/V2_FUNCTIONAL_COVERAGE.md").write_text("\n".join(out) + "\n")
    print(f"{hit} of {total} reachable bins hit ({100 * hit / total:.1f}%) on {cov.benches} benches "
          f"({time.time() - t0:.0f} s)")
    for k, m in missing.items():
        print(f"  {k}: {len(m)} missing")
    return 0 if not missing else 1


def main() -> int:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "replay"
    if cmd == "replay":
        return cmd_replay()
    if cmd == "mutants":
        return cmd_mutants(sys.argv[2:])
    if cmd == "matrix":
        return cmd_matrix("--image" in sys.argv)
    if cmd == "coverage":
        return cmd_coverage(int(sys.argv[2]) if len(sys.argv) > 2 else 50)
    if cmd == "random":
        from .random_traffic import main as random_main
        return random_main(sys.argv[2:])
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
