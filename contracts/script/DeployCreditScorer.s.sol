// SPDX-License-Identifier: MIT
pragma solidity ^0.8.25;

// forge script contracts/script/DeployCreditScorer.s.sol \
//     --rpc-url <base-mainnet-or-sepolia-url> \
//     --private-key <deployer-key> \
//     --broadcast --verify
//
// DEPLOYER_PRIVATE_KEY is read from the environment, never hardcoded or
// committed - same posture as BASE_RPC_URL in .env for the read path.
// This script deploys and does nothing else: no scoring, no post-deploy
// configuration. The deployer becomes `scorer` per the constructor, and
// there is currently no way to change that after deployment (see
// docs/PHASE_0.md open question 3 - a deliberate, still-open decision, not
// an oversight).

import {Script, console} from "forge-std/Script.sol";
import {CreditScorer} from "../src/CreditScorer.sol";

contract DeployCreditScorer is Script {
    function run() external returns (CreditScorer) {
        uint256 deployerKey = vm.envUint("DEPLOYER_PRIVATE_KEY");
        address deployer = vm.addr(deployerKey);

        vm.startBroadcast(deployerKey);
        CreditScorer creditScorer = new CreditScorer();
        vm.stopBroadcast();

        console.log("CreditScorer deployed at:", address(creditScorer));
        console.log("scorer (deployer):        ", deployer);
        require(creditScorer.scorer() == deployer, "scorer mismatch post-deploy");

        return creditScorer;
    }
}
