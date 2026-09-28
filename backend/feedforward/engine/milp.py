"""
engine/milp.py
==============
The one place that knows which PuLP is installed.

PuLP 3.x bundles the CBC solver (``PULP_CBC_CMD``); PuLP 4 dropped the bundle
and finds CBC from the ``pulp[cbc]`` extra through ``COIN_CMD``. Variables are
created with ``prob.add_variable`` / ``prob.add_variable_dicts``, which both
versions have (``LpVariable(..., cat=)`` and ``LpVariable.dicts`` are gone in 4).
"""
from __future__ import annotations

import pulp


def solver(time_limit: float | None = None):
    """CBC, quiet, with an optional time limit in seconds."""
    options = {"msg": False}
    if time_limit is not None:
        options["timeLimit"] = time_limit
    bundled = getattr(pulp, "PULP_CBC_CMD", None)
    return bundled(**options) if bundled is not None else pulp.COIN_CMD(**options)

