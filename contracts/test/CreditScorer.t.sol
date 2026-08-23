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
}
