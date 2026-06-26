package com.poc.pgp.crypto;

import com.poc.pgp.contract.CryptoProfile;

/**
 * Thrown by a {@link CryptoEngine} when it cannot honour the requested
 * {@link CryptoProfile} (cipher / compression / public-key algorithm). The shell
 * maps this to process exit code 4 (Req 4.4, 18.5), mirroring the Go runner's
 * {@code ProfileSupporter} contract.
 */
public class UnsupportedProfileException extends CryptoException {

    public UnsupportedProfileException(String message) {
        super(message);
    }
}
