package com.poc.pgp;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.DirectoryStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.stream.Stream;

/**
 * Aggregate checksum algorithms for the Key_Set and Test_Corpus. These reproduce
 * — byte-for-byte — the algorithms used by the Go runner ({@code checksum.go})
 * and the Python harness ({@code harness/keys.py}, {@code harness/corpus.py}), so
 * the verification gate agrees across all three implementations (Req 4.6). A
 * mismatch means the Runner saw different input than the harness intended, so the
 * run must not enter statistics (exit code 2).
 *
 * <p>This work happens before any crypto and is deliberately NOT timed (Req 1.1).
 */
public final class Checksum {

    private Checksum() {
    }

    /**
     * Reproduces the Key_Set aggregate checksum.
     *
     * <p>For every key file ({@code *-public.asc} / {@code *-private.asc}) it
     * builds a line {@code "<filename>:sha256:<hex>"}, sorts the lines, joins them
     * with {@code "\n"}, and returns the {@code "sha256:<hex>"} digest of that
     * text. Sorting makes the result independent of directory iteration order.
     */
    public static String computeKeySetChecksum(Path dir) throws IOException {
        List<String> lines = new ArrayList<>();
        try (DirectoryStream<Path> ds = Files.newDirectoryStream(dir)) {
            for (Path p : ds) {
                if (Files.isDirectory(p)) {
                    continue;
                }
                String name = p.getFileName().toString();
                if (!name.endsWith("-public.asc") && !name.endsWith("-private.asc")) {
                    continue;
                }
                lines.add(name + ":" + fileChecksum(p));
            }
        }
        lines.sort(Comparator.naturalOrder());
        String joined = String.join("\n", lines);
        return "sha256:" + sha256Hex(joined.getBytes(StandardCharsets.UTF_8));
    }

    /**
     * Reproduces the Test_Corpus aggregate checksum.
     *
     * <p>It walks every regular file under {@code root}, and for each (sorted by
     * POSIX-style relative path) feeds {@code "<relpath>\0<hex>\n"} into a single
     * SHA-256 hasher, where {@code <hex>} is the bare file digest (no
     * {@code "sha256:"} prefix). The result is the {@code "sha256:<hex>"} digest
     * of that stream.
     */
    public static String computeCorpusChecksum(Path root) throws IOException {
        List<Entry> entries = new ArrayList<>();
        try (Stream<Path> walk = Files.walk(root)) {
            for (Path p : (Iterable<Path>) walk::iterator) {
                if (Files.isDirectory(p)) {
                    continue;
                }
                String rel = toSlash(root.relativize(p).toString());
                entries.add(new Entry(rel, fileChecksumHex(p)));
            }
        }
        entries.sort(Comparator.comparing(Entry::rel));

        MessageDigest md = newSha256();
        for (Entry e : entries) {
            md.update(e.rel().getBytes(StandardCharsets.UTF_8));
            md.update((byte) 0);
            md.update(e.hex().getBytes(StandardCharsets.UTF_8));
            md.update((byte) '\n');
        }
        return "sha256:" + toHex(md.digest());
    }

    /**
     * Compares two {@code "sha256:<hex>"} strings case-insensitively on the hex
     * portion (the contract pattern allows upper- or lower-case hex).
     */
    public static boolean checksumEqual(String a, String b) {
        return a != null && a.equalsIgnoreCase(b);
    }

    /** {@code "sha256:<hex>"} digest of a file's bytes (streamed). */
    static String fileChecksum(Path path) throws IOException {
        return "sha256:" + fileChecksumHex(path);
    }

    /** Bare lower-case SHA-256 hex digest of a file's bytes, streamed. */
    static String fileChecksumHex(Path path) throws IOException {
        MessageDigest md = newSha256();
        byte[] buf = new byte[64 * 1024];
        try (InputStream in = Files.newInputStream(path)) {
            int n;
            while ((n = in.read(buf)) != -1) {
                md.update(buf, 0, n);
            }
        }
        return toHex(md.digest());
    }

    static String sha256Hex(byte[] data) {
        return toHex(newSha256().digest(data));
    }

    private static MessageDigest newSha256() {
        try {
            return MessageDigest.getInstance("SHA-256");
        } catch (NoSuchAlgorithmException e) {
            // SHA-256 is mandated on every JVM; this cannot happen in practice.
            throw new IllegalStateException("SHA-256 unavailable", e);
        }
    }

    private static String toHex(byte[] bytes) {
        StringBuilder sb = new StringBuilder(bytes.length * 2);
        for (byte b : bytes) {
            sb.append(Character.forDigit((b >> 4) & 0xF, 16));
            sb.append(Character.forDigit(b & 0xF, 16));
        }
        return sb.toString();
    }

    /** Normalises an OS path to POSIX-style separators (matches Go's filepath.ToSlash). */
    private static String toSlash(String path) {
        return path.replace('\\', '/');
    }

    private record Entry(String rel, String hex) {
    }
}
