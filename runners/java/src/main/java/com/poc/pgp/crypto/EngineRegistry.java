package com.poc.pgp.crypto;

import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.ServiceLoader;

/**
 * Registry mapping {@code variantId -> CryptoEngine}, mirroring the Go runner's
 * engine registry. The shell resolves the engine for the commanded
 * {@code variantId} here without depending on concrete variant classes.
 *
 * <p>Variants are normally discovered via the {@link ServiceLoader}
 * ({@link #loadFromServiceLoader()}); tests may also {@link #register} a double
 * directly. This is an instance (not static) so each test can build its own
 * registry in isolation.
 */
public final class EngineRegistry {

    private final Map<String, CryptoEngine> engines = new LinkedHashMap<>();

    /**
     * Registers an engine under its {@link CryptoEngine#variantId()}. Registering
     * the same id twice is a programming error and throws, surfacing duplicate
     * registration early (as the Go runner panics on a duplicate id).
     */
    public void register(CryptoEngine engine) {
        String id = engine.variantId();
        if (engines.containsKey(id)) {
            throw new IllegalStateException("engine already registered: " + id);
        }
        engines.put(id, engine);
    }

    /**
     * Discovers and registers every {@link CryptoEngine} advertised on the
     * classpath via {@code META-INF/services/com.poc.pgp.crypto.CryptoEngine}.
     */
    public void loadFromServiceLoader() {
        for (CryptoEngine engine : ServiceLoader.load(CryptoEngine.class)) {
            register(engine);
        }
    }

    /** Returns the engine registered for {@code variantId}, if any. */
    public Optional<CryptoEngine> get(String variantId) {
        return Optional.ofNullable(engines.get(variantId));
    }

    /** The sorted set of known variant ids (for diagnostics). */
    public List<String> registeredVariants() {
        List<String> ids = new ArrayList<>(engines.keySet());
        Collections.sort(ids);
        return ids;
    }
}
