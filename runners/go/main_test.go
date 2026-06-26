package main

import (
	"bytes"
	"encoding/json"
	"strings"
	"testing"
	"time"
)

// buildCommandJSON renders a *Command back to the wire JSON the harness sends.
func buildCommandJSON(t *testing.T, cmd *Command) string {
	t.Helper()
	b, err := json.Marshal(map[string]any{
		"command":          cmd.Command,
		"variantId":        cmd.VariantID,
		"mode":             cmd.Mode,
		"warmupIterations": cmd.WarmupIterations,
		"concurrency":      cmd.Concurrency,
		"cryptoProfile": map[string]string{
			"pubAlg":      cmd.CryptoProfile.PubAlg,
			"cipher":      cmd.CryptoProfile.Cipher,
			"compression": cmd.CryptoProfile.Compression,
			"hash":        cmd.CryptoProfile.Hash,
		},
		"outputEncoding": cmd.OutputEncoding,
		"keySetPath":     cmd.KeySetPath,
		"keySetChecksum": cmd.KeySetChecksum,
		"corpusPath":     cmd.CorpusPath,
		"corpusChecksum": cmd.CorpusChecksum,
		"outputDir":      cmd.OutputDir,
		"operation":      cmd.Operation,
	})
	if err != nil {
		t.Fatal(err)
	}
	return string(b)
}

func TestRunCLISuccessSeparatesStreams(t *testing.T) {
	cmd := baseCommand(t, "test-copy")
	in := strings.NewReader(buildCommandJSON(t, cmd))
	var stdout, stderr bytes.Buffer

	code := run(time.Now(), in, &stdout, &stderr)
	if code != exitOK {
		t.Fatalf("exit code = %d, want 0; stderr=%s", code, stderr.String())
	}

	// stdout must be exactly one JSON object that decodes as RunnerOutput.
	var out RunnerOutput
	dec := json.NewDecoder(bytes.NewReader(stdout.Bytes()))
	if err := dec.Decode(&out); err != nil {
		t.Fatalf("stdout is not valid RunnerOutput JSON: %v\n%s", err, stdout.String())
	}
	if dec.More() {
		t.Errorf("stdout contains more than one JSON object")
	}
	if out.RunnerID != "go" || out.VariantID != "test-copy" {
		t.Errorf("unexpected output identity: %+v", out)
	}
	// Diagnostics must go to stderr only, never stdout.
	if strings.Contains(stdout.String(), "[go-runner]") {
		t.Errorf("diagnostic text leaked into stdout")
	}
}

func TestRunCLIBadConfigExit3(t *testing.T) {
	in := strings.NewReader("{ not valid json")
	var stdout, stderr bytes.Buffer
	code := run(time.Now(), in, &stdout, &stderr)
	if code != exitBadConfig {
		t.Fatalf("exit code = %d, want %d", code, exitBadConfig)
	}
	if stdout.Len() != 0 {
		t.Errorf("no stdout expected on config error, got %q", stdout.String())
	}
	if stderr.Len() == 0 {
		t.Errorf("expected a diagnostic on stderr")
	}
}
