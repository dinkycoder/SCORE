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

from morpho.rpc import shares_to_assets_up, build_market_position


def test_shares_to_assets_up_rounds_up_not_down():
    """Hand-verified: 500_000_000 shares of a 1_000_000_000-share pool
    holding 999 total assets is 499.5009... Morpho rounds UP for a
    borrower's owed amount (SharesMathLib.toAssetsUp), so this must come
    out to 500, not 499 - a wallet's debt must never be understated by
    rounding."""
    assert shares_to_assets_up(500_000_000, 999, 1_000_000_000) == 500


def test_build_market_position_converts_raw_data_to_usd():
    """1.0 cbBTC collateral (8 decimals) at a price implying $100,000/BTC,
    against $50,000 (raw 6-decimal USDC) already-converted borrowed
    assets. Hand-verified: collateral_price_1e36 = 10**39 means
    1 cbBTC (1e8 raw) -> 1e8 * 1e39 // 1e36 = 1e11 raw USDC = $100,000."""
    position = build_market_position(
        market_id_hex="0x9103c3b4e834476c9a62ea009ba2c884ee42e94e6e314a26f04d312434191836",
        collateral_raw=100_000_000,       # 1.0 cbBTC
        borrowed_assets_raw=50_000_000_000,  # $50,000 in raw USDC
        collateral_price_1e36=10 ** 39,
        collateral_decimals=8,
        loan_decimals=6,
    )

    assert position.symbol == "cbBTC"
    assert position.supplied_underlying == pytest.approx(1.0)
    assert position.borrowed_underlying == pytest.approx(50_000.0)
    assert position.collateral_usd == pytest.approx(100_000.0)
    assert position.debt_usd == pytest.approx(50_000.0)
    assert position.collateral_factor == pytest.approx(0.86)
    assert position.is_entered is True


def test_build_market_position_with_no_debt():
    """A supplier with no borrow - debt_usd and borrowed_underlying must
    be exactly zero, not a rounding artifact."""
    position = build_market_position(
        market_id_hex="0x9103c3b4e834476c9a62ea009ba2c884ee42e94e6e314a26f04d312434191836",
        collateral_raw=100_000_000,
        borrowed_assets_raw=0,
        collateral_price_1e36=10 ** 39,
        collateral_decimals=8,
        loan_decimals=6,
    )
    assert position.debt_usd == 0.0
    assert position.borrowed_underlying == 0.0
