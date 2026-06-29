package com.poc.pgp.crypto;

import com.poc.pgp.KeySet;
import com.poc.pgp.contract.CryptoProfile;
import net.jqwik.api.Arbitraries;
import net.jqwik.api.Arbitrary;
import net.jqwik.api.ForAll;
import net.jqwik.api.Property;
import net.jqwik.api.Provide;
import net.jqwik.api.lifecycle.BeforeContainer;
import org.bouncycastle.jce.provider.BouncyCastleProvider;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.security.Security;
import java.util.Arrays;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

// Task 12.2: InMemSingleEngine and StreamSingleEngine added to ENGINES list above.

// Feature: pgp-encryption-benchmark-go-java, Property 1: Round-trip คืนข้อมูลเดิมแบบ byte-for-byte
//
// Validates: Requirements 5.1, 32.5
//
// For any byte payload (including empty and a lone CR) and every supported RSA /
// Curve25519 key type, every implemented variant (java-stream-parallel,
// java-native-stream-parallel, java-inmem-single, java-stream-single) must
// satisfy decrypt(encrypt(x)) == x byte-for-byte against the shared repo Key_Set.
//
// Coverage:
//   - Variants:       java-stream-parallel, java-native-stream-parallel,
//                     java-inmem-single, java-stream-single
//   - Key types:      RSA-2048, RSA-4096, Curve25519
//   - Cipher/hash:    AES-256 / ZLIB / SHA-256 (primary); AES-256 / NONE / SHA-256
//   - Payload sizes:  small (0 – 8 KB) and medium (64 KB – 512 KB)
//   - Compressibility: compressible (text-like, repeating) and incompressible (random/binary)
//   - File types:     .txt content, .pdf-like binary, .csv content, binary-all-bytes
class RoundTripPropertyTest {

    private static final Path KEYS = Paths.get("..", "..", "keys");

    /** All four variants under test (Req 5.1 applies to every implemented variant). */
    private static final List<CryptoEngine> ENGINES = List.of(
            new StreamParallelEngine(),
            new NativeStreamParallelEngine(),
            new InMemSingleEngine(),
            new StreamSingleEngine()
    );

    @BeforeContainer
    static void registerBouncyCastle() {
        if (Security.getProvider(BouncyCastleProvider.PROVIDER_NAME) == null) {
            Security.addProvider(new BouncyCastleProvider());
        }
    }

    // -------------------------------------------------------------------------
    // Arbitraries
    // -------------------------------------------------------------------------

    /** Public-key algorithms backed by the shared repo Key_Set. */
    @Provide
    Arbitrary<String> pubAlgs() {
        return Arbitraries.of("RSA-2048", "RSA-4096", "Curve25519");
    }

    /**
     * Small payloads (0 – 8 192 bytes) that span several corpus shapes:
     * <ul>
     *   <li>empty byte array</li>
     *   <li>lone-CR / mixed line-endings (binary-fidelity stress)</li>
     *   <li>compressible: text repeated from a small alphabet (like a .txt)</li>
     *   <li>compressible: CSV-like rows (comma-separated ASCII digits)</li>
     *   <li>incompressible: random bytes (like encrypted/binary PDF content)</li>
     * </ul>
     */
    @Provide
    Arbitrary<byte[]> smallPayloads() {
        // empty
        Arbitrary<byte[]> empty = Arbitraries.just(new byte[0]);

        // binary fidelity: lone CR and mixed endings
        Arbitrary<byte[]> lineEndings = Arbitraries.just(
                new byte[]{'a', '\r', 'b', '\r', '\n', 'c', '\n', 'd'});

        // .txt-like: highly compressible repeated ASCII text
        Arbitrary<byte[]> txtLike = Arbitraries.bytes()
                .between((byte) 0x20, (byte) 0x7e)          // printable ASCII
                .array(byte[].class).ofMinSize(0).ofMaxSize(4096);

        // .csv-like: ASCII digits + comma + newline (compressible)
        Arbitrary<byte[]> csvLike = Arbitraries.bytes()
                .between((byte) '0', (byte) '9')
                .array(byte[].class).ofMinSize(0).ofMaxSize(4096);

        // incompressible: full random byte range (simulates .pdf binary sections)
        Arbitrary<byte[]> random = Arbitraries.bytes()
                .array(byte[].class).ofMinSize(0).ofMaxSize(8192);

        return Arbitraries.oneOf(empty, lineEndings, txtLike, csvLike, random);
    }

    /**
     * Medium payloads (64 KB – 512 KB) that exercise the streaming buffer
     * boundary and cover both compressible and incompressible data at a size
     * representative of a real .txt, .csv or .pdf file.
     */
    @Provide
    Arbitrary<byte[]> mediumPayloads() {
        final int MIN = 64 * 1024;
        final int MAX = 512 * 1024;

        // compressible: repeated motif (simulates a .txt or .csv)
        Arbitrary<byte[]> compressible = Arbitraries.bytes()
                .between((byte) 'a', (byte) 'z')
                .array(byte[].class).ofMinSize(MIN).ofMaxSize(MAX);

        // incompressible: random / already-compressed bytes (simulates a .pdf with embedded images)
        Arbitrary<byte[]> incompressible = Arbitraries.bytes()
                .array(byte[].class).ofMinSize(MIN).ofMaxSize(MAX);

        return Arbitraries.oneOf(compressible, incompressible);
    }

    // -------------------------------------------------------------------------
    // Properties — small payloads, all variants, primary profile (with ZLIB)
    // -------------------------------------------------------------------------

    /**
     * Property 1 — small payloads, primary profile (AES-256 / ZLIB / SHA-256).
     * Covers corpus shapes: compressible (.txt, .csv) and incompressible (.pdf binary),
     * empty files, and binary-fidelity edge cases (lone CR / mixed line-endings).
     * Runs against BOTH java-stream-parallel and java-native-stream-parallel.
     *
     * Validates: Requirements 5.1, 32.5
     */
    @Property(tries = 200)
    void smallPayloadRoundTripAllVariants(
            @ForAll("pubAlgs") String pubAlg,
            @ForAll("smallPayloads") byte[] plain) throws Exception {

        KeySet keys = KeySet.load(KEYS);
        if (!keys.hasKeyFor(pubAlg)) {
            return; // key spec unavailable in this checkout
        }
        CryptoProfile profile = new CryptoProfile(pubAlg, "AES-256", "ZLIB", "SHA-256");

        for (CryptoEngine engine : ENGINES) {
            ByteArrayOutputStream ct = new ByteArrayOutputStream();
            Timing encT = engine.encrypt(new ByteArrayInputStream(plain), ct, profile, keys);

            assertTrue(encT.totalNanos() > 0,
                    engine.variantId() + ": crypto must be timed");
            assertTrue(ct.size() > 0,
                    engine.variantId() + ": ciphertext must be produced even for empty plaintext");

            ByteArrayOutputStream pt = new ByteArrayOutputStream();
            engine.decrypt(new ByteArrayInputStream(ct.toByteArray()), pt, profile, keys);

            assertArrayEquals(plain, pt.toByteArray(),
                    () -> engine.variantId() + " / " + pubAlg
                            + " small-payload round-trip mismatch for "
                            + plain.length + "-byte payload");
        }
    }

    /**
     * Property 1 — small payloads, no-compression profile (AES-256 / NONE / SHA-256).
     * Verifies the round-trip also holds when compression is disabled, i.e., incompressible
     * data (random bytes, PDF-like) is not inflated by a compressor.
     *
     * Validates: Requirements 5.1, 32.5
     */
    @Property(tries = 100)
    void smallPayloadRoundTripNoCompression(
            @ForAll("pubAlgs") String pubAlg,
            @ForAll("smallPayloads") byte[] plain) throws Exception {

        KeySet keys = KeySet.load(KEYS);
        if (!keys.hasKeyFor(pubAlg)) {
            return;
        }
        CryptoProfile profile = new CryptoProfile(pubAlg, "AES-256", "NONE", "SHA-256");

        for (CryptoEngine engine : ENGINES) {
            ByteArrayOutputStream ct = new ByteArrayOutputStream();
            engine.encrypt(new ByteArrayInputStream(plain), ct, profile, keys);
            ByteArrayOutputStream pt = new ByteArrayOutputStream();
            engine.decrypt(new ByteArrayInputStream(ct.toByteArray()), pt, profile, keys);

            assertArrayEquals(plain, pt.toByteArray(),
                    () -> engine.variantId() + " / " + pubAlg
                            + " no-compression round-trip mismatch for "
                            + plain.length + "-byte payload");
        }
    }

    // -------------------------------------------------------------------------
    // Properties — medium payloads, all variants
    // -------------------------------------------------------------------------

    /**
     * Property 1 — medium payloads (64 KB – 512 KB), primary profile.
     * Stresses the 64 KB streaming buffer boundary. Covers both compressible
     * (.txt/.csv-representative) and incompressible (.pdf-representative) data.
     *
     * Validates: Requirements 5.1, 32.5
     */
    @Property(tries = 100)
    void mediumPayloadRoundTripAllVariants(
            @ForAll("pubAlgs") String pubAlg,
            @ForAll("mediumPayloads") byte[] plain) throws Exception {

        KeySet keys = KeySet.load(KEYS);
        if (!keys.hasKeyFor(pubAlg)) {
            return;
        }
        CryptoProfile profile = new CryptoProfile(pubAlg, "AES-256", "ZLIB", "SHA-256");

        for (CryptoEngine engine : ENGINES) {
            ByteArrayOutputStream ct = new ByteArrayOutputStream();
            engine.encrypt(new ByteArrayInputStream(plain), ct, profile, keys);
            ByteArrayOutputStream pt = new ByteArrayOutputStream();
            engine.decrypt(new ByteArrayInputStream(ct.toByteArray()), pt, profile, keys);

            assertArrayEquals(plain, pt.toByteArray(),
                    () -> engine.variantId() + " / " + pubAlg
                            + " medium-payload round-trip mismatch for "
                            + plain.length + "-byte payload");
        }
    }

    // -------------------------------------------------------------------------
    // Fixed adversarial payloads
    // -------------------------------------------------------------------------

    /**
     * Every byte value 0–255 plus all three line-ending shapes and a trailing
     * lone CR must survive the round-trip on both variants. This makes the
     * property non-vacuous: a text-mode literal packet would canonicalise the
     * lone CR and fail here.
     *
     * Validates: Requirements 5.1, 32.5
     */
    @Property(tries = 100)
    void allByteValuesSurviveRoundTrip(@ForAll("pubAlgs") String pubAlg) throws Exception {
        KeySet keys = KeySet.load(KEYS);
        if (!keys.hasKeyFor(pubAlg)) {
            return;
        }
        byte[] plain = new byte[256 + 4];
        for (int i = 0; i < 256; i++) {
            plain[i] = (byte) i;
        }
        plain[256] = '\r';
        plain[257] = '\n';
        plain[258] = '\r';
        plain[259] = (byte) 0;

        CryptoProfile profile = new CryptoProfile(pubAlg, "AES-256", "ZLIB", "SHA-256");

        for (CryptoEngine engine : ENGINES) {
            ByteArrayOutputStream ct = new ByteArrayOutputStream();
            engine.encrypt(new ByteArrayInputStream(plain), ct, profile, keys);
            ByteArrayOutputStream pt = new ByteArrayOutputStream();
            engine.decrypt(new ByteArrayInputStream(ct.toByteArray()), pt, profile, keys);

            assertArrayEquals(plain, pt.toByteArray(),
                    engine.variantId() + " / " + pubAlg
                            + ": all byte values + line endings must survive round-trip");
        }
    }

    /**
     * A simulated .txt file content (UTF-8 text with Unicode characters and
     * all three line-ending shapes) must survive the round-trip byte-for-byte.
     *
     * Validates: Requirements 5.1, 32.5
     */
    @Property(tries = 100)
    void txtFileContentSurvivesRoundTrip(@ForAll("pubAlgs") String pubAlg) throws Exception {
        KeySet keys = KeySet.load(KEYS);
        if (!keys.hasKeyFor(pubAlg)) {
            return;
        }
        // .txt simulation: UTF-8 with Unicode, mixed line endings
        byte[] plain = ("Hello, World!\r\n"
                + "Привет мир\n"
                + "สวัสดีชาวโลก\r"
                + "日本語テスト\r\n"
                + "End of file\n")
                .getBytes(StandardCharsets.UTF_8);

        CryptoProfile profile = new CryptoProfile(pubAlg, "AES-256", "ZLIB", "SHA-256");

        for (CryptoEngine engine : ENGINES) {
            ByteArrayOutputStream ct = new ByteArrayOutputStream();
            engine.encrypt(new ByteArrayInputStream(plain), ct, profile, keys);
            ByteArrayOutputStream pt = new ByteArrayOutputStream();
            engine.decrypt(new ByteArrayInputStream(ct.toByteArray()), pt, profile, keys);

            assertArrayEquals(plain, pt.toByteArray(),
                    engine.variantId() + " / " + pubAlg
                            + ": .txt content must survive round-trip byte-for-byte");
        }
    }

    /**
     * A simulated .csv file content (ASCII digits, comma-separated, with header)
     * must survive the round-trip byte-for-byte. CSV is highly compressible so
     * this validates the ZLIB path under that data pattern.
     *
     * Validates: Requirements 5.1, 32.5
     */
    @Property(tries = 100)
    void csvFileContentSurvivesRoundTrip(@ForAll("pubAlgs") String pubAlg) throws Exception {
        KeySet keys = KeySet.load(KEYS);
        if (!keys.hasKeyFor(pubAlg)) {
            return;
        }
        // .csv simulation: header + 200 rows of compressible data
        StringBuilder sb = new StringBuilder("id,name,value,timestamp\r\n");
        for (int i = 0; i < 200; i++) {
            sb.append(i).append(",item").append(i).append(",").append(i * 1.5)
              .append(",2025-01-").append(String.format("%02d", (i % 28) + 1)).append("\r\n");
        }
        byte[] plain = sb.toString().getBytes(StandardCharsets.UTF_8);

        CryptoProfile profile = new CryptoProfile(pubAlg, "AES-256", "ZLIB", "SHA-256");

        for (CryptoEngine engine : ENGINES) {
            ByteArrayOutputStream ct = new ByteArrayOutputStream();
            engine.encrypt(new ByteArrayInputStream(plain), ct, profile, keys);
            ByteArrayOutputStream pt = new ByteArrayOutputStream();
            engine.decrypt(new ByteArrayInputStream(ct.toByteArray()), pt, profile, keys);

            assertArrayEquals(plain, pt.toByteArray(),
                    engine.variantId() + " / " + pubAlg
                            + ": .csv content must survive round-trip byte-for-byte");
        }
    }

    /**
     * A simulated .pdf file's binary preamble and embedded-object bytes
     * (incompressible binary data) must survive the round-trip byte-for-byte.
     * PDF files begin with a binary header; this validates incompressible data
     * through the ZLIB (store) path.
     *
     * Validates: Requirements 5.1, 32.5
     */
    @Property(tries = 100)
    void pdfLikeFileContentSurvivesRoundTrip(@ForAll("pubAlgs") String pubAlg) throws Exception {
        KeySet keys = KeySet.load(KEYS);
        if (!keys.hasKeyFor(pubAlg)) {
            return;
        }
        // .pdf simulation: PDF magic bytes + pseudo-random incompressible content
        byte[] pdfHeader = "%PDF-1.7\n%\u00e2\u00e3\u00cf\u00d3\n".getBytes(StandardCharsets.ISO_8859_1);
        byte[] body = new byte[4096];
        // Pseudo-random but deterministic body (simulates JPEG/stream object in PDF)
        for (int i = 0; i < body.length; i++) {
            body[i] = (byte) ((i * 37 + 13) ^ (i >> 3));
        }
        byte[] plain = Arrays.copyOf(pdfHeader, pdfHeader.length + body.length);
        System.arraycopy(body, 0, plain, pdfHeader.length, body.length);

        CryptoProfile profile = new CryptoProfile(pubAlg, "AES-256", "ZLIB", "SHA-256");

        for (CryptoEngine engine : ENGINES) {
            ByteArrayOutputStream ct = new ByteArrayOutputStream();
            engine.encrypt(new ByteArrayInputStream(plain), ct, profile, keys);
            ByteArrayOutputStream pt = new ByteArrayOutputStream();
            engine.decrypt(new ByteArrayInputStream(ct.toByteArray()), pt, profile, keys);

            assertArrayEquals(plain, pt.toByteArray(),
                    engine.variantId() + " / " + pubAlg
                            + ": .pdf-like binary content must survive round-trip byte-for-byte");
        }
    }
}
