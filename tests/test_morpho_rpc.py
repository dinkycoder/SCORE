"""
tests/test_morpho_rpc.py - MorphoRPCClient's own conversion/decode logic.

extract_features() itself needs no new tests here - it's reused
unchanged from the Moonwell path (see
docs/superpowers/specs/2026-08-23-morpho-reader-design.md §5). These
tests cover what's actually new: Morpho's shares math and the raw-data
-> MarketPosition conversion.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from morpho.rpc import shares_to_assets_up


def test_shares_to_assets_up_rounds_up_not_down():
    """Hand-verified: 500_000_000 shares of a 1_000_000_000-share pool
    holding 999 total assets is 499.5009... Morpho rounds UP for a
    borrower's owed amount (SharesMathLib.toAssetsUp), so this must come
    out to 500, not 499 - a wallet's debt must never be understated by
    rounding."""
    assert shares_to_assets_up(500_000_000, 999, 1_000_000_000) == 500
