"""
src/base/rpc.py - Base RPC client for querying Moonwell lending state.

Reads are performed via eth_call: no transaction, no gas, no signature.
Safe to run against Base mainnet.
"""

import logging
from typing import Dict, Any
from web3 import Web3

logger = logging.getLogger(__name__)

# Minimal ABI - only the function we need.
COMPTROLLER_ABI = [
    {
        "inputs": [{"internalType": "address", "name": "account", "type": "address"}],
        "name": "getAccountLiquidity",
        "outputs": [
            {"internalType": "uint256", "name": "error", "type": "uint256"},
            {"internalType": "uint256", "name": "liquidity", "type": "uint256"},
            {"internalType": "uint256", "name": "shortfall", "type": "uint256"},
        ],
        "stateMutability": "view",
        "type": "function",
    }
]

# Verified against docs.moonwell.fi/moonwell/protocol-information/contracts
# on 2026-08-15. Moonwell has NO Base Sepolia deployment; these are mainnet.
MOONWELL_COMPTROLLER_BASE = "0xfBb21d0380beE3312B33c4353c8936a0F13EF26C"
MOONWELL_ORACLE_BASE = "0xEC942bE8A8114bFD0396A5052c36027f2cA6a9d0"

BASE_MAINNET_RPC = "https://mainnet.base.org"


class BaseRPCClient:
    """Reads wallet state from Moonwell on Base."""

    def __init__(self, rpc_url: str = BASE_MAINNET_RPC,
                 comptroller_address: str = MOONWELL_COMPTROLLER_BASE):
        self.w3 = Web3(Web3.HTTPProvider(rpc_url))

        if not self.w3.is_connected():
            raise ConnectionError(f"Cannot connect to {rpc_url}")

        chain_id = self.w3.eth.chain_id
        if chain_id != 8453:
            logger.warning(
                "Connected to chain %s, expected 8453 (Base mainnet). "
                "Moonwell is not deployed on Base testnets.", chain_id
            )

        logger.info("Connected to Base. Chain ID: %s", chain_id)

        self.comptroller = self.w3.eth.contract(
            address=Web3.to_checksum_address(comptroller_address),
            abi=COMPTROLLER_ABI,
        )

    def get_latest_block(self) -> int:
        return self.w3.eth.block_number

    def get_account_liquidity(self, wallet_address: str) -> Dict[str, Any]:
        """
        Query borrowing capacity versus outstanding debt.

        Returns liquidity (surplus capacity) and shortfall (deficit).
        At most one is non-zero. A non-zero shortfall means the position
        is liquidatable right now.

        NOTE: raw values are scaled integers. The divisor and denomination
        are asserted-but-unverified; confirm empirically before trusting
        any downstream dollar figure.
        """
        addr = Web3.to_checksum_address(wallet_address)

        error, liquidity, shortfall = (
            self.comptroller.functions.getAccountLiquidity(addr).call()
        )

        if error != 0:
            raise RuntimeError(f"Comptroller returned error code {error}")

        return {
            "wallet_address": addr,
            "liquidity_raw": int(liquidity),
            "shortfall_raw": int(shortfall),
            "liquidity_scaled": float(Web3.from_wei(liquidity, "ether")),
            "shortfall_scaled": float(Web3.from_wei(shortfall, "ether")),
            "block_number": self.get_latest_block(),
        }