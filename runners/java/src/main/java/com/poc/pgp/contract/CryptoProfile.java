package com.poc.pgp.contract;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

/**
 * The set of PGP algorithm choices for a Scenario (Req 4.3), mirroring the
 * {@code cryptoProfile} object in {@code contract/command.schema.json}.
 */
@JsonIgnoreProperties(ignoreUnknown = false)
public record CryptoProfile(
        String pubAlg,
        String cipher,
        String compression,
        String hash) {

    /**
     * A stable, readable Crypto_Profile id derived from the fields (the Command
     * carries the profile but no id), matching the Go runner's
     * {@code deriveCryptoProfileID}: lower-cased, spaces to dashes, joined by
     * underscores, e.g. {@code "rsa-2048_aes-256_zlib_sha-256"}.
     */
    public String id() {
        return slug(pubAlg) + "_" + slug(cipher) + "_" + slug(compression) + "_" + slug(hash);
    }

    private static String slug(String s) {
        if (s == null) {
            return "";
        }
        return s.trim().toLowerCase().replace(' ', '-');
    }
}
