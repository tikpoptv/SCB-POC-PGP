package com.poc.pgp.crypto;

/**
 * Thrown by a {@link CryptoEngine} when an encrypt/decrypt operation fails. The
 * shell records this as a per-file operation failure (it does not abort the run)
 * unless it is an {@link UnsupportedProfileException}, which maps to exit code 4
 * (Req 4.4, 18.5, 12.1).
 */
public class CryptoException extends Exception {

    public CryptoException(String message) {
        super(message);
    }

    public CryptoException(String message, Throwable cause) {
        super(message, cause);
    }
}
