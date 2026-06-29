package com.poc.pgp.crypto;

import com.poc.pgp.contract.CryptoProfile;
import com.sun.management.HotSpotDiagnosticMXBean;

import java.lang.management.ManagementFactory;

/**
 * Reports whether the symmetric cipher of a {@link CryptoProfile} runs with CPU
 * Hardware_Acceleration (AES-NI) on this JVM (Req 23.1). The {@code java-*}
 * variants run AES through the JCE, whose AES block cipher is intrinsified by
 * HotSpot when {@code UseAESIntrinsics} is enabled — so that diagnostic flag is
 * a determinate proxy for "AES-NI is in use" (design.md: AES-256 via JCE/AES-NI).
 * Non-AES ciphers, or a JVM that cannot report the flag, yield {@code false}.
 */
final class HardwareAccel {

    private static final boolean AES_INTRINSICS_ENABLED = detectAesIntrinsics();

    private HardwareAccel() {
    }

    /** True only for AES ciphers when the JVM has AES intrinsics (AES-NI) enabled. */
    static boolean forCipher(String cipher) {
        return isAes(cipher) && AES_INTRINSICS_ENABLED;
    }

    private static boolean isAes(String cipher) {
        String norm = cipher == null ? "" : cipher.trim().toUpperCase().replace("-", "").replace("_", "");
        return norm.equals("AES256") || norm.equals("AES192") || norm.equals("AES128");
    }

    private static boolean detectAesIntrinsics() {
        try {
            HotSpotDiagnosticMXBean bean =
                    ManagementFactory.getPlatformMXBean(HotSpotDiagnosticMXBean.class);
            if (bean == null) {
                return false;
            }
            return Boolean.parseBoolean(bean.getVMOption("UseAESIntrinsics").getValue());
        } catch (RuntimeException e) {
            // Non-HotSpot JVM or the flag is unavailable: report no acceleration.
            return false;
        }
    }
}
