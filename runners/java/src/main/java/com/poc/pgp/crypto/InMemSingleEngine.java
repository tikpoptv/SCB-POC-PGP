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

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.security.SecureRandom;
import java.security.Security;
import java.util.Date;
import java.util.Iterator;

/**
 * The {@code java-inmem-single} variant (task 12.2): loads the entire plaintext
 * into a {@code byte[]} before encrypting, then writes the full ciphertext from
 * memory (single-thread). This is the in-memory counterpart to
 * {@link StreamSingleEngine} and mirrors the Go runner's {@code go-inmem-single}
 * variant (design.md: "in-memory" row, Java column).
 *
 * <p>Only the OpenPGP transform is timed with {@link System#nanoTime()}; key
 * loading and file I/O are the shell's concern (Req 1.1, 24.1). Asym/sym times
 * are interleaved inside the pipeline and cannot be isolated, so the breakdown
 * is {@link Timing#NOT_SEPARABLE} (Req 24.2, 24.3).
 *
 * <p>The literal-data packet is written in BINARY format
 * ({@link PGPLiteralData#BINARY}), never text/UTF-8 mode. A text-mode literal
 * packet makes consumers such as {@code gpg} canonicalise line endings (a lone
 * CR is stripped), which breaks byte-for-byte interop (Req 25.1, 25.2).
 *
 * <p>{@link #workerPoolSize} returns {@code 1} (inherits the default) so the
 * shell runs files sequentially, consistent with the "single-thread" design
 * dimension (Req 6.3, 15.1).
 */
public final class InMemSingleEngine implements CryptoEngine {

    public static final String VARIANT_ID = "java-inmem-single";

    /** Buffer size for streaming the ciphertext out after in-memory encrypt. */
    private static final int WRITE_BUFFER = 64 * 1024;

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
     * sequentially (Req 6.3, 15.1).
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
     * Reads all plaintext bytes from {@code in} into a {@code byte[]}, then
     * encrypts in-memory and writes the ciphertext to {@code out}. Only the
     * encrypt call is timed (Req 1.1, 24.1); reading {@code in} and writing
     * {@code out} are the shell's I/O responsibility.
     */
    @Override
    public Timing encrypt(InputStream in, OutputStream out, CryptoProfile profile, KeySet keys)
            throws CryptoException {
        int cipher = mapCipher(profile.cipher());
        int compression = mapCompression(profile.compression());
        mapHash(profile.hash()); // validated; PGP encryption without signing does not use it
        PGPPublicKey recipient = keys.encryptionKey(profile.pubAlg());

        // Load the entire plaintext into memory before starting the timed region.
        byte[] plain;
        try {
            plain = in.readAllBytes();
        } catch (Exception e) {
            throw new CryptoException("inmem read plaintext: " + e.getMessage(), e);
        }

        // ------ TIMED REGION: OpenPGP transform only (Req 1.1, 24.1) ----------
        long start = System.nanoTime();
        try {
            ByteArrayOutputStream cipherBuf = new ByteArrayOutputStream(plain.length + 512);

            PGPEncryptedDataGenerator encGen = new PGPEncryptedDataGenerator(
                    new JcePGPDataEncryptorBuilder(cipher)
                            .setWithIntegrityPacket(true)
                            .setSecureRandom(new SecureRandom()));
            encGen.addMethod(new JcePublicKeyKeyEncryptionMethodGenerator(recipient)
                    .setProvider(BouncyCastleProvider.PROVIDER_NAME));

            PGPCompressedDataGenerator compGen = new PGPCompressedDataGenerator(compression);
            PGPLiteralDataGenerator litGen = new PGPLiteralDataGenerator();

            try (OutputStream encOut = encGen.open(cipherBuf, new byte[WRITE_BUFFER]);
                 OutputStream compOut = compGen.open(encOut, new byte[WRITE_BUFFER]);
                 // BINARY literal format ('b'): never text mode — preserves all byte values.
                 OutputStream litOut = litGen.open(compOut, PGPLiteralData.BINARY, "",
                         new Date(0L), new byte[WRITE_BUFFER])) {
                litOut.write(plain);
            }

            out.write(cipherBuf.toByteArray());
        } catch (Exception e) {
            throw new CryptoException("inmem encrypt: " + e.getMessage(), e);
        }
        long total = System.nanoTime() - start;
        // ------ END TIMED REGION ------------------------------------------------

        return new Timing(total, Timing.NOT_SEPARABLE, Timing.NOT_SEPARABLE,
                HardwareAccel.forCipher(profile.cipher()));
    }

    /**
     * Reads all ciphertext bytes from {@code in} into a {@code byte[]}, decrypts
     * in-memory, and writes the recovered plaintext to {@code out}. Only the
     * decrypt call is timed (Req 1.1, 24.1).
     */
    @Override
    public Timing decrypt(InputStream in, OutputStream out, CryptoProfile profile, KeySet keys)
            throws CryptoException {
        mapCipher(profile.cipher());
        mapCompression(profile.compression());
        mapHash(profile.hash());
        PGPSecretKeyRing secretRing = keys.secretKeyRingFor(profile.pubAlg());

        // Load the entire ciphertext into memory before starting the timed region.
        byte[] cipherBytes;
        try {
            cipherBytes = in.readAllBytes();
        } catch (Exception e) {
            throw new CryptoException("inmem read ciphertext: " + e.getMessage(), e);
        }

        // ------ TIMED REGION: OpenPGP transform only (Req 1.1, 24.1) ----------
        long start = System.nanoTime();
        try {
            JcaPGPObjectFactory factory =
                    new JcaPGPObjectFactory(PGPUtil.getDecoderStream(
                            new java.io.ByteArrayInputStream(cipherBytes)));
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

            // Default JCE resolution so AES is served by SunJCE (AES-NI).
            PublicKeyDataDecryptorFactory dataDecryptor =
                    new JcePublicKeyDataDecryptorFactoryBuilder().build(privateKey);

            ByteArrayOutputStream plainBuf = new ByteArrayOutputStream();
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
                    plainBuf.write(litIn.readAllBytes());
                }
            }

            out.write(plainBuf.toByteArray());
        } catch (Exception e) {
            throw new CryptoException("inmem decrypt: " + e.getMessage(), e);
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
