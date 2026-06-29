package com.poc.pgp;

import com.poc.pgp.Classifier.Classification;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * Unit checks for the file-type classification / output-naming rules (Req 32).
 * Property 3 (jqwik) over the full input space is task 11.6.
 */
class ClassifierTest {

    @Test
    void supportedExtensionGetsPgpName() {
        assertEquals(Classification.SUPPORTED, Classifier.classify("report.pdf"));
        assertEquals("report.pdf.pgp", Classifier.outputName("report.pdf").orElseThrow());
    }

    @Test
    void zipOfManyKeepsFullExtension() {
        assertEquals("bundle.zip.pgp", Classifier.outputName("bundle.zip").orElseThrow());
    }

    @Test
    void controlFilesAreSkipped() {
        assertEquals(Classification.SKIP, Classifier.classify("batch.ctrl"));
        assertEquals(Classification.SKIP, Classifier.classify("batch.ctl"));
        assertEquals(Classifier.SKIP_REASON_CONTROL_FILE, Classifier.skipReasonFor(Classification.SKIP));
        assertTrue(Classifier.outputName("batch.ctrl").isEmpty());
    }

    @Test
    void unknownExtensionIsUnsupported() {
        assertEquals(Classification.UNSUPPORTED, Classifier.classify("notes.md"));
        assertEquals(Classifier.SKIP_REASON_UNSUPPORTED, Classifier.skipReasonFor(Classification.UNSUPPORTED));
    }

    @Test
    void classificationIsCaseInsensitive() {
        assertEquals(Classification.SUPPORTED, Classifier.classify("DATA.CSV"));
        assertEquals(Classification.SKIP, Classifier.classify("JOB.CTRL"));
    }

    @Test
    void everySupportedExtensionEncryptsToPgp() {
        for (String ext : new String[] {".txt", ".xlsx", ".xls", ".csv", ".pdf", ".zip", ".7z", ".dat", ".gz"}) {
            String name = "file" + ext;
            assertEquals(Classification.SUPPORTED, Classifier.classify(name), name);
            assertEquals(name + ".pgp", Classifier.outputName(name).orElseThrow(), name);
        }
    }

    @Test
    void fileWithoutExtensionIsUnsupported() {
        assertEquals(Classification.UNSUPPORTED, Classifier.classify("README"));
        assertTrue(Classifier.outputName("README").isEmpty());
    }
}
