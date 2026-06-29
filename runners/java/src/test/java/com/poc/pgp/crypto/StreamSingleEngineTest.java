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
 * Real (no-mock) round-trip checks for the {@code java-stream-single} engine
 * against the shared repo Key_Set (Req 5.1, 15.2, 24.2).
 */
class StreamSingleEngineTest {

    private static final Path KEYS = Paths.get("..", "..", "keys");

    private final StreamSingleEngine engine = new StreamSingleEngine();

    @BeforeAll
    static void registerBouncyCastle() {
        if (Security.getProvider(BouncyCastleProvider.PROVIDER_NAME) == null) {
            Security.addProvider(new BouncyCastleProvider());
        }
    }

    private static CryptoProfile profile(String pubAlg) {
        return new CryptoProfile(pubAlg, "AES-256", "ZLIB", "SHA-256");
    }

    // ---- Contract ---------------------------------------------------------- //

    @Test
    void variantIdMatchesContract() {
        assertEquals("java-stream-single", engine.variantId());
    }

    /** Single-thread variant: workerPoolSize must always return 1 (Req 6.3). */
    @Test
    void workerPoolSizeIsAlwaysOne() {
        assertEquals(1, engine.workerPoolSize(0));
        assertEquals(1, engine.workerPoolSize(1));
        assertEquals(1, engine.workerPoolSize(8), "stream-single is always single-thread");
        assertEquals(1, engine.workerPoolSize(64));
    }

    // ---- Round-trip correctness --------------------------------------------- //

    @Test
    void rsaRoundTripIsByteForByte() throws Exception {
        KeySet keys = KeySet.load(KEYS);
        byte[] plain = trickyPayload();

        ByteArrayOutputStream ct = new ByteArrayOutputStream();
        Timing encT = engine.encrypt(new ByteArrayInputStream(plain), ct, profile("RSA-2048"), keys);

        assertTrue(encT.totalNanos() > 0, "crypto must be timed");
        assertTrue(encT.breakdownConsistent(), "timing breakdown must be consistent");
        assertEquals(Timing.NOT_SEPARABLE, encT.asymNanos(), "asym should be NOT_SEPARABLE");
        assertEquals(Timing.NOT_SEPARABLE, encT.symNanos(), "sym should be NOT_SEPARABLE");
        assertTrue(ct.size() > 0, "ciphertext must be produced");

        ByteArrayOutputStream pt = new ByteArrayOutputStream();
        Timing decT = engine.decrypt(new ByteArrayInputStream(ct.toByteArray()), pt, profile("RSA-2048"), keys);

        assertTrue(decT.totalNanos() > 0, "decrypt must be timed");
        assertArrayEquals(plain, pt.toByteArray(), "round-trip must recover original bytes");
    }

    @Test
    void rsa4096RoundTripIsByteForByte() throws Exception {
        KeySet keys = KeySet.load(KEYS);
        if (!keys.hasKeyFor("RSA-4096")) {
            return;
        }
        byte[] plain = "RSA-4096 stream-single test payload".getBytes(StandardCharsets.UTF_8);

        ByteArrayOutputStream ct = new ByteArrayOutputStream();
        engine.encrypt(new ByteArrayInputStream(plain), ct, profile("RSA-4096"), keys);
        ByteArrayOutputStream pt = new ByteArrayOutputStream();
        engine.decrypt(new ByteArrayInputStream(ct.toByteArray()), pt, profile("RSA-4096"), keys);

        assertArrayEquals(plain, pt.toByteArray());
    }

    @Test
    void curve25519RoundTripIsByteForByte() throws Exception {
        KeySet keys = KeySet.load(KEYS);
        if (!keys.hasKeyFor("Curve25519")) {
            return;
        }
        byte[] plain = "ECDH path \r lone-CR and unicode ✓ é".getBytes(StandardCharsets.UTF_8);

        ByteArrayOutputStream ct = new ByteArrayOutputStream();
        engine.encrypt(new ByteArrayInputStream(plain), ct, profile("Curve25519"), keys);
        ByteArrayOutputStream pt = new ByteArrayOutputStream();
        engine.decrypt(new ByteArrayInputStream(ct.toByteArray()), pt, profile("Curve25519"), keys);

        assertArrayEquals(plain, pt.toByteArray());
    }

    /** Empty file (0 bytes) must round-trip without crash (Req 5.1). */
    @Test
    void emptyPayloadRoundTrips() throws Exception {
        KeySet keys = KeySet.load(KEYS);
        byte[] plain = new byte[0];

        ByteArrayOutputStream ct = new ByteArrayOutputStream();
        Timing encT = engine.encrypt(new ByteArrayInputStream(plain), ct, profile("RSA-2048"), keys);

        assertTrue(encT.totalNanos() > 0, "even empty encrypt must be timed");
        assertTrue(ct.size() > 0, "ciphertext must be produced for empty plaintext");

        ByteArrayOutputStream pt = new ByteArrayOutputStream();
        engine.decrypt(new ByteArrayInputStream(ct.toByteArray()), pt, profile("RSA-2048"), keys);

        assertArrayEquals(plain, pt.toByteArray(), "empty round-trip must return empty");
    }

    /**
     * A lone CR in plaintext must survive unchanged — validates BINARY literal
     * format (not text mode).
     */
    @Test
    void loneCarriageReturnSurvivesRoundTrip() throws Exception {
        KeySet keys = KeySet.load(KEYS);
        byte[] plain = "a\rb\r\nc\nd".getBytes(StandardCharsets.US_ASCII);

        ByteArrayOutputStream ct = new ByteArrayOutputStream();
        engine.encrypt(new ByteArrayInputStream(plain), ct, profile("RSA-2048"), keys);
        ByteArrayOutputStream pt = new ByteArrayOutputStream();
        engine.decrypt(new ByteArrayInputStream(ct.toByteArray()), pt, profile("RSA-2048"), keys);

        assertArrayEquals(plain, pt.toByteArray());
    }

    /** All 256 byte values must survive the streaming round-trip. */
    @Test
    void allByteValuesSurviveRoundTrip() throws Exception {
        KeySet keys = KeySet.load(KEYS);
        byte[] plain = new byte[256];
        for (int i = 0; i < 256; i++) {
            plain[i] = (byte) i;
        }

        ByteArrayOutputStream ct = new ByteArrayOutputStream();
        engine.encrypt(new ByteArrayInputStream(plain), ct, profile("RSA-2048"), keys);
        ByteArrayOutputStream pt = new ByteArrayOutputStream();
        engine.decrypt(new ByteArrayInputStream(ct.toByteArray()), pt, profile("RSA-2048"), keys);

        assertArrayEquals(plain, pt.toByteArray());
    }

    /**
     * Large payload (>64 KB streaming buffer) must round-trip: stress-tests the
     * 64 KB buffer boundary that the streaming engine uses (Req 15.2).
     */
    @Test
    void largeInputRoundTripsViaStreaming() throws Exception {
        KeySet keys = KeySet.load(KEYS);
        byte[] plain = new byte[5 * 1024 * 1024 + 7]; // 5 MB + 7 bytes
        for (int i = 0; i < plain.length; i++) {
            plain[i] = (byte) (i * 31 + 7);
        }

        ByteArrayOutputStream ct = new ByteArrayOutputStream();
        engine.encrypt(new ByteArrayInputStream(plain), ct, profile("RSA-2048"), keys);
        ByteArrayOutputStream pt = new ByteArrayOutputStream();
        engine.decrypt(new ByteArrayInputStream(ct.toByteArray()), pt, profile("RSA-2048"), keys);

        assertArrayEquals(plain, pt.toByteArray());
    }

    /** No-compression profile must also produce correct round-trips. */
    @Test
    void noCompressionProfileRoundTrips() throws Exception {
        KeySet keys = KeySet.load(KEYS);
        byte[] plain = "no-compression stream-single test".getBytes(StandardCharsets.UTF_8);
        CryptoProfile noComp = new CryptoProfile("RSA-2048", "AES-256", "NONE", "SHA-256");

        ByteArrayOutputStream ct = new ByteArrayOutputStream();
        engine.encrypt(new ByteArrayInputStream(plain), ct, noComp, keys);
        ByteArrayOutputStream pt = new ByteArrayOutputStream();
        engine.decrypt(new ByteArrayInputStream(ct.toByteArray()), pt, noComp, keys);

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
        assertTrue(threw, "ChaCha20 must raise UnsupportedProfileException");
    }

    // ---- Interop with other variants (cross-variant round-trip gate, Req 25.1, 25.2) -- //

    /**
     * Ciphertext produced by {@code java-stream-single} must be decryptable by
     * {@code java-stream-parallel} (intra-language interop).
     */
    @Test
    void streamSingleEncryptedCiphertextDecryptableByStreamParallel() throws Exception {
        KeySet keys = KeySet.load(KEYS);
        byte[] plain = "stream-single → stream-parallel interop".getBytes(StandardCharsets.UTF_8);

        ByteArrayOutputStream ct = new ByteArrayOutputStream();
        engine.encrypt(new ByteArrayInputStream(plain), ct, profile("RSA-2048"), keys);

        StreamParallelEngine parallelEngine = new StreamParallelEngine();
        ByteArrayOutputStream pt = new ByteArrayOutputStream();
        parallelEngine.decrypt(new ByteArrayInputStream(ct.toByteArray()), pt, profile("RSA-2048"), keys);

        assertArrayEquals(plain, pt.toByteArray(),
                "java-stream-parallel must decrypt java-stream-single ciphertext");
    }

    /**
     * Ciphertext produced by {@code java-inmem-single} must be decryptable by
     * {@code java-stream-single} (cross-strategy interop).
     */
    @Test
    void inMemCiphertextDecryptableByStreamSingle() throws Exception {
        KeySet keys = KeySet.load(KEYS);
        byte[] plain = "inmem → stream-single interop".getBytes(StandardCharsets.UTF_8);

        InMemSingleEngine inMemEngine = new InMemSingleEngine();
        ByteArrayOutputStream ct = new ByteArrayOutputStream();
        inMemEngine.encrypt(new ByteArrayInputStream(plain), ct, profile("RSA-2048"), keys);

        ByteArrayOutputStream pt = new ByteArrayOutputStream();
        engine.decrypt(new ByteArrayInputStream(ct.toByteArray()), pt, profile("RSA-2048"), keys);

        assertArrayEquals(plain, pt.toByteArray(),
                "java-stream-single must decrypt java-inmem-single ciphertext");
    }

    /**
     * Ciphertext produced by {@code java-stream-single} must be decryptable by
     * {@code java-inmem-single} (reverse cross-strategy interop).
     */
    @Test
    void streamSingleCiphertextDecryptableByInMem() throws Exception {
        KeySet keys = KeySet.load(KEYS);
        byte[] plain = "stream-single → inmem interop".getBytes(StandardCharsets.UTF_8);

        ByteArrayOutputStream ct = new ByteArrayOutputStream();
        engine.encrypt(new ByteArrayInputStream(plain), ct, profile("RSA-2048"), keys);

        InMemSingleEngine inMemEngine = new InMemSingleEngine();
        ByteArrayOutputStream pt = new ByteArrayOutputStream();
        inMemEngine.decrypt(new ByteArrayInputStream(ct.toByteArray()), pt, profile("RSA-2048"), keys);

        assertArrayEquals(plain, pt.toByteArray(),
                "java-inmem-single must decrypt java-stream-single ciphertext");
    }

    /** All byte values + line endings — makes binary-fidelity test non-vacuous. */
    private static byte[] trickyPayload() {
        ByteArrayOutputStream b = new ByteArrayOutputStream();
        b.writeBytes("x\r\ny\rz\n".getBytes(StandardCharsets.US_ASCII));
        for (int i = 0; i < 256; i++) {
            b.write(i);
        }
        b.writeBytes("\r".getBytes(StandardCharsets.US_ASCII));
        return b.toByteArray();
    }
}
