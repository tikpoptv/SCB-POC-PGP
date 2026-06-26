"""Property-based test for round-trip time = encrypt + decrypt (task 8.5)."""

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from harness.statistics_engine import round_trip_ms


# 9.3, 9.8). Constrain the generator to that input space: no NaN/infinity, no
# negatives. The wide upper bound keeps values realistic while still exercising
# large magnitudes where float addition could lose precision.
_TIMES = st.floats(
    min_value=0.0,
    max_value=1e9,
    allow_nan=False,
    allow_infinity=False,
)


# Feature: pgp-encryption-benchmark-go-java, Property 6: round-trip time = encrypt + decrypt
@settings(max_examples=200)
@given(encrypt_ms=_TIMES, decrypt_ms=_TIMES)
def test_round_trip_is_sum_of_encrypt_and_decrypt(encrypt_ms, decrypt_ms):
    assert round_trip_ms(encrypt_ms, decrypt_ms) == pytest.approx(
        encrypt_ms + decrypt_ms
    )
