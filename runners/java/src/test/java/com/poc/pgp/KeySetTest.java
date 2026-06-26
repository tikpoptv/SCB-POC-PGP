package com.poc.pgp;

import org.bouncycastle.jce.provider.BouncyCastleProvider;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;

import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.security.Security;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * Verifies the armored Key_Set loads via Bouncy Castle and that pubAlg → key-id
 * mapping/availability works (untimed key loading, Req 1.1, 4.1).
 */
class KeySetTest {

    private static final Path KEYS = Paths.get("..", "..", "keys");

    @BeforeAll
    static void registerBouncyCastle() {
        if (Security.getProvider(BouncyCastleProvider.PROVIDER_NAME) == null) {
            Security.addProvider(new BouncyCastleProvider());
        }
    }

    @Test
    void loadsRsaAndEccKeys() throws Exception {
        assertTrue(Files.isDirectory(KEYS), "expected repo keys/ dir at " + KEYS.toAbsolutePath());
        KeySet keys = KeySet.load(KEYS);

        assertTrue(keys.hasKeyFor("RSA-2048"));
        assertTrue(keys.hasKeyFor("RSA-4096"));
        assertTrue(keys.hasKeyFor("Curve25519"));
        assertFalse(keys.hasKeyFor("RSA-1024"));

        assertNotNull(keys.encryptionKey("RSA-2048"));
        assertNotNull(keys.secretKeyRingFor("RSA-2048"));
    }

    @Test
    void pubAlgAliasesMapToKeyId() {
        org.junit.jupiter.api.Assertions.assertEquals("rsa2048", KeySet.pubAlgToKeyId("RSA-2048"));
        org.junit.jupiter.api.Assertions.assertEquals("rsa4096", KeySet.pubAlgToKeyId("rsa4096"));
        org.junit.jupiter.api.Assertions.assertEquals("cv25519", KeySet.pubAlgToKeyId("Curve25519"));
        org.junit.jupiter.api.Assertions.assertNull(KeySet.pubAlgToKeyId("RSA-1024"));
    }
}
