"""Toolchain requirements for the test suite (M2.1 hardening).

Tiers 3-4 and the behavioural tests need Pasmo. Before M2.1 they were
``skipIf(pasmo missing)``, so a machine without Pasmo reported a green run
with no assembly or behavioural coverage at all (independent M2 review).

Policy now: a missing Pasmo is a test **error**, not a skip. A developer who
knowingly works without Pasmo (e.g. frontend-only changes) may opt in to
skipping with ``PBAS_ALLOW_MISSING_PASMO=1``; the skip reason then names that
variable, so the report can never look like full coverage by accident.
"""
from __future__ import annotations

import os
import shutil
import unittest

PASMO = shutil.which("pasmo")
ALLOW_MISSING_ENV = "PBAS_ALLOW_MISSING_PASMO"

MISSING_MESSAGE = (
    "pasmo is not on PATH: tier-3/4 and behavioural tests cannot run. Install "
    "Pasmo 0.5.3, or set PBAS_ALLOW_MISSING_PASMO=1 to skip them explicitly."
)


def requires_pasmo(cls):
    """Class decorator: the TestCase needs Pasmo.

    With Pasmo present the class is unchanged. Without it the class fails in
    ``setUpClass`` (reported as an error) unless the opt-in environment
    variable is set, in which case it is skipped with a reason naming it.
    """
    if PASMO is not None:
        return cls
    if os.environ.get(ALLOW_MISSING_ENV) == "1":
        return unittest.skip(f"pasmo not installed ({ALLOW_MISSING_ENV}=1)")(cls)

    def setUpClass(klass):  # noqa: N802 (unittest API name)
        raise RuntimeError(MISSING_MESSAGE)

    cls.setUpClass = classmethod(setUpClass)
    return cls


# M14: tests that need files kept only in the private development repository
# (the prototype in ../POC, earlier milestones' builds in artifacts/, the
# engineering records in docs/M*.md, the release packager). In the public
# repository those tests are skipped, each with the file it needs as the reason,
# so a run reports them honestly; in the private repository the files exist.
# PBAS_REQUIRE_PRIVATE=1 (tools/run_tests.py sets it in the private checkout)
# makes a missing file an error, so the private suite can never skip them.
REQUIRE_PRIVATE_ENV = "PBAS_REQUIRE_PRIVATE"


def _shown(path) -> str:
    """*path* relative to the repository (the folder above tests/), as a skip reason shows it."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    for base, prefix in ((root, ""), (root.parent, "../")):  # the prototype sits beside the repository
        try:
            return prefix + Path(path).resolve().relative_to(base).as_posix()
        except ValueError:
            continue
    return str(path)


def requires_files(*paths, what: str):
    """Decorator for a test method or class that reads *paths*.

    *what* names the material in the skip reason ("the prototype's examples").
    """
    from pathlib import Path

    missing = [_shown(p) for p in map(Path, paths) if not p.exists()]

    def wrap(obj):
        if not missing:
            return obj
        if os.environ.get(REQUIRE_PRIVATE_ENV) == "1":
            def fail(*_args, **_kw):
                raise RuntimeError(f"{REQUIRE_PRIVATE_ENV}=1 but {what} is missing: {missing[0]}")
            if isinstance(obj, type):
                obj.setUpClass = classmethod(lambda klass: fail())
                return obj
            return fail
        return unittest.skip(f"needs {what} ({missing[0]}), which is not in the public repository")(obj)

    return wrap


def need_file(path, what: str) -> None:
    """Inside a test: stop it with a skip (or, with PBAS_REQUIRE_PRIVATE=1, an error)
    when *path* is absent. For tests that check today's behaviour first and compare
    with a private record afterwards: the first part still runs everywhere."""
    from pathlib import Path

    if Path(path).exists():
        return
    if os.environ.get(REQUIRE_PRIVATE_ENV) == "1":
        raise RuntimeError(f"{REQUIRE_PRIVATE_ENV}=1 but {what} is missing: {path}")
    raise unittest.SkipTest(f"needs {what} ({_shown(path)}), which is not in the public repository")
