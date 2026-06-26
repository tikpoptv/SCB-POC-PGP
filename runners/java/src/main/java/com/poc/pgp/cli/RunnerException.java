package com.poc.pgp.cli;

/**
 * Pairs an error message with the process exit code the shell must return for it
 * ({@code contract/exit-codes.json}), mirroring the Go runner's
 * {@code runnerError}. The shell catches this, logs the message to stderr, and
 * returns {@link #exitCode()}.
 */
public class RunnerException extends RuntimeException {

    private final int exitCode;

    public RunnerException(int exitCode, String message) {
        super(message);
        this.exitCode = exitCode;
    }

    public RunnerException(int exitCode, String message, Throwable cause) {
        super(message, cause);
        this.exitCode = exitCode;
    }

    /** The process exit code this error maps to. */
    public int exitCode() {
        return exitCode;
    }
}
