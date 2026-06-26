package main

import (
	"strings"
	"testing"
)

const validChecksum = "sha256:" + "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"

// validCommandJSON returns a minimal valid Command document as JSON.
func validCommandJSON() string {
	return `{
		"command": "run",
		"variantId": "go-inmem-single",
		"mode": "steady_state",
		"warmupIterations": 5,
		"concurrency": 4,
		"cryptoProfile": {"pubAlg": "RSA-2048", "cipher": "AES-256", "compression": "ZLIB", "hash": "SHA-256"},
		"outputEncoding": "binary",
		"keySetPath": "/tmp/keys",
		"keySetChecksum": "` + validChecksum + `",
		"corpusPath": "/tmp/corpus",
		"corpusChecksum": "` + validChecksum + `",
		"outputDir": "/tmp/out",
		"operation": "roundtrip"
	}`
}

func TestParseCommandValid(t *testing.T) {
	cmd, err := ParseCommand([]byte(validCommandJSON()))
	if err != nil {
		t.Fatalf("expected valid command, got error: %v", err)
	}
	if cmd.VariantID != "go-inmem-single" {
		t.Errorf("variantId = %q, want go-inmem-single", cmd.VariantID)
	}
	if cmd.CryptoProfile.Cipher != "AES-256" {
		t.Errorf("cipher = %q, want AES-256", cmd.CryptoProfile.Cipher)
	}
	if cmd.Operation != "roundtrip" {
		t.Errorf("operation = %q, want roundtrip", cmd.Operation)
	}
}

func TestParseCommandConfigErrors(t *testing.T) {
	cases := []struct {
		name    string
		mutate  func(string) string
		wantSub string
	}{
		{"invalid json", func(string) string { return "{not json" }, "invalid JSON"},
		{"missing field", func(s string) string {
			return strings.Replace(s, `"operation": "roundtrip"`, `"operationX": "roundtrip"`, 1)
		}, "missing required field"},
		{"unknown field", func(s string) string {
			return strings.Replace(s, `"operation": "roundtrip"`, `"operation": "roundtrip", "extra": 1`, 1)
		}, "unknown field"},
		{"bad command verb", func(s string) string {
			return strings.Replace(s, `"command": "run"`, `"command": "go"`, 1)
		}, "'command' must be 'run'"},
		{"bad mode", func(s string) string {
			return strings.Replace(s, `"mode": "steady_state"`, `"mode": "warp"`, 1)
		}, "'mode' must be one of"},
		{"warmup out of range", func(s string) string {
			return strings.Replace(s, `"warmupIterations": 5`, `"warmupIterations": 500`, 1)
		}, "'warmupIterations' must be in [0,100]"},
		{"concurrency too low", func(s string) string {
			return strings.Replace(s, `"concurrency": 4`, `"concurrency": 0`, 1)
		}, "'concurrency' must be >= 1"},
		{"bad output encoding", func(s string) string {
			return strings.Replace(s, `"outputEncoding": "binary"`, `"outputEncoding": "base64"`, 1)
		}, "'outputEncoding' must be one of"},
		{"bad operation", func(s string) string {
			return strings.Replace(s, `"operation": "roundtrip"`, `"operation": "sign"`, 1)
		}, "'operation' must be one of"},
		{"empty pubAlg", func(s string) string {
			return strings.Replace(s, `"pubAlg": "RSA-2048"`, `"pubAlg": ""`, 1)
		}, "cryptoProfile.pubAlg"},
		{"bad checksum", func(s string) string {
			return strings.Replace(s, validChecksum, "md5:abc", 1)
		}, "must match sha256"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			_, err := ParseCommand([]byte(tc.mutate(validCommandJSON())))
			if err == nil {
				t.Fatalf("expected config error, got nil")
			}
			re, ok := err.(*runnerError)
			if !ok {
				t.Fatalf("expected *runnerError, got %T", err)
			}
			if re.code != exitBadConfig {
				t.Errorf("exit code = %d, want %d", re.code, exitBadConfig)
			}
			if !strings.Contains(re.msg, tc.wantSub) {
				t.Errorf("error %q does not contain %q", re.msg, tc.wantSub)
			}
		})
	}
}
