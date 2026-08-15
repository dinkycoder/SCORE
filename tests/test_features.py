"""
tests/test_features.py - Feature extraction, tested on synthetic positions.

No network. Positions are constructed by hand so the arithmetic is
checkable by inspection.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from base.rpc import MarketPosition, WalletPosition
from scoring.features import extract_features


def make_position(markets, liquidity=0.0, shortfall=0.0):
    return WalletPosition(
        wallet_address="0x" + "aa" * 20,
        block_number=50_000_000,
        markets=markets,
        reported_liquidity_usd=liquidity,
        reported_shortfall_usd=shortfall,
    )


def market(symbol, collateral=0.0, debt=0.0, cf=0.85):
    return MarketPosition(
        market_address="0x" + "bb" * 20,
        symbol=symbol,
        supplied_underlying=collateral,
        borrowed_underlying=debt,
        collateral_usd=collateral,
        debt_usd=debt,
        collateral_factor=cf,
    )


# -- leverage -------------------------------------------------------------

def test_ltv_is_debt_over_collateral():
    p = make_position([
        market("mUSDC", collateral=10_000, cf=0.9),
        market("mWETH", debt=5_000, cf=0.8),
    ], liquidity=4_000)

    f = extract_features(p)
    assert f.ltv == pytest.approx(0.5)


def test_capacity_used_applies_collateral_factor():
    """LTV ignores collateral factors; capacity_used must not."""
    p = make_position([
        market("mUSDC", collateral=10_000, cf=0.8),
        market("mWETH", debt=4_000, cf=0.8),
    ])

    f = extract_features(p)
    assert f.ltv == pytest.approx(0.4)           # 4000 / 10000
    assert f.capacity_used == pytest.approx(0.5)  # 4000 / (10000 * 0.8)
    assert f.headroom == pytest.approx(0.5)


def test_capacity_used_exceeds_ltv_when_cf_below_one():
    """Regression guard: the Week 1 bug reported zero leverage for every
    healthy wallet. Both measures must be positive for a real borrower."""
    p = make_position([
        market("mUSDC", collateral=18_966, cf=0.88),
        market("mWETH", debt=12_226, cf=0.84),
    ])

    f = extract_features(p)
    assert f.ltv > 0
    assert f.capacity_used > f.ltv


# -- directional risk ------------------------------------------------------

def test_stable_collateral_volatile_debt_flags_mismatch():
    p = make_position([
        market("mUSDC", collateral=18_966, cf=0.88),
        market("mWETH", debt=12_226, cf=0.84),
    ])

    f = extract_features(p)
    assert f.volatility_mismatch is True


def test_same_asset_both_sides_is_no_mismatch():
    p = make_position([market("mUSDC", collateral=10_000, debt=4_000, cf=0.9)])

    f = extract_features(p)
    assert f.volatility_mismatch is False


def test_price_move_to_liquidation():
    """Weighted collateral 8000 against debt 4000 tolerates a 100% move."""
    p = make_position([
        market("mUSDC", collateral=10_000, cf=0.8),
        market("mWETH", debt=4_000, cf=0.8),
    ])

    f = extract_features(p)
    assert f.price_move_to_liquidation == pytest.approx(1.0)


# -- edge cases -----------------------------------------------------------

def test_supplier_with_no_debt():
    p = make_position([market("mUSDC", collateral=10_000, cf=0.9)],
                      liquidity=9_000)

    f = extract_features(p)
    assert f.ltv == 0.0
    assert f.capacity_used == 0.0
    assert f.is_borrower is False
    assert f.price_move_to_liquidation is None
    assert f.volatility_mismatch is False


def test_empty_position_does_not_divide_by_zero():
    f = extract_features(make_position([]))
    assert f.ltv == 0.0
    assert f.capacity_used == 0.0
    assert f.market_count == 0
    assert f.is_borrower is False


def test_underwater_wallet():
    p = make_position([
        market("mUSDC", collateral=10_000, cf=0.8),
        market("mWETH", debt=9_000, cf=0.8),
    ], shortfall=1_000)

    f = extract_features(p)
    assert f.is_underwater is True
    assert f.capacity_used > 1.0
    assert f.headroom < 0
    assert f.price_move_to_liquidation < 0


def test_exposure_equals_debt():
    """EAD in the Basel decomposition is outstanding debt."""
    p = make_position([
        market("mUSDC", collateral=10_000, cf=0.8),
        market("mWETH", debt=3_500, cf=0.8),
    ])

    f = extract_features(p)
    assert f.exposure_usd == f.debt_usd == pytest.approx(3_500)


def test_to_dict_is_serialisable():
    import json
    p = make_position([
        market("mUSDC", collateral=10_000, cf=0.8),
        market("mWETH", debt=4_000, cf=0.8),
    ])

    json.dumps(extract_features(p).to_dict())