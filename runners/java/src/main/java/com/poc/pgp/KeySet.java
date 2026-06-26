package com.poc.pgp;

import org.bouncycastle.bcpg.sig.KeyFlags;
import org.bouncycastle.openpgp.PGPException;
import org.bouncycastle.openpgp.PGPPublicKey;
import org.bouncycastle.openpgp.PGPPublicKeyRing;
import org.bouncycastle.openpgp.PGPPublicKeyRingCollection;
import org.bouncycastle.openpgp.PGPSecretKeyRing;
import org.bouncycastle.openpgp.PGPSecretKeyRingCollection;
import org.bouncycastle.openpgp.PGPSignature;
import org.bouncycastle.openpgp.PGPSignatureSubpacketVector;
import org.bouncycastle.openpgp.PGPUtil;
import org.bouncycastle.openpgp.operator.jcajce.JcaKeyFingerprintCalculator;

import java.io.IOException;
import java.io.InputStream;
import java.nio.file.DirectoryStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Iterator;
import java.util.LinkedHashMap;
import java.util.Map;

/**
 * Holds the shared OpenPGP keys loaded from the Key_Set directory via Bouncy
 * Castle. The same Key_Set is used by every Runner and variant within a Scenario
 * (Req 4.1). Loading and parsing the armored keys happens before any crypto and
 * is NOT timed (Req 1.1).
 *
 * <p>It mirrors the Go runner's {@code KeySet}: each {@code "<id>-public.asc"} /
 * {@code "<id>-private.asc"} pair on disk is keyed by its id prefix
 * ({@code rsa2048}, {@code rsa4096}, {@code cv25519}); a {@code Crypto_Profile}
 * {@code pubAlg} label is mapped onto that id.
 */
public final class KeySet {

    private final Path path;
    private final Map<String, PGPPublicKeyRing> publicByID = new LinkedHashMap<>();
    private final Map<String, PGPSecretKeyRing> secretByID = new LinkedHashMap<>();

    private KeySet(Path path) {
        this.path = path;
    }

    public Path path() {
        return path;
    }

    /**
     * Parses every {@code "<id>-public.asc"} / {@code "<id>-private.asc"} pair in
     * {@code dir}. The checksum gate (run before this) already confirmed the bytes
     * match the harness reference.
     */
    public static KeySet load(Path dir) throws IOException, PGPException {
        KeySet ks = new KeySet(dir);
        try (DirectoryStream<Path> ds = Files.newDirectoryStream(dir)) {
            for (Path p : ds) {
                if (Files.isDirectory(p)) {
                    continue;
                }
                String name = p.getFileName().toString();
                if (name.endsWith("-public.asc")) {
                    String id = name.substring(0, name.length() - "-public.asc".length());
                    ks.publicByID.put(id, readPublicKeyRing(p));
                } else if (name.endsWith("-private.asc")) {
                    String id = name.substring(0, name.length() - "-private.asc".length());
                    ks.secretByID.put(id, readSecretKeyRing(p));
                }
            }
        }
        if (ks.publicByID.isEmpty() && ks.secretByID.isEmpty()) {
            throw new IOException("no OpenPGP key files (*-public.asc/*-private.asc) found in " + dir);
        }
        return ks;
    }

    /**
     * Maps a {@code Crypto_Profile} public-key algorithm label onto the key file
     * id prefix on disk (see {@code keys/KEYINFO.md}), mirroring the Go runner.
     */
    public static String pubAlgToKeyId(String pubAlg) {
        String norm = pubAlg == null ? "" : pubAlg.trim().toUpperCase().replace('_', '-');
        return switch (norm) {
            case "RSA-2048", "RSA2048" -> "rsa2048";
            case "RSA-4096", "RSA4096" -> "rsa4096";
            case "CURVE25519", "ECC-CURVE25519", "CV25519", "ED25519", "ECC" -> "cv25519";
            default -> null;
        };
    }

    /** Reports whether the Key_Set can serve {@code pubAlg} (public AND secret present). */
    public boolean hasKeyFor(String pubAlg) {
        String id = pubAlgToKeyId(pubAlg);
        return id != null && publicByID.containsKey(id) && secretByID.containsKey(id);
    }

    /** The public key ring for {@code pubAlg}. */
    public PGPPublicKeyRing publicKeyRingFor(String pubAlg) {
        String id = requireId(pubAlg);
        PGPPublicKeyRing ring = publicByID.get(id);
        if (ring == null) {
            throw new IllegalArgumentException("no public key loaded for " + pubAlg + " (id " + id + ")");
        }
        return ring;
    }

    /** The secret key ring for {@code pubAlg}. */
    public PGPSecretKeyRing secretKeyRingFor(String pubAlg) {
        String id = requireId(pubAlg);
        PGPSecretKeyRing ring = secretByID.get(id);
        if (ring == null) {
            throw new IllegalArgumentException("no secret key loaded for " + pubAlg + " (id " + id + ")");
        }
        return ring;
    }

    /**
     * The encryption-capable public key for {@code pubAlg}: the first subkey
     * flagged for encryption, falling back to any encryption-capable key. Engines
     * use this as the OpenPGP recipient (Req 5.1).
     */
    public PGPPublicKey encryptionKey(String pubAlg) {
        PGPPublicKeyRing ring = publicKeyRingFor(pubAlg);
        PGPPublicKey fallback = null;
        for (Iterator<PGPPublicKey> it = ring.getPublicKeys(); it.hasNext(); ) {
            PGPPublicKey key = it.next();
            if (!key.isEncryptionKey()) {
                continue;
            }
            if (fallback == null) {
                fallback = key;
            }
            if (isFlaggedForEncryption(key)) {
                return key;
            }
        }
        if (fallback == null) {
            throw new IllegalStateException("no encryption-capable public key for " + pubAlg);
        }
        return fallback;
    }

    private String requireId(String pubAlg) {
        String id = pubAlgToKeyId(pubAlg);
        if (id == null) {
            throw new IllegalArgumentException("unknown public-key algorithm " + pubAlg);
        }
        return id;
    }

    private static boolean isFlaggedForEncryption(PGPPublicKey key) {
        for (Iterator<PGPSignature> sigs = key.getSignatures(); sigs.hasNext(); ) {
            PGPSignature sig = sigs.next();
            PGPSignatureSubpacketVector hashed = sig.getHashedSubPackets();
            if (hashed == null) {
                continue;
            }
            int flags = hashed.getKeyFlags();
            if ((flags & (KeyFlags.ENCRYPT_COMMS | KeyFlags.ENCRYPT_STORAGE)) != 0) {
                return true;
            }
        }
        return false;
    }

    private static PGPPublicKeyRing readPublicKeyRing(Path path) throws IOException, PGPException {
        try (InputStream in = PGPUtil.getDecoderStream(Files.newInputStream(path))) {
            PGPPublicKeyRingCollection coll =
                    new PGPPublicKeyRingCollection(in, new JcaKeyFingerprintCalculator());
            Iterator<PGPPublicKeyRing> rings = coll.getKeyRings();
            if (!rings.hasNext()) {
                throw new PGPException("no public key ring in " + path.getFileName());
            }
            return rings.next();
        }
    }

    private static PGPSecretKeyRing readSecretKeyRing(Path path) throws IOException, PGPException {
        try (InputStream in = PGPUtil.getDecoderStream(Files.newInputStream(path))) {
            PGPSecretKeyRingCollection coll =
                    new PGPSecretKeyRingCollection(in, new JcaKeyFingerprintCalculator());
            Iterator<PGPSecretKeyRing> rings = coll.getKeyRings();
            if (!rings.hasNext()) {
                throw new PGPException("no secret key ring in " + path.getFileName());
            }
            return rings.next();
        }
    }
}
