// SPDX-License-Identifier: MIT
pragma solidity ^0.8.25;

contract CreditScorer {
    // All USD-denominated fields (ead here; pd/lgd/creditScore once a real
    // model exists) are WAD-scaled (1e18), matching the convention used
    // throughout the off-chain pipeline (see src/base/config.py: WAD).
    //
    // modelVersion == 0 means no trained model has scored this wallet - ead
    // may still be real (written by updateExposure), but pd/lgd/creditScore
    // are not computed values, just the zero default, and must not be read
    // as "scored at zero risk." modelVersion >= 1 means a real model wrote
    // this via updateScore. timestamp == 0 means the wallet has never been
    // written at all - the only way to tell "never touched" apart from
    // "exposure-only, no model yet" (both have modelVersion == 0).
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

    // Deliberately distinct from ScoreUpdated: a subscriber watching for a
    // real computed score must never see an EAD-only write and mistake its
    // creditScore=0 default for a model's actual output.
    event ExposureUpdated(
        address indexed wallet,
        uint256 ead,
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

    /// Writes only the measured exposure component for a wallet - no PD/LGD
    /// model exists yet (see README/COMPLIANCE.md). pd, lgd, and creditScore
    /// are left at their zero default and modelVersion stays 0, so this can
    /// never be confused with a real updateScore write. Once a model exists,
    /// updateScore fully overwrites whatever this wrote (see
    /// test_UpdateScoreAfterUpdateExposureUpgradesToRealModel).
    function updateExposure(address wallet, uint256 ead) external onlyScorer {
        require(wallet != address(0), "Invalid wallet address");
        scores[wallet] = Score(0, 0, ead, 0, block.timestamp, 0);
        scoreCount++;
        emit ExposureUpdated(wallet, ead, block.timestamp);
    }

    function getScore(address wallet) external view returns (Score memory) {
        return scores[wallet];
    }
}
