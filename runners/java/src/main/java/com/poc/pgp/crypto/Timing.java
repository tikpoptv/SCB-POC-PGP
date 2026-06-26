package com.poc.pgp.crypto;

/**
 * Crypto-only timing of a single encrypt or decrypt call (design.md, Java
 * interface). Times are nanoseconds measured with {@link System#nanoTime()}
 * (Req 1.1, 24.1). {@code asymNanos}/{@code symNanos} are {@link #NOT_SEPARABLE}
 * (-1) when the engine cannot isolate the asymmetric key wrap from the symmetric
 * data encryption (Req 24.3).
 *
 * <p>This is the exact shape from design.md:
 * {@code record Timing(long totalNanos, long asymNanos, long symNanos, boolean hardwareAccel)}.
 */
public record Timing(long totalNanos, long asymNanos, long symNanos, boolean hardwareAccel) {

    /** Sentinel for an asym/sym sub-measurement the engine cannot isolate (Req 24.3). */
    public static final long NOT_SEPARABLE = -1L;

    /** Convenience factory for a total-only measurement with no asym/sym breakdown. */
    public static Timing ofTotal(long totalNanos, boolean hardwareAccel) {
        return new Timing(totalNanos, NOT_SEPARABLE, NOT_SEPARABLE, hardwareAccel);
    }

    /**
     * Reports whether this Timing's asym/sym breakdown is consistent with its
     * total time (Req 24.2, design.md Property 23). Two valid shapes:
     * <ul>
     *   <li><b>Not claimed:</b> either sub-measurement is {@link #NOT_SEPARABLE},
     *       so the breakdown makes no claim and the invariant holds vacuously.</li>
     *   <li><b>Claimed:</b> both are measured — consistent only when both are
     *       non-negative, the total is positive, and {@code asym + sym <= total}
     *       (the total also absorbs measurement overhead).</li>
     * </ul>
     */
    public boolean breakdownConsistent() {
        if (asymNanos == NOT_SEPARABLE || symNanos == NOT_SEPARABLE) {
            return true;
        }
        if (asymNanos < 0 || symNanos < 0) {
            return false;
        }
        if (totalNanos <= 0) {
            return false;
        }
        return asymNanos + symNanos <= totalNanos;
    }

    /**
     * Returns a copy whose asym/sym breakdown is dropped to {@link #NOT_SEPARABLE}
     * when it is not consistent with the total — the fail-safe enforced at the
     * reporting boundary so a contradictory breakdown is never emitted (Req 24.2,
     * 24.3), mirroring the Go runner's {@code honestBreakdown}.
     */
    public Timing honest() {
        if (breakdownConsistent()) {
            return this;
        }
        return new Timing(totalNanos, NOT_SEPARABLE, NOT_SEPARABLE, hardwareAccel);
    }
}
