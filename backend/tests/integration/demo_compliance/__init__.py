"""Spec 018 demo-compliance integration tests (24 user stories).

Parallel agents own disjoint ranges:

- Agent A: US-1..US-8
- Agent B: US-9..US-16
- Agent C: US-17..US-24  (this range)

Each ``test_us{NN}_*.py`` module is self-contained; a shared
:mod:`conftest` provides the FastAPI test client, fake upstream HES/MDMS
clients, and seed helpers. Tests that exercise deferred capabilities
(e.g. smart-inverter curtailment on live HES, FLISR on a real network
model) are marked ``@pytest.mark.xfail`` with the gating reason so CI
stays green while the backing wave lands.
"""
