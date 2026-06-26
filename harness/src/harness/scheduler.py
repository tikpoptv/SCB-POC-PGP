"""RunScheduler — order Benchmark_Runs across Rounds, modes, and the null test."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Mapping, Sequence

from harness.config import BenchmarkConfig, RunMode, ScenarioConfig
from harness.contract import Command, Mode, Operation, OutputEncoding, RunnerId
from harness.environment import REQUIRED_FIELDS, Environment, EnvironmentProbe
from harness.subprocess_driver import RunnerResult, SubprocessDriver

__all__ = [
    "SchedulerError",
    "ResourceQuota",
    "SharedInputs",
    "RoundOrder",
    "PlannedRun",
    "RunSetPlan",
    "ExecutedRun",
    "RunSetResult",
    "RunScheduler",
    "DEFAULT_RUNNER_ORDER",
]

#: The pre-defined Round-1 order between the two Runners.
DEFAULT_RUNNER_ORDER: tuple[RunnerId, RunnerId] = (RunnerId.GO, RunnerId.JAVA)


class SchedulerError(ValueError):
    """Raised when a run cannot be planned (bad mode/warmup/quota/inputs)."""


@dataclass(frozen=True)
class ResourceQuota:
    """The CPU-core + memory budget imposed equally on both Runners."""

    cpu_cores: int
    memory_mb: int

    def difference(self, other: "ResourceQuota") -> dict[str, tuple[int, int]]:
        """Return the fields that differ as ``{field: (self, other)}``.

        An empty dict means the two quotas are identical (the only acceptable
        state for a fair comparison).
        """
        diff: dict[str, tuple[int, int]] = {}
        if self.cpu_cores != other.cpu_cores:
            diff["cpuCores"] = (self.cpu_cores, other.cpu_cores)
        if self.memory_mb != other.memory_mb:
            diff["memoryMb"] = (self.memory_mb, other.memory_mb)
        return diff

    def equals(self, other: "ResourceQuota") -> bool:
        """True when both quotas match exactly."""
        return not self.difference(other)

    def to_dict(self) -> dict[str, int]:
        return {"cpuCores": self.cpu_cores, "memoryMb": self.memory_mb}


@dataclass(frozen=True)
class SharedInputs:
    """The shared Key_Set / Test_Corpus binding for a Scenario.

    These paths and checksums are identical for every Runner in the Scenario;
    the scheduler only references them to build each :class:`Command`.
    """

    key_set_path: str
    key_set_checksum: str
    corpus_path: str
    corpus_checksum: str
    output_dir: str


@dataclass(frozen=True)
class RoundOrder:
    """The actual run order of one Round, recorded for the Result_Report."""

    round_index: int  # 1-based
    order: tuple[RunnerId, ...]

    def to_dict(self) -> dict[str, object]:
        return {"round": self.round_index, "order": [r.value for r in self.order]}


@dataclass(frozen=True)
class PlannedRun:
    """One Benchmark_Run the scheduler intends to execute."""

    scenario_id: str
    mode: RunMode
    round_index: int  # 1-based
    order_index: int  # position within the Round (0 = first, 1 = second)
    runner_id: RunnerId
    is_null_test: bool
    warmup_iterations: int
    quota: ResourceQuota
    command: Command


@dataclass(frozen=True)
class RunSetPlan:
    """An ordered set of runs for one (Scenario, mode, null-test) grouping.

    A *set* is the unit at which env/quota stability is judged: the environment
    captured when the set starts is the baseline for every run in it.
    """

    scenario_id: str
    mode: RunMode
    is_null_test: bool
    quota: ResourceQuota
    warmup_iterations: int
    runs: tuple[PlannedRun, ...]
    round_orders: tuple[RoundOrder, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "scenarioId": self.scenario_id,
            "mode": self.mode.value,
            "nullTest": self.is_null_test,
            "resourceQuota": self.quota.to_dict(),
            "warmupIterations": self.warmup_iterations,
            "roundOrders": [ro.to_dict() for ro in self.round_orders],
        }


@dataclass(frozen=True)
class ExecutedRun:
    """The outcome of one PlannedRun plus the environment seen at run time."""

    planned: PlannedRun
    result: RunnerResult
    environment: Environment


@dataclass
class RunSetResult:
    """The collected outcome of a RunSetPlan with comparability bookkeeping.

    ``comparable`` starts True and flips to False (with ``non_comparable_reason``
    set) if the environment or quota changes mid-set relative to ``baseline_env``
    / ``quota``. Already-collected ``runs`` are always retained.
    """

    scenario_id: str
    mode: RunMode
    is_null_test: bool
    quota: ResourceQuota
    warmup_iterations: int
    baseline_env: Environment
    round_orders: tuple[RoundOrder, ...]
    runs: list[ExecutedRun] = field(default_factory=list)
    comparable: bool = True
    non_comparable_reason: str | None = None

    def mark_non_comparable(self, reason: str) -> None:
        """Flag the set non-comparable (idempotent on the reason)."""
        if self.comparable:
            self.comparable = False
            self.non_comparable_reason = reason


InputsProvider = Callable[[ScenarioConfig], SharedInputs]
QuotaProvider = Callable[[ScenarioConfig, RunnerId], ResourceQuota]
EnvProbe = Callable[[], Environment]
VariantIdFor = Callable[[RunnerId], str]
DriverFactory = Callable[[RunnerId], SubprocessDriver]


class RunScheduler:
    """Plan and (optionally) execute the alternating multi-Round benchmark.

    Parameters
    ----------
    config:
        The validated :class:`BenchmarkConfig` (rounds, warmup, modes,
        scenarios, null test).
    inputs_provider:
        Resolves the shared Key_Set/Test_Corpus binding for a Scenario, used to
        build each :class:`Command`. May be a callable
        ``(ScenarioConfig) -> SharedInputs`` or a mapping
        ``{scenario_id: SharedInputs}``.
    drivers / driver_factory:
        How to obtain a :class:`SubprocessDriver` per Runner. Provide either a
        mapping ``{RunnerId|str: SubprocessDriver}`` or a factory
        ``(RunnerId) -> SubprocessDriver``. Required only for execution, not for
        planning.
    quota_provider:
        Resolves the :class:`ResourceQuota` for ``(scenario, runner)``. Defaults
        to ``cpu_cores = config.vcpu`` and ``memory_mb = scenario.memoryQuotaMb``
        for *both* Runners.
    env_probe:
        Captures the current :class:`Environment`. Defaults to a real probe.
    operation:
        The :class:`Operation` to request (default ``roundtrip``).
    variant_id_for:
        Maps a Runner to the ``variantId`` placed on its Command. Defaults to the
        Runner id string (e.g. ``"go"``).
    """

    def __init__(
        self,
        config: BenchmarkConfig,
        inputs_provider: InputsProvider | Mapping[str, SharedInputs],
        *,
        drivers: Mapping[object, SubprocessDriver] | None = None,
        driver_factory: DriverFactory | None = None,
        quota_provider: QuotaProvider | None = None,
        env_probe: EnvProbe | None = None,
        operation: Operation = Operation.ROUNDTRIP,
        variant_id_for: VariantIdFor | None = None,
    ) -> None:
        self._config = config
        self._inputs_provider = self._coerce_inputs_provider(inputs_provider)
        self._drivers = self._coerce_drivers(drivers)
        self._driver_factory = driver_factory
        self._quota_provider = quota_provider or self._default_quota_provider
        self._env_probe = env_probe or EnvironmentProbe.probe
        self._operation = operation
        self._variant_id_for = variant_id_for or (lambda runner: runner.value)

    @staticmethod
    def _coerce_inputs_provider(
        provider: InputsProvider | Mapping[str, SharedInputs],
    ) -> InputsProvider:
        if isinstance(provider, Mapping):
            mapping = dict(provider)

            def _lookup(scenario: ScenarioConfig) -> SharedInputs:
                try:
                    return mapping[scenario.id]
                except KeyError:
                    raise SchedulerError(
                        f"no SharedInputs registered for scenario {scenario.id!r}"
                    ) from None

            return _lookup
        if not callable(provider):
            raise SchedulerError("inputs_provider must be a callable or a mapping")
        return provider

    @staticmethod
    def _coerce_drivers(
        drivers: Mapping[object, SubprocessDriver] | None,
    ) -> dict[RunnerId, SubprocessDriver]:
        if drivers is None:
            return {}
        coerced: dict[RunnerId, SubprocessDriver] = {}
        for key, driver in drivers.items():
            runner = key if isinstance(key, RunnerId) else RunnerId(str(key))
            coerced[runner] = driver
        return coerced

    def _default_quota_provider(
        self, scenario: ScenarioConfig, runner: RunnerId
    ) -> ResourceQuota:
        # Identical for both Runners: full VM vCPU + the Scenario's memory quota.
        # ``runner`` is intentionally ignored.
        return ResourceQuota(
            cpu_cores=self._config.vcpu, memory_mb=scenario.memory_quota_mb
        )

    @staticmethod
    def runner_order(
        round_index: int,
        base_order: Sequence[RunnerId] = DEFAULT_RUNNER_ORDER,
    ) -> tuple[RunnerId, ...]:
        """The Runner order for ``round_index`` (1-based).

        Round 1 uses ``base_order`` verbatim; every subsequent Round reverses the
        order of the Round before it. Even Rounds are reversed, odd Rounds keep
        the base order.
        """
        if round_index < 1:
            raise SchedulerError(f"round_index must be >= 1, got {round_index}")
        order = tuple(base_order)
        return order if round_index % 2 == 1 else tuple(reversed(order))

    def plan(self) -> list[RunSetPlan]:
        """Produce every RunSetPlan: each Scenario × mode, plus null-test sets."""
        plans: list[RunSetPlan] = []
        for scenario in self._config.scenarios:
            for mode in self._config.modes:
                plans.append(self.plan_set(scenario, mode))
        # Null test: same Runner vs itself, one set per Scenario×mode.
        if self._config.null_test.enabled:
            null_runner = RunnerId(self._config.null_test.runner)
            for scenario in self._config.scenarios:
                for mode in self._config.modes:
                    plans.append(
                        self.plan_set(scenario, mode, null_runner=null_runner)
                    )
        return plans

    def plan_set(
        self,
        scenario: ScenarioConfig,
        mode: RunMode,
        *,
        null_runner: RunnerId | None = None,
    ) -> RunSetPlan:
        """Plan the ordered runs for one (Scenario, mode, null-test) set.

        For a normal set the two Runners are ``(go, java)``; for a null test
        both are ``null_runner``. Across Rounds the order alternates and warm-up
        is propagated into every Command.
        """
        warmup = self._config.warmup_iterations
        self._validate_mode_warmup(mode, warmup)

        is_null = null_runner is not None
        base_pair: tuple[RunnerId, RunnerId] = (
            (null_runner, null_runner) if is_null else DEFAULT_RUNNER_ORDER
        )

        quota = self._equal_quota(scenario, base_pair)
        inputs = self._inputs_provider(scenario)

        runs: list[PlannedRun] = []
        round_orders: list[RoundOrder] = []
        for round_index in range(1, self._config.rounds + 1):
            order = self.runner_order(round_index, base_pair)
            round_orders.append(RoundOrder(round_index=round_index, order=order))
            for order_index, runner in enumerate(order):
                command = self._build_command(
                    scenario=scenario,
                    runner=runner,
                    mode=mode,
                    warmup=warmup,
                    inputs=inputs,
                    round_index=round_index,
                    order_index=order_index,
                    is_null=is_null,
                )
                runs.append(
                    PlannedRun(
                        scenario_id=scenario.id,
                        mode=mode,
                        round_index=round_index,
                        order_index=order_index,
                        runner_id=runner,
                        is_null_test=is_null,
                        warmup_iterations=warmup,
                        quota=quota,
                        command=command,
                    )
                )

        return RunSetPlan(
            scenario_id=scenario.id,
            mode=mode,
            is_null_test=is_null,
            quota=quota,
            warmup_iterations=warmup,
            runs=tuple(runs),
            round_orders=tuple(round_orders),
        )

    def _validate_mode_warmup(self, mode: RunMode, warmup: int) -> None:
        # steady_state must collect only after >= 1 warm-up iteration.
        if mode is RunMode.STEADY_STATE and warmup < 1:
            raise SchedulerError(
                "steady_state mode requires warmupIterations >= 1 "
                f"(Req 17.1), got {warmup}"
            )

    def _equal_quota(
        self, scenario: ScenarioConfig, runners: Sequence[RunnerId]
    ) -> ResourceQuota:
        """Resolve and enforce an identical quota for every Runner."""
        quotas = {runner: self._quota_provider(scenario, runner) for runner in runners}
        # All quotas in the set must be identical (difference = 0).
        reference = next(iter(quotas.values()))
        for runner, quota in quotas.items():
            diff = reference.difference(quota)
            if diff:
                raise SchedulerError(
                    f"resource quota differs between Runners in scenario "
                    f"{scenario.id!r}: {runner.value} has {diff} "
                    f"(Req 3.4 requires the difference to be 0)"
                )
        return reference

    def _build_command(
        self,
        *,
        scenario: ScenarioConfig,
        runner: RunnerId,
        mode: RunMode,
        warmup: int,
        inputs: SharedInputs,
        round_index: int,
        order_index: int,
        is_null: bool,
    ) -> Command:
        profile = self._crypto_profile_for(scenario)
        suffix = "null-" if is_null else ""
        output_dir = (
            f"{inputs.output_dir.rstrip('/')}/{scenario.id}/{mode.value}/"
            f"{suffix}round-{round_index}/{runner.value}-{order_index}"
        )
        return Command(
            variant_id=self._variant_id_for(runner),
            mode=Mode(mode.value),
            warmup_iterations=warmup,
            concurrency=scenario.concurrency,
            crypto_profile=profile,
            output_encoding=OutputEncoding(scenario.output_encoding.value),
            key_set_path=inputs.key_set_path,
            key_set_checksum=inputs.key_set_checksum,
            corpus_path=inputs.corpus_path,
            corpus_checksum=inputs.corpus_checksum,
            output_dir=output_dir,
            operation=self._operation,
        )

    def _crypto_profile_for(self, scenario: ScenarioConfig):
        for profile in self._config.crypto_profiles:
            if profile.id == scenario.crypto_profile_id:
                return profile.profile
        # ConfigLoader guarantees referential integrity, so this is defensive.
        raise SchedulerError(
            f"scenario {scenario.id!r} references unknown cryptoProfile "
            f"{scenario.crypto_profile_id!r}"
        )

    def execute(self) -> list[RunSetResult]:
        """Plan and execute every set, returning the collected results."""
        return [self.execute_set(plan) for plan in self.plan()]

    def execute_set(self, plan: RunSetPlan) -> RunSetResult:
        """Execute one set, watching for mid-set env/quota change.

        The environment and quota captured before the first run are the baseline.
        If either changes before a later run, the whole set is marked
        non-comparable with a reason, but every result already gathered is kept.
        """
        baseline_env = self._env_probe()
        result = RunSetResult(
            scenario_id=plan.scenario_id,
            mode=plan.mode,
            is_null_test=plan.is_null_test,
            quota=plan.quota,
            warmup_iterations=plan.warmup_iterations,
            baseline_env=baseline_env,
            round_orders=plan.round_orders,
        )
        # If the baseline environment itself is incomplete, the set cannot be
        # judged comparable.
        if not baseline_env.comparable:
            result.mark_non_comparable(
                baseline_env.non_comparable_reason or "environment incomplete"
            )

        scenario = self._scenario_by_id(plan.scenario_id)

        for planned in plan.runs:
            current_env = self._env_probe()
            self._check_environment_stable(result, baseline_env, current_env)
            self._check_quota_stable(result, scenario, planned)

            driver = self._driver_for(planned.runner_id)
            run_result = driver.run(planned.command)
            result.runs.append(
                ExecutedRun(
                    planned=planned,
                    result=run_result,
                    environment=current_env,
                )
            )
        return result

    def _check_environment_stable(
        self,
        result: RunSetResult,
        baseline: Environment,
        current: Environment,
    ) -> None:
        changed = _changed_env_fields(baseline, current)
        if changed:
            result.mark_non_comparable(
                "environment changed mid-set: " + ", ".join(changed)
            )

    def _check_quota_stable(
        self,
        result: RunSetResult,
        scenario: ScenarioConfig,
        planned: PlannedRun,
    ) -> None:
        current_quota = self._quota_provider(scenario, planned.runner_id)
        diff = planned.quota.difference(current_quota)
        if diff:
            result.mark_non_comparable(
                f"resource quota changed mid-set for {planned.runner_id.value}: "
                f"{diff}"
            )

    def _scenario_by_id(self, scenario_id: str) -> ScenarioConfig:
        for scenario in self._config.scenarios:
            if scenario.id == scenario_id:
                return scenario
        raise SchedulerError(f"unknown scenario {scenario_id!r}")

    def _driver_for(self, runner: RunnerId) -> SubprocessDriver:
        if runner in self._drivers:
            return self._drivers[runner]
        if self._driver_factory is not None:
            driver = self._driver_factory(runner)
            self._drivers[runner] = driver
            return driver
        raise SchedulerError(
            f"no SubprocessDriver available for runner {runner.value!r}; "
            "provide drivers= or driver_factory="
        )


def _changed_env_fields(baseline: Environment, current: Environment) -> list[str]:
    """Names of comparability-critical fields that changed between two probes."""
    changed: list[str] = []
    for attr, schema_key in REQUIRED_FIELDS:
        if getattr(baseline, attr) != getattr(current, attr):
            changed.append(schema_key)
    return changed
