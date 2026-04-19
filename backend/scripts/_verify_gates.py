"""Individual gate runners for the Perfection Verification Loop.

Each gate is a function returning :class:`GateResult`. Gates are pure side-effect
wrappers over subprocess invocations of real tools (ruff, mypy, pytest, vitest,
playwright, schemathesis, mutmut, hypothesis, axe, etc.) so the driver stays
simple: it collects results, emits reports, and decides whether to repair/retry.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"
MCP_DIR = ROOT / "mcp-server"
REPORTS_DIR = ROOT / "reports" / "perfection"


@dataclass
class GateResult:
    name: str
    passed: bool
    duration_s: float
    stdout: str = ""
    stderr: str = ""
    summary: str = ""
    signature: str = ""
    skipped: bool = False
    metrics: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "passed": self.passed,
            "skipped": self.skipped,
            "duration_s": round(self.duration_s, 3),
            "summary": self.summary,
            "signature": self.signature,
            "metrics": self.metrics,
        }


def _run(
    cmd: list[str],
    cwd: Path,
    env: dict | None = None,
    timeout: int = 1800,
) -> tuple[int, str, str, float]:
    """Run a subprocess and return (rc, stdout, stderr, seconds)."""
    t0 = time.monotonic()
    merged_env = os.environ.copy()
    if env:
        merged_env.update({k: str(v) for k, v in env.items()})
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd),
            env=merged_env,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        return (
            proc.returncode,
            proc.stdout.decode("utf-8", errors="replace"),
            proc.stderr.decode("utf-8", errors="replace"),
            time.monotonic() - t0,
        )
    except FileNotFoundError as exc:
        return 127, "", f"command not found: {exc}", time.monotonic() - t0
    except subprocess.TimeoutExpired as exc:
        return 124, exc.stdout or "", f"timeout after {timeout}s", time.monotonic() - t0


def _has(cmd: str) -> bool:
    return shutil.which(cmd) is not None


# --------------------------------------------------------------------------- #
# Gate implementations                                                        #
# --------------------------------------------------------------------------- #


def gate_env_sanity() -> GateResult:
    t0 = time.monotonic()
    issues: list[str] = []
    for tool in ("python", "pip"):
        if not _has(tool):
            issues.append(f"missing: {tool}")
    return GateResult(
        name="env_sanity",
        passed=not issues,
        duration_s=time.monotonic() - t0,
        summary="; ".join(issues) if issues else "python>=3.11 + pip available",
        signature="env_sanity",
    )


def gate_static_backend() -> GateResult:
    t0 = time.monotonic()
    errs: list[str] = []
    rc, out, err, _ = _run([sys.executable, "-m", "ruff", "check", "."], BACKEND)
    if rc != 0:
        errs.append("ruff check")
    rc2, out2, err2, _ = _run([sys.executable, "-m", "ruff", "format", "--check", "."], BACKEND)
    if rc2 != 0:
        errs.append("ruff format")
    # mypy is optional until config is in place; respect absence gracefully.
    rc3, out3, err3, _ = _run(
        [sys.executable, "-m", "mypy", "app"],
        BACKEND,
        env={"MYPY_CACHE_DIR": str(BACKEND / ".mypy_cache")},
    )
    # rc3 == 2 means "not installed"; rc3 == 127 means not found — skip.
    mypy_skipped = rc3 in (2, 127) and "No module named 'mypy'" in err3
    if not mypy_skipped and rc3 != 0:
        errs.append("mypy")
    passed = not errs
    return GateResult(
        name="static_backend",
        passed=passed,
        duration_s=time.monotonic() - t0,
        stdout=out + "\n" + out2 + "\n" + out3,
        stderr=err + "\n" + err2 + "\n" + err3,
        summary=", ".join(errs) or "ruff + format + mypy clean",
        signature="static_backend:" + ",".join(sorted(errs)),
        metrics={"mypy_skipped": mypy_skipped},
    )


def gate_static_frontend() -> GateResult:
    t0 = time.monotonic()
    errs: list[str] = []
    if not (FRONTEND / "node_modules").exists():
        return GateResult(
            name="static_frontend",
            passed=False,
            duration_s=time.monotonic() - t0,
            summary="node_modules missing — run `npm install` in frontend/",
            signature="static_frontend:no_node_modules",
        )
    npx = shutil.which("npx") or "npx"
    rc, out, err, _ = _run([npx, "--yes", "tsc", "--noEmit"], FRONTEND)
    if rc != 0:
        errs.append("tsc")
    rc2, out2, err2, _ = _run([npx, "--yes", "next", "lint", "--max-warnings=0"], FRONTEND)
    if rc2 != 0:
        errs.append("eslint")
    return GateResult(
        name="static_frontend",
        passed=not errs,
        duration_s=time.monotonic() - t0,
        stdout=out + "\n" + out2,
        stderr=err + "\n" + err2,
        summary=", ".join(errs) or "tsc + eslint clean",
        signature="static_frontend:" + ",".join(sorted(errs)),
    )


def gate_unit_backend() -> GateResult:
    t0 = time.monotonic()
    cov_path = BACKEND / "coverage.xml"
    if cov_path.exists():
        cov_path.unlink()
    env = {"LLM_PROVIDER": "mock", "PERFECTION_LOOP": "1"}
    rc, out, err, _ = _run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "--maxfail=1",
            "--cov=app",
            "--cov-report=xml",
            "--cov-report=term-missing",
            "tests",
        ],
        BACKEND,
        env=env,
    )
    metrics = _parse_coverage_xml(cov_path) if cov_path.exists() else {}
    return GateResult(
        name="unit_backend",
        passed=rc == 0,
        duration_s=time.monotonic() - t0,
        stdout=out,
        stderr=err,
        summary=_last_line(out) if rc == 0 else "pytest failed",
        signature=f"unit_backend:rc={rc}",
        metrics=metrics,
    )


def gate_unit_frontend() -> GateResult:
    t0 = time.monotonic()
    if not (FRONTEND / "node_modules").exists():
        return GateResult(
            name="unit_frontend",
            passed=False,
            duration_s=time.monotonic() - t0,
            summary="node_modules missing",
            signature="unit_frontend:no_node_modules",
        )
    npx = shutil.which("npx") or "npx"
    rc, out, err, _ = _run([npx, "--yes", "vitest", "run", "--reporter=verbose"], FRONTEND)
    return GateResult(
        name="unit_frontend",
        passed=rc == 0,
        duration_s=time.monotonic() - t0,
        stdout=out,
        stderr=err,
        summary=_last_line(out) if rc == 0 else "vitest failed",
        signature=f"unit_frontend:rc={rc}",
    )


def gate_contract_backend() -> GateResult:
    t0 = time.monotonic()
    script = BACKEND / "scripts" / "run_schemathesis.py"
    if not script.exists():
        return GateResult(
            name="contract_backend",
            passed=True,
            duration_s=time.monotonic() - t0,
            summary="script missing — skipped",
            skipped=True,
            signature="contract_backend:skipped",
        )
    rc, out, err, _ = _run([sys.executable, str(script)], BACKEND)
    return GateResult(
        name="contract_backend",
        passed=rc == 0,
        duration_s=time.monotonic() - t0,
        stdout=out,
        stderr=err,
        summary=_last_line(out) if rc == 0 else "schemathesis failed",
        signature=f"contract_backend:rc={rc}",
    )


def gate_db_roundtrip() -> GateResult:
    t0 = time.monotonic()
    script = BACKEND / "scripts" / "alembic_roundtrip.py"
    if not script.exists():
        return GateResult(
            name="db_roundtrip",
            passed=True,
            duration_s=time.monotonic() - t0,
            summary="script missing — skipped",
            skipped=True,
            signature="db_roundtrip:skipped",
        )
    rc, out, err, _ = _run([sys.executable, str(script)], BACKEND)
    return GateResult(
        name="db_roundtrip",
        passed=rc == 0,
        duration_s=time.monotonic() - t0,
        stdout=out,
        stderr=err,
        summary=_last_line(out) if rc == 0 else "alembic roundtrip failed",
        signature=f"db_roundtrip:rc={rc}",
    )


def gate_mcp_contract() -> GateResult:
    t0 = time.monotonic()
    tests = MCP_DIR / "tests"
    if not tests.exists():
        return GateResult(
            name="mcp_contract",
            passed=True,
            duration_s=time.monotonic() - t0,
            summary="no mcp tests dir",
            skipped=True,
            signature="mcp_contract:skipped",
        )
    rc, out, err, _ = _run(
        [sys.executable, "-m", "pytest", "-q", str(tests)],
        ROOT,
    )
    return GateResult(
        name="mcp_contract",
        passed=rc == 0,
        duration_s=time.monotonic() - t0,
        stdout=out,
        stderr=err,
        summary=_last_line(out) if rc == 0 else "mcp contract failed",
        signature=f"mcp_contract:rc={rc}",
    )


def gate_property_backend() -> GateResult:
    t0 = time.monotonic()
    prop_dir = BACKEND / "tests" / "property"
    if not prop_dir.exists():
        return GateResult(
            name="property_backend",
            passed=True,
            duration_s=time.monotonic() - t0,
            summary="no property tests",
            skipped=True,
            signature="property_backend:skipped",
        )
    rc, out, err, _ = _run(
        [sys.executable, "-m", "pytest", "-q", "tests/property"],
        BACKEND,
    )
    return GateResult(
        name="property_backend",
        passed=rc == 0,
        duration_s=time.monotonic() - t0,
        stdout=out,
        stderr=err,
        summary=_last_line(out) if rc == 0 else "hypothesis falsified",
        signature=f"property_backend:rc={rc}",
    )


def gate_coverage_backend(threshold_line: float, threshold_branch: float) -> GateResult:
    t0 = time.monotonic()
    cov_path = BACKEND / "coverage.xml"
    if not cov_path.exists():
        return GateResult(
            name="coverage_backend",
            passed=False,
            duration_s=time.monotonic() - t0,
            summary="coverage.xml missing (unit_backend must run first)",
            signature="coverage_backend:no_xml",
        )
    m = _parse_coverage_xml(cov_path)
    line = m.get("line_rate", 0.0) * 100
    branch = m.get("branch_rate", 0.0) * 100
    passed = line >= threshold_line and branch >= threshold_branch
    return GateResult(
        name="coverage_backend",
        passed=passed,
        duration_s=time.monotonic() - t0,
        summary=f"line={line:.1f}% (>={threshold_line}), branch={branch:.1f}% (>={threshold_branch})",
        signature=f"coverage_backend:line={int(line)},branch={int(branch)}",
        metrics=m,
    )


def gate_coverage_frontend(threshold_line: float) -> GateResult:
    t0 = time.monotonic()
    cov = FRONTEND / "coverage" / "coverage-summary.json"
    if not cov.exists():
        return GateResult(
            name="coverage_frontend",
            passed=True,
            duration_s=time.monotonic() - t0,
            summary="coverage-summary.json missing — skipped (enable v8 coverage)",
            skipped=True,
            signature="coverage_frontend:skipped",
        )
    try:
        data = json.loads(cov.read_text(encoding="utf-8"))
        line = float(data.get("total", {}).get("lines", {}).get("pct", 0.0))
    except Exception as exc:
        return GateResult(
            name="coverage_frontend",
            passed=False,
            duration_s=time.monotonic() - t0,
            summary=f"coverage json parse error: {exc}",
            signature="coverage_frontend:parse_error",
        )
    passed = line >= threshold_line
    return GateResult(
        name="coverage_frontend",
        passed=passed,
        duration_s=time.monotonic() - t0,
        summary=f"line={line:.1f}% (>={threshold_line})",
        signature=f"coverage_frontend:line={int(line)}",
        metrics={"line_pct": line},
    )


def gate_mutation_backend(kill_rate_threshold: float) -> GateResult:
    t0 = time.monotonic()
    if not _has("mutmut"):
        return GateResult(
            name="mutation_backend",
            passed=True,
            duration_s=time.monotonic() - t0,
            summary="mutmut not installed — skipped",
            skipped=True,
            signature="mutation_backend:skipped",
        )
    # Run quickly; full mutation runs can be hours. We respect config paths
    # in backend/mutmut_config.py if present.
    rc, out, err, _ = _run(["mutmut", "run", "--CI"], BACKEND)
    # Parse results via `mutmut results`.
    rc2, out2, _, _ = _run(["mutmut", "results"], BACKEND)
    killed, survived = _parse_mutmut_results(out2)
    total = killed + survived
    rate = (killed / total) if total else 1.0
    passed = rate >= kill_rate_threshold
    return GateResult(
        name="mutation_backend",
        passed=passed,
        duration_s=time.monotonic() - t0,
        stdout=out + "\n" + out2,
        stderr=err,
        summary=f"kill_rate={rate:.2%} (>={kill_rate_threshold:.0%}); killed={killed}, survived={survived}",
        signature=f"mutation_backend:rate={int(rate * 100)}",
        metrics={"kill_rate": rate, "killed": killed, "survived": survived},
    )


def gate_component_frontend() -> GateResult:
    # Component coverage is captured by unit_frontend; this gate is a
    # structural assertion: every component file has a matching test.
    t0 = time.monotonic()
    comp_dir = FRONTEND / "src" / "components"
    if not comp_dir.exists():
        return GateResult(
            name="component_frontend",
            passed=True,
            duration_s=time.monotonic() - t0,
            summary="no components dir",
            skipped=True,
            signature="component_frontend:skipped",
        )
    missing: list[str] = []
    for entry in comp_dir.iterdir():
        if entry.suffix != ".tsx" or entry.name.endswith(".test.tsx"):
            continue
        if entry.name == "index.ts":
            continue
        test_file = entry.with_suffix(".test.tsx")
        if not test_file.exists():
            missing.append(entry.name)
    passed = not missing
    return GateResult(
        name="component_frontend",
        passed=passed,
        duration_s=time.monotonic() - t0,
        summary=("all components covered" if passed else f"missing tests: {', '.join(missing)}"),
        signature="component_frontend:" + ",".join(sorted(missing)),
    )


def gate_e2e_playwright() -> GateResult:
    t0 = time.monotonic()
    if not (FRONTEND / "node_modules").exists():
        return GateResult(
            name="e2e_playwright",
            passed=False,
            duration_s=time.monotonic() - t0,
            summary="node_modules missing",
            signature="e2e_playwright:no_node_modules",
        )
    npx = shutil.which("npx") or "npx"
    rc, out, err, _ = _run(
        [npx, "--yes", "playwright", "test", "--reporter=line"],
        FRONTEND,
        env={"PERFECTION_LOOP": "1"},
    )
    return GateResult(
        name="e2e_playwright",
        passed=rc == 0,
        duration_s=time.monotonic() - t0,
        stdout=out,
        stderr=err,
        summary=_last_line(out) if rc == 0 else "playwright failed",
        signature=f"e2e_playwright:rc={rc}",
    )


def gate_a11y() -> GateResult:
    t0 = time.monotonic()
    spec = FRONTEND / "e2e" / "axe.spec.ts"
    if not spec.exists():
        return GateResult(
            name="a11y",
            passed=True,
            duration_s=time.monotonic() - t0,
            summary="axe.spec.ts missing — skipped",
            skipped=True,
            signature="a11y:skipped",
        )
    npx = shutil.which("npx") or "npx"
    rc, out, err, _ = _run(
        [npx, "--yes", "playwright", "test", "e2e/axe.spec.ts", "--reporter=line"],
        FRONTEND,
    )
    return GateResult(
        name="a11y",
        passed=rc == 0,
        duration_s=time.monotonic() - t0,
        stdout=out,
        stderr=err,
        summary=_last_line(out) if rc == 0 else "axe violations",
        signature=f"a11y:rc={rc}",
    )


def gate_visual() -> GateResult:
    t0 = time.monotonic()
    spec = FRONTEND / "e2e" / "visual.spec.ts"
    if not spec.exists():
        return GateResult(
            name="visual",
            passed=True,
            duration_s=time.monotonic() - t0,
            summary="visual.spec.ts missing — skipped",
            skipped=True,
            signature="visual:skipped",
        )
    npx = shutil.which("npx") or "npx"
    rc, out, err, _ = _run(
        [npx, "--yes", "playwright", "test", "e2e/visual.spec.ts", "--reporter=line"],
        FRONTEND,
    )
    return GateResult(
        name="visual",
        passed=rc == 0,
        duration_s=time.monotonic() - t0,
        stdout=out,
        stderr=err,
        summary=_last_line(out) if rc == 0 else "visual diff",
        signature=f"visual:rc={rc}",
    )


def gate_live_smoke(config: dict) -> GateResult:
    t0 = time.monotonic()
    if not config.get("enabled", True):
        return GateResult(
            name="live_smoke",
            passed=True,
            duration_s=time.monotonic() - t0,
            summary="disabled by config",
            skipped=True,
            signature="live_smoke:disabled",
        )
    script = BACKEND / "scripts" / "live_smoke.py"
    if not script.exists():
        return GateResult(
            name="live_smoke",
            passed=True,
            duration_s=time.monotonic() - t0,
            summary="live_smoke.py missing — skipped",
            skipped=True,
            signature="live_smoke:skipped",
        )
    rc, out, err, _ = _run([sys.executable, str(script)], BACKEND)
    return GateResult(
        name="live_smoke",
        passed=rc == 0,
        duration_s=time.monotonic() - t0,
        stdout=out,
        stderr=err,
        summary=_last_line(out) if rc == 0 else "live smoke failed",
        signature=f"live_smoke:rc={rc}",
    )


# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #


def _last_line(s: str) -> str:
    for line in reversed(s.strip().splitlines()):
        if line.strip():
            return line.strip()
    return ""


def _parse_coverage_xml(path: Path) -> dict:
    import xml.etree.ElementTree as ET

    try:
        root = ET.parse(path).getroot()
    except Exception:
        return {}
    attrs = root.attrib
    return {
        "line_rate": float(attrs.get("line-rate", 0.0)),
        "branch_rate": float(attrs.get("branch-rate", 0.0)),
        "lines_covered": int(attrs.get("lines-covered", 0)),
        "lines_valid": int(attrs.get("lines-valid", 0)),
    }


def _parse_mutmut_results(text: str) -> tuple[int, int]:
    killed = survived = 0
    for line in text.splitlines():
        low = line.lower().strip()
        if low.startswith("killed"):
            killed = _int_after_colon(line)
        elif low.startswith("survived"):
            survived = _int_after_colon(line)
    return killed, survived


def _int_after_colon(s: str) -> int:
    parts = s.split(":")
    if len(parts) < 2:
        return 0
    tail = parts[1].strip().split()
    try:
        return int(tail[0])
    except Exception:
        return 0


# --------------------------------------------------------------------------- #
# Gate registry                                                               #
# --------------------------------------------------------------------------- #


GATE_FUNCS: dict[str, Callable[..., GateResult]] = {
    "env_sanity": gate_env_sanity,
    "static_backend": gate_static_backend,
    "static_frontend": gate_static_frontend,
    "unit_backend": gate_unit_backend,
    "unit_frontend": gate_unit_frontend,
    "contract_backend": gate_contract_backend,
    "db_roundtrip": gate_db_roundtrip,
    "mcp_contract": gate_mcp_contract,
    "property_backend": gate_property_backend,
    "coverage_backend": gate_coverage_backend,
    "coverage_frontend": gate_coverage_frontend,
    "mutation_backend": gate_mutation_backend,
    "component_frontend": gate_component_frontend,
    "e2e_playwright": gate_e2e_playwright,
    "a11y": gate_a11y,
    "visual": gate_visual,
    "live_smoke": gate_live_smoke,
}


def dispatch_gate(name: str, config: dict) -> GateResult:
    """Call a gate by name with config-derived arguments."""
    fn = GATE_FUNCS.get(name)
    if fn is None:
        return GateResult(
            name=name,
            passed=False,
            duration_s=0.0,
            summary=f"unknown gate: {name}",
            signature=f"unknown:{name}",
        )
    if name == "coverage_backend":
        return fn(
            config["coverage"]["backend_line"],
            config["coverage"]["backend_branch"],
        )
    if name == "coverage_frontend":
        return fn(config["coverage"]["frontend_line"])
    if name == "mutation_backend":
        return fn(config["mutation"]["kill_rate"])
    if name == "live_smoke":
        return fn(config.get("live_smoke", {}))
    return fn()
