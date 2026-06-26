package com.poc.pgp.contract;

import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.annotation.JsonPropertyOrder;

/**
 * One raw per-operation sample (Req 10.1, 20.5), mirroring the {@code operation}
 * object in {@code contract/runner-output.schema.json}. Built incrementally by
 * the shell as it processes each corpus file, so this is a mutable POJO with
 * public fields (Jackson serialises them in the declared order, matching the Go
 * runner's output). Nullable fields are always emitted (e.g. {@code
 * "skipReason": null}) to match the Go runner byte-shape.
 */
@JsonInclude(JsonInclude.Include.ALWAYS)
@JsonPropertyOrder({
        "fileName", "fileType", "originalBytes", "ciphertextBytes", "skipped",
        "skipReason", "encryptMs", "decryptMs", "asymEncryptMs", "asymDecryptMs",
        "symEncryptMs", "symDecryptMs", "roundTripOk", "failureType", "outputFileName"
})
public final class OperationSample {

    /** Failure classification values (Req 12.1). */
    public static final String FAILURE_OPERATION = "operation_failure";
    public static final String FAILURE_CORRECTNESS = "correctness_failure";

    public String fileName;
    public String fileType;
    public long originalBytes;
    public Long ciphertextBytes;
    public boolean skipped;
    public String skipReason;
    public Double encryptMs;
    public Double decryptMs;
    public Double asymEncryptMs;
    public Double asymDecryptMs;
    public Double symEncryptMs;
    public Double symDecryptMs;
    public boolean roundTripOk;
    public String failureType;
    public String outputFileName;
}
