package com.poc.pgp;

import com.poc.pgp.cli.CliRunner;
import com.poc.pgp.cli.RunnerShell;
import com.poc.pgp.crypto.EngineRegistry;
import org.bouncycastle.jce.provider.BouncyCastleProvider;
import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

import java.security.Security;

/**
 * Spring Boot entry point for the Java_Runner. Spring Boot is used ONLY as the
 * CLI/application shell (no web/data starters — Req 1.2): a
 * {@link org.springframework.boot.CommandLineRunner} reads the Command JSON from
 * stdin and writes the RunnerOutput JSON to stdout, logs go to stderr (see
 * {@code logback.xml}), and the process exits with the contract exit code via an
 * {@link org.springframework.boot.ExitCodeGenerator}.
 *
 * <p>The actual work lives in the runtime-neutral {@link RunnerShell}; this class
 * just wires the beans and controls the process lifecycle/exit code.
 */
@SpringBootApplication
public class JavaRunnerApplication {

    public static void main(String[] args) {
        // Register Bouncy Castle as a JCE provider before any crypto/key parsing.
        if (Security.getProvider(BouncyCastleProvider.PROVIDER_NAME) == null) {
            Security.addProvider(new BouncyCastleProvider());
        }

        SpringApplication app = new SpringApplication(JavaRunnerApplication.class);
        app.setBannerMode(Banner.Mode.OFF);
        app.setWebApplicationType(WebApplicationType.NONE);
        app.setLogStartupInfo(false);

        ConfigurableApplicationContext context = app.run(args);
        // SpringApplication.exit consults the CliRunner (an ExitCodeGenerator)
        // for the contract exit code, then we hand it to the JVM.
        System.exit(SpringApplication.exit(context));
    }

    /** The engine registry, populated from the classpath via ServiceLoader. */
    @Bean
    EngineRegistry engineRegistry() {
        EngineRegistry registry = new EngineRegistry();
        registry.loadFromServiceLoader();
        return registry;
    }

    @Bean
    RunnerShell runnerShell(EngineRegistry registry) {
        return new RunnerShell(registry);
    }

    @Bean
    CliRunner cliRunner(RunnerShell shell) {
        return new CliRunner(shell);
    }
}
