"""
src/api/server.py - HTTP interface to SCORE.

SCOPE: this service computes point-in-time SOLVENCY features from live
on-chain position data. It does NOT estimate probability of default,
loss given default, or any modelled quantity. No model has been trained.
Endpoints report only what is measured.
"""

import logging

from flask import Flask, jsonify
from flask_cors import CORS
from web3 import Web3

import base.config as config
from base.rpc import BaseRPCClient
from scoring.features import extract_features

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

_client = None


def get_client() -> BaseRPCClient:
    """Lazily construct the RPC client so market metadata is fetched once."""
    global _client
    if _client is None:
        _client = BaseRPCClient()
    return _client


@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "ok",
        "service": "SCORE",
        "version": "0.2.0",
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

    Returns measured on-chain quantities only. No risk score is returned
    because no model exists to produce one.
    """
    try:
        addr = Web3.to_checksum_address(wallet_address)
    except Exception:
        return jsonify({"error": "Invalid wallet address"}), 400

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
        "disclaimer": "Point-in-time solvency only. Not a credit score.",
    }), 200


@app.errorhandler(404)
def not_found(_):
    return jsonify({"error": "Endpoint not found"}), 404


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)