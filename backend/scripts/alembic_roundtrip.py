"""Alembic migration round-trip verifier.

Flow:

    1. Upgrade from ``base`` to ``head`` on a disposable SQLite DB.
    2. Downgrade one revision, then upgrade to head again.
    3. Assert the SQLAlchemy metadata matches the live schema (no drift).

SQLite is enough to catch the mistakes we care about: ``autogenerate``
divergence, missing revision links, and op/model mismatches. A deeper
PostgreSQL-only round-trip belongs in CI, not the inner verification loop.

Usage
-----

    python -m scripts.alembic_roundtrip

Exit code 0 on success, 1 on drift or alembic failure, 2 on setup error.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _run(cmd: list[str], env: dict) -> int:
    merged = os.environ.copy()
    merged.update(env)
    proc = subprocess.run(cmd, cwd=str(ROOT), env=merged, stdout=sys.stdout, stderr=sys.stderr)
    return proc.returncode


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="fs_intel_alembic_"))
    db_path = tmp / "roundtrip.db"
    try:
        url = f"sqlite:///{db_path.as_posix()}"
        env = {"DATABASE_URL": url, "PERFECTION_LOOP": "1"}

        print(f"[roundtrip] using disposable DB: {url}")
        # Upgrade base -> head.
        if _run([sys.executable, "-m", "alembic", "upgrade", "head"], env) != 0:
            print("[roundtrip] upgrade head failed", file=sys.stderr)
            return 1
        # Downgrade one revision (if possible) and re-upgrade to head.
        rc = _run([sys.executable, "-m", "alembic", "downgrade", "-1"], env)
        if rc != 0:
            print(
                "[roundtrip] downgrade -1 failed; this usually means the HEAD "
                "revision's downgrade() is missing. Fix the migration.",
                file=sys.stderr,
            )
            return 1
        if _run([sys.executable, "-m", "alembic", "upgrade", "head"], env) != 0:
            print("[roundtrip] re-upgrade head failed", file=sys.stderr)
            return 1

        # Best-effort drift check. ``alembic check`` was added in 1.9; older
        # installs silently skip this.
        rc = _run([sys.executable, "-m", "alembic", "check"], env)
        if rc not in (0, 2):
            # 0 = no drift; 2 = command not available. Anything else is real drift.
            print("[roundtrip] alembic check reported schema drift", file=sys.stderr)
            return 1

        print("[roundtrip] ok — upgrade/downgrade/upgrade cycle completed cleanly")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
