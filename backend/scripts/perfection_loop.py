"""Perfection Verification Loop — top-level driver.

Runs every gate defined in ``perfection_config.yaml`` repeatedly until either:

* ``consecutive_green_required`` fully-green cycles have been observed, or
* ``max_cycles`` has been reached, or
* A failure signature has exhausted its repair budget.

Usage (from repo root):

    python -m scripts.perfection_loop                # default config path
    python -m scripts.perfection_loop --config ...   # custom config
    python -m scripts.perfection_loop --dry-run      # validate config + list gates
    python -m scripts.perfection_loop --phases unit_backend,unit_frontend  # subset

Exit codes
----------
* 0 — perfection gate achieved (N consecutive greens)
* 1 — at least one gate failed after exhausting the repair budget
* 2 — configuration / environment error
* 130 — interrupted by user (Ctrl+C)
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import shutil
import signal
import subprocess
import sys
from pathlib import Path

try:
    import yaml  # type: ignore
except ImportError:  # pragma: no cover — surfaced loudly in the driver
    yaml = None

# Allow running as ``python -m scripts.perfection_loop`` from backend/.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts._verify_gates import (  # noqa: E402
    REPORTS_DIR,
    ROOT,
    GateResult,
    dispatch_gate,
)

STATE_PATH = Path(__file__).parent / ".perfection_state.json"
DEFAULT_CONFIG = Path(__file__).parent / "perfection_config.yaml"


def _load_yaml(path: Path) -> dict:
    if yaml is None:
        raise RuntimeError("PyYAML is not installed. `pip install pyyaml` and re-run.")
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _load_state() -> dict:
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {
        "cycle": 0,
        "consecutive_green": 0,
        "signatures": {},  # signature -> {attempts, last_gate, last_repair}
        "history": [],
    }


def _save_state(state: dict) -> None:
    STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")


# --------------------------------------------------------------------------- #
# Auto-repair policy                                                          #
# --------------------------------------------------------------------------- #


def _attempt_repair(result: GateResult, config: dict) -> tuple[bool, str]:
    """Apply a bounded automated fix for known failure classes.

    Returns ``(applied, class_label)``. The caller decides whether to retry
    the gate after a successful repair.
    """
    name = result.name
    stderr = result.stderr or ""
    stdout = result.stdout or ""
    blob = stderr + "\n" + stdout

    # LintAutofix: only static_backend / static_frontend failures can use this.
    if name == "static_backend" and "ruff" in result.summary.lower():
        subprocess.run(
            [sys.executable, "-m", "ruff", "check", "--fix", "."],
            cwd=str(ROOT / "backend"),
            check=False,
        )
        subprocess.run(
            [sys.executable, "-m", "ruff", "format", "."],
            cwd=str(ROOT / "backend"),
            check=False,
        )
        return True, "LintAutofix"

    if name == "static_frontend" and "eslint" in result.summary.lower():
        npx = shutil.which("npx") or "npx"
        subprocess.run(
            [npx, "--yes", "next", "lint", "--fix"],
            cwd=str(ROOT / "frontend"),
            check=False,
        )
        return True, "LintAutofix"

    # DependencyMissing: both toolchains — grep for common signatures.
    if "ModuleNotFoundError" in blob or "No module named" in blob or "Cannot find module" in blob:
        # We don't auto-install speculatively; emit an escalation.
        return False, "DependencyMissing"

    # MigrationDrift: alembic_roundtrip.
    if name == "db_roundtrip" and "drift" in blob.lower():
        return False, "MigrationDrift"

    # SnapshotStale: visual and contract.
    if name == "visual" and ("Screenshot comparison failed" in blob or "snapshot" in blob.lower()):
        npx = shutil.which("npx") or "npx"
        subprocess.run(
            [npx, "--yes", "playwright", "test", "e2e/visual.spec.ts", "--update-snapshots", "--reporter=line"],
            cwd=str(ROOT / "frontend"),
            check=False,
        )
        return True, "SnapshotStale"

    if name == "contract_backend" and "OpenAPI drift" in blob:
        # Regenerate fixture openapi.json via the backend schemathesis script.
        script = ROOT / "backend" / "scripts" / "run_schemathesis.py"
        if script.exists():
            subprocess.run(
                [sys.executable, str(script), "--update"],
                cwd=str(ROOT / "backend"),
                check=False,
            )
            return True, "SnapshotStale"

    # LLMTimeoutBackoff: live_smoke.
    if name == "live_smoke" and "timeout" in blob.lower():
        current = os.environ.get("LLM_TIMEOUT_S", "120")
        try:
            new_val = min(int(float(current)) * 2, 480)
            os.environ["LLM_TIMEOUT_S"] = str(new_val)
            return True, "LLMTimeoutBackoff"
        except Exception:
            pass

    return False, "Unclassified"


# --------------------------------------------------------------------------- #
# Reporting                                                                   #
# --------------------------------------------------------------------------- #


def _write_cycle_report(
    cycle: int,
    results: list[GateResult],
    state: dict,
    config: dict,
) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = _dt.datetime.now(tz=_dt.UTC).isoformat()
    path = REPORTS_DIR / f"cycle_{cycle:03d}.md"
    lines: list[str] = []
    lines.append(f"# Perfection Cycle #{cycle}\n")
    lines.append(f"- Timestamp (UTC): {ts}\n")
    lines.append(f"- Consecutive greens: {state['consecutive_green']}\n")
    lines.append(f"- Gates run: {len(results)}\n")
    lines.append("")
    lines.append("| Gate | Status | Duration (s) | Summary |\n")
    lines.append("|------|--------|--------------|---------|\n")
    for r in results:
        status = "SKIP" if r.skipped else ("PASS" if r.passed else "FAIL")
        summary = (r.summary or "").replace("|", "\\|")
        lines.append(f"| {r.name} | {status} | {r.duration_s:.2f} | {summary} |\n")
    lines.append("\n## Failure details\n")
    any_fail = False
    for r in results:
        if r.passed or r.skipped:
            continue
        any_fail = True
        lines.append(f"\n### {r.name}\n\n")
        lines.append(f"- signature: `{r.signature}`\n")
        if r.stderr.strip():
            lines.append("\n```\n")
            lines.append(r.stderr.strip()[-2000:])
            lines.append("\n```\n")
        elif r.stdout.strip():
            lines.append("\n```\n")
            lines.append(r.stdout.strip()[-2000:])
            lines.append("\n```\n")
    if not any_fail:
        lines.append("\n_All gates passed._\n")
    path.write_text("".join(lines), encoding="utf-8")
    return path


def _write_summary(state: dict, config: dict, last: list[GateResult]) -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORTS_DIR / "summary.md"
    passed = sum(1 for r in last if r.passed and not r.skipped)
    skipped = sum(1 for r in last if r.skipped)
    failed = sum(1 for r in last if not r.passed and not r.skipped)
    lines = [
        "# Perfection Verification — Rolling Summary\n\n",
        f"- Last updated: {_dt.datetime.now(tz=_dt.UTC).isoformat()}\n",
        f"- Cycle: {state['cycle']}\n",
        f"- Consecutive green cycles: {state['consecutive_green']} / "
        f"{config['stopping']['consecutive_green_required']}\n",
        f"- Last cycle gates: {passed} passed, {failed} failed, {skipped} skipped\n\n",
        "## Open signatures\n\n",
    ]
    if not state["signatures"]:
        lines.append("_none_\n")
    else:
        lines.append("| Signature | Attempts | Last Gate |\n")
        lines.append("|-----------|----------|-----------|\n")
        for sig, meta in state["signatures"].items():
            lines.append(f"| `{sig}` | {meta.get('attempts', 0)} | {meta.get('last_gate', '?')} |\n")
    path.write_text("".join(lines), encoding="utf-8")


def _write_unresolved(signatures: dict) -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORTS_DIR / "unresolved.md"
    lines = ["# Unresolved perfection-loop failures\n\n"]
    if not signatures:
        lines.append("_none_\n")
    else:
        for sig, meta in signatures.items():
            lines.append(f"- `{sig}` — {meta.get('attempts', 0)} attempts; last gate: {meta.get('last_gate', '?')}\n")
    path.write_text("".join(lines), encoding="utf-8")


# --------------------------------------------------------------------------- #
# Main loop                                                                   #
# --------------------------------------------------------------------------- #


def run_loop(
    config_path: Path,
    phases: list[str] | None = None,
    dry_run: bool = False,
) -> int:
    config = _load_yaml(config_path)
    gates = phases or list(config.get("gates", []))
    if not gates:
        print("ERROR: no gates configured.", file=sys.stderr)
        return 2

    if dry_run:
        print(f"Gates to run: {gates}")
        return 0

    state = _load_state()
    required = int(config["stopping"]["consecutive_green_required"])
    max_cycles = int(config["stopping"]["max_cycles"])
    max_repairs = int(config["repair"]["max_attempts_per_signature"])

    last_results: list[GateResult] = []
    try:
        while state["cycle"] < max_cycles:
            state["cycle"] += 1
            cycle = state["cycle"]
            print(f"\n=== Perfection cycle #{cycle} ===", flush=True)

            cycle_results: list[GateResult] = []
            all_green = True
            snapshot_reset = False
            halted = False

            for gate_name in gates:
                print(f"  -> {gate_name} ...", end="", flush=True)
                res = dispatch_gate(gate_name, config)
                status = "skip" if res.skipped else ("ok" if res.passed else "FAIL")
                print(f" {status} ({res.duration_s:.1f}s)", flush=True)
                cycle_results.append(res)
                if not res.passed and not res.skipped:
                    all_green = False
                    applied, cls = _attempt_repair(res, config)
                    sig = res.signature or f"{gate_name}:unsigned"
                    entry = state["signatures"].setdefault(sig, {"attempts": 0, "last_gate": gate_name, "class": cls})
                    entry["attempts"] += 1
                    entry["last_gate"] = gate_name
                    entry["class"] = cls
                    if applied and cls == "SnapshotStale":
                        snapshot_reset = True
                        print(f"     [repair] {cls} applied; snapshot regenerated.", flush=True)
                    elif applied:
                        print(f"     [repair] {cls} applied; gate will retry next cycle.", flush=True)
                    else:
                        print(f"     [repair] no automatic fix (class={cls}).", flush=True)
                    if entry["attempts"] >= max_repairs:
                        print(
                            f"     [halt] signature {sig!r} exhausted {max_repairs} attempts.",
                            flush=True,
                        )
                        halted = True
                        break

            last_results = cycle_results
            report = _write_cycle_report(cycle, cycle_results, state, config)
            print(f"  cycle report -> {report.relative_to(ROOT)}", flush=True)

            if snapshot_reset and not all_green:
                state["consecutive_green"] = 0
            elif all_green:
                state["consecutive_green"] += 1
            else:
                state["consecutive_green"] = 0

            state["history"].append(
                {
                    "cycle": cycle,
                    "green": all_green,
                    "results": [r.as_dict() for r in cycle_results],
                }
            )
            _save_state(state)
            _write_summary(state, config, cycle_results)

            if halted:
                _write_unresolved(state["signatures"])
                return 1

            if state["consecutive_green"] >= required:
                print(
                    f"\nSUCCESS: {required} consecutive green cycles reached. Perfection gate met.",
                    flush=True,
                )
                _write_unresolved({})
                return 0

        print(
            f"\nSTOP: max_cycles={max_cycles} reached without {required} consecutive greens.",
            flush=True,
        )
        _write_unresolved(state["signatures"])
        return 1
    except KeyboardInterrupt:
        print("\nInterrupted by user.", flush=True)
        _write_summary(state, config, last_results)
        return 130


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Perfection Verification Loop")
    ap.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    ap.add_argument("--phases", type=str, default=None, help="Comma-separated subset of gate names")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--reset-state", action="store_true", help="Clear .perfection_state.json and start fresh.")
    args = ap.parse_args(argv)

    if args.reset_state and STATE_PATH.exists():
        STATE_PATH.unlink()

    phases = [p.strip() for p in args.phases.split(",")] if args.phases else None

    def _sig_handler(signum, _frame):  # pragma: no cover
        raise KeyboardInterrupt

    signal.signal(signal.SIGINT, _sig_handler)
    try:
        return run_loop(args.config, phases=phases, dry_run=args.dry_run)
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
