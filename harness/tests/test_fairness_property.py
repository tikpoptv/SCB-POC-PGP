"""Property-based test for the fairness invariant (Property 13)."""

from __future__ import annotations

from dataclasses import replace

from hypothesis import given, settings
from hypothesis import strategies as st

from harness.contract import CryptoProfile, OutputEncoding, RunnerId
from harness.fairness import FairnessDimensions, RunDescriptor, check_fairness
from harness.scheduler import ResourceQuota

# Smart generators — constrain to the real fairness input space.
_checksums = st.builds(
    lambda hexpart: "sha256:" + hexpart,
    st.text(alphabet="0123456789abcdef", min_size=8, max_size=64),
)
_pub_algs = st.sampled_from(["RSA-2048", "RSA-3072", "RSA-4096", "ECC-P256"])
_ciphers = st.sampled_from(["AES-128", "AES-192", "AES-256", "ChaCha20"])
_compressions = st.sampled_from(["NONE", "ZIP", "ZLIB", "BZIP2"])
_hashes = st.sampled_from(["SHA-256", "SHA-384", "SHA-512"])
_concurrencies = st.integers(min_value=1, max_value=64)
_encodings = st.sampled_from(list(OutputEncoding))
_accels = st.booleans()
_cpu_cores = st.integers(min_value=1, max_value=64)
_memory_mb = st.integers(min_value=256, max_value=65536)

_crypto_profiles = st.builds(
    CryptoProfile,
    pub_alg=_pub_algs,
    cipher=_ciphers,
    compression=_compressions,
    hash=_hashes,
)
_quotas = st.builds(ResourceQuota, cpu_cores=_cpu_cores, memory_mb=_memory_mb)

_dimensions = st.builds(
    FairnessDimensions,
    key_set_checksum=_checksums,
    corpus_checksum=_checksums,
    crypto_profile=_crypto_profiles,
    concurrency=_concurrencies,
    output_encoding=_encodings,
    hardware_accel=_accels,
    resource_quota=_quotas,
)

# Runner/variant labels for the generated runs (one Go + one Java is the real
# head-to-head shape; extra variants exercise N>2).
_VARIANTS = (
    (RunnerId.GO, "go-stream-parallel"),
    (RunnerId.JAVA, "java-stream-parallel"),
    (RunnerId.GO, "go-inmem-single"),
    (RunnerId.JAVA, "java-inmem-single"),
)


def _runs(dims_list: list[FairnessDimensions]) -> list[RunDescriptor]:
    """Build one RunDescriptor per dimension set, cycling runner/variant tags."""
    runs: list[RunDescriptor] = []
    for i, dims in enumerate(dims_list):
        runner_id, variant_id = _VARIANTS[i % len(_VARIANTS)]
        # Keep variant ids unique even past the cycle length.
        if i >= len(_VARIANTS):
            variant_id = f"{variant_id}-{i}"
        runs.append(
            RunDescriptor(
                runner_id=runner_id, variant_id=variant_id, dimensions=dims
            )
        )
    return runs


# Perturbation registry — one entry per comparability-critical dimension.
# Each returns a strategy producing (perturbed_dimensions, reason_fragment) that
# differs from ``base`` on exactly that one dimension.
def _perturb_strategies(base: FairnessDimensions):
    cp = base.crypto_profile
    rq = base.resource_quota
    return st.one_of(
        _checksums.filter(lambda v: v != base.key_set_checksum).map(
            lambda v: (replace(base, key_set_checksum=v), "keySetChecksum mismatch")
        ),
        _checksums.filter(lambda v: v != base.corpus_checksum).map(
            lambda v: (replace(base, corpus_checksum=v), "corpusChecksum mismatch")
        ),
        _pub_algs.filter(lambda v: v != cp.pub_alg).map(
            lambda v: (
                replace(base, crypto_profile=replace(cp, pub_alg=v)),
                "cryptoProfile.pubAlg mismatch",
            )
        ),
        _ciphers.filter(lambda v: v != cp.cipher).map(
            lambda v: (
                replace(base, crypto_profile=replace(cp, cipher=v)),
                "cryptoProfile.cipher mismatch",
            )
        ),
        _compressions.filter(lambda v: v != cp.compression).map(
            lambda v: (
                replace(base, crypto_profile=replace(cp, compression=v)),
                "cryptoProfile.compression mismatch",
            )
        ),
        _hashes.filter(lambda v: v != cp.hash).map(
            lambda v: (
                replace(base, crypto_profile=replace(cp, hash=v)),
                "cryptoProfile.hash mismatch",
            )
        ),
        _concurrencies.filter(lambda v: v != base.concurrency).map(
            lambda v: (replace(base, concurrency=v), "concurrency mismatch")
        ),
        st.sampled_from(list(OutputEncoding))
        .filter(lambda v: v != base.output_encoding)
        .map(lambda v: (replace(base, output_encoding=v), "outputEncoding mismatch")),
        st.just(not base.hardware_accel).map(
            lambda v: (replace(base, hardware_accel=v), "hardwareAccel mismatch")
        ),
        _cpu_cores.filter(lambda v: v != rq.cpu_cores).map(
            lambda v: (
                replace(base, resource_quota=replace(rq, cpu_cores=v)),
                "resourceQuota mismatch",
            )
        ),
        _memory_mb.filter(lambda v: v != rq.memory_mb).map(
            lambda v: (
                replace(base, resource_quota=replace(rq, memory_mb=v)),
                "resourceQuota mismatch",
            )
        ),
    )


# Feature: pgp-encryption-benchmark-go-java, Property 13: Invariant ของความยุติธรรม (shared inputs & equal config)
@settings(max_examples=150, deadline=None)
@given(shared=_dimensions, n=st.integers(min_value=2, max_value=4))
def test_all_runs_share_dimensions_is_comparable(
    shared: FairnessDimensions, n: int
) -> None:
    runs = _runs([shared] * n)
    result = check_fairness("scenario", runs)

    assert result.comparable is True
    assert result.non_comparable_reasons == ()
    assert all(r.comparable for r in result.runs)
    assert len(result.comparable_runs) == n
    assert result.excluded_runs == ()


# Feature: pgp-encryption-benchmark-go-java, Property 13: Invariant ของความยุติธรรม (shared inputs & equal config)
@settings(max_examples=150, deadline=None)
@given(shared=_dimensions, n=st.integers(min_value=2, max_value=4), data=st.data())
def test_perturbing_one_dimension_excludes_only_that_run(
    shared: FairnessDimensions, n: int, data: st.DataObject
) -> None:
    # Run 0 is the implicit reference (shared); perturb exactly one later run.
    perturb_index = data.draw(
        st.integers(min_value=1, max_value=n - 1), label="perturb_index"
    )
    perturbed_dims, fragment = data.draw(
        _perturb_strategies(shared), label="perturbation"
    )

    dims_list = [shared] * n
    dims_list[perturb_index] = perturbed_dims
    runs = _runs(dims_list)
    result = check_fairness("scenario", runs)

    # The Scenario is non-comparable and names the perturbed dimension.
    assert result.comparable is False
    assert any(fragment in reason for reason in result.non_comparable_reasons)

    # Exactly the perturbed run is excluded; it carries the naming reason.
    excluded = result.excluded_runs
    assert len(excluded) == 1
    offender = excluded[0]
    assert offender.comparable is False
    assert any(fragment in reason for reason in offender.non_comparable_reasons)
    assert offender.variant_id == runs[perturb_index].variant_id

    # Every other run remains comparable and kept for the conclusion.
    assert len(result.comparable_runs) == n - 1
    for i, run_verdict in enumerate(result.runs):
        if i != perturb_index:
            assert run_verdict.comparable is True
