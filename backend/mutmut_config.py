"""Mutmut configuration for the Perfection Verification Loop.

Scope is deliberately narrow:

* ``app/pipeline/nodes`` — the LangGraph analysis nodes (highest semantic risk)
* ``app/orchestration``  — provider routing + config resolver

Running the full tree takes hours and is redundant; these two directories
are where a surviving mutant is most likely to reflect a real test-coverage
gap that matters for correctness.
"""

from __future__ import annotations


def pre_mutation(context):  # pragma: no cover — invoked by mutmut
    """Skip mutations inside comments / docstrings / __init__ boilerplate."""
    if context.filename.endswith("__init__.py"):
        context.skip = True


def post_mutation(context):  # pragma: no cover — invoked by mutmut
    return


# mutmut 2.x picks these up from the module's module-level vars.
paths_to_mutate = "app/pipeline/nodes/,app/orchestration/"
tests_dir = "tests/"
runner = "python -m pytest -q -x --no-header --disable-warnings tests"
# Exclude tests that involve network / sub-processes from the mutation run so
# cycle times stay bounded; mutation is a correctness signal over the core
# node logic, not an integration smoke.
also_copy = ()
