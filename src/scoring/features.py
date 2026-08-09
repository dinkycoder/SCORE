"""
src/scoring/features.py - Financial feature extraction for wallets.
"""

import logging
from dataclasses import dataclass
from typing import Dict, Any

logger = logging.getLogger(__name__)

@dataclass
class WalletState:
    """Represents a wallet's financial state on Base Moonwell."""
    wallet_address: str
    eth_balance: float
    moonwell_liquidity_usd: float
    moonwell_shortfall_usd: float
    block_number: int
    timestamp: int

@dataclass
class FinancialFeatures:
    """Extracted financial features for credit scoring."""
    ltv: float
    liquidity_usd: float
    shortfall_usd: float
    is_underwater: bool
    eth_balance: float
    activity_level: str

def extract_features(wallet_state: WalletState) -> FinancialFeatures:
    """Extract financial features from Moonwell wallet state."""
    total_value = wallet_state.moonwell_liquidity_usd + wallet_state.moonwell_shortfall_usd
    ltv = (
        wallet_state.moonwell_shortfall_usd / total_value
        if total_value > 0
        else 0.0
    )
    
    ltv = min(max(ltv, 0.0), 1.0)
    is_underwater = wallet_state.moonwell_shortfall_usd > 0
    
    if wallet_state.moonwell_liquidity_usd > 1000:
        activity_level = "active"
    else:
        activity_level = "dormant"
    
    features = FinancialFeatures(
        ltv=ltv,
        liquidity_usd=wallet_state.moonwell_liquidity_usd,
        shortfall_usd=wallet_state.moonwell_shortfall_usd,
        is_underwater=is_underwater,
        eth_balance=wallet_state.eth_balance,
        activity_level=activity_level,
    )
    
    logger.debug(f"Features extracted for {wallet_state.wallet_address}: LTV={ltv:.2%}")
    return features

def features_to_dict(features: FinancialFeatures) -> Dict[str, Any]:
    """Convert FinancialFeatures to dict for JSON serialization."""
    return {
        "ltv": round(features.ltv, 4),
        "liquidity_usd": round(features.liquidity_usd, 2),
        "shortfall_usd": round(features.shortfall_usd, 2),
        "is_underwater": features.is_underwater,
        "eth_balance": round(features.eth_balance, 4),
        "activity_level": features.activity_level,
    }