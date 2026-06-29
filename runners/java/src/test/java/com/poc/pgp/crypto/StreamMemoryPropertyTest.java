package com.poc.pgp.crypto;

// Feature: pgp-encryption-benchmark-go-java, Property 14: Streaming peak memory ไม่โตตามขนาดไฟล์
//
// Validates: Requirements 15.2
//
// For the streaming java-stream-parallel variant, growing the input size by
// large factors must NOT grow retained (live) memory proportionally: it stays
// roughly constant, bounded by a size-independent function of the fixed buffers
// rather than the file size — unlike an in-memory variant. The input is
// generated lazily (never materialised) and the ciphertext is discarded, so the
// only memory that could scale is memory the engine itself retains. Retained
// memory is sampled at the mid-point of the stream after a full GC, which
// filters out short-lived garbage and reflects the live working set.
//
// Keys are generated in-memory (not loaded from disk) for full test isolation.

import com.poc.pgp.KeySet;
import com.poc.pgp.contract.CryptoProfile;
import net.jqwik.api.Arbitraries;
import net.jqwik.api.Arbitrary;
import net.jqwik.api.ForAll;
import net.jqwik.api.Property;
import net.jqwik.api.Provide;
import net.jqwik.api.lifecycle.BeforeContainer;
import org.bouncycastle.bcpg.ArmoredOutputStream;
import org.bouncycastle.bcpg.HashAlgorithmTags;
import org.bouncycastle.jce.provider.BouncyCastleProvider;
import org.bouncycastle.openpgp.PGPEncryptedData;
import org.bouncycastle.openpgp.PGPKeyPair;
import org.bouncycastle.openpgp.PGPKeyRingGenerator;
import org.bouncycastle.openpgp.PGPPublicKeyRing;
import org.bouncycastle.openpgp.PGPSecretKeyRing;
import org.bouncycastle.openpgp.PGPSignature;
import org.bouncycastle.openpgp.operator.PGPDigestCalculator;
import org.bouncycastle.openpgp.operator.jcajce.JcaPGPContentSignerBuilder;
import org.bouncycastle.openpgp.operator.jcajce.JcaPGPDigestCalculatorProviderBuilder;
import org.bouncycastle.openpgp.operator.jcajce.JcaPGPKeyPair;
import org.bouncycastle.openpgp.operator.jcajce.JcePBESecretKeyEncryptorBuilder;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.lang.management.ManagementFactory;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyPairGenerator;
import java.security.SecureRandom;
import java.security.Security;
import java.util.Date;

import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * Property 14: Streaming peak memory ไม่โตตามขนาดไฟล์ (Java / jqwik)
 *
 * <p>Uses in-memory key generation for test isolation — no dependency on the
 * shared {@code keys/} directory on disk. Keys are generated once per JVM
 * run ({@link #setup()}) and reused across all iterations.
 *
 * <p>The property is non-vacuous: the {@link #inMemoryRetentionExceedsBound}
 * guard verifies that the fixed bound IS actually breached by a materialised
 * in-memory load at the same large size, while the streaming engine stays under
 * the bound. A streaming implementation that accidentally loaded everything into
 * memory would fail the property.
 *
 * <p>Validates: Requirements 15.2
 */
class StreamMemoryPropertyTest {

    // ── key storage (written once in setup()) ────────────────────────────────
    private static Path tempKeyDir;
    private static KeySet keySet;

    // ── size constants ────────────────────────────────────────────────────────

    /** Smallest payload tried by the property (1 MiB). */
    private static final int MIN_SIZE = 1 * 1024 * 1024;   // 1 MiB

    /**
     * Largest payload tried (16 MiB). Must exceed RETAINED_BOUND_BYTES so that
     * an in-memory implementation would breach the bound at this size.
     */
    private static final int MAX_SIZE = 16 * 1024 * 1024;  // 16 MiB

    /**
     * Size-independent ceiling on the streaming variant's retained heap. It sits
     * BELOW MAX_SIZE, so an implementation whose memory scaled with the file
     * (in-memory) would breach it at large sizes — making the property
     * discriminating, not vacuous (see {@link #inMemoryRetentionExceedsBound}).
     *
     * <p>Threshold is intentionally conservative (≈ 2× the 64 KiB × 3 nested
     * stream buffers) to absorb JVM / GC noise.
     */
    private static final long RETAINED_BOUND_BYTES = 12L * 1024 * 1024; // 12 MiB

    private final StreamParallelEngine engine = new StreamParallelEngine();

    // ── lifecycle ─────────────────────────────────────────────────────────────

    /**
     * jqwik lifecycle: initialises the shared key set before any property run.
     * The jqwik {@code @BeforeContainer} hook is called by the jqwik engine;
     * {@code @BeforeAll} covers the JUnit 5 {@code @Test} methods in the same
     * class. Both annotations are required for full lifecycle coverage.
     */
    @BeforeContainer
    @BeforeAll
    static void setup() throws Exception {
        if (Security.getProvider(BouncyCastleProvider.PROVIDER_NAME) == null) {
            Security.addProvider(new BouncyCastleProvider());
        }
        // Generate a fresh RSA-2048 key pair entirely in-memory, then write the
        // armored key files to a temp directory so KeySet.load() can read them.
        // This avoids any dependency on the shared keys/ directory on disk.
        tempKeyDir = Files.createTempDirectory("stream-mem-test-keys-");
        tempKeyDir.toFile().deleteOnExit();

        PGPKeyRingGenerator krGen = generateRsa2048KeyRingGenerator();

        PGPPublicKeyRing pubRing = krGen.generatePublicKeyRing();
        PGPSecretKeyRing secRing = krGen.generateSecretKeyRing();

        // Write armored public key as "rsa2048-public.asc"
        Path pubPath = tempKeyDir.resolve("rsa2048-public.asc");
        try (OutputStream fos = Files.newOutputStream(pubPath);
             ArmoredOutputStream armor = new ArmoredOutputStream(fos)) {
            pubRing.encode(armor);
        }

        // Write armored secret key as "rsa2048-private.asc"
        Path secPath = tempKeyDir.resolve("rsa2048-private.asc");
        try (OutputStream fos = Files.newOutputStream(secPath);
             ArmoredOutputStream armor = new ArmoredOutputStream(fos)) {
            secRing.encode(armor);
        }

        keySet = KeySet.load(tempKeyDir);
    }

    // ── property ──────────────────────────────────────────────────────────────

    @Provide
    Arbitrary<Integer> streamSizes() {
        return Arbitraries.integers().between(MIN_SIZE, MAX_SIZE);
    }

    /**
     * Property 14: for any file size in [1 MiB, 16 MiB], the streaming engine's
     * peak retained heap does not grow with file size — it stays below the fixed
     * {@link #RETAINED_BOUND_BYTES} threshold.
     *
     * <p>Growing file size by 16× (1 MiB → 16 MiB) must NOT grow retained
     * memory proportionally; if it did (O(N) memory), the bound would be breached
     * well before 12 MiB.
     */
    @Property(tries = 100)
    void streamingRetainedMemoryIsSizeIndependent(
            @ForAll("streamSizes") int size,
            @ForAll long seedRaw) throws Exception {

        long seed = seedRaw | 1L; // ensure non-zero for the xorshift generator
        long retained = measureStreamingRetained(size, seed);

        assertTrue(retained <= RETAINED_BOUND_BYTES, () -> String.format(
                "Streaming retained heap = %d bytes for input size %d bytes (%.1f MiB) "
                        + "exceeds the size-independent bound %d bytes (%.1f MiB). "
                        + "Peak memory must not grow with file size (Req 15.2, Property 14).",
                retained, size, size / (1024.0 * 1024.0),
                RETAINED_BOUND_BYTES, RETAINED_BOUND_BYTES / (1024.0 * 1024.0)));
    }

    // ── meaningfulness guard ──────────────────────────────────────────────────

    /**
     * Proves the bound is discriminating: an implementation that keeps the whole
     * file live (the in-memory shape) retains memory proportional to file size
     * and breaches the bound at MAX_SIZE, while the streaming engine stays under
     * it for the SAME size. Without this guard the property could pass vacuously
     * (i.e., the bound might be so large that even in-memory implementations
     * pass).
     */
    @Test
    void inMemoryRetentionExceedsBound() throws Exception {
        int size = MAX_SIZE; // 16 MiB > 12 MiB bound

        long streamRetained = measureStreamingRetained(size, 0x9E3779B97F4A7C15L);
        assertTrue(streamRetained <= RETAINED_BOUND_BYTES, () -> String.format(
                "Streaming retained heap = %d bytes at size %d MiB exceeded the "
                        + "bound %d bytes (%d MiB); the streaming implementation may have "
                        + "a memory regression.",
                streamRetained, size / (1024 * 1024),
                RETAINED_BOUND_BYTES, RETAINED_BOUND_BYTES / (1024 * 1024)));

        long inMemRetained = measureInMemoryRetained(size);
        assertTrue(inMemRetained > RETAINED_BOUND_BYTES, () -> String.format(
                "In-memory retained heap = %d bytes at size %d MiB did NOT exceed the "
                        + "bound %d bytes (%d MiB); the streaming property could pass vacuously "
                        + "(bound is too generous). Adjust RETAINED_BOUND_BYTES.",
                inMemRetained, size / (1024 * 1024),
                RETAINED_BOUND_BYTES, RETAINED_BOUND_BYTES / (1024 * 1024)));
    }

    // ── measurement helpers ───────────────────────────────────────────────────

    /**
     * Runs a streaming encrypt and samples retained heap at the stream mid-point.
     * The source is a lazy pseudo-random (incompressible) byte stream that never
     * materialises the whole payload — only the engine can accumulate live
     * objects proportional to file size.
     */
    private long measureStreamingRetained(int size, long seed) throws Exception {
        CryptoProfile profile = new CryptoProfile("RSA-2048", "AES-256", "ZLIB", "SHA-256");
        long baseline = quiescedUsedHeap();
        RetainedProbe probe = new RetainedProbe(baseline);
        PatternInputStream src = new PatternInputStream(size, seed, size / 2L, probe);
        CountingDiscardStream sink = new CountingDiscardStream();
        engine.encrypt(src, sink, profile, keySet);
        assertTrue(sink.count > 0, "encrypt must produce ciphertext");
        return probe.retained();
    }

    /**
     * Loads the whole input into a live {@code byte[]} (kept referenced for the
     * duration of the encrypt) and encrypts from it, sampling retained heap at
     * the mid-point — this is the in-memory shape, used by the discrimination
     * guard.
     */
    private long measureInMemoryRetained(int size) throws Exception {
        CryptoProfile profile = new CryptoProfile("RSA-2048", "AES-256", "ZLIB", "SHA-256");
        // Baseline BEFORE the file is materialised so the live array counts.
        long baseline = quiescedUsedHeap();
        byte[] whole = new byte[size];
        long s = 0x1234567ABCL;
        for (int i = 0; i < size; i++) {
            s ^= s << 13; s ^= s >>> 7; s ^= s << 17;
            whole[i] = (byte) s;
        }
        RetainedProbe probe = new RetainedProbe(baseline);
        InputStream backing = new ByteArrayInputStream(whole);
        InputStream probed = new ProbeAtMidpoint(backing, size, size / 2L, probe);
        CountingDiscardStream sink = new CountingDiscardStream();
        engine.encrypt(probed, sink, profile, keySet);
        // Keep `whole` reachable past the probe so it counts as retained.
        assertTrue(whole.length == size);
        return probe.retained();
    }

    /** Full GC × 2, then current used heap — a low-noise baseline for retained memory. */
    private static long quiescedUsedHeap() {
        System.gc();
        System.gc();
        return ManagementFactory.getMemoryMXBean().getHeapMemoryUsage().getUsed();
    }

    // ── key generation helpers ────────────────────────────────────────────────

    /**
     * Generates a self-signed RSA-2048 OpenPGP key ring (no passphrase) using
     * Bouncy Castle, entirely in-memory for test isolation.
     */
    private static PGPKeyRingGenerator generateRsa2048KeyRingGenerator() throws Exception {
        KeyPairGenerator kpGen = KeyPairGenerator.getInstance("RSA", BouncyCastleProvider.PROVIDER_NAME);
        kpGen.initialize(2048, new SecureRandom());
        java.security.KeyPair kp = kpGen.generateKeyPair();

        Date now = new Date();
        PGPKeyPair pgpKeyPair = new JcaPGPKeyPair(
                org.bouncycastle.bcpg.PublicKeyAlgorithmTags.RSA_GENERAL, kp, now);

        PGPDigestCalculator sha1Calc = new JcaPGPDigestCalculatorProviderBuilder()
                .build()
                .get(HashAlgorithmTags.SHA1);

        return new PGPKeyRingGenerator(
                PGPSignature.POSITIVE_CERTIFICATION,
                pgpKeyPair,
                "stream-mem-test@test.local",
                sha1Calc,
                null,
                null,
                new JcaPGPContentSignerBuilder(
                        pgpKeyPair.getPublicKey().getAlgorithm(),
                        HashAlgorithmTags.SHA256)
                        .setProvider(BouncyCastleProvider.PROVIDER_NAME),
                new JcePBESecretKeyEncryptorBuilder(PGPEncryptedData.AES_256, sha1Calc)
                        .setProvider(BouncyCastleProvider.PROVIDER_NAME)
                        .build(new char[0])); // no passphrase
    }

    // ── inner helpers ─────────────────────────────────────────────────────────

    /** Records retained heap (used-heap delta over a baseline) when fired once. */
    private static final class RetainedProbe {
        private final long baseline;
        private long retained = 0;
        private boolean fired = false;

        RetainedProbe(long baseline) {
            this.baseline = baseline;
        }

        void fire() {
            if (fired) {
                return;
            }
            fired = true;
            System.gc();
            System.gc();
            long used = ManagementFactory.getMemoryMXBean().getHeapMemoryUsage().getUsed();
            retained = Math.max(0, used - baseline);
        }

        long retained() {
            return retained;
        }
    }

    /**
     * Emits {@code total} pseudo-random (incompressible) bytes lazily via an
     * xorshift generator, never materialising more than one buffer at a time.
     * The retained probe is fired once after {@code probeAt} bytes have been
     * produced, so the only in-flight live objects at that point belong to the
     * engine itself.
     */
    private static final class PatternInputStream extends InputStream {
        private long remaining;
        private long produced = 0;
        private long state;
        private final long probeAt;
        private final RetainedProbe probe;

        PatternInputStream(long total, long seed, long probeAt, RetainedProbe probe) {
            this.remaining = total;
            this.state = seed;
            this.probeAt = probeAt;
            this.probe = probe;
        }

        @Override
        public int read() {
            if (remaining <= 0) {
                return -1;
            }
            remaining--;
            produced++;
            state ^= state << 13; state ^= state >>> 7; state ^= state << 17;
            maybeProbe();
            return (int) (state & 0xFF);
        }

        @Override
        public int read(byte[] b, int off, int len) {
            if (remaining <= 0) {
                return -1;
            }
            int n = (int) Math.min(len, remaining);
            long s = state;
            for (int i = 0; i < n; i++) {
                s ^= s << 13; s ^= s >>> 7; s ^= s << 17;
                b[off + i] = (byte) s;
            }
            state = s;
            remaining -= n;
            produced += n;
            maybeProbe();
            return n;
        }

        private void maybeProbe() {
            if (probe != null && produced >= probeAt) {
                probe.fire();
            }
        }
    }

    /** Wraps an InputStream, firing the probe once {@code probeAt} bytes are read. */
    private static final class ProbeAtMidpoint extends InputStream {
        private final InputStream in;
        private long read = 0;
        private final long probeAt;
        private final RetainedProbe probe;

        ProbeAtMidpoint(InputStream in, long total, long probeAt, RetainedProbe probe) {
            this.in = in;
            this.probeAt = probeAt;
            this.probe = probe;
        }

        @Override
        public int read() throws IOException {
            int b = in.read();
            if (b != -1 && ++read >= probeAt) {
                probe.fire();
            }
            return b;
        }

        @Override
        public int read(byte[] b, int off, int len) throws IOException {
            int n = in.read(b, off, len);
            if (n > 0) {
                read += n;
                if (read >= probeAt) {
                    probe.fire();
                }
            }
            return n;
        }
    }

    /** Discards everything written while counting the bytes. */
    private static final class CountingDiscardStream extends OutputStream {
        long count = 0;

        @Override
        public void write(int b) {
            count++;
        }

        @Override
        public void write(byte[] b, int off, int len) {
            count += len;
        }
    }
}
