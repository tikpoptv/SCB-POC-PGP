package com.poc.pgp.cli;

import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.poc.pgp.contract.Command;
import com.poc.pgp.contract.CryptoProfile;

import java.util.List;
import java.util.Set;
import java.util.regex.Pattern;

/**
 * Decodes and validates a Command JSON document against the shared schema
 * ({@code contract/command.schema.json}). Any structural or value problem is a
 * config error mapped to exit code 3 ({@link RunnerException}), mirroring the Go
 * runner's {@code ParseCommand}/{@code validate}.
 */
public final class CommandParser {

    private static final ObjectMapper MAPPER = new ObjectMapper()
            // additionalProperties:false — reject unknown fields at any level.
            .enable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);

    /** Required top-level fields from the schema (presence is checked explicitly). */
    private static final List<String> REQUIRED_FIELDS = List.of(
            "command", "variantId", "mode", "warmupIterations", "concurrency",
            "cryptoProfile", "outputEncoding", "keySetPath", "keySetChecksum",
            "corpusPath", "corpusChecksum", "outputDir", "operation");

    private static final Set<String> ALLOWED_MODES = Set.of("cold_start", "steady_state");
    private static final Set<String> ALLOWED_OPERATIONS = Set.of("encrypt", "decrypt", "roundtrip");
    private static final Set<String> ALLOWED_ENCODINGS = Set.of("binary", "armored");
    private static final Pattern CHECKSUM_PATTERN = Pattern.compile("^sha256:[0-9a-fA-F]{64}$");

    private CommandParser() {
    }

    public static Command parse(byte[] data) {
        // First pass: confirm every required top-level field is present. Jackson
        // cannot distinguish a missing field from a zero/null value on its own.
        JsonNode root;
        try {
            root = MAPPER.readTree(data);
        } catch (Exception e) {
            throw new RunnerException(ExitCodes.CONFIG_ERROR, "command: invalid JSON: " + e.getMessage());
        }
        if (root == null || !root.isObject()) {
            throw new RunnerException(ExitCodes.CONFIG_ERROR, "command: expected a JSON object");
        }
        for (String f : REQUIRED_FIELDS) {
            if (!root.has(f)) {
                throw new RunnerException(ExitCodes.CONFIG_ERROR, "command: missing required field \"" + f + "\"");
            }
        }

        // Typed decode (rejects unknown fields at every level).
        Command cmd;
        try {
            cmd = MAPPER.treeToValue(root, Command.class);
        } catch (Exception e) {
            throw new RunnerException(ExitCodes.CONFIG_ERROR, "command: " + e.getMessage());
        }

        validate(cmd);
        return cmd;
    }

    /** Enforces the value constraints from the schema (violations are exit code 3, Req 19.6). */
    private static void validate(Command c) {
        if (!"run".equals(c.command())) {
            throw config("field 'command' must be 'run', got " + quote(c.command()));
        }
        if (isBlank(c.variantId())) {
            throw config("'variantId' must be a non-empty string");
        }
        if (!ALLOWED_MODES.contains(c.mode())) {
            throw config("'mode' must be one of cold_start|steady_state, got " + quote(c.mode()));
        }
        if (c.warmupIterations() == null || c.warmupIterations() < 0 || c.warmupIterations() > 100) {
            throw config("'warmupIterations' must be in [0,100], got " + c.warmupIterations());
        }
        if (c.concurrency() == null || c.concurrency() < 1) {
            throw config("'concurrency' must be >= 1, got " + c.concurrency());
        }
        if (!ALLOWED_ENCODINGS.contains(c.outputEncoding())) {
            throw config("'outputEncoding' must be one of binary|armored, got " + quote(c.outputEncoding()));
        }
        if (!ALLOWED_OPERATIONS.contains(c.operation())) {
            throw config("'operation' must be one of encrypt|decrypt|roundtrip, got " + quote(c.operation()));
        }
        CryptoProfile p = c.cryptoProfile();
        if (p == null) {
            throw config("'cryptoProfile' is required");
        }
        requireNonBlank("cryptoProfile.pubAlg", p.pubAlg());
        requireNonBlank("cryptoProfile.cipher", p.cipher());
        requireNonBlank("cryptoProfile.compression", p.compression());
        requireNonBlank("cryptoProfile.hash", p.hash());
        requireNonBlank("keySetPath", c.keySetPath());
        requireNonBlank("corpusPath", c.corpusPath());
        requireNonBlank("outputDir", c.outputDir());
        if (c.keySetChecksum() == null || !CHECKSUM_PATTERN.matcher(c.keySetChecksum()).matches()) {
            throw config("'keySetChecksum' must match sha256:<64 hex>, got " + quote(c.keySetChecksum()));
        }
        if (c.corpusChecksum() == null || !CHECKSUM_PATTERN.matcher(c.corpusChecksum()).matches()) {
            throw config("'corpusChecksum' must match sha256:<64 hex>, got " + quote(c.corpusChecksum()));
        }
    }

    private static void requireNonBlank(String name, String value) {
        if (isBlank(value)) {
            throw config(quote(name) + " must be a non-empty string");
        }
    }

    private static boolean isBlank(String s) {
        return s == null || s.trim().isEmpty();
    }

    private static String quote(String s) {
        return s == null ? "null" : "\"" + s + "\"";
    }

    private static RunnerException config(String detail) {
        return new RunnerException(ExitCodes.CONFIG_ERROR, "command: " + detail);
    }
}
