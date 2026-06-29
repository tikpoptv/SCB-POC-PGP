package com.poc.pgp.crypto;

import com.poc.pgp.KeySet;
import com.poc.pgp.contract.CryptoProfile;

import java.io.InputStream;
import java.io.OutputStream;

/**
 * The {@code java-native-stream-parallel} variant (task 11.3): the EXACT same
 * streaming + parallel OpenPGP engine as {@link StreamParallelEngine}, but
 * reported under the native Implementation_Variant id so the Result_Report can
 * label native vs JVM results separately (Req 22.4). It does real PGP
 * encrypt/decrypt identical to {@code java-stream-parallel}; the only difference
 * is that this variant id is served by the GraalVM Native Image binary
 * ({@code com.poc.pgp.NativeMain}), not the JVM (Req 22.1, 22.2).
 *
 * <p>It is a thin delegate over {@link StreamParallelEngine} so the crypto path
 * is provably the same code — keeping the native/JVM comparison honest.
 */
public final class NativeStreamParallelEngine implements CryptoEngine {

    public static final String VARIANT_ID = "java-native-stream-parallel";

    private final StreamParallelEngine delegate = new StreamParallelEngine();

    @Override
    public String variantId() {
        return VARIANT_ID;
    }

    @Override
    public int workerPoolSize(int concurrency) {
        return delegate.workerPoolSize(concurrency);
    }

    @Override
    public void supportsProfile(CryptoProfile profile) throws UnsupportedProfileException {
        delegate.supportsProfile(profile);
    }

    @Override
    public Timing encrypt(InputStream in, OutputStream out, CryptoProfile profile, KeySet keys)
            throws CryptoException {
        return delegate.encrypt(in, out, profile, keys);
    }

    @Override
    public Timing decrypt(InputStream in, OutputStream out, CryptoProfile profile, KeySet keys)
            throws CryptoException {
        return delegate.decrypt(in, out, profile, keys);
    }
}
