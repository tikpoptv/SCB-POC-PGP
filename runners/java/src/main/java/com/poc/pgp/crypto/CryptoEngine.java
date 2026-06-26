package com.poc.pgp.crypto;

import com.poc.pgp.KeySet;
import com.poc.pgp.contract.CryptoProfile;

import java.io.InputStream;
import java.io.OutputStream;

/**
 * The contract every Java Implementation_Variant implements (design.md, Java
 * interface). {@link #encrypt}/{@link #decrypt} time ONLY the crypto call using
 * {@link System#nanoTime()}; key loading and file I/O are handled by the shell
 * and are not part of the returned {@link Timing} (Req 1.1, 24.1).
 *
 * <p>This is the exact shape from design.md:
 * <pre>{@code
 * public interface CryptoEngine {
 *     Timing encrypt(InputStream in, OutputStream out, CryptoProfile profile, KeySet keys) throws CryptoException;
 *     Timing decrypt(InputStream in, OutputStream out, CryptoProfile profile, KeySet keys) throws CryptoException;
 *     String variantId();
 * }
 * }</pre>
 *
 * <p>The concrete {@code java-stream-parallel} variant is task 11.2; น้อง's
 * {@code java-inmem-single}/{@code java-stream-single} variants are integrated
 * onto this same interface in task 12.2. Variants are discovered via the
 * {@link java.util.ServiceLoader} (declare them in
 * {@code META-INF/services/com.poc.pgp.crypto.CryptoEngine}).
 */
public interface CryptoEngine {

    /**
     * Encrypts {@code in} to {@code out}, returning crypto-only {@link Timing}.
     * Implementations MUST time only the OpenPGP transform, not the stream I/O
     * the shell wires around them (Req 1.1, 24.1).
     */
    Timing encrypt(InputStream in, OutputStream out, CryptoProfile profile, KeySet keys) throws CryptoException;

    /**
     * Decrypts {@code in} to {@code out}, returning crypto-only {@link Timing}
     * (Req 1.1, 24.1).
     */
    Timing decrypt(InputStream in, OutputStream out, CryptoProfile profile, KeySet keys) throws CryptoException;

    /** The unique Implementation_Variant identifier, e.g. {@code "java-stream-parallel"} (Req 6.1). */
    String variantId();

    /**
     * Optional: reject a {@link CryptoProfile} this engine cannot honour, mapping
     * to exit code 4 (Req 4.4, 18.5). The default accepts every profile; the
     * public-key algorithm is validated separately by the shell against the
     * loaded {@link KeySet}.
     */
    default void supportsProfile(CryptoProfile profile) throws UnsupportedProfileException {
        // Default: accept. Variants override to reject unsupported ciphers etc.
    }

    /**
     * Optional: how many corpus files this variant wants processed concurrently
     * for the commanded concurrency level (validated to {@code [1, vCPU]} by the
     * Harness). The default {@code 1} means sequential, file-by-file processing.
     * Parallel variants (e.g. {@code java-stream-parallel}, task 11.2) return the
     * commanded concurrency so the shell dispatches files across a worker pool
     * (Req 16.1, 16.2).
     */
    default int workerPoolSize(int concurrency) {
        return 1;
    }
}
