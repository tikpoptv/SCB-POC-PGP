package com.poc.pgp.cli;

import com.poc.pgp.contract.Command;
import org.junit.jupiter.api.Test;

import java.nio.charset.StandardCharsets;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

/**
 * Verifies the Command parser accepts a valid command and rejects malformed /
 * out-of-range / unknown-field commands with config exit code 3 (Req 19.6).
 */
class CommandParserTest {

    private static final String CHECKSUM =
            "sha256:e969fac436ece096238575d673192a849a77dc77778e29c159d82aeb0eb15f11";

    private static String validJson() {
        return "{"
                + "\"command\":\"run\","
                + "\"variantId\":\"java-stream-parallel\","
                + "\"mode\":\"steady_state\","
                + "\"warmupIterations\":5,"
                + "\"concurrency\":4,"
                + "\"cryptoProfile\":{\"pubAlg\":\"RSA-2048\",\"cipher\":\"AES-256\",\"compression\":\"ZLIB\",\"hash\":\"SHA-256\"},"
                + "\"outputEncoding\":\"binary\","
                + "\"keySetPath\":\"../../keys\","
                + "\"keySetChecksum\":\"" + CHECKSUM + "\","
                + "\"corpusPath\":\"../../corpus\","
                + "\"corpusChecksum\":\"" + CHECKSUM + "\","
                + "\"outputDir\":\"/tmp/out\","
                + "\"operation\":\"roundtrip\""
                + "}";
    }

    private static Command parse(String json) {
        return CommandParser.parse(json.getBytes(StandardCharsets.UTF_8));
    }

    private static int exitCodeOf(String json) {
        RunnerException ex = assertThrows(RunnerException.class, () -> parse(json));
        return ex.exitCode();
    }

    @Test
    void parsesValidCommand() {
        Command cmd = parse(validJson());
        assertEquals("run", cmd.command());
        assertEquals("java-stream-parallel", cmd.variantId());
        assertEquals(4, cmd.concurrency());
        assertEquals("RSA-2048", cmd.cryptoProfile().pubAlg());
        assertEquals("rsa-2048_aes-256_zlib_sha-256", cmd.cryptoProfile().id());
    }

    @Test
    void rejectsInvalidJson() {
        assertEquals(ExitCodes.CONFIG_ERROR, exitCodeOf("{not json"));
    }

    @Test
    void rejectsMissingRequiredField() {
        String json = validJson().replace(",\"operation\":\"roundtrip\"", "");
        assertEquals(ExitCodes.CONFIG_ERROR, exitCodeOf(json));
    }

    @Test
    void rejectsUnknownField() {
        String json = validJson().replaceFirst("\\{", "{\"bogus\":1,");
        assertEquals(ExitCodes.CONFIG_ERROR, exitCodeOf(json));
    }

    @Test
    void rejectsBadCommandVerb() {
        assertEquals(ExitCodes.CONFIG_ERROR, exitCodeOf(validJson().replace("\"run\"", "\"sprint\"")));
    }

    @Test
    void rejectsOutOfRangeWarmup() {
        assertEquals(ExitCodes.CONFIG_ERROR, exitCodeOf(validJson().replace("\"warmupIterations\":5", "\"warmupIterations\":101")));
    }

    @Test
    void rejectsConcurrencyBelowOne() {
        assertEquals(ExitCodes.CONFIG_ERROR, exitCodeOf(validJson().replace("\"concurrency\":4", "\"concurrency\":0")));
    }

    @Test
    void rejectsBadMode() {
        assertEquals(ExitCodes.CONFIG_ERROR, exitCodeOf(validJson().replace("\"steady_state\"", "\"turbo\"")));
    }

    @Test
    void rejectsBadOutputEncoding() {
        assertEquals(ExitCodes.CONFIG_ERROR, exitCodeOf(validJson().replace("\"binary\"", "\"base64\"")));
    }

    @Test
    void rejectsBadChecksumPattern() {
        assertEquals(ExitCodes.CONFIG_ERROR, exitCodeOf(validJson().replace(CHECKSUM, "sha256:nothex")));
    }
}
