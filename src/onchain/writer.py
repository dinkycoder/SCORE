"""
src/onchain/writer.py - writes measured exposure to CreditScorer on-chain.

SCOPE: this writes ONLY the EAD (exposure) component, via
CreditScorer.updateExposure. It does NOT call updateScore and never will
until a PD/LGD model actually exists - no model has been trained (see
README.md / COMPLIANCE.md / src/api/server.py's /capabilities), and this
project does not write placeholder pd/lgd/creditScore values that could be
mistaken for a real computed result. See contracts/src/CreditScorer.sol
and docs/PHASE_0.md for the modelVersion==0 convention this relies on.

Reading (BaseRPCClient, extract_features) needs no configuration here and
must never be blocked by its absence. Writing needs both
CREDIT_SCORER_ADDRESS (a real deployment) and SCORER_PRIVATE_KEY (a
signing key with ETH for gas) configured, or it fails loud via
ScorerNotConfiguredError rather than silently no-oping.
"""

import logging
from dataclasses import dataclass
from typing import Optional

from web3 import Web3

from base import config

logger = logging.getLogger(__name__)

CREDIT_SCORER_ABI = [
    {"inputs": [{"name": "wallet", "type": "address"},
                {"name": "ead", "type": "uint256"}],
     "name": "updateExposure", "outputs": [],
     "stateMutability": "nonpayable", "type": "function"},
    {"inputs": [{"name": "wallet", "type": "address"}],
     "name": "getScore",
     "outputs": [{"components": [
         {"name": "pd", "type": "uint256"},
         {"name": "lgd", "type": "uint256"},
         {"name": "ead", "type": "uint256"},
         {"name": "creditScore", "type": "uint256"},
         {"name": "timestamp", "type": "uint256"},
         {"name": "modelVersion", "type": "uint256"},
     ], "name": "", "type": "tuple"}],
     "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "scorer",
     "outputs": [{"name": "", "type": "address"}],
     "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "scoreCount",
     "outputs": [{"name": "", "type": "uint256"}],
     "stateMutability": "view", "type": "function"},
]


class ScorerNotConfiguredError(RuntimeError):
    """Raised when a write is attempted without a deployed contract address
    and a signing key both configured. Writing is optional infrastructure
    layered on top of the read path; it must fail loud, not silently no-op,
    and it must never block reading."""


def usd_to_wad(usd: float) -> int:
    """Scale a USD float to the WAD (1e18) fixed-point integer CreditScorer
    stores, matching the convention used throughout the read path (see
    base.config.WAD)."""
    return round(usd * config.WAD)


@dataclass
class ExposureWriteResult:
    """The outcome of one successful updateExposure transaction."""
    wallet: str
    ead_usd: float
    ead_wad: int
    tx_hash: str
    block_number: int


class ScoreWriter:
    """
    Signs and sends updateExposure transactions to a deployed CreditScorer.

    Never writes pd/lgd/creditScore - see module docstring. Blocks until
    each transaction is mined and raises if it reverted, so a caller never
    mistakes a failed write for a successful one.
    """

    def __init__(self, w3: Optional[Web3] = None,
                 contract_address: Optional[str] = None,
                 private_key: Optional[str] = None):
        address = contract_address or config.CREDIT_SCORER_ADDRESS
        key = private_key or config.SCORER_PRIVATE_KEY
        if not address or not key:
            raise ScorerNotConfiguredError(
                "CREDIT_SCORER_ADDRESS and SCORER_PRIVATE_KEY must both be "
                "set to write on-chain (see .env). Reading does not need "
                "either and must not be affected by their absence."
            )

        self.w3 = w3 or Web3(Web3.HTTPProvider(config.RPC_URL))
        self.account = self.w3.eth.account.from_key(key)
        self.contract = self.w3.eth.contract(
            address=Web3.to_checksum_address(address), abi=CREDIT_SCORER_ABI)

    def write_exposure(self, wallet: str, exposure_usd: float) -> ExposureWriteResult:
        """
        Writes exposure_usd (WAD-scaled) for `wallet` via updateExposure.

        Blocks until mined. Raises if the transaction reverted (e.g. the
        configured key is not the contract's `scorer`) - a reverted write
        must never look like a successful one to the caller.
        """
        addr = Web3.to_checksum_address(wallet)
        ead_wad = usd_to_wad(exposure_usd)

        tx = self.contract.functions.updateExposure(addr, ead_wad).build_transaction({
            "from": self.account.address,
            "nonce": self.w3.eth.get_transaction_count(self.account.address),
        })
        signed = self.account.sign_transaction(tx)
        tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)

        if receipt.status != 1:
            raise RuntimeError(
                "updateExposure reverted for " + addr + " (tx " +
                tx_hash.hex() + ") - check that the configured key is the "
                "contract's scorer()."
            )

        logger.info("Wrote exposure $%.2f for %s (tx %s, block %d)",
                    exposure_usd, addr, tx_hash.hex(), receipt.blockNumber)

        return ExposureWriteResult(
            wallet=addr,
            ead_usd=exposure_usd,
            ead_wad=ead_wad,
            tx_hash=tx_hash.hex(),
            block_number=receipt.blockNumber,
        )
