"""
src/api/server.py - HTTP interface to SCORE.

SCOPE: this service computes point-in-time SOLVENCY features from live
on-chain position data. It does NOT estimate probability of default,
loss given default, or any modelled quantity. No model has been trained.
Endpoints report only what is measured.

Every scored address is screened against the OFAC SDN list (see
docs/OFAC_SCREENING.md). Screening fails loud: if the sanctions list cannot
be freshly verified, the endpoint returns an error rather than a result, so
a screening gap can never masquerade as a clean position.
"""

import logging

from flask import Flask, jsonify
from flask_cors import CORS
from web3 import Web3

import base.config as config
from base.rpc import BaseRPCClient
from scoring.features import extract_features
from compliance.sanctions import (
    SanctionsScreener,
    StaleListError,
    ListUnavailableError,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

_client = None
_screener = None


def get_client() -> BaseRPCClient:
    """Lazily construct the RPC client so market metadata is fetched once."""
    global _client
    if _client is None:
        _client = BaseRPCClient()
    return _client


def get_screener() -> SanctionsScreener:
    """Lazily construct the sanctions screener so the list loads once."""
    global _screener
    if _screener is None:
        _screener = SanctionsScreener()
    return _screener


@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "ok",
        "service": "SCORE",
        "version": "0.3.0",
        "chain_id": config.CHAIN_ID,
        "using_public_rpc": config.USING_PUBLIC_RPC,
    }), 200


@app.route("/capabilities", methods=["GET"])
def capabilities():
    """
    What this service can and cannot currently do.

    Stated explicitly because the gap between the two is the difference
    between a solvency check and a credit score.
    """
    return jsonify({
        "implemented": {
            "point_in_time_solvency": [
                "ltv",
                "capacity_used",
                "headroom",
                "collateral_usd",
                "debt_usd",
                "exposure_usd",
                "market_count",
                "volatility_mismatch",
                "price_move_to_liquidation",
                "is_underwater",
                "is_borrower",
            ],
            "compliance": [
                "ofac_sdn_screening",
            ],
        },
        "not_implemented": {
            "probability_of_default": "Requires liquidation labels over a "
                                      "label period. Not yet extracted.",
            "loss_given_default": "Requires realised liquidation severity. "
                                  "Not yet extracted.",
            "behavioural_history": "Requires event-log extraction (Borrow, "
                                   "Repay, LiquidateBorrow). Not yet built.",
            "trained_model": "No model has been trained. No accuracy figures "
                             "are claimed.",
        },
        "protocol": "Moonwell",
        "network": "Base mainnet",
    }), 200


@app.route("/position/<wallet_address>", methods=["GET"])
def position(wallet_address: str):
    """
    Point-in-time solvency features for a wallet.

    Flow:
      1. Validate the address.
      2. Screen it against the OFAC SDN list. If the list cannot be freshly
         verified, return 503 - never fall through to a result, because a
         screening gap must not look like a clean position.
      3. Read the position and compute features.

    A sanctioned address is still read and returned, but flagged: flagging
    for risk is permissible, and the caller needs to see both the match and
    the position. What matters is that the match is surfaced, not hidden.
    """
    try:
        addr = Web3.to_checksum_address(wallet_address)
    except Exception:
        return jsonify({"error": "Invalid wallet address"}), 400

    # -- sanctions screening (fail loud) ---------------------------------
    try:
        screening = get_screener().screen(addr)
    except StaleListError as exc:
        logger.error("Sanctions list stale; refusing to screen: %s", exc)
        return jsonify({
            "error": "Sanctions screening unavailable",
            "detail": "The OFAC list could not be freshly verified, so this "
                      "request cannot be completed. This is a deliberate "
                      "fail-closed behaviour.",
        }), 503
    except ListUnavailableError as exc:
        logger.error("Sanctions list unavailable; refusing to screen: %s", exc)
        return jsonify({
            "error": "Sanctions screening unavailable",
            "detail": "No OFAC list could be obtained, so this request "
                      "cannot be completed.",
        }), 503

    # -- position read ---------------------------------------------------
    try:
        client = get_client()
        pos = client.get_wallet_position(addr)
        features = extract_features(pos)
    except Exception as exc:
        logger.exception("Failed to read position for %s", addr)
        return jsonify({"error": "Upstream read failed",
                        "detail": str(exc)[:200]}), 502

    return jsonify({
        "wallet": addr,
        "block_number": pos.block_number,
        "sanctions": {
            "is_sanctioned": screening.is_sanctioned,
            "list_age_hours": screening.list_age_hours,
            "source": screening.list_source,
        },
        "features": features.to_dict(),
        "markets": [
            {
                "symbol": m.symbol,
                "supplied": m.supplied_underlying,
                "borrowed": m.borrowed_underlying,
                "collateral_usd": m.collateral_usd,
                "debt_usd": m.debt_usd,
                "collateral_factor": m.collateral_factor,
            }
            for m in pos.markets
        ],
        "disclaimer": "Point-in-time solvency only. Not a credit score. "
                      "Sanctions screening is necessary but not sufficient; "
                      "see COMPLIANCE.md.",
    }), 200


@app.errorhandler(404)
def not_found(_):
    return jsonify({"error": "Endpoint not found"}), 404


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
