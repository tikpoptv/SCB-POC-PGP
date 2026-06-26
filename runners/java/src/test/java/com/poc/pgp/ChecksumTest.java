package com.poc.pgp;

import org.junit.jupiter.api.Test;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * Verifies the Java aggregate checksum algorithms match the Go runner
 * byte-for-byte (Req 4.6). The reference values below were produced by the Go
 * runner ({@code runners/go/go-runner}) over this repository's {@code keys/} and
 * {@code corpus/} directories, so a match proves cross-implementation parity.
 */
class ChecksumTest {

    // Reference values emitted by the Go runner over the repo keys/ and corpus/.
    private static final String GO_KEYSET_CHECKSUM =
            "sha256:e969fac436ece096238575d673192a849a77dc77778e29c159d82aeb0eb15f11";
    private static final String GO_CORPUS_CHECKSUM =
            "sha256:e5512187e61437532e257ca2c8f1a7f51651aef8d1948cc48fb199c33e87a000";

    private static final Path KEYS = Paths.get("..", "..", "keys");
    private static final Path CORPUS = Paths.get("..", "..", "corpus");

    @Test
    void keySetChecksumMatchesGoRunner() throws IOException {
        assertTrue(Files.isDirectory(KEYS), "expected repo keys/ dir at " + KEYS.toAbsolutePath());
        assertEquals(GO_KEYSET_CHECKSUM, Checksum.computeKeySetChecksum(KEYS));
    }

    @Test
    void corpusChecksumMatchesGoRunner() throws IOException {
        assertTrue(Files.isDirectory(CORPUS), "expected repo corpus/ dir at " + CORPUS.toAbsolutePath());
        assertEquals(GO_CORPUS_CHECKSUM, Checksum.computeCorpusChecksum(CORPUS));
    }

    @Test
    void checksumEqualIsCaseInsensitiveOnHex() {
        assertTrue(Checksum.checksumEqual(
                "sha256:ABCDEF0000000000000000000000000000000000000000000000000000000000",
                "sha256:abcdef0000000000000000000000000000000000000000000000000000000000"));
    }
}
