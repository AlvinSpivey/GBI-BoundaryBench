"""Consensus fault injection, Appendix B.1 Systems Validation item 2.

    "Simulate network partition and validator crash faults to test the liveness and
    safety invariants of the non-equivocating Byzantine state logs. For any selected
    BFT protocol, test the protocol-specific resilience and quorum conditions. Under
    the usual classical 3f+1 model, tolerating f Byzantine faults requires the active
    replica population to satisfy n >= 3f+1; falling below the required threshold must
    halt authoritative writes."

The selected protocol is classical PBFT-style commit: a value commits when it
collects a quorum of 2f+1 matching votes from a population of n replicas.

The analysis here is **exact and exhaustive**, not sampled. For a given
(n, f, actual Byzantine count, crashed, partitioned) it enumerates every possible
split of correct replicas between two conflicting values and reports whether both
can reach quorum. That makes the safety statement a proof over the model rather
than the absence of a counterexample in a random search.

Two results matter and the second is the one that makes the first meaningful:

* with at most f Byzantine faults, no split admits two commits (safety holds);
* with f+1, a split does exist (the bound is **tight**).

A model that reported safety for f+1 faults would be wrong, and a suite that never
checked f+1 could not tell the difference.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

CONSENSUS_VERSION = "dcse-consensus-v3.0"


def required_replicas(f: int) -> int:
    """Classical 3f+1."""

    return 3 * f + 1


def quorum_size(f: int) -> int:
    """Classical PBFT commit quorum, 2f+1."""

    return 2 * f + 1


@dataclass(frozen=True)
class RoundConfig:
    n: int
    f_declared: int
    byzantine: int
    crashed: int = 0
    partitioned: int = 0

    @property
    def correct_and_reachable(self) -> int:
        """Correct replicas whose votes are actually delivered."""

        return max(0, self.n - self.byzantine - self.crashed - self.partitioned)


def analyse_round(config: RoundConfig) -> dict[str, Any]:
    """Exhaustive safety and liveness analysis for one round configuration.

    Byzantine replicas are assumed maximally adversarial: they equivocate, voting
    for every candidate value simultaneously. Crashed and partitioned replicas
    contribute no votes.
    """

    n, f = config.n, config.f_declared
    quorum = quorum_size(f)
    required = required_replicas(f)
    threshold_met = n >= required

    voters = config.correct_and_reachable
    byz = config.byzantine

    # Safety: enumerate every split of reachable correct replicas across two
    # conflicting values. Byzantine votes are added to both.
    unsafe_splits: list[dict[str, int]] = []
    for left in range(voters + 1):
        right = voters - left
        if left + byz >= quorum and right + byz >= quorum:
            unsafe_splits.append({"votes_for_v1": left + byz, "votes_for_v2": right + byz})
    safety_holds = not unsafe_splits

    # Liveness: an honest primary, all reachable correct replicas voting for one
    # value, Byzantine replicas withholding (the worst case for progress).
    liveness_votes = voters
    liveness = liveness_votes >= quorum

    return {
        "n": n,
        "f_declared": f,
        "required_replicas_3f_plus_1": required,
        "quorum_2f_plus_1": quorum,
        "threshold_met": threshold_met,
        "byzantine": byz,
        "crashed": config.crashed,
        "partitioned": config.partitioned,
        "reachable_correct_replicas": voters,
        "safety_holds": safety_holds,
        "unsafe_split_count": len(unsafe_splits),
        "example_unsafe_split": unsafe_splits[0] if unsafe_splits else None,
        "liveness_votes_available": liveness_votes,
        "liveness_holds": liveness,
        # Fail-closed rule from B.1: below threshold, halt regardless of votes.
        "authoritative_writes_permitted": bool(threshold_met and safety_holds and liveness),
        "halt_reason": (
            None
            if threshold_met and safety_holds and liveness
            else (
                "replica_population_below_3f_plus_1"
                if not threshold_met
                else "safety_invariant_at_risk"
                if not safety_holds
                else "insufficient_votes_for_quorum"
            )
        ),
    }


def run_consensus_suite(max_f: int = 4) -> dict[str, Any]:
    """The full fault-injection sweep, plus the tightness demonstration."""

    within_tolerance: list[dict[str, Any]] = []
    beyond_tolerance: list[dict[str, Any]] = []
    below_threshold: list[dict[str, Any]] = []
    crash_liveness: list[dict[str, Any]] = []
    partition_liveness: list[dict[str, Any]] = []

    for f in range(1, max_f + 1):
        n = required_replicas(f)
        # Safety at or below the declared tolerance.
        for byzantine in range(0, f + 1):
            within_tolerance.append(analyse_round(RoundConfig(n=n, f_declared=f, byzantine=byzantine)))
        # Safety beyond the declared tolerance: must be violable, or the bound is
        # not tight and the model is not modelling anything.
        beyond_tolerance.append(
            analyse_round(RoundConfig(n=n, f_declared=f, byzantine=f + 1))
        )
        # Replica population below 3f+1: must halt.
        for deficit in (1, 2):
            below_threshold.append(
                analyse_round(RoundConfig(n=n - deficit, f_declared=f, byzantine=0))
            )
        # Crash faults: progress up to f crashes, halt beyond.
        for crashed in range(0, f + 2):
            crash_liveness.append(
                analyse_round(RoundConfig(n=n, f_declared=f, byzantine=0, crashed=crashed))
            )
        # Network partition isolating k correct replicas.
        for partitioned in range(0, f + 2):
            partition_liveness.append(
                analyse_round(
                    RoundConfig(n=n, f_declared=f, byzantine=0, partitioned=partitioned)
                )
            )

    safety_within = all(row["safety_holds"] for row in within_tolerance)
    tight = all(not row["safety_holds"] for row in beyond_tolerance)
    halts_below = all(
        row["authoritative_writes_permitted"] is False
        and row["halt_reason"] == "replica_population_below_3f_plus_1"
        for row in below_threshold
    )
    crash_progress = all(
        row["liveness_holds"]
        for row in crash_liveness
        if row["crashed"] <= row["f_declared"]
    )
    crash_halts = all(
        not row["liveness_holds"]
        for row in crash_liveness
        if row["crashed"] > row["f_declared"]
    )
    partition_progress = all(
        row["liveness_holds"]
        for row in partition_liveness
        if row["partitioned"] <= row["f_declared"]
    )
    partition_halts = all(
        not row["liveness_holds"]
        for row in partition_liveness
        if row["partitioned"] > row["f_declared"]
    )
    # A halted round must never permit an authoritative write.
    no_write_when_halted = all(
        row["authoritative_writes_permitted"] is False
        for row in crash_liveness + partition_liveness + beyond_tolerance + below_threshold
        if not (row["safety_holds"] and row["liveness_holds"] and row["threshold_met"])
    )

    return {
        "schema_version": "boundarybench.dcse_consensus_suite.v1",
        "consensus_version": CONSENSUS_VERSION,
        "protocol": "classical PBFT-style commit, quorum 2f+1 of n >= 3f+1",
        "analysis_method": "exhaustive enumeration of correct-replica splits, not sampling",
        "configurations_analysed": (
            len(within_tolerance)
            + len(beyond_tolerance)
            + len(below_threshold)
            + len(crash_liveness)
            + len(partition_liveness)
        ),
        "safety_within_tolerance": {
            "configurations": len(within_tolerance),
            "all_safe": safety_within,
        },
        "bound_is_tight": {
            "configurations": len(beyond_tolerance),
            "all_violable_at_f_plus_1": tight,
            "example": beyond_tolerance[0] if beyond_tolerance else None,
        },
        "below_threshold_halts": {
            "configurations": len(below_threshold),
            "all_halt_with_correct_reason": halts_below,
        },
        "crash_faults": {
            "configurations": len(crash_liveness),
            "progress_up_to_f": crash_progress,
            "halts_beyond_f": crash_halts,
        },
        "network_partition": {
            "configurations": len(partition_liveness),
            "progress_up_to_f": partition_progress,
            "halts_beyond_f": partition_halts,
        },
        "never_writes_when_halted": no_write_when_halted,
        "all_invariants_hold": bool(
            safety_within
            and tight
            and halts_below
            and crash_progress
            and crash_halts
            and partition_progress
            and partition_halts
            and no_write_when_halted
        ),
        "scope": (
            "An analytical model of the quorum condition, exhaustive over the model's "
            "state space. It is not a running BFT cluster, contains no network stack, "
            "and makes no latency or throughput claim."
        ),
    }
