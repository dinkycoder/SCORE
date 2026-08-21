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

    capacity_used: Optional[float]
    """Debt / weighted collateral. This IS what the protocol enforces:
    at 1.0 the position becomes liquidatable. The better risk signal.
    None when `degraded` is True: a market held real collateral but its
    collateral_factor could not be decoded, so weighted collateral is not
    known and must not be asserted as if it were."""

    headroom: Optional[float]
    """1 - capacity_used. Fraction of borrowing power still unused.
    Negative means already liquidatable. Equivalently: the fractional
    COLLATERAL-price drop that would trigger liquidation, holding debt
    price fixed - e.g. capacity_used=0.5 means collateral can fall 50%
    before liquidation. See `debt_rise_to_liquidation` for the other
    direction, which is a different number, not this one restated. None
    when `degraded` is True, for the same reason as capacity_used."""

    degraded: bool
    """True when a market holds nonzero collateral but its
    collateral_factor failed to decode (e.g. a reverted markets() call
    tolerated by allowFailure). Weighted collateral cannot be computed in
    that state, so capacity_used, headroom, and debt_rise_to_liquidation
    report None rather than the falsely-safe 0.0/1.0 a missing weight
    would otherwise produce. is_underwater is unaffected: it comes from
    the protocol's own getAccountLiquidity call, not from this weighting."""

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

    debt_rise_to_liquidation: Optional[float]
    """The fractional DEBT-price rise that would trigger liquidation,
    holding collateral price fixed. This is NOT the same number as
    headroom, and the two must not be substituted for each other: for
    weighted collateral 8000 against debt 4000 (capacity_used=0.5,
    headroom=0.5), the collateral only needs to drop 50% to liquidate
    (that reading is `headroom`), but debt would need to RISE 100% to have
    the same effect, because liquidation occurs when weighted collateral
    falls to debt - weighted*(1-drop)=debt gives drop=headroom, while
    debt*(1+rise)=weighted gives rise=weighted/debt-1. The dominant
    Compound-family position here is volatile collateral against stable
    debt, so the collateral-drop reading (`headroom`) is usually the
    relevant stress test; this field is the other direction, given its own
    name so it can't be mistaken for the first. None when `degraded` is
    True or when there is no debt."""

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

    # A market with real collateral but an undecoded collateral_factor
    # cannot be weighted. Treating it as zero-weight (the previous
    # behaviour) makes a heavily-leveraged wallet look pristine, since
    # weighted collateral silently drops to whatever the OTHER markets
    # contribute. Flag it instead of asserting a number we don't have.
    # Note this catches PARTIAL blindness too: a wallet with one reliable
    # collateral market and one undecoded one still gets flagged, even
    # though `weighted` alone would look positive and non-zero.
    degraded = any(m.collateral_usd > 0 and m.collateral_factor is None
                   for m in position.markets)

    # LTV against raw collateral. Zero collateral with zero debt is a
    # wallet with no position, not an infinitely leveraged one.
    ltv = debt / collateral if collateral > 0 else 0.0

    # The ratio the protocol actually enforces. Weighted collateral applies
    # each asset's collateral factor (and excludes any not-entered market;
    # see MarketPosition.is_entered), so this reaches 1.0 exactly when the
    # position becomes liquidatable.
    #
    # debt > 0 with weighted <= 0 is the position the previous formula got
    # backwards: `debt / weighted if weighted > 0 else 0.0` treated "no
    # usable collateral counted" as the SAFE default (0.0) instead of the
    # dangerous one. It's unknowable/unbounded, not zero, so it reports
    # None rather than asserting a number - the same reasoning as
    # `degraded`, just triggered by a different cause (all counted
    # collateral excluded, e.g. supplied-but-not-entered, rather than an
    # undecoded factor).
    if degraded or (debt > 0 and weighted <= 0):
        capacity_used = None
        headroom = None
    elif weighted > 0:
        capacity_used = debt / weighted
        headroom = 1.0 - capacity_used
    else:
        capacity_used = 0.0
        headroom = 1.0

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

    # The debt-price rise that triggers liquidation - the OTHER direction
    # from headroom (see CreditFeatures.debt_rise_to_liquidation for why
    # they differ). Liquidation occurs when weighted collateral falls to
    # debt; holding collateral fixed and raising debt instead, the move is
    # (weighted / debt) - 1. Unknowable when degraded, same as capacity_used.
    if not degraded and debt > 0 and weighted > 0:
        debt_rise_to_liquidation = (weighted / debt) - 1.0
    else:
        # Covers: no debt (nothing to compute), degraded (undecoded
        # factor), and debt > 0 with weighted <= 0 (no usable collateral
        # counted - see capacity_used above for why that's None, not 0).
        debt_rise_to_liquidation = None

    features = CreditFeatures(
        ltv=round(ltv, 6),
        capacity_used=round(capacity_used, 6) if capacity_used is not None else None,
        headroom=round(headroom, 6) if headroom is not None else None,
        degraded=degraded,
        collateral_usd=round(collateral, 2),
        debt_usd=round(debt, 2),
        exposure_usd=round(debt, 2),
        market_count=position.market_count,
        volatility_mismatch=volatility_mismatch,
        debt_rise_to_liquidation=(
            round(debt_rise_to_liquidation, 6)
            if debt_rise_to_liquidation is not None else None
        ),
        is_underwater=position.is_underwater,
        is_borrower=debt > 0,
    )

    logger.debug(
        "features for %s: LTV=%.4f capacity=%s underwater=%s degraded=%s",
        position.wallet_address, features.ltv,
        features.capacity_used, features.is_underwater, features.degraded,
    )

    return features