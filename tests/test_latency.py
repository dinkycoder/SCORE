"""
tests/test_latency.py - Enforce the Phase 0 latency target.

Phase 0 sets p95 under 500ms for a single-wallet score. This test hits
the live chain and will FAIL until the client batches its calls: reading
one position currently costs ~15 sequential round trips at ~150ms each.

Marked `live` so it can be excluded from CI, which has no RPC key:

    pytest tests/ -m "not live"      # unit tests only
    pytest tests/ -m live            # this one
"""

import statistics
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import base.config as config
from base.rpc import BaseRPCClient
from scoring.features import extract_features

# A wallet with an active Moonwell position, confirmed 2026-08-22.
# Collateral spread across 8 markets, debt in a 9th - a more thorough
# arithmetic exercise than a single-collateral/single-debt position.
# The previous reference wallet (0xAA503ae3...) closed its position
# entirely since it was chosen on 2026-08-15, which is exactly why this
# comment carries a confirmation date: a hardcoded wallet is a liability
# that decays, not a one-time fix. If this one closes out too, use
# scripts/find_borrowers.py to find a live replacement, then verify with
# `pytest tests/test_latency.py -m live -s` before trusting the new one.
TEST_WALLET = "0xEE0126C2c78C02eD9C128B4905FCE387e4326E66"

P95_TARGET_MS = 500
SAMPLES = 10


pytestmark = pytest.mark.live


@pytest.fixture(scope="module")
def client():
    if config.USING_PUBLIC_RPC:
        pytest.skip("Public RPC is rate limited; set BASE_RPC_URL in .env")
    return BaseRPCClient()


def test_score_latency_p95(client):
    """A single-wallet score must complete within the Phase 0 target."""
    timings = []

    for _ in range(SAMPLES):
        start = time.perf_counter()
        position = client.get_wallet_position(TEST_WALLET)
        extract_features(position)
        timings.append((time.perf_counter() - start) * 1000)

    timings.sort()
    p50 = statistics.median(timings)
    p95 = timings[int(len(timings) * 0.95) - 1]

    print()
    print("  samples: " + str(SAMPLES))
    print("  p50:     " + format(p50, ".0f") + "ms")
    print("  p95:     " + format(p95, ".0f") + "ms")
    print("  target:  " + str(P95_TARGET_MS) + "ms")
    print("  min/max: " + format(min(timings), ".0f") + "/"
          + format(max(timings), ".0f") + "ms")

    assert p95 < P95_TARGET_MS, (
        "p95 of " + format(p95, ".0f") + "ms exceeds the "
        + str(P95_TARGET_MS) + "ms target. Sequential eth_call round trips "
        "are the bottleneck; batching via Multicall3 is the fix."
    )


def test_correctness_survives_optimisation(client):
    """Guard rail for the multicall work: batched reads must produce the
    same numbers as sequential ones. Compares the client against the
    Comptroller's own liquidity figure, which is computed independently
    on-chain."""
    position = client.get_wallet_position(TEST_WALLET)

    derived = position.total_weighted_collateral_usd - position.total_debt_usd
    reported = (position.reported_liquidity_usd
                - position.reported_shortfall_usd)

    if abs(reported) < 1.0:
        pytest.skip("Wallet has near-zero liquidity; comparison uninformative")

    assert derived == pytest.approx(reported, rel=0.02), (
        "Derived liquidity (" + format(derived, ".2f") + ") disagrees with "
        "the Comptroller (" + format(reported, ".2f") + "). The position "
        "arithmetic is wrong."
    )