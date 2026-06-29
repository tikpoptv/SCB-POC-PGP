package com.poc.pgp.crypto;

import com.poc.pgp.KeySet;
import com.poc.pgp.contract.CryptoProfile;
import net.jqwik.api.Arbitraries;
import net.jqwik.api.Arbitrary;
import net.jqwik.api.Combinators;
import net.jqwik.api.ForAll;
import net.jqwik.api.Property;
import net.jqwik.api.Provide;
import net.jqwik.api.lifecycle.BeforeContainer;
import org.bouncycastle.bcpg.ArmoredOutputStream;
import org.bouncycastle.bcpg.HashAlgorithmTags;
import org.bouncycastle.jce.provider.BouncyCastleProvider;
import org.bouncycastle.openpgp.PGPKeyPair;
import org.bouncycastle.openpgp.PGPKeyRingGenerator;
import org.bouncycastle.openpgp.PGPPublicKeyRing;
import org.bouncycastle.openpgp.PGPSecretKeyRing;
import org.bouncycastle.openpgp.PGPSignature;
import org.bouncycastle.openpgp.operator.PBESecretKeyEncryptor;
import org.bouncycastle.openpgp.operator.PGPContentSignerBuilder;
import org.bouncycastle.openpgp.operator.PGPDigestCalculator;
import org.bouncycastle.openpgp.operator.jcajce.JcaPGPKeyPair;
import org.bouncycastle.openpgp.operator.jcajce.JcaPGPContentSignerBuilder;
import org.bouncycastle.openpgp.operator.jcajce.JcaPGPDigestCalculatorProviderBuilder;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.SecureRandom;
import java.security.Security;
import java.util.Date;

import static org.junit.jupiter.api.Assertions.assertTrue;

// Feature: pgp-encryption-benchmark-go-java, Property 23: breakdown asym/sym สอดคล้องกับเวลารวม
//
// Validates: Requirements 24.2
//
// For any operation that reports both an asymmetric and a symmetric time, the
// two are non-negative and their sum does not exceed the total time (within
// measurement overhead). When the engine cannot isolate the two it records the
// NOT_SEPARABLE sentinel and makes no claim, so the invariant holds vacuously.
// The invariant lives in the pure Timing.breakdownConsistent() helper, which the
// real engine's output is also checked against.
class TimingBreakdownPropertyTest {

    /** In-memory generated key set written to a temp directory for test isolation. */
    private static Path IN_MEMORY_KEYS;

    @BeforeContainer
    static void registerBouncyCastleAndGenerateKeys() throws Exception {
        if (Security.getProvider(BouncyCastleProvider.PROVIDER_NAME) == null) {
            Security.addProvider(new BouncyCastleProvider());
        }
        // Generate a fresh RSA-2048 key pair in memory and export as armored ASC
        // files under a temporary directory — no dependency on repo key files.
        IN_MEMORY_KEYS = Files.createTempDirectory("timing-breakdown-keys-");
        generateAndWriteRsa2048KeyPair(IN_MEMORY_KEYS);
    }

    /**
     * Generates an RSA-2048 OpenPGP key pair entirely in memory (no passphrase,
     * matching the repo Key_Set convention in KEYINFO.md) and writes the armored
     * public and private rings as {@code rsa2048-public.asc} / {@code rsa2048-private.asc}
     * so that {@link KeySet#load} can parse them with the standard naming convention.
     */
    private static void generateAndWriteRsa2048KeyPair(Path dir) throws Exception {
        KeyPairGenerator kpg = KeyPairGenerator.getInstance("RSA", BouncyCastleProvider.PROVIDER_NAME);
        kpg.initialize(2048, new SecureRandom());
        KeyPair kp = kpg.generateKeyPair();

        PGPKeyPair pgpKp = new JcaPGPKeyPair(
                org.bouncycastle.bcpg.PublicKeyAlgorithmTags.RSA_GENERAL, kp, new Date());

        PGPDigestCalculator sha1Calc = new JcaPGPDigestCalculatorProviderBuilder()
                .build().get(HashAlgorithmTags.SHA1);
        PGPContentSignerBuilder signerBuilder = new JcaPGPContentSignerBuilder(
                pgpKp.getPublicKey().getAlgorithm(), HashAlgorithmTags.SHA256)
                .setProvider(BouncyCastleProvider.PROVIDER_NAME);
        // Unprotected secret key: no passphrase (mirrors KEYINFO.md convention).
        PBESecretKeyEncryptor noPassphrase = null;

        PGPKeyRingGenerator gen = new PGPKeyRingGenerator(
                PGPSignature.POSITIVE_CERTIFICATION,
                pgpKp,
                "test",
                sha1Calc,
                null,
                null,
                signerBuilder,
                noPassphrase);

        PGPPublicKeyRing pubRing = gen.generatePublicKeyRing();
        PGPSecretKeyRing secRing = gen.generateSecretKeyRing();

        // Write armored public key: rsa2048-public.asc
        try (OutputStream fout = Files.newOutputStream(dir.resolve("rsa2048-public.asc"));
             ArmoredOutputStream aout = new ArmoredOutputStream(fout)) {
            pubRing.encode(aout);
        }
        // Write armored private key: rsa2048-private.asc
        try (OutputStream fout = Files.newOutputStream(dir.resolve("rsa2048-private.asc"));
             ArmoredOutputStream aout = new ArmoredOutputStream(fout)) {
            secRing.encode(aout);
        }
    }

    /**
     * Plausible Timing values in both valid shapes: the NOT_SEPARABLE sentinel
     * (no claim) and a claimed breakdown whose asym+sym never exceeds the total.
     */
    @Provide
    Arbitrary<Timing> plausibleTimings() {
        Arbitrary<Boolean> hw = Arbitraries.of(true, false);

        Arbitrary<Timing> sentinel = Combinators.combine(
                Arbitraries.longs().between(0, 1_000_000_000L), hw)
                .as((total, h) -> new Timing(total, Timing.NOT_SEPARABLE, Timing.NOT_SEPARABLE, h));

        Arbitrary<Timing> claimed = Combinators.combine(
                Arbitraries.longs().between(0, 1_000_000_000L),
                Arbitraries.longs().between(0, 1_000_000_000L),
                Arbitraries.longs().between(0, 1_000_000L),
                hw)
                .as((asym, sym, overhead, h) -> {
                    long total = asym + sym + overhead;
                    if (total <= 0) {
                        total = 1;
                    }
                    return new Timing(total, asym, sym, h);
                });

        return Arbitraries.oneOf(sentinel, claimed);
    }

    @Property(tries = 200)
    void plausibleBreakdownIsConsistent(@ForAll("plausibleTimings") Timing t) {
        assertTrue(t.breakdownConsistent(),
                () -> "plausible timing must be consistent: " + t);
        // When the breakdown is actually claimed, re-state the invariant directly.
        if (t.asymNanos() != Timing.NOT_SEPARABLE && t.symNanos() != Timing.NOT_SEPARABLE) {
            assertTrue(t.asymNanos() >= 0 && t.symNanos() >= 0, "claimed parts must be non-negative");
            assertTrue(t.totalNanos() > 0, "claimed total must be positive");
            assertTrue(t.asymNanos() + t.symNanos() <= t.totalNanos(), "asym+sym must not exceed total");
        }
    }

    /**
     * The helper must REJECT an inconsistent claimed breakdown (asym+sym >
     * total). This keeps the property non-vacuous: the invariant can fail.
     */
    @Property(tries = 100)
    void inconsistentClaimedBreakdownIsRejected(
            @ForAll long asymRaw, @ForAll long symRaw, @ForAll long excessRaw) {
        long asym = Math.floorMod(asymRaw, 1_000_000L) + 1;
        long sym = Math.floorMod(symRaw, 1_000_000L) + 1;
        long excess = Math.floorMod(excessRaw, 1_000_000L) + 1;
        long total = asym + sym - excess; // strictly less than asym + sym
        Timing bad = new Timing(total, asym, sym, false);
        assertTrue(!bad.breakdownConsistent(),
                () -> "asym+sym exceeding total must be inconsistent: " + bad);
        // honest() must scrub the contradictory breakdown back to the sentinel.
        Timing scrubbed = bad.honest();
        assertTrue(scrubbed.asymNanos() == Timing.NOT_SEPARABLE
                && scrubbed.symNanos() == Timing.NOT_SEPARABLE, "honest() must drop a bad breakdown");
    }

    /**
     * The real java-stream-parallel engine: every Timing it returns must satisfy
     * the invariant. The engine reports NOT_SEPARABLE, so it holds vacuously, but
     * this guards against any future variant emitting an inconsistent breakdown.
     *
     * <p>Uses in-memory generated RSA-2048 keys (written to a temp dir in
     * {@link #registerBouncyCastleAndGenerateKeys}) for full test isolation —
     * no dependency on the repo key files (Req 24.2).
     */
    @Property(tries = 100)
    void realEngineTimingIsConsistentWithInMemoryKeys(@ForAll byte[] plain) throws Exception {
        // Load KeySet from in-memory generated keys (temp dir, isolated from repo).
        KeySet keys = KeySet.load(IN_MEMORY_KEYS);

        StreamParallelEngine engine = new StreamParallelEngine();
        // RSA-2048 is the key type generated in memory above.
        CryptoProfile profile = new CryptoProfile("RSA-2048", "AES-256", "ZLIB", "SHA-256");

        // Rule 4: totalNanos > 0 for real encrypt/decrypt operations.
        ByteArrayOutputStream ct = new ByteArrayOutputStream();
        Timing encT = engine.encrypt(new ByteArrayInputStream(plain), ct, profile, keys);
        assertTrue(encT.totalNanos() > 0, "encrypt totalNanos must be > 0 for a real operation");
        assertTrue(encT.breakdownConsistent(), () -> "encrypt breakdown inconsistent: " + encT);

        // Rule 2 & 3: asymNanos >= 0 and symNanos >= 0 when not NOT_SEPARABLE.
        // (The streaming engine reports NOT_SEPARABLE, so these hold vacuously here,
        //  but guard against future variants that do report a claimed breakdown.)
        if (encT.asymNanos() != Timing.NOT_SEPARABLE) {
            assertTrue(encT.asymNanos() >= 0, "asymNanos must be >= 0 when not NOT_SEPARABLE");
        }
        if (encT.symNanos() != Timing.NOT_SEPARABLE) {
            assertTrue(encT.symNanos() >= 0, "symNanos must be >= 0 when not NOT_SEPARABLE");
        }

        // Rule 1: asymNanos + symNanos <= totalNanos when both are claimed (not NOT_SEPARABLE).
        if (encT.asymNanos() != Timing.NOT_SEPARABLE && encT.symNanos() != Timing.NOT_SEPARABLE) {
            assertTrue(encT.asymNanos() + encT.symNanos() <= encT.totalNanos(),
                    () -> "encrypt: asymNanos + symNanos must be <= totalNanos: " + encT);
        }

        // Rule 4: totalNanos > 0 for decrypt as well.
        ByteArrayOutputStream pt = new ByteArrayOutputStream();
        Timing decT = engine.decrypt(new ByteArrayInputStream(ct.toByteArray()), pt, profile, keys);
        assertTrue(decT.totalNanos() > 0, "decrypt totalNanos must be > 0 for a real operation");
        assertTrue(decT.breakdownConsistent(), () -> "decrypt breakdown inconsistent: " + decT);

        if (decT.asymNanos() != Timing.NOT_SEPARABLE) {
            assertTrue(decT.asymNanos() >= 0, "decrypt asymNanos must be >= 0 when not NOT_SEPARABLE");
        }
        if (decT.symNanos() != Timing.NOT_SEPARABLE) {
            assertTrue(decT.symNanos() >= 0, "decrypt symNanos must be >= 0 when not NOT_SEPARABLE");
        }

        if (decT.asymNanos() != Timing.NOT_SEPARABLE && decT.symNanos() != Timing.NOT_SEPARABLE) {
            assertTrue(decT.asymNanos() + decT.symNanos() <= decT.totalNanos(),
                    () -> "decrypt: asymNanos + symNanos must be <= totalNanos: " + decT);
        }
    }
}
