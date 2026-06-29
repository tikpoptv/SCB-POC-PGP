package com.poc.pgp.crypto;

import com.poc.pgp.KeySet;
import com.poc.pgp.contract.CryptoProfile;
import org.bouncycastle.bcpg.CompressionAlgorithmTags;
import org.bouncycastle.bcpg.HashAlgorithmTags;
import org.bouncycastle.bcpg.SymmetricKeyAlgorithmTags;
import org.bouncycastle.jce.provider.BouncyCastleProvider;
import org.bouncycastle.openpgp.PGPCompressedData;
import org.bouncycastle.openpgp.PGPCompressedDataGenerator;
import org.bouncycastle.openpgp.PGPEncryptedData;
import org.bouncycastle.openpgp.PGPEncryptedDataGenerator;
import org.bouncycastle.openpgp.PGPEncryptedDataList;
import org.bouncycastle.openpgp.PGPException;
import org.bouncycastle.openpgp.PGPLiteralData;
import org.bouncycastle.openpgp.PGPLiteralDataGenerator;
import org.bouncycastle.openpgp.PGPPrivateKey;
import org.bouncycastle.openpgp.PGPPublicKey;
import org.bouncycastle.openpgp.PGPPublicKeyEncryptedData;
import org.bouncycastle.openpgp.PGPSecretKey;
import org.bouncycastle.openpgp.PGPSecretKeyRing;
import org.bouncycastle.openpgp.PGPUtil;
import org.bouncycastle.openpgp.jcajce.JcaPGPObjectFactory;
import org.bouncycastle.openpgp.operator.PublicKeyDataDecryptorFactory;
import org.bouncycastle.openpgp.operator.jcajce.JcePBESecretKeyDecryptorBuilder;
import org.bouncycastle.openpgp.operator.jcajce.JcePGPDataEncryptorBuilder;
import org.bouncycastle.openpgp.operator.jcajce.JcePublicKeyDataDecryptorFactoryBuilder;
import org.bouncycastle.openpgp.operator.jcajce.JcePublicKeyKeyEncryptionMethodGenerator;

import java.io.InputStream;
import java.io.OutputStream;
import java.security.SecureRandom;
import java.security.Security;
import java.util.Date;
import java.util.Iterator;

/**
 * The {@code java-stream-single} variant (task 12.2): streams plaintext/ciphertext
 * through Bouncy Castle's OpenPGP generators with a fixed, reusable buffer so
 * peak memory does NOT grow with file size (O(1) buffer); processes files
 * sequentially (single-thread). This is the single-thread counterpart to
 * {@link StreamParallelEngine} and mirrors the Go runner's
 * {@code go-stream-single} variant (design.md: "streaming" row, Java column).
 *
 * <p>Only the OpenPGP transform is timed with {@link System#nanoTime()}; key
 * loading and file I/O are the shell's concern (Req 1.1, 24.1). Asym/sym times
 * are interleaved inside the streamed pipeline and cannot be isolated, so the
 * breakdown is {@link Timing#NOT_SEPARABLE} (Req 24.2, 24.3).
 *
 * <p>The literal-data packet is written in BINARY format
 * ({@link PGPLiteralData#BINARY}), never text/UTF-8 mode. A text-mode literal
 * packet makes consumers such as {@code gpg} canonicalise line endings (a lone
 * CR is stripped), which breaks byte-for-byte interop (Req 25.1, 25.2).
 *
 * <p>{@link #workerPoolSize} returns {@code 1} (inherits the default) so the
 * shell runs files sequentially, consistent with the "single-thread" design
 * dimension (Req 6.3, 15.1, 15.2).
 */
public final class StreamSingleEngine implements CryptoEngine {

    public static final String VARIANT_ID = "java-stream-single";

    /** Bounds peak memory per in-flight file, independent of file size (Req 15.2). */
    private static final int STREAM_BUFFER_SIZE = 64 * 1024;

    /** Empty passphrase: the POC Key_Set secret keys are unprotected (KEYINFO.md). */
    private static final char[] NO_PASSPHRASE = new char[0];

    static {
        if (Security.getProvider(BouncyCastleProvider.PROVIDER_NAME) == null) {
            Security.addProvider(new BouncyCastleProvider());
        }
    }

    @Override
    public String variantId() {
        return VARIANT_ID;
    }

    /**
     * Always 1: this is the single-thread variant; the shell runs files
     * sequentially (Req 6.3, 15.2).
     */
    @Override
    public int workerPoolSize(int concurrency) {
        return 1;
    }

    @Override
    public void supportsProfile(CryptoProfile profile) throws UnsupportedProfileException {
        mapCipher(profile.cipher());
        mapCompression(profile.compression());
        mapHash(profile.hash());
    }

    /**
     * Streams plaintext from {@code in} through the OpenPGP pipeline to
     * {@code out} using a fixed buffer. Peak memory is bounded by
     * {@link #STREAM_BUFFER_SIZE} regardless of file size (Req 15.2). Only the
     * encrypt call is timed (Req 1.1, 24.1).
     */
    @Override
    public Timing encrypt(InputStream in, OutputStream out, CryptoProfile profile, KeySet keys)
            throws CryptoException {
        int cipher = mapCipher(profile.cipher());
        int compression = mapCompression(profile.compression());
        mapHash(profile.hash()); // validated; PGP encryption without signing does not use it
        PGPPublicKey recipient = keys.encryptionKey(profile.pubAlg());

        // ------ TIMED REGION: OpenPGP transform only (Req 1.1, 24.1) ----------
        long start = System.nanoTime();
        try {
            PGPEncryptedDataGenerator encGen = new PGPEncryptedDataGenerator(
                    new JcePGPDataEncryptorBuilder(cipher)
                            .setWithIntegrityPacket(true)
                            .setSecureRandom(new SecureRandom()));
            encGen.addMethod(new JcePublicKeyKeyEncryptionMethodGenerator(recipient)
                    .setProvider(BouncyCastleProvider.PROVIDER_NAME));

            PGPCompressedDataGenerator compGen = new PGPCompressedDataGenerator(compression);
            PGPLiteralDataGenerator litGen = new PGPLiteralDataGenerator();

            // Nested close() flushes trailing ciphertext blocks inside the timed region.
            try (OutputStream encOut = encGen.open(out, new byte[STREAM_BUFFER_SIZE]);
                 OutputStream compOut = compGen.open(encOut, new byte[STREAM_BUFFER_SIZE]);
                 // BINARY literal format ('b'): never text mode — see class doc.
                 OutputStream litOut = litGen.open(compOut, PGPLiteralData.BINARY, "",
                         new Date(0L), new byte[STREAM_BUFFER_SIZE])) {
                copy(in, litOut);
            }
        } catch (Exception e) {
            throw new CryptoException("stream-single encrypt: " + e.getMessage(), e);
        }
        long total = System.nanoTime() - start;
        // ------ END TIMED REGION ------------------------------------------------

        return new Timing(total, Timing.NOT_SEPARABLE, Timing.NOT_SEPARABLE,
                HardwareAccel.forCipher(profile.cipher()));
    }

    /**
     * Streams ciphertext from {@code in} through the OpenPGP decrypt pipeline to
     * {@code out} using a fixed buffer. Peak memory is O(1) (Req 15.2). Only the
     * decrypt call is timed (Req 1.1, 24.1).
     */
    @Override
    public Timing decrypt(InputStream in, OutputStream out, CryptoProfile profile, KeySet keys)
            throws CryptoException {
        mapCipher(profile.cipher());
        mapCompression(profile.compression());
        mapHash(profile.hash());
        PGPSecretKeyRing secretRing = keys.secretKeyRingFor(profile.pubAlg());

        // ------ TIMED REGION: OpenPGP transform only (Req 1.1, 24.1) ----------
        long start = System.nanoTime();
        try {
            JcaPGPObjectFactory factory =
                    new JcaPGPObjectFactory(PGPUtil.getDecoderStream(in));
            PGPEncryptedDataList encList = nextEncryptedDataList(factory);

            PGPPublicKeyEncryptedData encData = null;
            PGPPrivateKey privateKey = null;
            for (Iterator<PGPEncryptedData> it = encList.getEncryptedDataObjects(); it.hasNext(); ) {
                PGPEncryptedData ed = it.next();
                if (!(ed instanceof PGPPublicKeyEncryptedData pked)) {
                    continue;
                }
                PGPSecretKey secretKey = secretRing.getSecretKey(pked.getKeyID());
                if (secretKey != null) {
                    privateKey = secretKey.extractPrivateKey(
                            new JcePBESecretKeyDecryptorBuilder()
                                    .setProvider(BouncyCastleProvider.PROVIDER_NAME)
                                    .build(NO_PASSPHRASE));
                    encData = pked;
                    break;
                }
            }
            if (encData == null || privateKey == null) {
                throw new PGPException("no matching secret key for ciphertext recipients");
            }

            // Default JCE resolution so AES is served by SunJCE (AES-NI) for
            // SEIPD-v1 and Bouncy Castle for modern AEAD ciphertext.
            PublicKeyDataDecryptorFactory dataDecryptor =
                    new JcePublicKeyDataDecryptorFactoryBuilder().build(privateKey);

            try (InputStream clear = encData.getDataStream(dataDecryptor)) {
                Object message = new JcaPGPObjectFactory(clear).nextObject();
                if (message instanceof PGPCompressedData compressed) {
                    message = new JcaPGPObjectFactory(compressed.getDataStream()).nextObject();
                }
                if (!(message instanceof PGPLiteralData literal)) {
                    throw new PGPException("unexpected OpenPGP packet: "
                            + (message == null ? "none" : message.getClass().getSimpleName()));
                }
                try (InputStream litIn = literal.getInputStream()) {
                    copy(litIn, out);
                }
            }
        } catch (Exception e) {
            throw new CryptoException("stream-single decrypt: " + e.getMessage(), e);
        }
        long total = System.nanoTime() - start;
        // ------ END TIMED REGION ------------------------------------------------

        return new Timing(total, Timing.NOT_SEPARABLE, Timing.NOT_SEPARABLE,
                HardwareAccel.forCipher(profile.cipher()));
    }

    private static PGPEncryptedDataList nextEncryptedDataList(JcaPGPObjectFactory factory)
            throws Exception {
        Object o = factory.nextObject();
        while (o != null && !(o instanceof PGPEncryptedDataList)) {
            o = factory.nextObject();
        }
        if (o == null) {
            throw new PGPException("no PGP encrypted-data packet found");
        }
        return (PGPEncryptedDataList) o;
    }

    private static void copy(InputStream in, OutputStream out) throws java.io.IOException {
        byte[] buf = new byte[STREAM_BUFFER_SIZE];
        int n;
        while ((n = in.read(buf)) != -1) {
            out.write(buf, 0, n);
        }
    }

    // ----- Crypto_Profile -> Bouncy Castle algorithm tags -------------------- //

    private static String normalize(String s) {
        return s == null ? "" : s.trim().toUpperCase().replace("-", "").replace("_", "").replace(" ", "");
    }

    private static int mapCipher(String cipher) throws UnsupportedProfileException {
        return switch (normalize(cipher)) {
            case "AES256" -> SymmetricKeyAlgorithmTags.AES_256;
            case "AES192" -> SymmetricKeyAlgorithmTags.AES_192;
            case "AES128" -> SymmetricKeyAlgorithmTags.AES_128;
            default -> throw new UnsupportedProfileException(
                    "unsupported cipher \"" + cipher + "\" (supported: AES-256, AES-192, AES-128)");
        };
    }

    private static int mapCompression(String compression) throws UnsupportedProfileException {
        return switch (normalize(compression)) {
            case "ZLIB" -> CompressionAlgorithmTags.ZLIB;
            case "ZIP" -> CompressionAlgorithmTags.ZIP;
            case "NONE", "" -> CompressionAlgorithmTags.UNCOMPRESSED;
            default -> throw new UnsupportedProfileException(
                    "unsupported compression \"" + compression + "\" (supported: ZLIB, ZIP, NONE)");
        };
    }

    private static int mapHash(String hash) throws UnsupportedProfileException {
        return switch (normalize(hash)) {
            case "SHA256" -> HashAlgorithmTags.SHA256;
            case "SHA384" -> HashAlgorithmTags.SHA384;
            case "SHA512" -> HashAlgorithmTags.SHA512;
            case "SHA224" -> HashAlgorithmTags.SHA224;
            default -> throw new UnsupportedProfileException(
                    "unsupported hash \"" + hash + "\" (supported: SHA-256, SHA-384, SHA-512, SHA-224)");
        };
    }
}
