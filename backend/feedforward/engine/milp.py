"""
engine/milp.py
==============
The one place that knows which PuLP is installed.

PuLP 3.x bundles the CBC solver (``PULP_CBC_CMD``), returns an int from
``solve()`` and reports status through ``LpStatus``. PuLP 4 dropped the bundle
(CBC comes from the ``pulp[cbc]`` extra, through ``COIN_CMD``), returns an
``LpSolveStats`` and removed ``LpStatus``, ``LpVariable(..., cat=)`` and
``LpVariable.dicts``. Models create variables with ``prob.add_variable`` /
``prob.add_variable_dicts`` (both versions) and solve through ``solve`` here.
"""
from __future__ import annotations

import warnings

import pulp


# Stop within 1% of the best possible objective. Proving the last fraction of
# a percent took 20 s for athlete-sized weeks (more snacks, more combinations)
# and changed nutrient coverage by under 0.4 points; with the gap they take
# well under a second.
GAP = 0.01


def _cbc(time_limit: float | None):
    options = {"msg": False, "gapRel": GAP}
    if time_limit is not None:
        options["timeLimit"] = time_limit
    bundled = getattr(pulp, "PULP_CBC_CMD", None)
    return bundled(**options) if bundled is not None else pulp.COIN_CMD(**options)


# PuLP 4 statuses for "CBC stopped at a limit": with a solution in hand, the
# solution is usable. PuLP 3 reported all of these as "Optimal" (status 1);
# GapLimit in particular is CBC's default optimality tolerance being met.
_LIMIT_STOPS = ("TimeLimit", "GapLimit", "NodeLimit", "IterationLimit", "SolutionLimit")


def replace_objective(prob: pulp.LpProblem, objective, name: str = "objective") -> None:
    """
    Replace the objective of a model already solved once, for a second solve
    (the week planner's needs-first levers). Both PuLP versions take
    ``prob += expr, name`` and warn that it overwrites; here that is the point.
    """
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="Overwriting previously set objective")
        prob += objective, name


def solve(prob: pulp.LpProblem, time_limit: float | None = None) -> tuple[bool, str]:
    """
    Solve with CBC. Returns (usable, status): usable when there is a solution
    to read, i.e. optimal, or the best one found when CBC stopped at a limit
    (time, optimality gap, nodes...). Infeasible, unbounded, numerical errors
    and interruptions are not usable.
    """
    result = prob.solve(_cbc(time_limit))
    if isinstance(result, int):                                   # PuLP 3
        status = pulp.LpStatus[result]
        return status == "Optimal", status
    status = result.status                                        # PuLP 4: LpSolveStats
    usable = status.name == "Optimal" or (status.name in _LIMIT_STOPS and bool(result.has_solution))
    return usable, status.name
