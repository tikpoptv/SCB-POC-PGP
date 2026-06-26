package main

import (
	"io"
	"os"
	"path/filepath"
	"testing"
	"time"
)

// copyEngine is an identity engine: ciphertext == plaintext, so a roundtrip
// reproduces the original bytes without real crypto.
type copyEngine struct{ id string }

func (e copyEngine) VariantID() string { return e.id }
func (e copyEngine) Encrypt(in io.Reader, out io.Writer, _ CryptoProfile, _ *KeySet) (Timing, error) {
	_, err := io.Copy(out, in)
	return Timing{TotalNanos: 1_000_000, AsymNanos: NotSeparable, SymNanos: NotSeparable, HardwareAccel: true}, err
}
func (e copyEngine) Decrypt(in io.Reader, out io.Writer, _ CryptoProfile, _ *KeySet) (Timing, error) {
	_, err := io.Copy(out, in)
	return Timing{TotalNanos: 2_000_000, AsymNanos: NotSeparable, SymNanos: NotSeparable, HardwareAccel: true}, err
}

// corruptEngine decrypts to wrong bytes so the round-trip comparison fails.
type corruptEngine struct{ id string }

func (e corruptEngine) VariantID() string { return e.id }
func (e corruptEngine) Encrypt(in io.Reader, out io.Writer, _ CryptoProfile, _ *KeySet) (Timing, error) {
	_, err := io.Copy(out, in)
	return Timing{TotalNanos: 1, AsymNanos: NotSeparable, SymNanos: NotSeparable}, err
}
func (e corruptEngine) Decrypt(_ io.Reader, out io.Writer, _ CryptoProfile, _ *KeySet) (Timing, error) {
	_, err := out.Write([]byte("CORRUPTED"))
	return Timing{TotalNanos: 1, AsymNanos: NotSeparable, SymNanos: NotSeparable}, err
}

func init() {
	RegisterEngine("test-copy", func() CryptoEngine { return copyEngine{id: "test-copy"} })
	RegisterEngine("test-corrupt", func() CryptoEngine { return corruptEngine{id: "test-corrupt"} })
}

func quietLog(string, ...any) {}

// repoKeysDir is the shared Key_Set checked into the repo (../../keys).
const repoKeysDir = "../../keys"

// setupKeySet copies the RSA-2048 key pair into an isolated dir and returns the
// dir plus its checksum.
func setupKeySet(t *testing.T) (string, string) {
	t.Helper()
	dir := t.TempDir()
	for _, name := range []string{"rsa2048-public.asc", "rsa2048-private.asc"} {
		b, err := os.ReadFile(filepath.Join(repoKeysDir, name))
		if err != nil {
			t.Skipf("repo key %s unavailable: %v", name, err)
		}
		if err := os.WriteFile(filepath.Join(dir, name), b, 0o644); err != nil {
			t.Fatal(err)
		}
	}
	sum, err := ComputeKeySetChecksum(dir)
	if err != nil {
		t.Fatal(err)
	}
	return dir, sum
}

// setupCorpus builds a small corpus with a supported file and a control file.
func setupCorpus(t *testing.T) (string, string) {
	t.Helper()
	dir := t.TempDir()
	writeFile(t, filepath.Join(dir, "doc.txt"), []byte("the quick brown fox jumps over the lazy dog"))
	writeFile(t, filepath.Join(dir, "skip.ctrl"), []byte("control"))
	sum, err := ComputeCorpusChecksum(dir)
	if err != nil {
		t.Fatal(err)
	}
	return dir, sum
}

func baseCommand(t *testing.T, variant string) *Command {
	t.Helper()
	keysDir, keySum := setupKeySet(t)
	corpusDir, corpusSum := setupCorpus(t)
	return &Command{
		Command:          "run",
		VariantID:        variant,
		Mode:             "steady_state",
		WarmupIterations: 1,
		Concurrency:      1,
		CryptoProfile:    CryptoProfile{PubAlg: "RSA-2048", Cipher: "AES-256", Compression: "ZLIB", Hash: "SHA-256"},
		OutputEncoding:   "binary",
		KeySetPath:       keysDir,
		KeySetChecksum:   keySum,
		CorpusPath:       corpusDir,
		CorpusChecksum:   corpusSum,
		OutputDir:        t.TempDir(),
		Operation:        "roundtrip",
	}
}

func findOp(out *RunnerOutput, name string) *OperationSample {
	for i := range out.Operations {
		if out.Operations[i].FileName == name {
			return &out.Operations[i]
		}
	}
	return nil
}

func TestRunRoundtripSuccess(t *testing.T) {
	cmd := baseCommand(t, "test-copy")
	out, err := Run(cmd, time.Now(), quietLog)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if out.RunnerID != "go" {
		t.Errorf("runnerId = %q, want go", out.RunnerID)
	}
	if out.ScenarioID == "" || out.CryptoProfileID == "" {
		t.Errorf("scenarioId/cryptoProfileId must be non-empty: %q / %q", out.ScenarioID, out.CryptoProfileID)
	}
	if out.KeySetChecksumSeen != cmd.KeySetChecksum {
		t.Errorf("keySetChecksumSeen mismatch")
	}
	if len(out.Operations) != 2 {
		t.Fatalf("expected 2 operations, got %d", len(out.Operations))
	}

	doc := findOp(out, "doc.txt")
	if doc == nil {
		t.Fatal("missing doc.txt operation")
	}
	if !doc.RoundTripOk {
		t.Errorf("doc.txt roundTripOk = false, want true")
	}
	if doc.FailureType != nil {
		t.Errorf("doc.txt failureType = %v, want nil", *doc.FailureType)
	}
	if doc.EncryptMs == nil || doc.DecryptMs == nil {
		t.Fatal("doc.txt missing encrypt/decrypt timing")
	}
	if *doc.EncryptMs <= 0 || *doc.DecryptMs <= 0 {
		t.Errorf("expected positive crypto timing, got enc=%v dec=%v", *doc.EncryptMs, *doc.DecryptMs)
	}
	if doc.CiphertextBytes == nil || *doc.CiphertextBytes <= 0 {
		t.Errorf("expected ciphertextBytes recorded")
	}
	if doc.OutputFileName == nil || *doc.OutputFileName != "doc.txt.pgp" {
		t.Errorf("output name = %v, want doc.txt.pgp", doc.OutputFileName)
	}
	// asym/sym not separable -> -1
	if doc.AsymEncryptMs == nil || *doc.AsymEncryptMs != -1 {
		t.Errorf("asymEncryptMs = %v, want -1", doc.AsymEncryptMs)
	}

	ctrl := findOp(out, "skip.ctrl")
	if ctrl == nil || !ctrl.Skipped {
		t.Fatalf("skip.ctrl should be skipped")
	}
	if ctrl.SkipReason == nil || *ctrl.SkipReason != skipReasonControlFile {
		t.Errorf("skip reason = %v, want control_file", ctrl.SkipReason)
	}
	if !out.HardwareAccel {
		t.Errorf("hardwareAccel should aggregate to true from the copy engine")
	}
}

func TestRunUnsupportedFileSkipped(t *testing.T) {
	keysDir, keySum := setupKeySet(t)
	corpusDir := t.TempDir()
	writeFile(t, filepath.Join(corpusDir, "doc.txt"), []byte("hello"))
	writeFile(t, filepath.Join(corpusDir, "image.png"), []byte("not encrypted"))
	corpusSum, err := ComputeCorpusChecksum(corpusDir)
	if err != nil {
		t.Fatal(err)
	}
	cmd := &Command{
		Command:          "run",
		VariantID:        "test-copy",
		Mode:             "steady_state",
		WarmupIterations: 0,
		Concurrency:      1,
		CryptoProfile:    CryptoProfile{PubAlg: "RSA-2048", Cipher: "AES-256", Compression: "ZLIB", Hash: "SHA-256"},
		OutputEncoding:   "binary",
		KeySetPath:       keysDir,
		KeySetChecksum:   keySum,
		CorpusPath:       corpusDir,
		CorpusChecksum:   corpusSum,
		OutputDir:        t.TempDir(),
		Operation:        "roundtrip",
	}
	out, err := Run(cmd, time.Now(), quietLog)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	png := findOp(out, "image.png")
	if png == nil {
		t.Fatal("missing image.png operation")
	}
	if !png.Skipped {
		t.Errorf("image.png should be skipped (unsupported)")
	}
	if png.SkipReason == nil || *png.SkipReason != skipReasonUnsupported {
		t.Errorf("image.png skip reason = %v, want %q", png.SkipReason, skipReasonUnsupported)
	}
	if png.OutputFileName != nil {
		t.Errorf("unsupported file must have no output name, got %v", *png.OutputFileName)
	}

	doc := findOp(out, "doc.txt")
	if doc == nil || doc.Skipped {
		t.Fatal("doc.txt should be processed, not skipped")
	}
}

func TestRunColdStartSetsStartupMs(t *testing.T) {
	cmd := baseCommand(t, "test-copy")
	cmd.Mode = "cold_start"
	cmd.WarmupIterations = 0
	out, err := Run(cmd, time.Now().Add(-5*time.Millisecond), quietLog)
	if err != nil {
		t.Fatal(err)
	}
	if out.ProcessStartupMs == nil {
		t.Fatal("cold_start must record processStartupMs")
	}
	if *out.ProcessStartupMs < 0 {
		t.Errorf("processStartupMs must be >= 0, got %v", *out.ProcessStartupMs)
	}
}

func TestRunSteadyStateNoStartupMs(t *testing.T) {
	cmd := baseCommand(t, "test-copy")
	out, err := Run(cmd, time.Now(), quietLog)
	if err != nil {
		t.Fatal(err)
	}
	if out.ProcessStartupMs != nil {
		t.Errorf("steady_state must not record processStartupMs, got %v", *out.ProcessStartupMs)
	}
}

func TestRunCorrectnessFailure(t *testing.T) {
	cmd := baseCommand(t, "test-corrupt")
	out, err := Run(cmd, time.Now(), quietLog)
	if err != nil {
		t.Fatalf("run should succeed (recorded failure), got %v", err)
	}
	doc := findOp(out, "doc.txt")
	if doc == nil {
		t.Fatal("missing doc.txt")
	}
	if doc.RoundTripOk {
		t.Errorf("expected roundTripOk = false for corrupt engine")
	}
	if doc.FailureType == nil || *doc.FailureType != failureCorrectness {
		t.Errorf("failureType = %v, want correctness_failure", doc.FailureType)
	}
}

func TestRunChecksumMismatchExit2(t *testing.T) {
	cmd := baseCommand(t, "test-copy")
	cmd.CorpusChecksum = "sha256:" + "ff" + cmd.CorpusChecksum[9:]
	_, err := Run(cmd, time.Now(), quietLog)
	assertExit(t, err, exitChecksumOrVer)
}

func TestRunUnknownVariantExit3(t *testing.T) {
	cmd := baseCommand(t, "does-not-exist")
	_, err := Run(cmd, time.Now(), quietLog)
	assertExit(t, err, exitBadConfig)
}

func TestRunUnsupportedPubAlgExit4(t *testing.T) {
	cmd := baseCommand(t, "test-copy")
	cmd.CryptoProfile.PubAlg = "RSA-9999"
	_, err := Run(cmd, time.Now(), quietLog)
	assertExit(t, err, exitUnsupportedProf)
}

func assertExit(t *testing.T, err error, want int) {
	t.Helper()
	if err == nil {
		t.Fatalf("expected error with exit code %d, got nil", want)
	}
	re, ok := err.(*runnerError)
	if !ok {
		t.Fatalf("expected *runnerError, got %T: %v", err, err)
	}
	if re.code != want {
		t.Errorf("exit code = %d, want %d (%s)", re.code, want, re.msg)
	}
}
