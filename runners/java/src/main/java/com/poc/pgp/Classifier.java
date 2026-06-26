package com.poc.pgp;

import java.util.Optional;
import java.util.Set;

/**
 * File-type classification and output-naming rules (Req 32), shared with the
 * Benchmark_Harness ({@code harness/corpus.py}) and the Go runner
 * ({@code classify.go}): supported extensions are encrypted to
 * {@code "<name>.pgp"}, {@code .ctrl}/{@code .ctl} control files are skipped, and
 * any other extension is skipped with reason {@code "unsupported"}. Matching is
 * case-insensitive on the extension.
 *
 * <p>The shell (this task, 11.1) needs these rules to iterate the corpus. Task
 * 11.4 owns the canonical rule set across all Java variants and its jqwik
 * property tests (Property 3, task 11.6); this class is the shared
 * implementation those build on.
 */
public final class Classifier {

    /** How a file name maps onto the file-type rules (Req 32). */
    public enum Classification {
        /** Extension is in the supported allow-list; the file is encrypted (Req 32.1, 32.2). */
        SUPPORTED,
        /** A {@code .ctrl}/{@code .ctl} control file, never encrypted (Req 32.3). */
        SKIP,
        /** Any other extension; skipped with reason {@code "unsupported"} (Req 32.7). */
        UNSUPPORTED
    }

    /** Skip reasons recorded on a skipped operation (Req 32.3, 32.7). */
    public static final String SKIP_REASON_CONTROL_FILE = "control_file";
    public static final String SKIP_REASON_UNSUPPORTED = "unsupported";

    /** Real file types the benchmark encrypts (Req 32.1). */
    private static final Set<String> SUPPORTED_EXTENSIONS = Set.of(
            ".txt", ".xlsx", ".xls", ".csv", ".pdf", ".zip", ".7z", ".dat", ".gz");

    /** Control files that are never encrypted (Req 32.3). */
    private static final Set<String> SKIP_EXTENSIONS = Set.of(".ctrl", ".ctl");

    private Classifier() {
    }

    /** Lower-cased extension including the dot ({@code ""} if none), like Go's {@code filepath.Ext}. */
    public static String fileExtension(String name) {
        int slash = Math.max(name.lastIndexOf('/'), name.lastIndexOf('\\'));
        int dot = name.lastIndexOf('.');
        if (dot <= slash) {
            return "";
        }
        return name.substring(dot).toLowerCase();
    }

    /**
     * Classifies {@code name} as supported, skip ({@code .ctrl}/{@code .ctl}), or
     * unsupported. The check is case-insensitive; control files take precedence so
     * they are always skipped as control files rather than treated as unsupported.
     */
    public static Classification classify(String name) {
        String ext = fileExtension(name);
        if (SKIP_EXTENSIONS.contains(ext)) {
            return Classification.SKIP;
        }
        if (SUPPORTED_EXTENSIONS.contains(ext)) {
            return Classification.SUPPORTED;
        }
        return Classification.UNSUPPORTED;
    }

    /** The skip reason for a non-supported classification, or {@code null} for supported. */
    public static String skipReasonFor(Classification c) {
        return switch (c) {
            case SKIP -> SKIP_REASON_CONTROL_FILE;
            case UNSUPPORTED -> SKIP_REASON_UNSUPPORTED;
            case SUPPORTED -> null;
        };
    }

    /**
     * The encrypted output name for a supported file: the original name with
     * {@code ".pgp"} appended (Req 32.2). The full extension is preserved, so
     * {@code "report.pdf"} → {@code "report.pdf.pgp"} and a zip-of-many
     * {@code "bundle.zip"} → {@code "bundle.zip.pgp"} (Req 32.4). Empty when the
     * file is not a supported type (skip/unsupported).
     */
    public static Optional<String> outputName(String name) {
        if (classify(name) != Classification.SUPPORTED) {
            return Optional.empty();
        }
        return Optional.of(name + ".pgp");
    }
}
