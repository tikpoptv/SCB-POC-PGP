// Command go-runner is the Go implementation of the PGP benchmark Runner: it
// reads a single Command JSON object from stdin and writes a single RunnerOutput
// JSON object to stdout. All diagnostics go to stderr only.
package main

import (
	"fmt"
	"io"
	"os"
	"time"
)

// Exit codes from the shared CLI contract (contract/exit-codes.json).
const (
	exitOK              = 0
	exitOperationFail   = 1
	exitChecksumOrVer   = 2
	exitBadConfig       = 3
	exitUnsupportedProf = 4
)

func main() {
	programStart := time.Now()
	os.Exit(run(programStart, os.Stdin, os.Stdout, os.Stderr))
}

// run is the testable entry point: it reads a Command from in, writes the
// RunnerOutput to out, logs to errOut, and returns the process exit code.
func run(programStart time.Time, in io.Reader, out, errOut io.Writer) int {
	logf := func(format string, args ...any) {
		fmt.Fprintf(errOut, "[go-runner] "+format+"\n", args...)
	}

	data, err := io.ReadAll(in)
	if err != nil {
		logf("failed to read stdin: %v", err)
		return exitOperationFail
	}

	cmd, err := ParseCommand(data)
	if err != nil {
		return finishErr(err, logf)
	}

	output, err := Run(cmd, programStart, logf)
	if err != nil {
		return finishErr(err, logf)
	}

	encoded, err := output.Encode()
	if err != nil {
		logf("failed to encode RunnerOutput: %v", err)
		return exitOperationFail
	}
	if _, err := out.Write(append(encoded, '\n')); err != nil {
		logf("failed to write stdout: %v", err)
		return exitOperationFail
	}
	return exitOK
}

// finishErr logs an error and maps it to a process exit code. A *runnerError
// carries its own code; anything else is a generic operation failure.
func finishErr(err error, logf func(string, ...any)) int {
	var re *runnerError
	if asRunnerError(err, &re) {
		logf("error (exit %d): %s", re.code, re.msg)
		return re.code
	}
	logf("operation failure: %v", err)
	return exitOperationFail
}

func asRunnerError(err error, target **runnerError) bool {
	re, ok := err.(*runnerError)
	if ok {
		*target = re
	}
	return ok
}
