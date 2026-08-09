import pytest
from src.scoring.features import WalletState, extract_features

def test_extract_features_basic():
    wallet = WalletState(
        wallet_address="0x1234567890abcdef1234567890abcdef12345678",
        total_collateral_usd=10000.0,
        total_borrowed_usd=5000.0,
        repaid_usd=2000.0,
        deposit_count=5,
        borrow_count=3,
        repay_count=2,
    )
    
    features = extract_features(wallet)
    assert features.ltv == 0.5
    assert features.repay_to_borrow_ratio == 0.4
