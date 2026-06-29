package com.poc.pgp.cli;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.poc.pgp.Checksum;
import com.poc.pgp.Classifier;
import com.poc.pgp.KeySet;
import com.poc.pgp.contract.Command;
import com.poc.pgp.contract.OperationSample;
import com.poc.pgp.contract.RunnerOutput;
import com.poc.pgp.crypto.CryptoEngine;
import com.poc.pgp.crypto.CryptoException;
import com.poc.pgp.crypto.EngineRegistry;
import com.poc.pgp.crypto.Timing;
import com.poc.pgp.crypto.UnsupportedProfileException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.lang.management.ManagementFactory;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.stream.Stream;

/**
 * The runtime-neutral core of the Java_Runner CLI shell. It reads one Command
 * JSON from a stream, runs it end-to-end, and writes one RunnerOutput JSON to a
 * stream, mapping every failure to a contract exit code. It is a plain class (no
 * Spring) so it is fully unit-testable; the Spring Boot {@code CommandLineRunner}
 * merely delegates to {@link #run(InputStream, OutputStream)}.
 *
 * <p>Order of work mirrors the Go runner ({@code runner.go}):
 * <ol>
 *   <li>verify Key_Set / Test_Corpus checksums (NOT timed; Req 4.6 → exit 2)</li>
 *   <li>load the Key_Set (NOT timed; Req 1.1)</li>
 *   <li>resolve the variant engine and confirm it supports the profile (exit 3/4)</li>
 *   <li>for steady_state, run warm-up iterations whose samples are discarded</li>
 *   <li>process the corpus, timing ONLY the crypto calls via the engine (Req 1.1, 24.1)</li>
 * </ol>
 *
 * <p>GraalVM version (Req 22.3): {@link com.poc.pgp.NativeMain} sets the system
 * property {@link #GRAALVM_VERSION_PROP} before calling {@link #run} so that
 * this shell can stamp the actual GraalVM version into every
 * {@link com.poc.pgp.contract.RunnerOutput} it produces.
 */
public final class RunnerShell {

    private static final Logger log = LoggerFactory.getLogger(RunnerShell.class);

    /**
     * System-property key written by {@link com.poc.pgp.NativeMain} (and only
     * that entry point) to carry the actual GraalVM version string into the shell
     * without changing the RunnerShell constructor signature. Populated from
     * {@code java.vm.version} at native start-up; absent (null) on a JVM run.
     * The value ends up in {@link com.poc.pgp.contract.RunnerOutput#graalvmVersion}
     * for Req 22.3.
     */
    public static final String GRAALVM_VERSION_PROP = "com.poc.pgp.graalvmVersion";

    private final EngineRegistry registry;
    private final ObjectMapper mapper = new ObjectMapper();

    public RunnerShell(EngineRegistry registry) {
        this.registry = registry;
    }

    /**
     * Reads one Command from {@code stdin}, runs it, writes one RunnerOutput to
     * {@code stdout}, and returns the process exit code. Never throws — every
     * error is mapped to an exit code and logged to stderr.
     */
    public int run(InputStream stdin, OutputStream stdout) {
        byte[] data;
        try {
            data = stdin.readAllBytes();
        } catch (IOException e) {
            log.error("failed to read stdin: {}", e.toString());
            return ExitCodes.OPERATION_FAILURE;
        }

        try {
            Command cmd = CommandParser.parse(data);
            RunnerOutput output = execute(cmd);
            byte[] json = mapper.writeValueAsBytes(output);
            stdout.write(json);
            stdout.write('\n');
            stdout.flush();
            return ExitCodes.SUCCESS;
        } catch (RunnerException re) {
            log.error("error (exit {}): {}", re.exitCode(), re.getMessage());
            return re.exitCode();
        } catch (Exception e) {
            log.error("operation failure: {}", e.toString(), e);
            return ExitCodes.OPERATION_FAILURE;
        }
    }

    /** Executes a single validated Command and returns the RunnerOutput. */
    RunnerOutput execute(Command cmd) {
        Path keySetPath = Paths.get(cmd.keySetPath());
        Path corpusPath = Paths.get(cmd.corpusPath());

        // --- 1. Checksum gate (untimed; Req 4.6 → exit 2) ----------------------
        String keySeen = computeKeySetChecksum(keySetPath);
        if (!Checksum.checksumEqual(keySeen, cmd.keySetChecksum())) {
            throw new RunnerException(ExitCodes.CHECKSUM_OR_VERSION_MISMATCH,
                    "key-set checksum mismatch: expected " + cmd.keySetChecksum() + ", computed " + keySeen);
        }
        String corpusSeen = computeCorpusChecksum(corpusPath);
        if (!Checksum.checksumEqual(corpusSeen, cmd.corpusChecksum())) {
            throw new RunnerException(ExitCodes.CHECKSUM_OR_VERSION_MISMATCH,
                    "corpus checksum mismatch: expected " + cmd.corpusChecksum() + ", computed " + corpusSeen);
        }
        log.info("checksum gate passed (keySet={} corpus={})", keySeen, corpusSeen);

        // --- 2. Load Key_Set (untimed; Req 1.1) --------------------------------
        KeySet keys;
        try {
            keys = KeySet.load(keySetPath);
        } catch (Exception e) {
            throw new RunnerException(ExitCodes.OPERATION_FAILURE, "load key set: " + e.getMessage(), e);
        }
        if (!keys.hasKeyFor(cmd.cryptoProfile().pubAlg())) {
            throw new RunnerException(ExitCodes.UNSUPPORTED_CRYPTO_PROFILE,
                    "crypto-profile not supported: no key for pubAlg \"" + cmd.cryptoProfile().pubAlg() + "\"");
        }

        // --- 3. Resolve variant engine (exit 3 unknown / exit 4 unsupported) ---
        CryptoEngine engine = registry.get(cmd.variantId()).orElseThrow(() ->
                new RunnerException(ExitCodes.CONFIG_ERROR,
                        "unknown variantId \"" + cmd.variantId() + "\" (registered: "
                                + String.join(", ", registry.registeredVariants()) + ")"));
        try {
            engine.supportsProfile(cmd.cryptoProfile());
        } catch (UnsupportedProfileException e) {
            throw new RunnerException(ExitCodes.UNSUPPORTED_CRYPTO_PROFILE,
                    "crypto-profile not supported: " + e.getMessage());
        }

        List<CorpusFile> files = collectCorpusFiles(corpusPath);
        try {
            Files.createDirectories(Paths.get(cmd.outputDir()));
        } catch (IOException e) {
            throw new RunnerException(ExitCodes.OPERATION_FAILURE, "create output dir: " + e.getMessage(), e);
        }

        // Process_Startup_Time for cold_start: JVM uptime to the crypto-ready
        // point (covers JVM start, class loading and Spring init). Supplementary
        // cold-start metric, NOT merged into core/steady-state (Req 21.4, 21.7).
        Double processStartupMs = null;
        if ("cold_start".equals(cmd.mode())) {
            processStartupMs = (double) ManagementFactory.getRuntimeMXBean().getUptime();
        }

        // --- 4. Warm-up iterations (discarded; Req 8.6/8.7/17.1) ---------------
        for (int i = 0; i < cmd.warmupIterations(); i++) {
            processCorpus(engine, cmd, keys, files, false);
            log.info("warm-up iteration {}/{} complete", i + 1, cmd.warmupIterations());
        }

        // --- 5. Recorded pass (crypto-only timing) -----------------------------
        CorpusResult result = processCorpus(engine, cmd, keys, files, true);

        RunnerOutput out = new RunnerOutput();
        out.variantId = cmd.variantId();
        out.mode = cmd.mode();
        out.scenarioId = deriveScenarioId(corpusPath);
        out.cryptoProfileId = cmd.cryptoProfile().id();
        out.concurrency = cmd.concurrency();
        out.outputEncoding = cmd.outputEncoding();
        out.processStartupMs = processStartupMs;
        out.hardwareAccel = result.hardwareAccel;
        out.graalvmVersion = System.getProperty(GRAALVM_VERSION_PROP); // null for JVM; set by NativeMain (Req 22.3)
        out.keySetChecksumSeen = keySeen;
        out.corpusChecksumSeen = corpusSeen;
        out.gc = null; // JVM GC stats are added by a later task.
        out.operations = result.samples;
        return out;
    }

    // ----- corpus processing ------------------------------------------------- //

    private record CorpusFile(Path abs, String rel) {
    }

    private static final class CorpusResult {
        final List<OperationSample> samples;
        final boolean hardwareAccel;

        CorpusResult(List<OperationSample> samples, boolean hardwareAccel) {
            this.samples = samples;
            this.hardwareAccel = hardwareAccel;
        }
    }

    private List<CorpusFile> collectCorpusFiles(Path root) {
        List<CorpusFile> files = new ArrayList<>();
        try (Stream<Path> walk = Files.walk(root)) {
            for (Path p : (Iterable<Path>) walk::iterator) {
                if (Files.isDirectory(p)) {
                    continue;
                }
                String rel = root.relativize(p).toString().replace('\\', '/');
                files.add(new CorpusFile(p, rel));
            }
        } catch (IOException e) {
            throw new RunnerException(ExitCodes.OPERATION_FAILURE, "scan corpus: " + e.getMessage(), e);
        }
        files.sort(Comparator.comparing(CorpusFile::rel));
        return files;
    }

    /**
     * Runs the requested operation over every file. Engines that opt into a
     * worker pool ({@link CryptoEngine#workerPoolSize}) are driven across that
     * many threads (Req 16.1, 16.2); others run sequentially. Either way the
     * recorded samples are emitted in deterministic corpus order.
     */
    private CorpusResult processCorpus(CryptoEngine engine, Command cmd, KeySet keys,
                                       List<CorpusFile> files, boolean record) {
        int workers = Math.max(1, engine.workerPoolSize(cmd.concurrency()));
        if (workers == 1 || files.size() <= 1) {
            return processSequential(engine, cmd, keys, files, record);
        }
        return processParallel(engine, cmd, keys, files, record, workers);
    }

    private CorpusResult processSequential(CryptoEngine engine, Command cmd, KeySet keys,
                                           List<CorpusFile> files, boolean record) {
        List<OperationSample> ops = new ArrayList<>();
        boolean hwAccel = false;
        for (CorpusFile f : files) {
            FileResult r = processFile(engine, cmd, keys, f);
            hwAccel |= r.hardwareAccel;
            if (record) {
                ops.add(r.sample);
            }
        }
        return new CorpusResult(ops, hwAccel);
    }

    private CorpusResult processParallel(CryptoEngine engine, Command cmd, KeySet keys,
                                         List<CorpusFile> files, boolean record, int workers) {
        ExecutorService pool = Executors.newFixedThreadPool(workers);
        try {
            List<Future<FileResult>> futures = new ArrayList<>(files.size());
            for (CorpusFile f : files) {
                Callable<FileResult> task = () -> processFile(engine, cmd, keys, f);
                futures.add(pool.submit(task));
            }
            List<OperationSample> ops = new ArrayList<>();
            boolean hwAccel = false;
            for (Future<FileResult> future : futures) {
                FileResult r;
                try {
                    r = future.get();
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    throw new RunnerException(ExitCodes.OPERATION_FAILURE, "corpus processing interrupted", e);
                } catch (ExecutionException e) {
                    Throwable cause = e.getCause() != null ? e.getCause() : e;
                    throw new RunnerException(ExitCodes.OPERATION_FAILURE,
                            "corpus processing failed: " + cause.getMessage(), cause);
                }
                hwAccel |= r.hardwareAccel;
                if (record) {
                    ops.add(r.sample);
                }
            }
            return new CorpusResult(ops, hwAccel);
        } finally {
            pool.shutdown();
        }
    }

    private record FileResult(OperationSample sample, boolean hardwareAccel) {
    }

    private FileResult processFile(CryptoEngine engine, Command cmd, KeySet keys, CorpusFile f) {
        OperationSample sample = new OperationSample();
        sample.fileName = f.rel();
        sample.fileType = Classifier.fileExtension(f.rel());
        try {
            sample.originalBytes = Files.size(f.abs());
        } catch (IOException e) {
            throw new RunnerException(ExitCodes.OPERATION_FAILURE, "stat " + f.rel() + ": " + e.getMessage(), e);
        }
        sample.roundTripOk = false;

        // File-type classification (Req 32): control files and unsupported
        // extensions are skipped before any crypto.
        Classifier.Classification cls = Classifier.classify(f.rel());
        if (cls != Classifier.Classification.SUPPORTED) {
            sample.skipped = true;
            sample.skipReason = Classifier.skipReasonFor(cls);
            return new FileResult(sample, false);
        }

        return switch (cmd.operation()) {
            case "encrypt" -> doEncryptOnly(engine, cmd, keys, f, sample);
            case "decrypt" -> doDecryptOnly(engine, cmd, keys, f, sample);
            default -> doRoundtrip(engine, cmd, keys, f, sample);
        };
    }

    private FileResult doRoundtrip(CryptoEngine engine, Command cmd, KeySet keys, CorpusFile f, OperationSample sample) {
        String outName = Classifier.outputName(f.rel()).orElseThrow();
        sample.outputFileName = outName;
        Path ctPath = Paths.get(cmd.outputDir()).resolve(outName);
        Path decPath = ctPath.resolveSibling(ctPath.getFileName() + ".dec");

        Timing encT;
        try {
            EncryptResult er = encryptToFile(engine, cmd, keys, f.abs(), ctPath);
            encT = er.timing;
            applyEncryptTiming(sample, encT);
            sample.ciphertextBytes = er.ciphertextBytes;
        } catch (Exception e) {
            markFailure(sample, OperationSample.FAILURE_OPERATION);
            log.warn("encrypt failed for {}: {}", f.rel(), e.toString());
            return new FileResult(sample, false);
        }

        Timing decT;
        try {
            decT = decryptToFile(engine, cmd, keys, ctPath, decPath);
            applyDecryptTiming(sample, decT);
        } catch (Exception e) {
            markFailure(sample, OperationSample.FAILURE_OPERATION);
            log.warn("decrypt failed for {}: {}", f.rel(), e.toString());
            return new FileResult(sample, encT.hardwareAccel());
        }

        boolean equal;
        try {
            equal = filesEqual(f.abs(), decPath);
        } catch (IOException e) {
            markFailure(sample, OperationSample.FAILURE_OPERATION);
            return new FileResult(sample, encT.hardwareAccel() || decT.hardwareAccel());
        } finally {
            quietDelete(decPath);
        }
        sample.roundTripOk = equal;
        if (!equal) {
            markFailure(sample, OperationSample.FAILURE_CORRECTNESS);
        }
        return new FileResult(sample, encT.hardwareAccel() || decT.hardwareAccel());
    }

    private FileResult doEncryptOnly(CryptoEngine engine, Command cmd, KeySet keys, CorpusFile f, OperationSample sample) {
        String outName = Classifier.outputName(f.rel()).orElseThrow();
        sample.outputFileName = outName;
        Path ctPath = Paths.get(cmd.outputDir()).resolve(outName);
        try {
            EncryptResult er = encryptToFile(engine, cmd, keys, f.abs(), ctPath);
            applyEncryptTiming(sample, er.timing);
            sample.ciphertextBytes = er.ciphertextBytes;
            return new FileResult(sample, er.timing.hardwareAccel());
        } catch (Exception e) {
            markFailure(sample, OperationSample.FAILURE_OPERATION);
            log.warn("encrypt failed for {}: {}", f.rel(), e.toString());
            return new FileResult(sample, false);
        }
    }

    private FileResult doDecryptOnly(CryptoEngine engine, Command cmd, KeySet keys, CorpusFile f, OperationSample sample) {
        Path decPath = Paths.get(cmd.outputDir()).resolve(f.rel() + ".dec");
        try {
            Timing decT = decryptToFile(engine, cmd, keys, f.abs(), decPath);
            applyDecryptTiming(sample, decT);
            return new FileResult(sample, decT.hardwareAccel());
        } catch (Exception e) {
            markFailure(sample, OperationSample.FAILURE_OPERATION);
            log.warn("decrypt failed for {}: {}", f.rel(), e.toString());
            return new FileResult(sample, false);
        }
    }

    private record EncryptResult(long ciphertextBytes, Timing timing) {
    }

    private EncryptResult encryptToFile(CryptoEngine engine, Command cmd, KeySet keys, Path src, Path dst)
            throws IOException, CryptoException {
        Files.createDirectories(dst.getParent());
        Timing timing;
        try (InputStream in = Files.newInputStream(src);
             OutputStream out = Files.newOutputStream(dst)) {
            timing = engine.encrypt(in, out, cmd.cryptoProfile(), keys);
        }
        return new EncryptResult(Files.size(dst), timing);
    }

    private Timing decryptToFile(CryptoEngine engine, Command cmd, KeySet keys, Path src, Path dst)
            throws IOException, CryptoException {
        Files.createDirectories(dst.getParent());
        try (InputStream in = Files.newInputStream(src);
             OutputStream out = Files.newOutputStream(dst)) {
            return engine.decrypt(in, out, cmd.cryptoProfile(), keys);
        }
    }

    private static boolean filesEqual(Path a, Path b) throws IOException {
        return Files.mismatch(a, b) == -1L;
    }

    private static void quietDelete(Path p) {
        try {
            Files.deleteIfExists(p);
        } catch (IOException ignored) {
            // best-effort cleanup of the decrypted scratch file
        }
    }

    private static void markFailure(OperationSample sample, String failureType) {
        sample.failureType = failureType;
        sample.roundTripOk = false;
    }

    // ----- timing helpers ---------------------------------------------------- //

    private static void applyEncryptTiming(OperationSample sample, Timing t) {
        Timing h = t.honest();
        sample.encryptMs = nanosToMs(h.totalNanos());
        sample.asymEncryptMs = subTimingMs(h.asymNanos());
        sample.symEncryptMs = subTimingMs(h.symNanos());
    }

    private static void applyDecryptTiming(OperationSample sample, Timing t) {
        Timing h = t.honest();
        sample.decryptMs = nanosToMs(h.totalNanos());
        sample.asymDecryptMs = subTimingMs(h.asymNanos());
        sample.symDecryptMs = subTimingMs(h.symNanos());
    }

    private static double nanosToMs(long n) {
        return n / 1e6;
    }

    /** -1 stays -1 (not separable, Req 24.3); otherwise convert to ms. */
    private static Double subTimingMs(long n) {
        if (n == Timing.NOT_SEPARABLE) {
            return -1.0;
        }
        return nanosToMs(n);
    }

    private static String deriveScenarioId(Path corpusPath) {
        Path name = corpusPath.toAbsolutePath().normalize().getFileName();
        if (name == null) {
            return "scenario";
        }
        String base = name.toString();
        return base.isEmpty() ? "scenario" : base;
    }

    // package-private helpers wrapping IOExceptions from the checksum stage.

    private String computeKeySetChecksum(Path dir) {
        try {
            return Checksum.computeKeySetChecksum(dir);
        } catch (IOException e) {
            throw new RunnerException(ExitCodes.OPERATION_FAILURE, "compute key-set checksum: " + e.getMessage(), e);
        }
    }

    private String computeCorpusChecksum(Path root) {
        try {
            return Checksum.computeCorpusChecksum(root);
        } catch (IOException e) {
            throw new RunnerException(ExitCodes.OPERATION_FAILURE, "compute corpus checksum: " + e.getMessage(), e);
        }
    }
}
