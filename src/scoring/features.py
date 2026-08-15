"""
src/scoring/features.py - Credit features from a Moonwell wallet position.

These are point-in-time features only. They describe solvency: where a
wallet stands right now. They say nothing about propensity - whether this
borrower behaves in ways that precede liquidation - which requires event
history and is a later stage.

Everything here is deliberately interpretable. A credit decision must be
explainable to the borrower it affects (CFPB Circular 2022-03), so the
features feeding it cannot be opaque.
"""

import logging
from dataclasses import dataclass, asdict
from typing import Any, Dict, Optional

from base.rpc import WalletPosition

logger = logging.getLogger(__name__)


@dataclass
class CreditFeatures:
    """Point-in-time credit features for one wallet."""

    # -- Leverage ---------------------------------------------------------
    ltv: float
    """Debt / collateral. The intuitive leverage measure, but NOT the
    quantity the protocol enforces against."""

    capacity_used: float
    """Debt / weighted collateral. This IS what the protocol enforces:
    at 1.0 the position becomes liquidatable. The better risk signal."""

    headroom: float
    """1 - capacity_used. Fraction of borrowing power still unused.
    Negative means already liquidatable."""

    # -- Scale ------------------------------------------------------------
    collateral_usd: float
    debt_usd: float
    exposure_usd: float
    """Debt outstanding. This is EAD in the Basel decomposition."""

    # -- Composition ------------------------------------------------------
    market_count: int
    """Markets with an active position. Concentration proxy."""

    volatility_mismatch: bool
    """True when collateral and debt are in different assets, so the
    position carries directional price risk beyond its leverage. A wallet
    with stable collateral and volatile debt is short that asset and can
    be liquidated by a price RISE, which LTV alone does not reveal."""

    price_move_to_liquidation: Optional[float]
    """Fractional adverse price move that would trigger liquidation, or
    None when there is no debt. 0.35 means a 35% move against the position."""

    # -- State ------------------------------------------------------------
    is_underwater: bool
    is_borrower: bool

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# Assets whose USD value is designed to stay near constant. Anything else
# is treated as volatile for the mismatch check. Symbols are Moonwell
# mToken symbols (mUSDC, mUSDbC, ...).
STABLE_SYMBOLS = {"musdc", "musdbc", "meurc", "mdai", "musdt"}


def _is_stable(symbol: str) -> bool:
    return symbol.lower() in STABLE_SYMBOLS


def extract_features(position: WalletPosition) -> CreditFeatures:
    """Compute credit features from a wallet's on-chain position."""

    collateral = position.total_collateral_usd
    weighted = position.total_weighted_collateral_usd
    debt = position.total_debt_usd

    # LTV against raw collateral. Zero collateral with zero debt is a
    # wallet with no position, not an infinitely leveraged one.
    ltv = debt / collateral if collateral > 0 else 0.0

    # The ratio the protocol actually enforces. Weighted collateral applies
    # each asset's collateral factor, so this reaches 1.0 exactly when the
    # position becomes liquidatable.
    capacity_used = debt / weighted if weighted > 0 else 0.0
    headroom = 1.0 - capacity_used

    # Directional risk. Collateral and debt in different assets means the
    # position is exposed to the relative price between them.
    collateral_symbols = {m.symbol for m in position.markets
                          if m.collateral_usd > 0}
    debt_symbols = {m.symbol for m in position.markets if m.debt_usd > 0}

    if collateral_symbols and debt_symbols:
        stable_collateral = all(_is_stable(s) for s in collateral_symbols)
        stable_debt = all(_is_stable(s) for s in debt_symbols)
        volatility_mismatch = (stable_collateral != stable_debt) or bool(
            collateral_symbols ^ debt_symbols
        )
    else:
        volatility_mismatch = False

    # How far prices must move against this position before liquidation.
    # Liquidation occurs when weighted collateral falls to debt, so the
    # move is (weighted / debt) - 1.
    if debt > 0 and weighted > 0:
        price_move_to_liquidation = (weighted / debt) - 1.0
    else:
        price_move_to_liquidation = None

    features = CreditFeatures(
        ltv=round(ltv, 6),
        capacity_used=round(capacity_used, 6),
        headroom=round(headroom, 6),
        collateral_usd=round(collateral, 2),
        debt_usd=round(debt, 2),
        exposure_usd=round(debt, 2),
        market_count=position.market_count,
        volatility_mismatch=volatility_mismatch,
        price_move_to_liquidation=(
            round(price_move_to_liquidation, 6)
            if price_move_to_liquidation is not None else None
        ),
        is_underwater=position.is_underwater,
        is_borrower=debt > 0,
    )

    logger.debug(
        "features for %s: LTV=%.4f capacity=%.4f underwater=%s",
        position.wallet_address, features.ltv,
        features.capacity_used, features.is_underwater,
    )

    return features