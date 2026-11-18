"""Compares the local trade log against Deriv's own portfolio. Pure
Python, no dependency — same reasoning as tools/indicators.py.

Why this exists: `scripts/run_phase{3,4,5}_*.py` track open contracts by
subscribing to `proposal_open_contract` and writing the result locally.
If the process crashes, is killed, or loses its websocket connection
while a contract is open, that subscription never delivers its closing
update, and the local log is left showing a contract as "open" forever
— or, in the other direction, Deriv's account could show a contract this
log never recorded at all (bought from another client, or from before
this tool existed). Neither failure mode self-heals without an explicit
reconciliation pass.
"""
from __future__ import annotations


def diff_portfolio(
    local_open_contract_ids: set[int], deriv_open_contract_ids: set[int]
) -> tuple[set[int], set[int]]:
    """Returns (ghosts, orphans).

    ghosts: contract ids the local log still calls "open" that Deriv no
    longer shows as open — almost always a missed close event. These
    should be healed by querying Deriv for the real outcome and updating
    the local record.

    orphans: contract ids Deriv shows as open that the local log has no
    record of at all. These are NOT auto-adopted into the local log —
    this function only reports the mismatch; a human decides what to do
    with a position this tool didn't create.
    """
    ghosts = local_open_contract_ids - deriv_open_contract_ids
    orphans = deriv_open_contract_ids - local_open_contract_ids
    return ghosts, orphans
