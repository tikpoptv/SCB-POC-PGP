package com.poc.pgp.crypto;

import com.poc.pgp.KeySet;
import com.poc.pgp.contract.CryptoProfile;
import org.bouncycastle.jce.provider.BouncyCastleProvider;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.security.Security;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * Real (no-mock) round-trip checks for the {@code java-stream-parallel} engine
 * against the shared repo Key_Set (Req 5.1, 15.2, 16.x, 24.2).
 */
class StreamParallelEngineTest {

    private static final Path KEYS = Paths.get("..", "..", "keys");

    private final StreamParallelEngine engine = new StreamParallelEngine();

    @BeforeAll
    static void registerBouncyCastle() {
        if (Security.getProvider(BouncyCastleProvider.PROVIDER_NAME) == null) {
            Security.addProvider(new BouncyCastleProvider());
        }
    }

    private static CryptoProfile profile(String pubAlg) {
        return new CryptoProfile(pubAlg, "AES-256", "ZLIB", "SHA-256");
    }

    @Test
    void variantIdMatchesContract() {
        assertEquals("java-stream-parallel", engine.variantId());
    }

    @Test
    void workerPoolSizeClampsToCpuCount() {
        int cpus = Runtime.getRuntime().availableProcessors();
        assertEquals(1, engine.workerPoolSize(0), "below 1 clamps to 1");
        assertEquals(1, engine.workerPoolSize(1));
        assertEquals(cpus, engine.workerPoolSize(cpus + 8), "above vCPU clamps to vCPU");
    }

    @Test
    void rsaRoundTripIsByteForByte() throws Exception {
        KeySet keys = KeySet.load(KEYS);
        byte[] plain = trickyPayload();

        ByteArrayOutputStream ct = new ByteArrayOutputStream();
        Timing encT = engine.encrypt(new ByteArrayInputStream(plain), ct, profile("RSA-2048"), keys);
        assertTrue(encT.totalNanos() > 0, "crypto must be timed");
        assertTrue(encT.breakdownConsistent());
        assertEquals(Timing.NOT_SEPARABLE, encT.asymNanos());

        ByteArrayOutputStream pt = new ByteArrayOutputStream();
        engine.decrypt(new ByteArrayInputStream(ct.toByteArray()), pt, profile("RSA-2048"), keys);

        assertArrayEquals(plain, pt.toByteArray());
    }

    @Test
    void curve25519RoundTripIsByteForByte() throws Exception {
        KeySet keys = KeySet.load(KEYS);
        byte[] plain = "ECDH path \r lone-CR and unicode ✓ é".getBytes(StandardCharsets.UTF_8);

        ByteArrayOutputStream ct = new ByteArrayOutputStream();
        engine.encrypt(new ByteArrayInputStream(plain), ct, profile("Curve25519"), keys);
        ByteArrayOutputStream pt = new ByteArrayOutputStream();
        engine.decrypt(new ByteArrayInputStream(ct.toByteArray()), pt, profile("Curve25519"), keys);

        assertArrayEquals(plain, pt.toByteArray());
    }

    @Test
    void loneCarriageReturnSurvivesRoundTrip() throws Exception {
        // The binary literal-data packet must NOT canonicalise a lone CR (the
        // text-mode bug that broke gpg interop). All three line-ending shapes
        // must come back unchanged.
        KeySet keys = KeySet.load(KEYS);
        byte[] plain = "a\rb\r\nc\nd".getBytes(StandardCharsets.US_ASCII);

        ByteArrayOutputStream ct = new ByteArrayOutputStream();
        engine.encrypt(new ByteArrayInputStream(plain), ct, profile("RSA-2048"), keys);
        ByteArrayOutputStream pt = new ByteArrayOutputStream();
        engine.decrypt(new ByteArrayInputStream(ct.toByteArray()), pt, profile("RSA-2048"), keys);

        assertArrayEquals(plain, pt.toByteArray());
    }

    @Test
    void largeInputRoundTripsViaStreaming() throws Exception {
        KeySet keys = KeySet.load(KEYS);
        byte[] plain = new byte[5 * 1024 * 1024 + 7]; // > buffer size, odd tail
        for (int i = 0; i < plain.length; i++) {
            plain[i] = (byte) (i * 31 + 7);
        }

        ByteArrayOutputStream ct = new ByteArrayOutputStream();
        engine.encrypt(new ByteArrayInputStream(plain), ct, profile("RSA-2048"), keys);
        ByteArrayOutputStream pt = new ByteArrayOutputStream();
        engine.decrypt(new ByteArrayInputStream(ct.toByteArray()), pt, profile("RSA-2048"), keys);

        assertArrayEquals(plain, pt.toByteArray());
    }

    @Test
    void unsupportedCipherIsRejected() throws Exception {
        KeySet keys = KeySet.load(KEYS);
        CryptoProfile bad = new CryptoProfile("RSA-2048", "ChaCha20", "ZLIB", "SHA-256");
        boolean threw = false;
        try {
            engine.encrypt(new ByteArrayInputStream(new byte[1]), new ByteArrayOutputStream(), bad, keys);
        } catch (UnsupportedProfileException e) {
            threw = true;
        }
        assertTrue(threw, "ChaCha20 is not supported and must raise UnsupportedProfileException");
    }

    /** All byte values plus every line-ending shape, to stress binary fidelity. */
    private static byte[] trickyPayload() {
        ByteArrayOutputStream b = new ByteArrayOutputStream();
        byte[] crlf = "x\r\ny\rz\n".getBytes(StandardCharsets.US_ASCII);
        b.writeBytes(crlf);
        for (int i = 0; i < 256; i++) {
            b.write(i);
        }
        b.writeBytes("\r".getBytes(StandardCharsets.US_ASCII)); // trailing lone CR
        return b.toByteArray();
    }
}
