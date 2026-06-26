"""Property-based test for non-comparable marking & exclusion (Property 18)."""

from hypothesis import given, settings
from hypothesis import strategies as st

from harness.contract import CryptoProfile, OutputEncoding, RunnerId
from harness.fairness import (
    FairnessDimensions,
    RunDescriptor,
    check_fairness,
)
from harness.scheduler import ResourceQuota

# Realistic prior non-comparable reason strings, one per propagated anomaly.
_PRIOR_REASONS: tuple[str, ...] = (
    "runner version mismatch: go 1.22 vs recorded 1.21 (Req 2.5)",
    "environment changed mid-set: vcpu count 8 -> 4 (Req 3.5)",
    "unsupported crypto profile: pubAlg 'Ed25519' not offered by Java (Req 4.4)",
    "resource sampling failed: no samples captured for this run (Req 7.7)",
    "unsupported key type/size: 'RSA-1024' below policy floor (Req 14.5)",
    "unsupported cipher 'ChaCha20' for this runner (Req 18.5)",
    "interop failure: Go ciphertext rejected by Java decrypt (Req 25.5)",
    "thermal throttling detected during run (Req 27.6)",
    "hardware-accel disagreement vs peer runner (Req 23.4)",
)

# Identical dimensions shared by every run, so a dimension mismatch can never
# be the reason a run is excluded — the prior reason is the only driver.
_SHARED_DIMENSIONS = FairnessDimensions(
    key_set_checksum="sha256:" + "ab" * 32,
    corpus_checksum="sha256:" + "cd" * 32,
    crypto_profile=CryptoProfile(
        pub_alg="RSA-2048", cipher="AES-256", compression="ZLIB", hash="SHA-256"
    ),
    concurrency=4,
    output_encoding=OutputEncoding.BINARY,
    hardware_accel=True,
    resource_quota=ResourceQuota(cpu_cores=8, memory_mb=3072),
)

# A run = a runner id + a (possibly empty) subset of distinct prior reasons.
_RUN = st.tuples(
    st.sampled_from(list(RunnerId)),
    st.lists(st.sampled_from(_PRIOR_REASONS), max_size=len(_PRIOR_REASONS), unique=True),
)

# A scenario = a non-empty list of such runs.
_RUNS = st.lists(_RUN, min_size=1, max_size=6)


# Feature: pgp-encryption-benchmark-go-java, Property 18: การ mark non-comparable และกันออกจากข้อสรุป
@settings(max_examples=200, deadline=None)
@given(spec=_RUNS)
def test_runs_with_prior_reasons_are_marked_non_comparable_and_excluded(spec):
    descriptors = [
        RunDescriptor(
            runner_id=runner_id,
            variant_id=f"variant-{i}",
            dimensions=_SHARED_DIMENSIONS,
            prior_non_comparable_reasons=tuple(priors),
        )
        for i, (runner_id, priors) in enumerate(spec)
    ]

    result = check_fairness("scenario-prop18", descriptors)

    # The verdicts cover exactly the runs we supplied, in order.
    assert len(result.runs) == len(descriptors)

    any_prior = any(priors for _, priors in spec)

    # Scenario-level: comparable IFF no run carries any prior reason.
    assert result.comparable is (not any_prior)
    # Every distinct prior reason surfaces at the Scenario level.
    expected_scenario_reasons = {r for _, priors in spec for r in priors}
    assert expected_scenario_reasons.issubset(set(result.non_comparable_reasons))

    excluded = set(result.excluded_runs)
    comparable = set(result.comparable_runs)

    for verdict, descriptor in zip(result.runs, descriptors):
        priors = descriptor.prior_non_comparable_reasons
        if priors:
            # A run with prior reason(s) is non-comparable, excluded from the
            assert verdict.comparable is False
            assert verdict in excluded
            assert verdict not in comparable
            # Each prior reason is surfaced on the run's own verdict.
            for reason in priors:
                assert reason in verdict.non_comparable_reasons
        else:
            # A clean run (identical dimensions, no prior) stays comparable.
            assert verdict.comparable is True
            assert verdict in comparable
            assert verdict not in excluded

    # comparable_runs and excluded_runs partition the runs with no overlap.
    assert comparable.isdisjoint(excluded)
    assert len(result.comparable_runs) + len(result.excluded_runs) == len(result.runs)
