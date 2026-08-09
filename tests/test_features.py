"""
tests/test_features.py — Unit tests for feature extraction.
"""

import pytest
from src.scoring.features import WalletState, extract_features, features_to_dict


def test_extract_features_healthy_wallet():
    wallet = WalletState(
        wallet_address="0x1234567890abcdef1234567890abcdef12345678",
        eth_balance=2.5,
        moonwell_liquidity_usd=50000.0,
        moonwell_shortfall_usd=0.0,
        block_number=12345,
        timestamp=1723206000,
    )
    
    features = extract_features(wallet)
    assert features.ltv == 0.0
    assert features.is_underwater == False


def test_extract_features_underwater_wallet():
    wallet = WalletState(
        wallet_address="0xabcdefabcdefabcdefabcdefabcdefabcdefabcd",
        eth_balance=0.5,
        moonwell_liquidity_usd=10000.0,
        moonwell_shortfall_usd=5000.0,
        block_number=12345,
        timestamp=1723206000,
    )
    
    features = extract_features(wallet)
    assert features.is_underwater == True


def test_features_to_dict():
    wallet = WalletState(
        wallet_address="0x1234567890abcdef1234567890abcdef12345678",
        eth_balance=1.5,
        moonwell_liquidity_usd=25000.75,
        moonwell_shortfall_usd=100.25,
        block_number=12345,
        timestamp=1723206000,
    )
    
    features = extract_features(wallet)
    features_dict = features_to_dict(features)
    
    assert isinstance(features_dict, dict)
    assert "ltv" in features_dict