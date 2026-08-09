"""
src/base/rpc.py — Base RPC client for querying Moonwell lending state.
"""

import json
import logging
from typing import Optional, Dict, Any
from web3 import Web3

logger = logging.getLogger(__name__)

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

class BaseRPCClient:
    """Client for querying Base blockchain and Moonwell lending protocol."""
    
    MOONWELL_COMPTROLLER_SEPOLIA = "0xfBb21d0380beE3312B33c4353c8936a3921d3e47"
    
    def __init__(self, rpc_url: str):
        self.w3 = Web3(Web3.HTTPProvider(rpc_url))
        if not self.w3.is_connected():
            raise ConnectionError(f"Cannot connect to {rpc_url}")
        logger.info(f"Connected to Base RPC. Chain ID: {self.w3.eth.chain_id}")
        self.comptroller = self.w3.eth.contract(
            address=Web3.to_checksum_address(self.MOONWELL_COMPTROLLER_SEPOLIA),
            abi=COMPTROLLER_ABI,
        )
    
    def get_balance(self, address: str) -> float:
        try:
            checksum_addr = Web3.to_checksum_address(address)
            balance_wei = self.w3.eth.get_balance(checksum_addr)
            balance_eth = Web3.from_wei(balance_wei, 'ether')
            logger.debug(f"ETH balance for {address}: {balance_eth}")
            return balance_eth
        except Exception as e:
            logger.error(f"Error fetching ETH balance for {address}: {e}")
            raise
    
    def is_contract(self, address: str) -> bool:
        try:
            checksum_addr = Web3.to_checksum_address(address)
            code = self.w3.eth.get_code(checksum_addr)
            return code != b''
        except Exception as e:
            logger.error(f"Error checking if {address} is contract: {e}")
            raise
    
    def get_latest_block(self) -> int:
        return self.w3.eth.block_number
    
    def get_account_liquidity(self, wallet_address: str) -> Dict[str, Any]:
        try:
            checksum_addr = Web3.to_checksum_address(wallet_address)
            error, liquidity, shortfall = self.comptroller.functions.getAccountLiquidity(
                checksum_addr
            ).call()
            
            result = {
                "error": error,
                "liquidity_wei": int(liquidity),
                "shortfall_wei": int(shortfall),
                "liquidity_usd": Web3.from_wei(liquidity, 'ether'),
                "shortfall_usd": Web3.from_wei(shortfall, 'ether'),
            }
            logger.debug(f"Liquidity for {wallet_address}: {result}")
            return result
        except Exception as e:
            logger.error(f"Error fetching account liquidity for {wallet_address}: {e}")
            raise
    
    def get_wallet_state(self, wallet_address: str) -> Dict[str, Any]:
        try:
            checksum_addr = Web3.to_checksum_address(wallet_address)
            eth_balance = self.get_balance(checksum_addr)
            liquidity_info = self.get_account_liquidity(checksum_addr)
            is_contract = self.is_contract(checksum_addr)
            
            wallet_state = {
                "wallet_address": checksum_addr,
                "eth_balance": eth_balance,
                "is_contract": is_contract,
                "moonwell_liquidity_usd": liquidity_info["liquidity_usd"],
                "moonwell_shortfall_usd": liquidity_info["shortfall_usd"],
                "block_number": self.get_latest_block(),
                "timestamp": self.w3.eth.get_block("latest").timestamp,
            }
            
            logger.info(f"Wallet state fetched for {wallet_address}")
            return wallet_state
        except Exception as e:
            logger.error(f"Error fetching wallet state for {wallet_address}: {e}")
            raise
