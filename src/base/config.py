"""
src/base/config.py - Single source of truth for chain configuration.

The RPC URL comes from the environment so that the endpoint can be
swapped, and the API key kept out of version control, without touching
any code. Everything else here is a verified on-chain constant.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from the project root regardless of where a script is run from.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(_PROJECT_ROOT / ".env")

# --- Network -------------------------------------------------------------
RPC_URL = os.getenv("BASE_RPC_URL", "https://mainnet.base.org")
CHAIN_ID = 8453  # Base mainnet

USING_PUBLIC_RPC = "mainnet.base.org" in RPC_URL

# --- Moonwell contracts --------------------------------------------------
# Verified against docs.moonwell.fi/moonwell/protocol-information/contracts
# on 2026-08-15. Moonwell has NO Base testnet deployment.
COMPTROLLER = "0xfBb21d0380beE3312B33c4353c8936a0F13EF26C"

MARKETS = {
    "USDC": "0xEdc817A28E8B93B03976FBd4a3dDBc9f7D176c22",
    "WETH": "0x628ff693426583D9a7FB391E54366292F509D457",
    "cbBTC": "0xF877ACaFA28c19b96727966690b2f44d35aD5976",
    "EURC": "0xb682c840B5F4FC58B20769E691A6fa1305A501a2",
}

# --- Scaling -------------------------------------------------------------
# Confirmed empirically 2026-08-15: derived and reported liquidity agreed
# to 1.000000 on wallet 0xAA503ae3. USD values are scaled by 1e18.
WAD = 10 ** 18

# --- CreditScorer (write path) --------------------------------------------
# Both unset until a real deployment happens (see
# contracts/script/DeployCreditScorer.s.sol). Reading (get_wallet_position,
# extract_features) needs neither and must never be blocked by their
# absence - only src/onchain/writer.py does, and it fails loud rather than
# writing silently misconfigured.
CREDIT_SCORER_ADDRESS = os.getenv("CREDIT_SCORER_ADDRESS") or None
SCORER_PRIVATE_KEY = os.getenv("SCORER_PRIVATE_KEY") or None


def describe() -> str:
    """Human-readable config summary, with the API key masked."""
    if USING_PUBLIC_RPC:
        endpoint = RPC_URL + "  (PUBLIC - rate limited)"
    else:
        host = RPC_URL.split("/v2/")[0] if "/v2/" in RPC_URL else RPC_URL
        endpoint = host + "/v2/***"
    return "RPC: " + endpoint + "\nChain: " + str(CHAIN_ID)