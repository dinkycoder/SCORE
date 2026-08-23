// SPDX-License-Identifier: MIT
pragma solidity ^0.8.25;

contract CreditScorer {
    struct Score {
        uint256 pd;
        uint256 lgd;
        uint256 ead;
        uint256 creditScore;
        uint256 timestamp;
        uint256 modelVersion;
    }

    mapping(address => Score) public scores;
    address public scorer;

    // Counts updateScore CALLS, not distinct wallets scored - re-scoring an
    // already-scored wallet increments this again. There is no cheap way to
    // track distinct wallets in a plain mapping without an extra "have we
    // seen this address" set, which this contract does not keep.
    uint256 public scoreCount;

    event ScoreUpdated(
        address indexed wallet,
        uint256 creditScore,
        uint256 timestamp
    );

    modifier onlyScorer() {
        require(msg.sender == scorer, "Only scorer can update scores");
        _;
    }

    constructor() {
        scorer = msg.sender;
    }

    function updateScore(
        address wallet,
        uint256 pd,
        uint256 lgd,
        uint256 ead,
        uint256 creditScore
    ) external onlyScorer {
        require(wallet != address(0), "Invalid wallet address");
        scores[wallet] = Score(pd, lgd, ead, creditScore, block.timestamp, 1);
        scoreCount++;
        emit ScoreUpdated(wallet, creditScore, block.timestamp);
    }

    function getScore(address wallet) external view returns (Score memory) {
        return scores[wallet];
    }
}
