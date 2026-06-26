package main

import (
	"encoding/json"
	"fmt"
	"regexp"
	"strings"
)

// This file is the Go view of the shared CLI contract JSON shapes
// (contract/command.schema.json and contract/runner-output.schema.json).

var (
	allowedModes      = map[string]bool{"cold_start": true, "steady_state": true}
	allowedOperations = map[string]bool{"encrypt": true, "decrypt": true, "roundtrip": true}
	allowedEncodings  = map[string]bool{"binary": true, "armored": true}
	checksumPattern   = regexp.MustCompile(`^sha256:[0-9a-fA-F]{64}$`)
)

// CryptoProfile is the set of PGP algorithm choices for a Scenario.
type CryptoProfile struct {
	PubAlg      string `json:"pubAlg"`
	Cipher      string `json:"cipher"`
	Compression string `json:"compression"`
	Hash        string `json:"hash"`
}

// Command is the single JSON object the harness sends on stdin.
type Command struct {
	Command          string        `json:"command"`
	VariantID        string        `json:"variantId"`
	Mode             string        `json:"mode"`
	WarmupIterations int           `json:"warmupIterations"`
	Concurrency      int           `json:"concurrency"`
	CryptoProfile    CryptoProfile `json:"cryptoProfile"`
	OutputEncoding   string        `json:"outputEncoding"`
	KeySetPath       string        `json:"keySetPath"`
	KeySetChecksum   string        `json:"keySetChecksum"`
	CorpusPath       string        `json:"corpusPath"`
	CorpusChecksum   string        `json:"corpusChecksum"`
	OutputDir        string        `json:"outputDir"`
	Operation        string        `json:"operation"`
}

// requiredCommandFields are checked separately from typed decoding because
// encoding/json cannot tell a missing field from a zero value.
var requiredCommandFields = []string{
	"command", "variantId", "mode", "warmupIterations", "concurrency",
	"cryptoProfile", "outputEncoding", "keySetPath", "keySetChecksum",
	"corpusPath", "corpusChecksum", "outputDir", "operation",
}

// ParseCommand decodes and validates a Command JSON document, reporting any
// problem as a config error (exit code 3).
func ParseCommand(data []byte) (*Command, error) {
	var raw map[string]json.RawMessage
	dec := json.NewDecoder(strings.NewReader(string(data)))
	if err := dec.Decode(&raw); err != nil {
		return nil, errWithCode(exitBadConfig, "command: invalid JSON: %v", err)
	}
	for _, f := range requiredCommandFields {
		if _, ok := raw[f]; !ok {
			return nil, errWithCode(exitBadConfig, "command: missing required field %q", f)
		}
	}

	var cmd Command
	strict := json.NewDecoder(strings.NewReader(string(data)))
	strict.DisallowUnknownFields()
	if err := strict.Decode(&cmd); err != nil {
		return nil, errWithCode(exitBadConfig, "command: %v", err)
	}

	if err := cmd.validate(); err != nil {
		return nil, err
	}
	return &cmd, nil
}

// validate enforces the value constraints from command.schema.json.
func (c *Command) validate() error {
	if c.Command != "run" {
		return errWithCode(exitBadConfig, "command: field 'command' must be 'run', got %q", c.Command)
	}
	if strings.TrimSpace(c.VariantID) == "" {
		return errWithCode(exitBadConfig, "command: 'variantId' must be a non-empty string")
	}
	if !allowedModes[c.Mode] {
		return errWithCode(exitBadConfig, "command: 'mode' must be one of cold_start|steady_state, got %q", c.Mode)
	}
	if c.WarmupIterations < 0 || c.WarmupIterations > 100 {
		return errWithCode(exitBadConfig, "command: 'warmupIterations' must be in [0,100], got %d", c.WarmupIterations)
	}
	if c.Concurrency < 1 {
		return errWithCode(exitBadConfig, "command: 'concurrency' must be >= 1, got %d", c.Concurrency)
	}
	if !allowedEncodings[c.OutputEncoding] {
		return errWithCode(exitBadConfig, "command: 'outputEncoding' must be one of binary|armored, got %q", c.OutputEncoding)
	}
	if !allowedOperations[c.Operation] {
		return errWithCode(exitBadConfig, "command: 'operation' must be one of encrypt|decrypt|roundtrip, got %q", c.Operation)
	}
	for name, val := range map[string]string{
		"cryptoProfile.pubAlg":      c.CryptoProfile.PubAlg,
		"cryptoProfile.cipher":      c.CryptoProfile.Cipher,
		"cryptoProfile.compression": c.CryptoProfile.Compression,
		"cryptoProfile.hash":        c.CryptoProfile.Hash,
		"keySetPath":                c.KeySetPath,
		"corpusPath":                c.CorpusPath,
		"outputDir":                 c.OutputDir,
	} {
		if strings.TrimSpace(val) == "" {
			return errWithCode(exitBadConfig, "command: %q must be a non-empty string", name)
		}
	}
	if !checksumPattern.MatchString(c.KeySetChecksum) {
		return errWithCode(exitBadConfig, "command: 'keySetChecksum' must match sha256:<64 hex>, got %q", c.KeySetChecksum)
	}
	if !checksumPattern.MatchString(c.CorpusChecksum) {
		return errWithCode(exitBadConfig, "command: 'corpusChecksum' must match sha256:<64 hex>, got %q", c.CorpusChecksum)
	}
	return nil
}

// GcStats mirrors the optional gc object in RunnerOutput.
type GcStats struct {
	Collections  int      `json:"collections"`
	TotalPauseMs float64  `json:"totalPauseMs"`
	GcType       string   `json:"gcType"`
	HeapInitMb   *float64 `json:"heapInitMb,omitempty"`
	HeapMaxMb    *float64 `json:"heapMaxMb,omitempty"`
}

// OperationSample is one raw per-operation sample.
type OperationSample struct {
	FileName        string   `json:"fileName"`
	FileType        string   `json:"fileType"`
	OriginalBytes   int64    `json:"originalBytes"`
	CiphertextBytes *int64   `json:"ciphertextBytes"`
	Skipped         bool     `json:"skipped"`
	SkipReason      *string  `json:"skipReason"`
	EncryptMs       *float64 `json:"encryptMs"`
	DecryptMs       *float64 `json:"decryptMs"`
	AsymEncryptMs   *float64 `json:"asymEncryptMs"`
	AsymDecryptMs   *float64 `json:"asymDecryptMs"`
	SymEncryptMs    *float64 `json:"symEncryptMs"`
	SymDecryptMs    *float64 `json:"symDecryptMs"`
	RoundTripOk     bool     `json:"roundTripOk"`
	FailureType     *string  `json:"failureType"`
	OutputFileName  *string  `json:"outputFileName"`
}

// RunnerOutput is the single JSON object the runner writes to stdout.
type RunnerOutput struct {
	RunnerID            string            `json:"runnerId"`
	VariantID           string            `json:"variantId"`
	Mode                string            `json:"mode"`
	ScenarioID          string            `json:"scenarioId"`
	CryptoProfileID     string            `json:"cryptoProfileId"`
	Concurrency         int               `json:"concurrency"`
	OutputEncoding      string            `json:"outputEncoding"`
	ProcessStartupMs    *float64          `json:"processStartupMs"`
	HardwareAccel       bool              `json:"hardwareAccel"`
	KeySetChecksumSeen  string            `json:"keySetChecksumSeen"`
	CorpusChecksumSeen  string            `json:"corpusChecksumSeen"`
	Gc                  *GcStats          `json:"gc"`
	Operations          []OperationSample `json:"operations"`
	ResourceSamplesNote string            `json:"resourceSamplesNote,omitempty"`
}

const (
	failureOperation   = "operation_failure"
	failureCorrectness = "correctness_failure"
)

// Encode renders the output as a single compact JSON line.
func (o *RunnerOutput) Encode() ([]byte, error) {
	b, err := json.Marshal(o)
	if err != nil {
		return nil, fmt.Errorf("encode RunnerOutput: %w", err)
	}
	return b, nil
}
