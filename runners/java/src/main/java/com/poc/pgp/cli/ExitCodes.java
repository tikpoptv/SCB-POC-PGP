package com.poc.pgp.cli;

/**
 * Process exit codes from the shared CLI contract
 * ({@code contract/exit-codes.json}, design.md "Runner CLI Contract"). Kept in
 * sync with that file and mirrored byte-for-byte with the Go runner.
 */
public final class ExitCodes {

    /** Success (includes runs with recorded per-file correctness failures). */
    public static final int SUCCESS = 0;
    /** Generic operation failure; any code &gt; 0 other than 2/3/4 is also this (Req 5.3). */
    public static final int OPERATION_FAILURE = 1;
    /** Key_Set/Test_Corpus checksum or version mismatch (Req 4.6, 2.5). */
    public static final int CHECKSUM_OR_VERSION_MISMATCH = 2;
    /** Invalid config/command JSON (Req 19.6). */
    public static final int CONFIG_ERROR = 3;
    /** Requested crypto-profile not supported by this Runner (Req 4.4, 18.5). */
    public static final int UNSUPPORTED_CRYPTO_PROFILE = 4;

    private ExitCodes() {
    }
}
