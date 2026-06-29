package com.poc.pgp;

import com.poc.pgp.cli.RunnerShell;
import com.poc.pgp.crypto.EngineRegistry;
import com.poc.pgp.crypto.NativeStreamParallelEngine;
import org.bouncycastle.jce.provider.BouncyCastleProvider;

import java.security.Security;

/**
 * Plain (non-Spring) entry point used to build the GraalVM Native Image variant
 * {@code java-native-stream-parallel} (task 11.3, Req 22.1). It wires the same
 * runtime-neutral {@link RunnerShell} the JVM runner uses, but registers the
 * {@link NativeStreamParallelEngine} so the binary answers to the native
 * Implementation_Variant id. Spring Boot is intentionally NOT on this path: the
 * native binary needs no application container, and avoiding Spring keeps the
 * native image small and the AOT build straightforward.
 *
 * <p>The crypto code is byte-for-byte identical to {@code java-stream-parallel}
 * (the engine delegates), so the native vs JVM comparison stays honest — only
 * the runtime (AOT native binary vs JVM) differs.
 *
 * <p>GraalVM version recording (Req 22.3): the actual GraalVM version string is
 * captured from {@code java.vm.version} at start-up and stored in
 * {@link RunnerShell#GRAALVM_VERSION_PROP} so {@link RunnerShell} can embed it
 * in every {@link com.poc.pgp.contract.RunnerOutput} it produces. When running
 * on the JVM (e.g. during agent metadata capture) the field stays null.
 */
public final class NativeMain {

    private NativeMain() {
    }

    public static void main(String[] args) {
        // Register Bouncy Castle as a JCE provider before any crypto/key parsing.
        if (Security.getProvider(BouncyCastleProvider.PROVIDER_NAME) == null) {
            Security.addProvider(new BouncyCastleProvider());
        }

        // Diagnostic self-test: `java-native-runner selftest <keysDir>` does a
        // direct in-memory PGP round-trip and prints OK / the full stack trace.
        // Useful to validate the native binary's crypto path without a corpus.
        if (args.length >= 1 && "selftest".equals(args[0])) {
            System.exit(selfTest(args.length >= 2 ? args[1] : "keys"));
        }

        // Honesty guard: this main is meant to run as a native image. When run on
        // the JVM (e.g. while capturing reachability metadata) warn but continue,
        // so the same code path is exercised for the agent.
        boolean nativeRuntime = "runtime".equals(System.getProperty("org.graalvm.nativeimage.imagecode"));
        if (!nativeRuntime) {
            System.err.println("[java-native-stream-parallel] NOTE: running on the JVM, not a native image");
        }

        // Req 22.3 — record the GraalVM runtime version in the runner output so
        // the Harness can persist it as versions.graalvm in results.json.
        // In a native image, java.vm.version reports the GraalVM version string
        // (e.g. "Oracle GraalVM 23.1.2+1-jvmci-23.1-b33" or "GraalVM CE 24.1.1").
        // Publish it via a well-known system property that RunnerShell reads back.
        String vmVersion = System.getProperty("java.vm.version");
        if (vmVersion != null && !vmVersion.isEmpty()) {
            System.setProperty(RunnerShell.GRAALVM_VERSION_PROP, vmVersion);
        }

        EngineRegistry registry = new EngineRegistry();
        registry.register(new NativeStreamParallelEngine());

        RunnerShell shell = new RunnerShell(registry);
        int code = shell.run(System.in, System.out);
        System.exit(code);
    }

    private static int selfTest(String keysDir) {
        try {
            com.poc.pgp.KeySet keys = com.poc.pgp.KeySet.load(java.nio.file.Paths.get(keysDir));
            NativeStreamParallelEngine engine = new NativeStreamParallelEngine();
            com.poc.pgp.contract.CryptoProfile profile =
                    new com.poc.pgp.contract.CryptoProfile("RSA-2048", "AES-256", "ZLIB", "SHA-256");
            byte[] plain = "native self-test \r lone-CR \r\n done".getBytes(java.nio.charset.StandardCharsets.UTF_8);
            java.io.ByteArrayOutputStream ct = new java.io.ByteArrayOutputStream();
            engine.encrypt(new java.io.ByteArrayInputStream(plain), ct, profile, keys);
            java.io.ByteArrayOutputStream pt = new java.io.ByteArrayOutputStream();
            engine.decrypt(new java.io.ByteArrayInputStream(ct.toByteArray()), pt, profile, keys);
            boolean ok = java.util.Arrays.equals(plain, pt.toByteArray());
            System.err.println("[selftest] ciphertextBytes=" + ct.size() + " roundTripOk=" + ok);
            return ok ? 0 : 1;
        } catch (Throwable t) {
            t.printStackTrace();
            return 1;
        }
    }
}
