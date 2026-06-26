package com.poc.pgp.contract;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

/**
 * The single JSON object the harness sends on stdin
 * ({@code contract/command.schema.json}). One object per process invocation.
 *
 * <p>Integer fields are boxed ({@link Integer}) so a missing value decodes as
 * {@code null} and can be reported as a config error rather than silently
 * becoming {@code 0} (presence is also checked up-front by
 * {@link com.poc.pgp.cli.CommandParser}). Unknown fields are rejected
 * ({@code additionalProperties:false}).
 */
@JsonIgnoreProperties(ignoreUnknown = false)
public record Command(
        String command,
        String variantId,
        String mode,
        Integer warmupIterations,
        Integer concurrency,
        CryptoProfile cryptoProfile,
        String outputEncoding,
        String keySetPath,
        String keySetChecksum,
        String corpusPath,
        String corpusChecksum,
        String outputDir,
        String operation) {
}
