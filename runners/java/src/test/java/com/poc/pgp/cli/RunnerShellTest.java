package com.poc.pgp.cli;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.poc.pgp.KeySet;
import com.poc.pgp.contract.CryptoProfile;
import com.poc.pgp.crypto.CryptoEngine;
import com.poc.pgp.crypto.EngineRegistry;
import com.poc.pgp.crypto.Timing;
import org.bouncycastle.jce.provider.BouncyCastleProvider;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.security.Security;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * Exercises the CLI shell orchestration end-to-end (parse → checksum gate → key
 * load → engine dispatch → RunnerOutput emission), independent of any real
 * crypto variant. A passthrough {@link CryptoEngine} test double stands in for a
 * variant (the real {@code java-stream-parallel} is task 11.2) so this verifies
 * the shell, exit codes, and JSON contract shape (Req 1.1, 4.6, 4.7, 5.3, 24.1).
 */
class RunnerShellTest {

    private static final String KEYSET_CHECKSUM =
            "sha256:e969fac436ece096238575d673192a849a77dc77778e29c159d82aeb0eb15f11";
    private static final String CORPUS_CHECKSUM =
            "sha256:e5512187e61437532e257ca2c8f1a7f51651aef8d1948cc48fb199c33e87a000";
    private static final String BOGUS_CHECKSUM =
            "sha256:0000000000000000000000000000000000000000000000000000000000000000";

    private static final ObjectMapper MAPPER = new ObjectMapper();

    @BeforeAll
    static void registerBouncyCastle() {
        if (Security.getProvider(BouncyCastleProvider.PROVIDER_NAME) == null) {
            Security.addProvider(new BouncyCastleProvider());
        }
    }

    private static String command(String variantId, String keyChk, String corpusChk, Path outDir) {
        return "{"
                + "\"command\":\"run\","
                + "\"variantId\":\"" + variantId + "\","
                + "\"mode\":\"cold_start\","
                + "\"warmupIterations\":0,"
                + "\"concurrency\":1,"
                + "\"cryptoProfile\":{\"pubAlg\":\"RSA-2048\",\"cipher\":\"AES-256\",\"compression\":\"ZLIB\",\"hash\":\"SHA-256\"},"
                + "\"outputEncoding\":\"binary\","
                + "\"keySetPath\":\"../../keys\","
                + "\"keySetChecksum\":\"" + keyChk + "\","
                + "\"corpusPath\":\"../../corpus\","
                + "\"corpusChecksum\":\"" + corpusChk + "\","
                + "\"outputDir\":\"" + outDir.toString().replace("\\", "\\\\") + "\","
                + "\"operation\":\"roundtrip\""
                + "}";
    }

    private static int run(EngineRegistry registry, String json, ByteArrayOutputStream stdout) {
        InputStream stdin = new ByteArrayInputStream(json.getBytes(StandardCharsets.UTF_8));
        return new RunnerShell(registry).run(stdin, stdout);
    }

    @Test
    void successfulRoundtripEmitsRunnerOutput(@TempDir Path outDir) throws Exception {
        EngineRegistry registry = new EngineRegistry();
        registry.register(new PassthroughEngine());

        ByteArrayOutputStream stdout = new ByteArrayOutputStream();
        int code = run(registry, command("fake-passthrough", KEYSET_CHECKSUM, CORPUS_CHECKSUM, outDir), stdout);

        assertEquals(ExitCodes.SUCCESS, code);
        JsonNode out = MAPPER.readTree(stdout.toByteArray());
        assertEquals("java", out.get("runnerId").asText());
        assertEquals("fake-passthrough", out.get("variantId").asText());
        assertEquals("binary", out.get("outputEncoding").asText());
        assertEquals("rsa-2048_aes-256_zlib_sha-256", out.get("cryptoProfileId").asText());
        assertEquals(KEYSET_CHECKSUM, out.get("keySetChecksumSeen").asText());
        assertEquals(CORPUS_CHECKSUM, out.get("corpusChecksumSeen").asText());
        assertTrue(out.get("processStartupMs").isNumber(), "cold_start should report processStartupMs");

        JsonNode ops = out.get("operations");
        assertEquals(3, ops.size(), "corpus has 3 supported files");
        for (JsonNode op : ops) {
            assertFalse(op.get("skipped").asBoolean());
            assertTrue(op.get("roundTripOk").asBoolean(), "passthrough round-trips byte-for-byte");
            assertNotNull(op.get("outputFileName").asText());
            assertTrue(op.get("ciphertextBytes").asLong() >= 0);
            assertTrue(op.get("encryptMs").asDouble() >= 0);
            assertTrue(op.get("decryptMs").asDouble() >= 0);
        }
    }

    @Test
    void checksumMismatchExitsTwoWithNoStdout(@TempDir Path outDir) {
        EngineRegistry registry = new EngineRegistry();
        registry.register(new PassthroughEngine());

        ByteArrayOutputStream stdout = new ByteArrayOutputStream();
        int code = run(registry, command("fake-passthrough", BOGUS_CHECKSUM, CORPUS_CHECKSUM, outDir), stdout);

        assertEquals(ExitCodes.CHECKSUM_OR_VERSION_MISMATCH, code);
        assertEquals(0, stdout.size(), "no RunnerOutput on a failed gate");
    }

    @Test
    void unknownVariantExitsThree(@TempDir Path outDir) {
        EngineRegistry registry = new EngineRegistry(); // nothing registered
        ByteArrayOutputStream stdout = new ByteArrayOutputStream();
        int code = run(registry, command("does-not-exist", KEYSET_CHECKSUM, CORPUS_CHECKSUM, outDir), stdout);

        assertEquals(ExitCodes.CONFIG_ERROR, code);
        assertEquals(0, stdout.size());
    }

    @Test
    void invalidConfigExitsThree(@TempDir Path outDir) {
        EngineRegistry registry = new EngineRegistry();
        ByteArrayOutputStream stdout = new ByteArrayOutputStream();
        int code = run(registry, "{ not valid json", stdout);

        assertEquals(ExitCodes.CONFIG_ERROR, code);
        assertEquals(0, stdout.size());
    }

    /**
     * A test-only engine that copies bytes straight through, so an encrypt then
     * decrypt round-trips byte-for-byte. It is NOT a real variant — it exists only
     * to drive the shell orchestration in tests.
     */
    private static final class PassthroughEngine implements CryptoEngine {
        @Override
        public Timing encrypt(InputStream in, OutputStream out, CryptoProfile profile, KeySet keys) {
            return copyTimed(in, out);
        }

        @Override
        public Timing decrypt(InputStream in, OutputStream out, CryptoProfile profile, KeySet keys) {
            return copyTimed(in, out);
        }

        @Override
        public String variantId() {
            return "fake-passthrough";
        }

        private static Timing copyTimed(InputStream in, OutputStream out) {
            long start = System.nanoTime();
            try {
                in.transferTo(out);
            } catch (Exception e) {
                throw new RuntimeException(e);
            }
            return Timing.ofTotal(System.nanoTime() - start, false);
        }
    }
}
