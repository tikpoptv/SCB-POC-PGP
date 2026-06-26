"""Property-based test for the alternating run order (Property 12)."""

from hypothesis import given, settings
from hypothesis import strategies as st

from harness.config import (
    BenchmarkConfig,
    CryptoProfileConfig,
    DataCompressibility,
    FileSizeTier,
    KeySpec,
    KeyType,
    MemoryMode,
    NullTestConfig,
    RunMode,
    ScenarioConfig,
)
from harness.contract import CryptoProfile, OutputEncoding, RunnerId
from harness.scheduler import DEFAULT_RUNNER_ORDER, RunScheduler, SharedInputs

_CHK = "sha256:" + "ab" * 32
_TWO_RUNNERS = {RunnerId.GO, RunnerId.JAVA}


def _scenario() -> ScenarioConfig:
    return ScenarioConfig(
        id="s1",
        file_size_tier=FileSizeTier.SMALL,
        key_spec=KeySpec(type=KeyType.RSA, bits=2048),
        concurrency=4,
        memory_mode=MemoryMode.STREAMING,
        crypto_profile_id="p1",
        data_compressibility=DataCompressibility.BOTH,
        output_encoding=OutputEncoding.BINARY,
        memory_quota_mb=2048,
    )


def _config(rounds: int) -> BenchmarkConfig:
    return BenchmarkConfig(
        rounds=rounds,
        warmup_iterations=5,
        seed=1,
        sampling_interval_ms=100,
        crypto_profiles=(
            CryptoProfileConfig(
                id="p1",
                profile=CryptoProfile(
                    pub_alg="RSA-2048",
                    cipher="AES-256",
                    compression="ZLIB",
                    hash="SHA-256",
                ),
            ),
        ),
        key_specs=(KeySpec(type=KeyType.RSA, bits=2048),),
        scenarios=(_scenario(),),
        modes=(RunMode.STEADY_STATE,),
        vcpu=8,
        null_test=NullTestConfig(),
    )


def _inputs(scenario: ScenarioConfig) -> SharedInputs:
    return SharedInputs(
        key_set_path="/tmpfs/keys",
        key_set_checksum=_CHK,
        corpus_path=f"/tmpfs/corpus/{scenario.id}",
        corpus_checksum=_CHK,
        output_dir="/tmpfs/out",
    )


def _assert_alternating(orders: list[tuple[RunnerId, ...]]) -> None:
    """Shared invariant check for a 1-based sequence of per-Round orders."""
    assert orders[0] == DEFAULT_RUNNER_ORDER == (RunnerId.GO, RunnerId.JAVA)
    for index, order in enumerate(orders):
        assert len(order) == 2
        assert set(order) == _TWO_RUNNERS
        if index > 0:
            assert order == tuple(reversed(orders[index - 1])), (
                f"round {index + 1} did not reverse round {index}"
            )


# Feature: pgp-encryption-benchmark-go-java, Property 12: ลำดับการรันสลับกันทุกรอบ
@settings(max_examples=200, deadline=None)
@given(rounds=st.integers(min_value=1, max_value=200))
def test_runner_order_alternates_for_arbitrary_round_counts(rounds: int) -> None:
    orders = [RunScheduler.runner_order(r) for r in range(1, rounds + 1)]
    _assert_alternating(orders)


# Feature: pgp-encryption-benchmark-go-java, Property 12: ลำดับการรันสลับกันทุกรอบ
@settings(max_examples=120, deadline=None)
@given(rounds=st.integers(min_value=1, max_value=200))
def test_planned_round_orders_alternate_for_arbitrary_round_counts(rounds: int) -> None:
    sched = RunScheduler(_config(rounds), _inputs)
    plan = sched.plan_set(_scenario(), RunMode.STEADY_STATE)

    assert len(plan.round_orders) == rounds
    # round_index is 1-based and strictly increasing.
    assert [ro.round_index for ro in plan.round_orders] == list(range(1, rounds + 1))

    orders = [ro.order for ro in plan.round_orders]
    _assert_alternating(orders)

    for round_index in range(1, rounds + 1):
        in_round = [r for r in plan.runs if r.round_index == round_index]
        assert {r.runner_id for r in in_round} == _TWO_RUNNERS
        assert len(in_round) == 2
