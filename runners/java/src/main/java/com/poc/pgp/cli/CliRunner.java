package com.poc.pgp.cli;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.ExitCodeGenerator;

/**
 * The Spring Boot {@code CommandLineRunner} that drives the CLI: on startup it
 * delegates to {@link RunnerShell#run} (reading stdin, writing stdout), captures
 * the contract exit code, and exposes it as an {@link ExitCodeGenerator} so
 * {@link org.springframework.boot.SpringApplication#exit} returns it to the JVM.
 */
public class CliRunner implements CommandLineRunner, ExitCodeGenerator {

    private final RunnerShell shell;
    private int exitCode = ExitCodes.SUCCESS;

    public CliRunner(RunnerShell shell) {
        this.shell = shell;
    }

    @Override
    public void run(String... args) {
        exitCode = shell.run(System.in, System.out);
    }

    @Override
    public int getExitCode() {
        return exitCode;
    }
}
