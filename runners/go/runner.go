package main

import (
	"fmt"
	"io"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"sync"
	"time"
)

const runnerID = "go"

// Run executes a single Command end-to-end and returns the RunnerOutput. It
// verifies the Key_Set/Test_Corpus checksums, loads the Key_Set, resolves the
// variant engine, runs any warm-up iterations, then processes the corpus timing
// only the crypto calls. programStart is used to derive Process_Startup_Time for
// cold_start runs; logf writes diagnostics to stderr only.
func Run(cmd *Command, programStart time.Time, logf func(string, ...any)) (*RunnerOutput, error) {
	keySeen, err := ComputeKeySetChecksum(cmd.KeySetPath)
	if err != nil {
		return nil, errWithCode(exitOperationFail, "compute key-set checksum: %v", err)
	}
	if !checksumEqual(keySeen, cmd.KeySetChecksum) {
		return nil, errWithCode(exitChecksumOrVer,
			"key-set checksum mismatch: expected %s, computed %s", cmd.KeySetChecksum, keySeen)
	}
	corpusSeen, err := ComputeCorpusChecksum(cmd.CorpusPath)
	if err != nil {
		return nil, errWithCode(exitOperationFail, "compute corpus checksum: %v", err)
	}
	if !checksumEqual(corpusSeen, cmd.CorpusChecksum) {
		return nil, errWithCode(exitChecksumOrVer,
			"corpus checksum mismatch: expected %s, computed %s", cmd.CorpusChecksum, corpusSeen)
	}
	logf("checksum gate passed (keySet=%s corpus=%s)", keySeen, corpusSeen)

	keys, err := LoadKeySet(cmd.KeySetPath)
	if err != nil {
		return nil, errWithCode(exitOperationFail, "load key set: %v", err)
	}
	if !keys.HasKeyFor(cmd.CryptoProfile.PubAlg) {
		return nil, errWithCode(exitUnsupportedProf,
			"crypto-profile not supported: no key for pubAlg %q", cmd.CryptoProfile.PubAlg)
	}

	eng, ok := NewEngine(cmd.VariantID)
	if !ok {
		return nil, errWithCode(exitBadConfig,
			"unknown variantId %q (registered: %s)", cmd.VariantID, strings.Join(RegisteredVariants(), ", "))
	}
	if sup, isSup := eng.(ProfileSupporter); isSup {
		if perr := sup.SupportsProfile(cmd.CryptoProfile); perr != nil {
			return nil, errWithCode(exitUnsupportedProf, "crypto-profile not supported: %v", perr)
		}
	}

	var processStartupMs *float64
	if cmd.Mode == "cold_start" {
		ms := float64(time.Since(programStart).Nanoseconds()) / 1e6
		processStartupMs = &ms
	}

	files, err := collectCorpusFiles(cmd.CorpusPath)
	if err != nil {
		return nil, errWithCode(exitOperationFail, "scan corpus: %v", err)
	}

	if err := os.MkdirAll(cmd.OutputDir, 0o755); err != nil {
		return nil, errWithCode(exitOperationFail, "create output dir: %v", err)
	}

	for i := 0; i < cmd.WarmupIterations; i++ {
		if _, _, werr := processCorpus(eng, cmd, keys, files, false); werr != nil {
			return nil, werr
		}
		logf("warm-up iteration %d/%d complete", i+1, cmd.WarmupIterations)
	}

	ops, hwAccel, err := processCorpus(eng, cmd, keys, files, true)
	if err != nil {
		return nil, err
	}

	out := &RunnerOutput{
		RunnerID:            runnerID,
		VariantID:           cmd.VariantID,
		Mode:                cmd.Mode,
		ScenarioID:          deriveScenarioID(cmd.CorpusPath),
		CryptoProfileID:     deriveCryptoProfileID(cmd.CryptoProfile),
		Concurrency:         cmd.Concurrency,
		OutputEncoding:      cmd.OutputEncoding,
		ProcessStartupMs:    processStartupMs,
		HardwareAccel:       hwAccel,
		KeySetChecksumSeen:  keySeen,
		CorpusChecksumSeen:  corpusSeen,
		Gc:                  nil,
		Operations:          ops,
		ResourceSamplesNote: "CPU/RAM sampled externally by the Harness",
	}
	return out, nil
}

// corpusFile is one regular file discovered under the corpus root.
type corpusFile struct {
	abs string
	rel string // POSIX-style path relative to the corpus root
}

// collectCorpusFiles walks the corpus and returns its regular files sorted by
// relative path so processing order is deterministic.
func collectCorpusFiles(root string) ([]corpusFile, error) {
	var files []corpusFile
	err := filepath.WalkDir(root, func(p string, d os.DirEntry, err error) error {
		if err != nil {
			return err
		}
		if d.IsDir() {
			return nil
		}
		rel, rerr := filepath.Rel(root, p)
		if rerr != nil {
			return rerr
		}
		files = append(files, corpusFile{abs: p, rel: filepath.ToSlash(rel)})
		return nil
	})
	if err != nil {
		return nil, err
	}
	sort.Slice(files, func(i, j int) bool { return files[i].rel < files[j].rel })
	return files, nil
}

// processCorpus runs the requested operation over every file. When record is
// false (warm-up) the work is still performed but no samples are kept. Engines
// implementing ConcurrencyHint are driven across a worker pool; all others use
// the sequential path. Either way samples are emitted in deterministic corpus
// order. Per-file failures are recorded on the sample and do not abort the run;
// only infrastructure errors return a fatal error.
func processCorpus(eng CryptoEngine, cmd *Command, keys *KeySet, files []corpusFile, record bool) ([]OperationSample, bool, error) {
	workers := 1
	if hint, ok := eng.(ConcurrencyHint); ok {
		workers = hint.WorkerPoolSize(cmd.Concurrency)
	}
	if workers < 1 {
		workers = 1
	}
	if workers == 1 || len(files) <= 1 {
		return processCorpusSequential(eng, cmd, keys, files, record)
	}
	return processCorpusParallel(eng, cmd, keys, files, record, workers)
}

func processCorpusSequential(eng CryptoEngine, cmd *Command, keys *KeySet, files []corpusFile, record bool) ([]OperationSample, bool, error) {
	var ops []OperationSample
	hwAccel := false
	for _, f := range files {
		sample, hw, err := processFile(eng, cmd, keys, f)
		if err != nil {
			return nil, false, err
		}
		if hw {
			hwAccel = true
		}
		if record {
			ops = append(ops, sample)
		}
	}
	if ops == nil {
		ops = []OperationSample{}
	}
	return ops, hwAccel, nil
}

// processCorpusParallel dispatches files across a bounded worker pool. Each file
// is independent and the engine is safe for concurrent use; results are written
// into per-file slots and aggregated in corpus order, so the recorded samples
// match the sequential path apart from wall-clock interleaving.
func processCorpusParallel(eng CryptoEngine, cmd *Command, keys *KeySet, files []corpusFile, record bool, workers int) ([]OperationSample, bool, error) {
	type fileResult struct {
		sample OperationSample
		hw     bool
		err    error
	}
	results := make([]fileResult, len(files))

	sem := make(chan struct{}, workers)
	var wg sync.WaitGroup
	for i := range files {
		wg.Add(1)
		sem <- struct{}{}
		go func(idx int) {
			defer wg.Done()
			defer func() { <-sem }()
			sample, hw, err := processFile(eng, cmd, keys, files[idx])
			results[idx] = fileResult{sample: sample, hw: hw, err: err}
		}(i)
	}
	wg.Wait()

	var ops []OperationSample
	hwAccel := false
	for _, r := range results {
		if r.err != nil {
			return nil, false, r.err
		}
		if r.hw {
			hwAccel = true
		}
		if record {
			ops = append(ops, r.sample)
		}
	}
	if ops == nil {
		ops = []OperationSample{}
	}
	return ops, hwAccel, nil
}

// processFile handles one corpus file according to cmd.Operation. Control files
// and unsupported extensions are skipped with a reason; supported types proceed
// to crypto.
func processFile(eng CryptoEngine, cmd *Command, keys *KeySet, f corpusFile) (OperationSample, bool, error) {
	info, err := os.Stat(f.abs)
	if err != nil {
		return OperationSample{}, false, fmt.Errorf("stat %s: %w", f.rel, err)
	}
	sample := OperationSample{
		FileName:      f.rel,
		FileType:      fileExtension(f.rel),
		OriginalBytes: info.Size(),
		RoundTripOk:   false,
	}

	if class := classifyFile(f.rel); class != ClassSupported {
		sample.Skipped = true
		reason := skipReasonFor(class)
		sample.SkipReason = &reason
		return sample, false, nil
	}

	switch cmd.Operation {
	case "encrypt":
		return doEncryptOnly(eng, cmd, keys, f, sample)
	case "decrypt":
		return doDecryptOnly(eng, cmd, keys, f, sample)
	default: // "roundtrip"
		return doRoundtrip(eng, cmd, keys, f, sample)
	}
}

// doRoundtrip encrypts then decrypts and verifies byte-for-byte equality.
func doRoundtrip(eng CryptoEngine, cmd *Command, keys *KeySet, f corpusFile, sample OperationSample) (OperationSample, bool, error) {
	outName, _ := outputName(f.rel)
	sample.OutputFileName = &outName
	ctPath := filepath.Join(cmd.OutputDir, filepath.FromSlash(outName))

	ctSize, encT, err := encryptToFile(eng, cmd, keys, f.abs, ctPath)
	if err != nil {
		markFailure(&sample, failureOperation)
		return sample, false, nil
	}
	applyEncryptTiming(&sample, encT)
	sample.CiphertextBytes = &ctSize

	decPath := ctPath + ".dec"
	_, decT, err := decryptToFile(eng, cmd, keys, ctPath, decPath)
	if err != nil {
		markFailure(&sample, failureOperation)
		return sample, encT.HardwareAccel, nil
	}
	applyDecryptTiming(&sample, decT)

	equal, err := filesEqual(f.abs, decPath)
	_ = os.Remove(decPath)
	if err != nil {
		markFailure(&sample, failureOperation)
		return sample, encT.HardwareAccel || decT.HardwareAccel, nil
	}
	sample.RoundTripOk = equal
	if !equal {
		markFailure(&sample, failureCorrectness)
	}
	return sample, encT.HardwareAccel || decT.HardwareAccel, nil
}

func doEncryptOnly(eng CryptoEngine, cmd *Command, keys *KeySet, f corpusFile, sample OperationSample) (OperationSample, bool, error) {
	outName, _ := outputName(f.rel)
	sample.OutputFileName = &outName
	ctPath := filepath.Join(cmd.OutputDir, filepath.FromSlash(outName))

	ctSize, encT, err := encryptToFile(eng, cmd, keys, f.abs, ctPath)
	if err != nil {
		markFailure(&sample, failureOperation)
		return sample, false, nil
	}
	applyEncryptTiming(&sample, encT)
	sample.CiphertextBytes = &ctSize
	return sample, encT.HardwareAccel, nil
}

func doDecryptOnly(eng CryptoEngine, cmd *Command, keys *KeySet, f corpusFile, sample OperationSample) (OperationSample, bool, error) {
	decPath := filepath.Join(cmd.OutputDir, filepath.FromSlash(f.rel)+".dec")
	_, decT, err := decryptToFile(eng, cmd, keys, f.abs, decPath)
	if err != nil {
		markFailure(&sample, failureOperation)
		return sample, false, nil
	}
	applyDecryptTiming(&sample, decT)
	return sample, decT.HardwareAccel, nil
}

// encryptToFile runs the engine writing ciphertext from src to dst, returning
// the ciphertext byte size and the crypto-only Timing.
func encryptToFile(eng CryptoEngine, cmd *Command, keys *KeySet, src, dst string) (int64, Timing, error) {
	if err := os.MkdirAll(filepath.Dir(dst), 0o755); err != nil {
		return 0, Timing{}, err
	}
	in, err := os.Open(src)
	if err != nil {
		return 0, Timing{}, err
	}
	defer in.Close()
	out, err := os.Create(dst)
	if err != nil {
		return 0, Timing{}, err
	}
	timing, encErr := eng.Encrypt(in, out, cmd.CryptoProfile, keys)
	closeErr := out.Close()
	if encErr != nil {
		return 0, Timing{}, encErr
	}
	if closeErr != nil {
		return 0, Timing{}, closeErr
	}
	fi, err := os.Stat(dst)
	if err != nil {
		return 0, Timing{}, err
	}
	return fi.Size(), timing, nil
}

// decryptToFile runs the engine writing plaintext from ciphertext src to dst,
// returning the plaintext byte size and the crypto-only Timing.
func decryptToFile(eng CryptoEngine, cmd *Command, keys *KeySet, src, dst string) (int64, Timing, error) {
	if err := os.MkdirAll(filepath.Dir(dst), 0o755); err != nil {
		return 0, Timing{}, err
	}
	in, err := os.Open(src)
	if err != nil {
		return 0, Timing{}, err
	}
	defer in.Close()
	out, err := os.Create(dst)
	if err != nil {
		return 0, Timing{}, err
	}
	timing, decErr := eng.Decrypt(in, out, cmd.CryptoProfile, keys)
	closeErr := out.Close()
	if decErr != nil {
		return 0, Timing{}, decErr
	}
	if closeErr != nil {
		return 0, Timing{}, closeErr
	}
	fi, err := os.Stat(dst)
	if err != nil {
		return 0, Timing{}, err
	}
	return fi.Size(), timing, nil
}

// filesEqual compares two files byte-for-byte without loading them whole.
func filesEqual(a, b string) (bool, error) {
	fa, err := os.Open(a)
	if err != nil {
		return false, err
	}
	defer fa.Close()
	fb, err := os.Open(b)
	if err != nil {
		return false, err
	}
	defer fb.Close()

	const chunk = 64 * 1024
	bufA := make([]byte, chunk)
	bufB := make([]byte, chunk)
	for {
		na, errA := io.ReadFull(fa, bufA)
		nb, errB := io.ReadFull(fb, bufB)
		if na != nb {
			return false, nil
		}
		if na > 0 {
			for i := 0; i < na; i++ {
				if bufA[i] != bufB[i] {
					return false, nil
				}
			}
		}
		aEnd := errA == io.EOF || errA == io.ErrUnexpectedEOF
		bEnd := errB == io.EOF || errB == io.ErrUnexpectedEOF
		if aEnd || bEnd {
			if aEnd != bEnd {
				return false, nil
			}
			return true, nil
		}
		if errA != nil {
			return false, errA
		}
		if errB != nil {
			return false, errB
		}
	}
}

func markFailure(sample *OperationSample, kind string) {
	k := kind
	sample.FailureType = &k
	sample.RoundTripOk = false
}

func applyEncryptTiming(sample *OperationSample, t Timing) {
	t = honestBreakdown(t)
	ms := nanosToMs(t.TotalNanos)
	sample.EncryptMs = &ms
	sample.AsymEncryptMs = subTimingMs(t.AsymNanos)
	sample.SymEncryptMs = subTimingMs(t.SymNanos)
}

func applyDecryptTiming(sample *OperationSample, t Timing) {
	t = honestBreakdown(t)
	ms := nanosToMs(t.TotalNanos)
	sample.DecryptMs = &ms
	sample.AsymDecryptMs = subTimingMs(t.AsymNanos)
	sample.SymDecryptMs = subTimingMs(t.SymNanos)
}

// honestBreakdown drops an asym/sym breakdown that is inconsistent with the
// total time to the NotSeparable sentinel rather than emitting a contradiction.
func honestBreakdown(t Timing) Timing {
	if !t.breakdownConsistent() {
		t.AsymNanos = NotSeparable
		t.SymNanos = NotSeparable
	}
	return t
}

func nanosToMs(n int64) float64 { return float64(n) / 1e6 }

// subTimingMs renders an asym/sym sub-measurement: -1 stays -1 (not separable),
// otherwise it is converted to ms.
func subTimingMs(n int64) *float64 {
	if n == NotSeparable {
		v := -1.0
		return &v
	}
	v := nanosToMs(n)
	return &v
}

// deriveScenarioID derives a Scenario identifier from the corpus directory name.
func deriveScenarioID(corpusPath string) string {
	base := filepath.Base(filepath.Clean(corpusPath))
	if base == "." || base == string(filepath.Separator) || base == "" {
		return "scenario"
	}
	return base
}

// deriveCryptoProfileID derives a stable, readable id from the profile fields.
func deriveCryptoProfileID(p CryptoProfile) string {
	slug := func(s string) string {
		return strings.ToLower(strings.ReplaceAll(strings.TrimSpace(s), " ", "-"))
	}
	return slug(p.PubAlg) + "_" + slug(p.Cipher) + "_" + slug(p.Compression) + "_" + slug(p.Hash)
}
