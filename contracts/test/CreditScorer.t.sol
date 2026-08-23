// SPDX-License-Identifier: MIT
pragma solidity ^0.8.25;

import {Test} from "forge-std/Test.sol";
import {CreditScorer} from "../src/CreditScorer.sol";

contract CreditScorerTest is Test {
    CreditScorer internal creditScorer;
    address internal deployer = address(this);
    address internal wallet = address(0xBEEF);
    address internal stranger = address(0xDEAD);

    event ScoreUpdated(address indexed wallet, uint256 creditScore, uint256 timestamp);
    event ExposureUpdated(address indexed wallet, uint256 ead, uint256 timestamp);

    function setUp() public {
        creditScorer = new CreditScorer();
    }

    // -- constructor ----------------------------------------------------------

    function test_ConstructorSetsScorerToDeployer() public view {
        assertEq(creditScorer.scorer(), deployer);
    }

    function test_ConstructorScoreCountStartsAtZero() public view {
        assertEq(creditScorer.scoreCount(), 0);
    }

    // -- updateScore: happy path -----------------------------------------------

    function test_UpdateScoreStoresAllFields() public {
        creditScorer.updateScore(wallet, 100, 200, 300, 750);

        CreditScorer.Score memory score = creditScorer.getScore(wallet);
        assertEq(score.pd, 100);
        assertEq(score.lgd, 200);
        assertEq(score.ead, 300);
        assertEq(score.creditScore, 750);
        assertEq(score.timestamp, block.timestamp);
    }

    function test_ModelVersionIsHardcodedToOne() public {
        // Not a bug - just undocumented state. There is no way to write any
        // modelVersion other than 1, and no reader of this field can tell a
        // real second model version from a decode error. Locked in as a
        // regression guard so a future model-version change is a deliberate
        // decision, not an accidental silent one.
        creditScorer.updateScore(wallet, 1, 2, 3, 4);
        assertEq(creditScorer.getScore(wallet).modelVersion, 1);
    }

    function test_UpdateScoreIncrementsScoreCount() public {
        assertEq(creditScorer.scoreCount(), 0);
        creditScorer.updateScore(wallet, 1, 2, 3, 4);
        assertEq(creditScorer.scoreCount(), 1);
        creditScorer.updateScore(stranger, 5, 6, 7, 8);
        assertEq(creditScorer.scoreCount(), 2);
    }

    function test_UpdateScoreEmitsScoreUpdated() public {
        vm.expectEmit(true, false, false, true, address(creditScorer));
        emit ScoreUpdated(wallet, 750, block.timestamp);
        creditScorer.updateScore(wallet, 100, 200, 300, 750);
    }

    function test_MultipleWalletsScoredIndependently() public {
        creditScorer.updateScore(wallet, 1, 2, 3, 4);
        creditScorer.updateScore(stranger, 10, 20, 30, 40);

        CreditScorer.Score memory a = creditScorer.getScore(wallet);
        CreditScorer.Score memory b = creditScorer.getScore(stranger);

        assertEq(a.creditScore, 4);
        assertEq(b.creditScore, 40);
    }

    // -- re-scoring: an existing wallet, not a new one -------------------------

    function test_RescoringSameWalletOverwritesPreviousValues() public {
        creditScorer.updateScore(wallet, 1, 2, 3, 100);
        creditScorer.updateScore(wallet, 9, 9, 9, 999);

        assertEq(creditScorer.getScore(wallet).creditScore, 999);
    }

    function test_RescoringSameWalletStillIncrementsScoreCount() public {
        // scoreCount counts UPDATE CALLS, not distinct wallets scored - the
        // contract has no notion of "have we seen this wallet before." A
        // reader of this field expecting "how many wallets have a score"
        // will get the wrong number the moment any wallet is re-scored.
        // Locked in as a regression guard, not silently assumed, since nothing
        // in the contract documents which of the two scoreCount actually is.
        creditScorer.updateScore(wallet, 1, 2, 3, 4);
        creditScorer.updateScore(wallet, 5, 6, 7, 8);

        assertEq(creditScorer.scoreCount(), 2);
    }

    // -- access control ---------------------------------------------------------

    function test_UpdateScoreRevertsForNonScorer() public {
        vm.prank(stranger);
        vm.expectRevert("Only scorer can update scores");
        creditScorer.updateScore(wallet, 1, 2, 3, 4);
    }

    function testFuzz_UpdateScoreRevertsForAnyNonScorerCaller(address caller) public {
        vm.assume(caller != deployer);
        vm.prank(caller);
        vm.expectRevert("Only scorer can update scores");
        creditScorer.updateScore(wallet, 1, 2, 3, 4);
    }

    // -- input validation ---------------------------------------------------------

    function test_UpdateScoreRevertsForZeroAddress() public {
        vm.expectRevert("Invalid wallet address");
        creditScorer.updateScore(address(0), 1, 2, 3, 4);
    }

    // -- unscored wallets ---------------------------------------------------------

    function test_GetScoreForNeverScoredWalletReturnsZeroStruct() public view {
        CreditScorer.Score memory score = creditScorer.getScore(stranger);
        assertEq(score.pd, 0);
        assertEq(score.lgd, 0);
        assertEq(score.ead, 0);
        assertEq(score.creditScore, 0);
        assertEq(score.timestamp, 0);
        assertEq(score.modelVersion, 0);
    }

    // -- fuzz: the happy path holds for arbitrary values, not just fixed examples

    function testFuzz_UpdateScoreRoundTripsArbitraryValues(
        address fuzzWallet,
        uint256 pd,
        uint256 lgd,
        uint256 ead,
        uint256 creditScoreValue
    ) public {
        vm.assume(fuzzWallet != address(0));

        creditScorer.updateScore(fuzzWallet, pd, lgd, ead, creditScoreValue);
        CreditScorer.Score memory score = creditScorer.getScore(fuzzWallet);

        assertEq(score.pd, pd);
        assertEq(score.lgd, lgd);
        assertEq(score.ead, ead);
        assertEq(score.creditScore, creditScoreValue);
        assertEq(score.modelVersion, 1);
    }

    // -- updateExposure: EAD-only writes, no model exists yet -------------------
    //
    // No PD/LGD model has been trained (see README/COMPLIANCE.md - this project
    // does not claim a model that doesn't exist). updateExposure writes only
    // the measured solvency component and leaves pd/lgd/creditScore at 0 AND
    // modelVersion at 0, so a reader can always tell "not computed" from "a
    // real model scored this at zero risk" - the two are never the same write.

    function test_UpdateExposureStoresEadOnlyAndLeavesModelFieldsZero() public {
        creditScorer.updateExposure(wallet, 12_345);

        CreditScorer.Score memory score = creditScorer.getScore(wallet);
        assertEq(score.ead, 12_345);
        assertEq(score.pd, 0);
        assertEq(score.lgd, 0);
        assertEq(score.creditScore, 0);
        assertEq(score.modelVersion, 0);
    }

    function test_UpdateExposureSetsTimestamp() public {
        creditScorer.updateExposure(wallet, 1);
        assertEq(creditScorer.getScore(wallet).timestamp, block.timestamp);
    }

    function test_UpdateExposureTimestampDistinguishesFromNeverTouched() public view {
        // A never-touched wallet has timestamp == 0 (mapping default). Combined
        // with the case above (touched, timestamp != 0, modelVersion == 0),
        // this is how "no model yet" and "never scored at all" stay
        // distinguishable through the same struct without an extra field.
        assertEq(creditScorer.getScore(stranger).timestamp, 0);
    }

    function test_UpdateExposureIncrementsScoreCount() public {
        creditScorer.updateExposure(wallet, 1);
        assertEq(creditScorer.scoreCount(), 1);
    }

    function test_UpdateExposureEmitsExposureUpdatedNotScoreUpdated() public {
        // A distinct event, not ScoreUpdated with creditScore=0 - a subscriber
        // watching ScoreUpdated must never see an EAD-only write and mistake
        // the 0 for a real computed score.
        vm.expectEmit(true, false, false, true, address(creditScorer));
        emit ExposureUpdated(wallet, 12_345, block.timestamp);
        creditScorer.updateExposure(wallet, 12_345);
    }

    function test_UpdateExposureRevertsForNonScorer() public {
        vm.prank(stranger);
        vm.expectRevert("Only scorer can update scores");
        creditScorer.updateExposure(wallet, 1);
    }

    function test_UpdateExposureRevertsForZeroAddress() public {
        vm.expectRevert("Invalid wallet address");
        creditScorer.updateExposure(address(0), 1);
    }

    function test_UpdateScoreAfterUpdateExposureUpgradesToRealModel() public {
        // The natural lifecycle: exposure now, a real model later. Confirms
        // the later updateScore call fully overwrites the EAD-only state
        // rather than merging with it or being blocked by it.
        creditScorer.updateExposure(wallet, 12_345);
        assertEq(creditScorer.getScore(wallet).modelVersion, 0);

        creditScorer.updateScore(wallet, 100, 200, 12_345, 750);

        CreditScorer.Score memory score = creditScorer.getScore(wallet);
        assertEq(score.modelVersion, 1);
        assertEq(score.pd, 100);
        assertEq(score.creditScore, 750);
    }

    function testFuzz_UpdateExposureRoundTripsArbitraryEad(address fuzzWallet, uint256 ead) public {
        vm.assume(fuzzWallet != address(0));

        creditScorer.updateExposure(fuzzWallet, ead);
        CreditScorer.Score memory score = creditScorer.getScore(fuzzWallet);

        assertEq(score.ead, ead);
        assertEq(score.modelVersion, 0);
        assertEq(score.pd, 0);
        assertEq(score.lgd, 0);
        assertEq(score.creditScore, 0);
    }
}
