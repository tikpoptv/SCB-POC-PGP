package com.poc.pgp.crypto;

import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * Verifies that the {@link EngineRegistry} loaded via the ServiceLoader
 * (META-INF/services) contains all four required variant ids, including the two
 * new variants added in task 12.2 (Req 6.1, 6.3).
 */
class EngineRegistryVariantTest {

    /**
     * All four variant ids must be discoverable via the ServiceLoader so the
     * Harness can request any of them without an explicit hard-coded lookup.
     */
    @Test
    void serviceLoaderRegistersAllFourVariants() {
        EngineRegistry registry = new EngineRegistry();
        registry.loadFromServiceLoader();

        List<String> registered = registry.registeredVariants();

        assertTrue(registered.contains("java-stream-parallel"),
                "java-stream-parallel must be registered");
        assertTrue(registered.contains("java-inmem-single"),
                "java-inmem-single must be registered (task 12.2)");
        assertTrue(registered.contains("java-stream-single"),
                "java-stream-single must be registered (task 12.2)");

        // java-native-stream-parallel is NOT in the ServiceLoader — it is only
        // activated via NativeMain for GraalVM native-image builds (task 11.3).
        // Asserting it is absent prevents accidental duplicate registration.
        assertFalse(registered.contains("java-native-stream-parallel"),
                "java-native-stream-parallel must NOT be in the JVM ServiceLoader");
    }

    /** Direct registration must expose the new variant ids as expected. */
    @Test
    void directRegistrationExposesNewVariants() {
        EngineRegistry registry = new EngineRegistry();
        registry.register(new InMemSingleEngine());
        registry.register(new StreamSingleEngine());

        assertTrue(registry.get("java-inmem-single").isPresent(),
                "java-inmem-single must be retrievable after direct registration");
        assertTrue(registry.get("java-stream-single").isPresent(),
                "java-stream-single must be retrievable after direct registration");
    }

    /** variantId() of each new engine must match the contract constant. */
    @Test
    void variantIdsMatchConstants() {
        assertEquals("java-inmem-single", InMemSingleEngine.VARIANT_ID);
        assertEquals("java-stream-single", StreamSingleEngine.VARIANT_ID);
        assertEquals("java-inmem-single", new InMemSingleEngine().variantId());
        assertEquals("java-stream-single", new StreamSingleEngine().variantId());
    }

    private static void assertEquals(String expected, String actual) {
        org.junit.jupiter.api.Assertions.assertEquals(expected, actual);
    }
}
