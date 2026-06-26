"""Property-based test: warm-up / startup never leaks into core/steady-state."""

import json

from hypothesis import given, settings
from hypothesis import strategies as st

from harness.statistics import (
    COLD_START_LABEL,
    StatisticsEngine,
)

# A realistic per-operation latency sample (ms): strictly positive, finite.
_SAMPLE = st.floats(
    min_value=1e-4, max_value=1e4, allow_nan=False, allow_infinity=False
)
# Recorded post-warm-up samples — non-empty so core stats are always computed.
_RECORDED = st.lists(_SAMPLE, min_size=1, max_size=40)
# Warm-up samples — may be empty, and may be much larger than recorded samples
# so that folding them in WOULD change the stats if they were not excluded.
_WARMUP_SAMPLE = st.floats(
    min_value=1e-4, max_value=1e6, allow_nan=False, allow_infinity=False
)
_WARMUP = st.lists(_WARMUP_SAMPLE, min_size=0, max_size=40)
# An arbitrary Process_Startup_Time and optional JIT warm-up (ms).
_STARTUP = st.floats(min_value=0.0, max_value=1e7, allow_nan=False, allow_infinity=False)
_JIT = st.one_of(
    st.none(),
    st.floats(min_value=0.0, max_value=1e7, allow_nan=False, allow_infinity=False),
)

# The fixed key set of a core/steady-state latency-statistics block. None of the
# Cold_Start fields may appear here.
_CORE_KEYS = {
    "applicable",
    "sampleCount",
    "unit",
    "percentileMethod",
    "min",
    "mean",
    "p50",
    "p95",
    "p99",
    "max",
    "stddev",
    "cv",
    "p95Reliable",
    "p99Reliable",
}
_COLD_START_KEYS = {"processStartupMs", "jitWarmupMs", "totalColdStartMs", "coldStart"}


# Feature: pgp-encryption-benchmark-go-java, Property 8: การกันค่า warm-up / startup ออกจาก core crypto-time / steady-state
@settings(max_examples=200)
@given(
    rec_enc=_RECORDED,
    rec_dec=_RECORDED,
    warm_enc=_WARMUP,
    warm_dec=_WARMUP,
    startup=_STARTUP,
    jit=_JIT,
)
def test_core_steady_state_excludes_warmup_and_startup(
    rec_enc, rec_dec, warm_enc, warm_dec, startup, jit
):
    engine = StatisticsEngine()

    # The core/steady-state set computed from the recorded samples alone.
    core = engine.compute_operations(rec_enc, rec_dec)
    core_dict = core.to_dict()

    # 1) The excluding-warm-up set of the two-set report (with arbitrary warm-up
    #    samples injected) must be byte-for-byte the recorded-only core set.
    report = engine.compute_two_sets(
        rec_enc, rec_dec, encrypt_warmup=warm_enc, decrypt_warmup=warm_dec
    )
    assert report.excluding_warmup.to_dict() == core_dict

    # 2) Injecting warm-up samples cannot change the excluding set: it equals the
    #    excluding set computed with NO warm-up samples supplied.
    report_no_warmup = engine.compute_two_sets(rec_enc, rec_dec)
    assert report.excluding_warmup.to_dict() == report_no_warmup.excluding_warmup.to_dict()

    # The recorded-only maxima are the true core maxima — warm-up values (which
    # may be far larger) are never reflected in the excluding set.
    assert core.encrypt.maximum == max(rec_enc)
    assert core.decrypt.maximum == max(rec_dec)

    # 3) Process_Startup_Time / JIT warm-up is computed as a SEPARATE Cold_Start
    #    metric and must not change a single core statistic. Building the
    #    Cold_Start total with arbitrary startup/jit leaves the core untouched.
    cold = engine.cold_start_metric(startup, jit_warmup_ms=jit)
    assert engine.compute_operations(rec_enc, rec_dec).to_dict() == core_dict

    if cold is not None:
        # The Cold_Start total is the sum of its available components — derived
        # independently of the recorded samples.
        components = [v for v in (startup, jit) if v is not None]
        assert cold.total_cold_start_ms == sum(components)
        assert cold.label == COLD_START_LABEL

    # 4) No Cold_Start field/label may appear inside the core stats dict, and
    #    each operation block exposes exactly the core latency-statistics keys.
    for block in (core_dict["encrypt"], core_dict["decrypt"]):
        assert _COLD_START_KEYS.isdisjoint(block.keys())
        # Applicable blocks carry exactly the core stat keys (no extras).
        if block.get("applicable"):
            assert set(block.keys()) == _CORE_KEYS

    blob = json.dumps(core_dict)
    assert COLD_START_LABEL not in blob
    assert "coldStart" not in blob
    assert "processStartupMs" not in blob
    assert "jitWarmupMs" not in blob
    assert "totalColdStartMs" not in blob
