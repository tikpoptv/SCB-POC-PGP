package com.poc.pgp.contract;

import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.annotation.JsonPropertyOrder;

/**
 * Optional GC statistics reported by the Runner (Req 17.2, 17.3), mirroring the
 * {@code gc} object in {@code contract/runner-output.schema.json}. The scaffold
 * emits {@code gc: null}; populating it from {@code GarbageCollectorMXBean} is a
 * later task.
 */
@JsonInclude(JsonInclude.Include.ALWAYS)
@JsonPropertyOrder({"collections", "totalPauseMs", "gcType", "heapInitMb", "heapMaxMb"})
public record GcStats(
        int collections,
        double totalPauseMs,
        String gcType,
        Double heapInitMb,
        Double heapMaxMb) {
}
