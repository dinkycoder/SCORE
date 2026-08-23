"""
tests/test_onchain_writer.py - writes exposure to CreditScorer on-chain.

Split the same way as the rest of this suite:
  - offline tests: pure logic, no network, always run.
  - anvil-marked tests: spin up a local anvil chain and deploy for real via
    the actual DeployCreditScorer.s.sol script (exercising the deployment
    script itself, not just the writer), then round-trip a write through
    it. Skipped automatically if Foundry isn't installed - no real network,
    no real funds, ever touched by these.
"""

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from onchain.writer import ScoreWriter, ScorerNotConfiguredError, usd_to_wad

# -- Foundry discovery ------------------------------------------------------
# foundryup installs to ~/.foundry/bin, which is not reliably on PATH yet in
# every shell (see scripts/README.md) - check both.

_FOUNDRY_BIN_DIR = Path.home() / ".foundry" / "bin"


def _find_binary(name: str):
    found = shutil.which(name)
    if found:
        return found
    for candidate in (_FOUNDRY_BIN_DIR / (name + ".exe"), _FOUNDRY_BIN_DIR / name):
        if candidate.exists():
            return str(candidate)
    return None


ANVIL_BIN = _find_binary("anvil")
FORGE_BIN = _find_binary("forge")

requires_foundry = pytest.mark.skipif(
    not (ANVIL_BIN and FORGE_BIN),
    reason="Foundry (anvil/forge) not installed - install via foundryup to "
           "run these tests",
)

# Anvil's well-known default test accounts (mnemonic "test test test ...
# junk"). Verified against a running anvil instance's own printed startup
# banner and eth_accounts, 2026-08-22 - zero real value, safe to hardcode.
ANVIL_DEPLOYER_KEY = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
ANVIL_OTHER_KEY = "0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d"
ANVIL_OTHER_ADDRESS = "0x70997970C51812dc3A010C7d01b50e0d17dc79C8"

ANVIL_PORT = 8555  # distinct from a developer's own manual anvil session


# -- offline: pure logic, no network -----------------------------------------

def test_usd_to_wad_scales_to_1e18():
    assert usd_to_wad(1.0) == 10 ** 18
    assert usd_to_wad(12_345.67) == round(12_345.67 * 10 ** 18)


def test_usd_to_wad_handles_zero():
    assert usd_to_wad(0.0) == 0


def test_raises_when_not_configured(monkeypatch):
    """Writing must fail loud without a deployed address and a signing key
    - reading (get_wallet_position, extract_features) needs neither, and
    must never be blocked by this."""
    monkeypatch.setattr("onchain.writer.config.CREDIT_SCORER_ADDRESS", None)
    monkeypatch.setattr("onchain.writer.config.SCORER_PRIVATE_KEY", None)
    with pytest.raises(ScorerNotConfiguredError):
        ScoreWriter()


# -- anvil: a real (local, zero-value) chain ---------------------------------

def _wait_for_anvil(rpc_url: str, timeout: float = 10.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = requests.post(rpc_url, json={"jsonrpc": "2.0", "id": 1,
                                              "method": "eth_chainId",
                                              "params": []}, timeout=1)
            if r.status_code == 200:
                return
        except requests.RequestException:
            pass
        time.sleep(0.2)
    raise RuntimeError("anvil did not become ready at " + rpc_url)


@pytest.fixture(scope="module")
def anvil_rpc_url():
    if not ANVIL_BIN:
        pytest.skip("anvil not installed")
    proc = subprocess.Popen(
        [ANVIL_BIN, "--port", str(ANVIL_PORT), "--silent"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    rpc_url = "http://127.0.0.1:" + str(ANVIL_PORT)
    try:
        _wait_for_anvil(rpc_url)
        yield rpc_url
    finally:
        proc.terminate()
        proc.wait(timeout=10)


@pytest.fixture
def deployed_credit_scorer(anvil_rpc_url):
    """Deploys via the real forge script - this is also a live integration
    test of contracts/script/DeployCreditScorer.s.sol, not just the writer.
    Returns the deployed contract address."""
    contracts_dir = Path(__file__).resolve().parents[1] / "contracts"
    env = dict(os.environ, DEPLOYER_PRIVATE_KEY=ANVIL_DEPLOYER_KEY)
    result = subprocess.run(
        [FORGE_BIN, "script", "script/DeployCreditScorer.s.sol",
         "--rpc-url", anvil_rpc_url, "--broadcast"],
        cwd=str(contracts_dir), env=env,
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr

    for line in result.stdout.splitlines():
        if "CreditScorer deployed at:" in line:
            return line.split(":", 1)[1].strip()
    raise RuntimeError("deployed address not found in forge script output:\n"
                       + result.stdout)


@requires_foundry
@pytest.mark.anvil
def test_write_exposure_round_trips(deployed_credit_scorer, anvil_rpc_url):
    from web3 import Web3
    from onchain.writer import CREDIT_SCORER_ABI

    w3 = Web3(Web3.HTTPProvider(anvil_rpc_url))
    writer = ScoreWriter(w3=w3, contract_address=deployed_credit_scorer,
                         private_key=ANVIL_DEPLOYER_KEY)

    result = writer.write_exposure(ANVIL_OTHER_ADDRESS, 12_345.67)

    assert result.wallet == Web3.to_checksum_address(ANVIL_OTHER_ADDRESS)
    assert result.ead_wad == usd_to_wad(12_345.67)

    contract = w3.eth.contract(
        address=Web3.to_checksum_address(deployed_credit_scorer),
        abi=CREDIT_SCORER_ABI)
    score = contract.functions.getScore(ANVIL_OTHER_ADDRESS).call()
    pd, lgd, ead, credit_score, timestamp, model_version = score

    assert ead == usd_to_wad(12_345.67)
    assert pd == 0 and lgd == 0 and credit_score == 0
    assert model_version == 0, "EAD-only write must not claim a real model"
    assert timestamp > 0


@requires_foundry
@pytest.mark.anvil
def test_write_exposure_reverts_for_non_scorer_key(deployed_credit_scorer, anvil_rpc_url):
    """The deployed contract's scorer is the deployer key
    (ANVIL_DEPLOYER_KEY). Signing with a different key must revert on-chain,
    and the writer must surface that as a raised error, not a silent
    no-op."""
    from web3 import Web3

    w3 = Web3(Web3.HTTPProvider(anvil_rpc_url))
    writer = ScoreWriter(w3=w3, contract_address=deployed_credit_scorer,
                         private_key=ANVIL_OTHER_KEY)

    with pytest.raises(Exception):
        writer.write_exposure(ANVIL_OTHER_ADDRESS, 1.0)
