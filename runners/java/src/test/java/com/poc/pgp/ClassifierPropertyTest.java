package com.poc.pgp;

import com.poc.pgp.Classifier.Classification;
import net.jqwik.api.Arbitraries;
import net.jqwik.api.Arbitrary;
import net.jqwik.api.ForAll;
import net.jqwik.api.Property;
import net.jqwik.api.Provide;

import java.util.Locale;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

// Feature: pgp-encryption-benchmark-go-java, Property 3: กฎการจำแนกชนิดไฟล์และการตั้งชื่อผลลัพธ์
//
// Validates: Requirements 32.2, 32.3, 32.4, 32.7
//
// For any file name: a supported extension (.txt .xlsx .xls .csv .pdf .zip .7z
// .dat .gz) maps to "<name>.pgp" (and a zip-of-many ".zip" to "<name>.zip.pgp");
// a .ctrl/.ctl control file is skipped (no encryption) with reason
// "control_file"; any other extension is skipped with reason "unsupported".
// Matching is case-insensitive on the extension.
class ClassifierPropertyTest {

    private static final String[] SUPPORTED =
            {".txt", ".xlsx", ".xls", ".csv", ".pdf", ".zip", ".7z", ".dat", ".gz"};
    private static final String[] SKIP = {".ctrl", ".ctl"};
    private static final String[] UNSUPPORTED =
            {".png", ".mp4", ".sh", ".docx", ".json", ".exe", ".md", ".bin", ".tar", ".log", ""};

    /** Non-empty base name, possibly with nested directory segments. */
    @Provide
    Arbitrary<String> baseName() {
        Arbitrary<String> seg = Arbitraries.strings()
                .withChars("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-")
                .ofMinLength(1).ofMaxLength(8);
        return seg.list().ofMinSize(1).ofMaxSize(3).map(parts -> String.join("/", parts));
    }

    /** Randomises the case of each character so matching stays case-insensitive. */
    private static Arbitrary<String> randomCase(String s) {
        return Arbitraries.of(Boolean.TRUE, Boolean.FALSE).list().ofSize(s.length())
                .map(flags -> {
                    StringBuilder b = new StringBuilder(s.length());
                    for (int i = 0; i < s.length(); i++) {
                        char c = s.charAt(i);
                        b.append(flags.get(i) ? Character.toUpperCase(c) : Character.toLowerCase(c));
                    }
                    return b.toString();
                });
    }

    @Property(tries = 200)
    void supportedExtensionGetsPgpName(@ForAll("baseName") String base,
                                       @ForAll("supportedExt") String ext) {
        String name = base + ext;
        assertEquals(Classification.SUPPORTED, Classifier.classify(name), name);
        assertEquals(name + ".pgp", Classifier.outputName(name).orElseThrow(), name);
        assertNull(Classifier.skipReasonFor(Classification.SUPPORTED));
        // zip-of-many: a .zip file must keep its full extension before .pgp.
        if (ext.toLowerCase(Locale.ROOT).equals(".zip")) {
            assertTrue(Classifier.outputName(name).orElseThrow().toLowerCase(Locale.ROOT)
                    .endsWith(".zip.pgp"), name);
        }
    }

    @Provide
    Arbitrary<String> supportedExt() {
        return Arbitraries.of(SUPPORTED).flatMap(ClassifierPropertyTest::randomCase);
    }

    @Property(tries = 100)
    void controlFilesAreSkipped(@ForAll("baseName") String base, @ForAll("skipExt") String ext) {
        String name = base + ext;
        assertEquals(Classification.SKIP, Classifier.classify(name), name);
        assertEquals(Classifier.SKIP_REASON_CONTROL_FILE,
                Classifier.skipReasonFor(Classifier.classify(name)), name);
        assertFalse(Classifier.outputName(name).isPresent(), name);
    }

    @Provide
    Arbitrary<String> skipExt() {
        return Arbitraries.of(SKIP).flatMap(ClassifierPropertyTest::randomCase);
    }

    @Property(tries = 100)
    void otherExtensionsAreUnsupported(@ForAll("baseName") String base, @ForAll("unsupportedExt") String ext) {
        String name = base + ext;
        assertEquals(Classification.UNSUPPORTED, Classifier.classify(name), name);
        assertEquals(Classifier.SKIP_REASON_UNSUPPORTED,
                Classifier.skipReasonFor(Classifier.classify(name)), name);
        assertFalse(Classifier.outputName(name).isPresent(), name);
    }

    @Provide
    Arbitrary<String> unsupportedExt() {
        return Arbitraries.of(UNSUPPORTED)
                .flatMap(ext -> ext.isEmpty() ? Arbitraries.just("") : randomCase(ext));
    }
}
