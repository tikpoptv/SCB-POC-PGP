package com.poc.pgp.contract;

import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.annotation.JsonPropertyOrder;

import java.util.ArrayList;
import java.util.List;

/**
 * The single JSON object the Runner writes to stdout
 * ({@code contract/runner-output.schema.json}). CPU/RAM samples are collected
 * externally by the Harness; this carries raw per-operation samples plus run
 * metadata. Field order matches the Go runner's output for readability.
 *
 * <p>{@code graalvmVersion}: populated only by {@code NativeMain} (the
 * {@code java-native-stream-parallel} variant) with the actual GraalVM version
 * string captured at start-up. Satisfies Req 22.3 — the Result_Report records
 * the real build-toolchain version for the native binary.
 */
@JsonInclude(JsonInclude.Include.ALWAYS)
@JsonPropertyOrder({
        "runnerId", "variantId", "mode", "scenarioId", "cryptoProfileId",
        "concurrency", "outputEncoding", "processStartupMs", "hardwareAccel",
        "graalvmVersion", "keySetChecksumSeen", "corpusChecksumSeen", "gc", "operations",
        "resourceSamplesNote"
})
public final class RunnerOutput {

    /** This Runner's id in the contract ({@code runnerId} enum). */
    public static final String RUNNER_ID = "java";

    public String runnerId = RUNNER_ID;
    public String variantId;
    public String mode;
    public String scenarioId;
    public String cryptoProfileId;
    public int concurrency;
    public String outputEncoding;
    public Double processStartupMs;
    public boolean hardwareAccel;

    /**
     * GraalVM version string (major.minor.patch) of the native-image runtime,
     * recorded only when running as a native binary (Req 22.3). Null for JVM
     * variants; the Harness reads {@code org.graalvm.nativeimage.imagecode}
     * and this field to log it in {@code versions.graalvm} in results.json.
     */
    @JsonInclude(JsonInclude.Include.NON_NULL)
    public String graalvmVersion;

    public String keySetChecksumSeen;
    public String corpusChecksumSeen;
    public GcStats gc;
    public List<OperationSample> operations = new ArrayList<>();
    public String resourceSamplesNote = "CPU/RAM sampled externally by the Harness";
}
