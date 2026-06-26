"""Unit tests for the RunScheduler (Task 6.3)."""

import pytest

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
from harness.contract import (
    Command,
    CryptoProfile,
    ExitCode,
    Mode,
    Operation,
    OutputEncoding,
    RunnerId,
    RunnerOutput,
)
from harness.environment import Environment
from harness.scheduler import (
    DEFAULT_RUNNER_ORDER,
    PlannedRun,
    ResourceQuota,
    RunScheduler,
    RunSetPlan,
    SchedulerError,
    SharedInputs,
)
from harness.subprocess_driver import RunnerResult

_CHK = "sha256:" + "ab" * 32


# Fixtures / builders
def _profile(profile_id: str = "p1") -> CryptoProfileConfig:
    return CryptoProfileConfig(
        id=profile_id,
        profile=CryptoProfile(
            pub_alg="RSA-2048", cipher="AES-256", compression="ZLIB", hash="SHA-256"
        ),
    )


def _scenario(scenario_id: str = "s1", *, memory_quota_mb: int = 2048) -> ScenarioConfig:
    return ScenarioConfig(
        id=scenario_id,
        file_size_tier=FileSizeTier.SMALL,
        key_spec=KeySpec(type=KeyType.RSA, bits=2048),
        concurrency=4,
        memory_mode=MemoryMode.STREAMING,
        crypto_profile_id="p1",
        data_compressibility=DataCompressibility.BOTH,
        output_encoding=OutputEncoding.BINARY,
        memory_quota_mb=memory_quota_mb,
    )


def _config(
    *,
    rounds: int = 4,
    warmup: int = 5,
    modes: tuple[RunMode, ...] = (RunMode.STEADY_STATE,),
    scenarios: tuple[ScenarioConfig, ...] | None = None,
    null_test: NullTestConfig | None = None,
    vcpu: int = 8,
) -> BenchmarkConfig:
    return BenchmarkConfig(
        rounds=rounds,
        warmup_iterations=warmup,
        seed=1,
        sampling_interval_ms=100,
        crypto_profiles=(_profile(),),
        key_specs=(KeySpec(type=KeyType.RSA, bits=2048),),
        scenarios=scenarios if scenarios is not None else (_scenario(),),
        modes=modes,
        vcpu=vcpu,
        null_test=null_test or NullTestConfig(),
    )


def _inputs(scenario: ScenarioConfig) -> SharedInputs:
    return SharedInputs(
        key_set_path="/tmpfs/keys",
        key_set_checksum=_CHK,
        corpus_path=f"/tmpfs/corpus/{scenario.id}",
        corpus_checksum=_CHK,
        output_dir="/tmpfs/out",
    )


def _runner_output(runner: RunnerId) -> RunnerOutput:
    return RunnerOutput(
        runner_id=runner,
        variant_id=runner.value,
        mode=Mode.STEADY_STATE,
        scenario_id="s1",
        crypto_profile_id="p1",
        concurrency=4,
        output_encoding=OutputEncoding.BINARY,
        hardware_accel=True,
        key_set_checksum_seen=_CHK,
        corpus_checksum_seen=_CHK,
        operations=(),
    )


class FakeDriver:
    """Records every Command it is asked to run and returns a success result."""

    def __init__(self, runner: RunnerId) -> None:
        self.runner = runner
        self.commands: list[Command] = []

    def run(self, command: Command, *, timeout_s=None) -> RunnerResult:
        self.commands.append(command)
        return RunnerResult(
            exit_code=0,
            classified=ExitCode.SUCCESS,
            stdout="",
            stderr="",
            duration_s=0.01,
            output=_runner_output(self.runner),
        )


def _complete_env(**overrides) -> Environment:
    base = dict(
        vcpu=8,
        ram_mb=16384,
        os="Linux",
        os_version="Ubuntu 22.04",
        cpu_arch="x86_64",
        storage_type="tmpfs",
    )
    base.update(overrides)
    return Environment(**base)


def test_round_one_uses_predefined_go_then_java():
    assert RunScheduler.runner_order(1) == (RunnerId.GO, RunnerId.JAVA)


def test_subsequent_rounds_reverse_the_previous_order():
    assert RunScheduler.runner_order(2) == (RunnerId.JAVA, RunnerId.GO)
    assert RunScheduler.runner_order(3) == (RunnerId.GO, RunnerId.JAVA)
    assert RunScheduler.runner_order(4) == (RunnerId.JAVA, RunnerId.GO)


def test_runner_order_alternates_for_many_rounds():
    prev = None
    for r in range(1, 51):
        order = RunScheduler.runner_order(r)
        if prev is not None:
            assert order == tuple(reversed(prev)), f"round {r} did not reverse round {r-1}"
        prev = order


def test_runner_order_rejects_non_positive_round():
    with pytest.raises(SchedulerError):
        RunScheduler.runner_order(0)


# plan_set — order + both runners per round + warmup propagation
def test_plan_set_alternates_and_runs_both_runners_each_round():
    cfg = _config(rounds=4)
    sched = RunScheduler(cfg, _inputs)
    plan = sched.plan_set(_scenario(), RunMode.STEADY_STATE)

    assert [ro.order for ro in plan.round_orders] == [
        (RunnerId.GO, RunnerId.JAVA),
        (RunnerId.JAVA, RunnerId.GO),
        (RunnerId.GO, RunnerId.JAVA),
        (RunnerId.JAVA, RunnerId.GO),
    ]
    # Each round contributes exactly two runs, one per runner.
    assert len(plan.runs) == 8
    for round_index in range(1, 5):
        in_round = [r for r in plan.runs if r.round_index == round_index]
        assert {r.runner_id for r in in_round} == {RunnerId.GO, RunnerId.JAVA}


def test_plan_set_propagates_warmup_into_every_command():
    cfg = _config(rounds=3, warmup=7)
    sched = RunScheduler(cfg, _inputs)
    plan = sched.plan_set(_scenario(), RunMode.STEADY_STATE)
    assert plan.warmup_iterations == 7
    assert all(run.command.warmup_iterations == 7 for run in plan.runs)


def test_plan_set_builds_command_with_shared_scenario_inputs():
    cfg = _config(rounds=1)
    sched = RunScheduler(cfg, _inputs)
    plan = sched.plan_set(_scenario(), RunMode.STEADY_STATE)
    go_cmd = next(r.command for r in plan.runs if r.runner_id is RunnerId.GO)
    java_cmd = next(r.command for r in plan.runs if r.runner_id is RunnerId.JAVA)

    # Same shared inputs / profile / encoding / concurrency for both runners.
    for cmd in (go_cmd, java_cmd):
        assert cmd.key_set_path == "/tmpfs/keys"
        assert cmd.corpus_checksum == _CHK
        assert cmd.crypto_profile.cipher == "AES-256"
        assert cmd.output_encoding is OutputEncoding.BINARY
        assert cmd.concurrency == 4
        assert cmd.mode is Mode.STEADY_STATE
        assert cmd.operation is Operation.ROUNDTRIP
    assert go_cmd.variant_id == "go"
    assert java_cmd.variant_id == "java"
    # Output dirs are per-run distinct.
    assert go_cmd.output_dir != java_cmd.output_dir


def test_plan_covers_each_configured_mode():
    cfg = _config(modes=(RunMode.COLD_START, RunMode.STEADY_STATE))
    sched = RunScheduler(cfg, _inputs)
    plans = sched.plan()
    modes = {p.mode for p in plans}
    assert modes == {RunMode.COLD_START, RunMode.STEADY_STATE}


def test_cold_start_allows_zero_warmup():
    cfg = _config(warmup=0, modes=(RunMode.COLD_START,))
    sched = RunScheduler(cfg, _inputs)
    plan = sched.plan_set(_scenario(), RunMode.COLD_START)
    assert all(run.command.warmup_iterations == 0 for run in plan.runs)


def test_steady_state_requires_at_least_one_warmup():
    cfg = _config(warmup=0, modes=(RunMode.STEADY_STATE,))
    sched = RunScheduler(cfg, _inputs)
    with pytest.raises(SchedulerError, match="steady_state"):
        sched.plan_set(_scenario(), RunMode.STEADY_STATE)


def test_null_test_pairs_same_runner_against_itself():
    cfg = _config(
        rounds=2,
        modes=(RunMode.STEADY_STATE,),
        null_test=NullTestConfig(enabled=True, runner="go"),
    )
    sched = RunScheduler(cfg, _inputs)
    plans = sched.plan()
    null_plans = [p for p in plans if p.is_null_test]
    assert null_plans, "expected at least one null-test set"
    for plan in null_plans:
        for ro in plan.round_orders:
            assert ro.order == (RunnerId.GO, RunnerId.GO)
        assert all(run.runner_id is RunnerId.GO for run in plan.runs)


def test_no_null_test_set_when_disabled():
    cfg = _config(null_test=NullTestConfig(enabled=False))
    sched = RunScheduler(cfg, _inputs)
    assert all(not p.is_null_test for p in sched.plan())


def test_both_runners_get_identical_quota():
    cfg = _config()
    sched = RunScheduler(cfg, _inputs)
    plan = sched.plan_set(_scenario(memory_quota_mb=3072), RunMode.STEADY_STATE)
    assert plan.quota == ResourceQuota(cpu_cores=8, memory_mb=3072)
    assert all(run.quota == plan.quota for run in plan.runs)


def test_quota_difference_is_zero_for_default_provider():
    q = ResourceQuota(cpu_cores=8, memory_mb=2048)
    assert q.difference(ResourceQuota(cpu_cores=8, memory_mb=2048)) == {}
    assert q.equals(ResourceQuota(cpu_cores=8, memory_mb=2048))


def test_planning_rejects_unequal_quota_between_runners():
    cfg = _config()

    def lopsided(scenario, runner):
        cores = 8 if runner is RunnerId.GO else 4  # difference != 0
        return ResourceQuota(cpu_cores=cores, memory_mb=2048)

    sched = RunScheduler(cfg, _inputs, quota_provider=lopsided)
    with pytest.raises(SchedulerError, match="quota differs"):
        sched.plan_set(_scenario(), RunMode.STEADY_STATE)


def _drivers():
    return {RunnerId.GO: FakeDriver(RunnerId.GO), RunnerId.JAVA: FakeDriver(RunnerId.JAVA)}


def test_execute_runs_every_planned_run_in_order():
    cfg = _config(rounds=3)
    drivers = _drivers()
    sched = RunScheduler(
        cfg, _inputs, drivers=drivers, env_probe=lambda: _complete_env()
    )
    results = sched.execute()
    assert len(results) == 1
    rset = results[0]
    assert rset.comparable is True
    assert len(rset.runs) == 6  # 3 rounds * 2 runners
    # go ran once per round = 3 times, same for java.
    assert len(drivers[RunnerId.GO].commands) == 3
    assert len(drivers[RunnerId.JAVA].commands) == 3
    observed = [run.planned.runner_id for run in rset.runs]
    assert observed == [
        RunnerId.GO, RunnerId.JAVA,   # round 1
        RunnerId.JAVA, RunnerId.GO,   # round 2
        RunnerId.GO, RunnerId.JAVA,   # round 3
    ]


def test_env_change_mid_set_marks_non_comparable_but_keeps_data():
    cfg = _config(rounds=3)
    drivers = _drivers()

    seq = iter(
        [
            _complete_env(),                  # baseline
            _complete_env(),                  # run 1 ok
            _complete_env(vcpu=4),            # run 2: vCPU changed -> non-comparable
        ]
    )
    last = _complete_env(vcpu=4)

    def probe():
        try:
            return next(seq)
        except StopIteration:
            return last

    sched = RunScheduler(cfg, _inputs, drivers=drivers, env_probe=probe)
    rset = sched.execute_set(sched.plan_set(_scenario(), RunMode.STEADY_STATE))

    assert rset.comparable is False
    assert "vcpu" in rset.non_comparable_reason
    # Data already collected is retained (every run still executed/recorded).
    assert len(rset.runs) == 6


def test_quota_change_mid_set_marks_non_comparable():
    cfg = _config(rounds=2)
    drivers = _drivers()

    calls = {"n": 0}

    def changing_quota(scenario, runner):
        calls["n"] += 1
        # First few calls (planning + early runs) = 2048; later flips to 1024.
        mb = 2048 if calls["n"] <= 4 else 1024
        return ResourceQuota(cpu_cores=cfg.vcpu, memory_mb=mb)

    sched = RunScheduler(
        cfg,
        _inputs,
        drivers=drivers,
        quota_provider=changing_quota,
        env_probe=lambda: _complete_env(),
    )
    plan = sched.plan_set(_scenario(), RunMode.STEADY_STATE)
    rset = sched.execute_set(plan)
    assert rset.comparable is False
    assert "quota changed" in rset.non_comparable_reason
    assert len(rset.runs) == 4


def test_incomplete_baseline_env_makes_set_non_comparable():
    cfg = _config(rounds=1)
    drivers = _drivers()
    sched = RunScheduler(
        cfg, _inputs, drivers=drivers, env_probe=lambda: _complete_env(storage_type=None)
    )
    rset = sched.execute_set(sched.plan_set(_scenario(), RunMode.STEADY_STATE))
    assert rset.comparable is False
    assert "storageType" in rset.non_comparable_reason


# Driver resolution
def test_driver_factory_is_used_when_no_mapping_provided():
    cfg = _config(rounds=1)
    created: list[RunnerId] = []

    def factory(runner: RunnerId) -> FakeDriver:
        created.append(runner)
        return FakeDriver(runner)

    sched = RunScheduler(
        cfg, _inputs, driver_factory=factory, env_probe=lambda: _complete_env()
    )
    sched.execute()
    assert set(created) == {RunnerId.GO, RunnerId.JAVA}


def test_missing_driver_raises():
    cfg = _config(rounds=1)
    sched = RunScheduler(cfg, _inputs, env_probe=lambda: _complete_env())
    with pytest.raises(SchedulerError, match="no SubprocessDriver"):
        sched.execute()


def test_inputs_provider_accepts_mapping():
    cfg = _config(rounds=1)
    scenario = _scenario()
    sched = RunScheduler(cfg, {scenario.id: _inputs(scenario)})
    plan = sched.plan_set(scenario, RunMode.STEADY_STATE)
    assert plan.runs[0].command.corpus_path == f"/tmpfs/corpus/{scenario.id}"
