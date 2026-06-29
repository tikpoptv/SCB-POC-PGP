package com.poc.pgp;

import com.poc.pgp.cli.RunnerShell;
import com.poc.pgp.crypto.EngineRegistry;
import com.poc.pgp.crypto.NativeStreamParallelEngine;
import org.bouncycastle.jce.provider.BouncyCastleProvider;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.security.SecureRandom;
import java.security.Security;

/**
 * TEMPORARY build-time helper (task 11.3): run on the JVM under the GraalVM
 * native-image agent to capture the reflection / resource / proxy reachability
 * metadata Bouncy Castle + Jackson need at native run time. It drives the SAME
 * {@link RunnerShell} path the native binary uses, for every key type, so the
 * generated config covers the real crypto code. NOT shipped in the native image
 * (the native entry point is {@link NativeMain}); deleted after metadata capture.
 */
public final class AgentExercise {

    private AgentExercise() {
    }

    public static void main(String[] args) throws Exception {
        Security.addProvider(new BouncyCastleProvider());

        Path keysDir = Paths.get("..", "..", "keys").toAbsolutePath().normalize();
        Path tmp = Files.createTempDirectory("agent-corpus");
        Path corpus = tmp.resolve("corpus");
        Files.createDirectories(corpus);

        // A small but representative corpus: supported types, a control file, an
        // unsupported type, and a larger .dat to exercise the streaming path.
        Files.writeString(corpus.resolve("hello.txt"), "hello \r world \r\n line \n end");
        Files.writeString(corpus.resolve("data.csv"), "a,b,c\n1,2,3\n");
        Files.writeString(corpus.resolve("job.ctrl"), "skip me");
        Files.writeString(corpus.resolve("notes.md"), "unsupported");
        byte[] big = new byte[2 * 1024 * 1024];
        new SecureRandom(new byte[] {1, 2, 3}).nextBytes(big);
        Files.write(corpus.resolve("blob.dat"), big);

        String keySetChecksum = Checksum.computeKeySetChecksum(keysDir);
        String corpusChecksum = Checksum.computeCorpusChecksum(corpus);
        Path outDir = tmp.resolve("out");

        EngineRegistry registry = new EngineRegistry();
        registry.register(new NativeStreamParallelEngine());
        RunnerShell shell = new RunnerShell(registry);

        for (String pubAlg : new String[] {"RSA-2048", "RSA-4096", "Curve25519"}) {
            String cmd = command(pubAlg, keysDir, keySetChecksum, corpus, corpusChecksum,
                    outDir.resolve(pubAlg));
            ByteArrayOutputStream out = new ByteArrayOutputStream();
            int code = shell.run(new ByteArrayInputStream(cmd.getBytes(StandardCharsets.UTF_8)), out);
            System.err.println("[agent-exercise] " + pubAlg + " exit=" + code
                    + " outputLen=" + out.size());
            if (code != 0) {
                System.err.println(out.toString(StandardCharsets.UTF_8));
                throw new IllegalStateException("agent exercise failed for " + pubAlg + " (exit " + code + ")");
            }
        }
        System.err.println("[agent-exercise] done");
    }

    private static String command(String pubAlg, Path keysDir, String keySetChecksum,
                                  Path corpus, String corpusChecksum, Path outDir) {
        return "{"
                + "\"command\":\"run\","
                + "\"variantId\":\"java-native-stream-parallel\","
                + "\"mode\":\"steady_state\","
                + "\"warmupIterations\":1,"
                + "\"concurrency\":2,"
                + "\"cryptoProfile\":{\"pubAlg\":\"" + pubAlg + "\",\"cipher\":\"AES-256\","
                + "\"compression\":\"ZLIB\",\"hash\":\"SHA-256\"},"
                + "\"outputEncoding\":\"binary\","
                + "\"keySetPath\":\"" + json(keysDir.toString()) + "\","
                + "\"keySetChecksum\":\"" + keySetChecksum + "\","
                + "\"corpusPath\":\"" + json(corpus.toString()) + "\","
                + "\"corpusChecksum\":\"" + corpusChecksum + "\","
                + "\"outputDir\":\"" + json(outDir.toString()) + "\","
                + "\"operation\":\"roundtrip\""
                + "}";
    }

    private static String json(String s) {
        return s.replace("\\", "\\\\").replace("\"", "\\\"");
    }
}
