package main

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"unicode"
	"unicode/utf8"
)

const (
	defaultMaxBatchFiles        = 20
	absoluteMaxBatchFiles       = 1000
	maxManifestBytes      int64 = 1 << 20
	maxBatchIDBytes             = 256
	maxBatchErrorBytes          = 512
)

type batchOptions struct {
	manifestPath string
	inputRoot    string
	outputRoot   string
	maxFiles     int
	workers      int
}

type batchManifest struct {
	Version int                 `json:"version"`
	Files   []batchManifestFile `json:"files"`
}

type batchManifestFile struct {
	ID     string `json:"id"`
	Input  string `json:"input"`
	Output string `json:"output"`
}

type preparedBatchFile struct {
	manifest batchManifestFile
	files    fileOptions
}

type preparedBatch struct {
	files    []preparedBatchFile
	maxFiles int
	workers  int
}

type batchReport struct {
	Version   int           `json:"version"`
	Operation string        `json:"operation"`
	MaxFiles  int           `json:"maxFiles"`
	Workers   int           `json:"workers"`
	Results   []batchResult `json:"results"`
}

type batchResult struct {
	ID        string `json:"id"`
	Input     string `json:"input"`
	Output    string `json:"output"`
	Status    string `json:"status"`
	ErrorCode string `json:"errorCode,omitempty"`
	Error     string `json:"error,omitempty"`
}

type batchOperationError struct {
	failed int
}

func (err batchOperationError) Error() string {
	return fmt.Sprintf("batch completed with %d failed file(s)", err.failed)
}

func addBatchFlags(flags *flag.FlagSet, options *batchOptions) {
	flags.StringVar(&options.manifestPath, "manifest", "", "batch manifest JSON file")
	flags.StringVar(&options.inputRoot, "input-root", "", "root directory for batch inputs")
	flags.StringVar(&options.outputRoot, "output-root", "", "root directory for batch outputs")
	flags.IntVar(&options.maxFiles, "max-files", defaultMaxBatchFiles, "maximum files allowed in a batch")
	flags.IntVar(&options.workers, "workers", 0, "batch workers (0 uses GOMAXPROCS)")
}

func prepareBatch(files fileOptions, options batchOptions) (*preparedBatch, bool, error) {
	if err := validateBatchLimits(options.maxFiles, options.workers); err != nil {
		return nil, false, err
	}
	if options.manifestPath == "" {
		if options.inputRoot != "" || options.outputRoot != "" || options.maxFiles != defaultMaxBatchFiles || options.workers != 0 {
			return nil, false, errors.New("batch options require -manifest")
		}
		return nil, false, nil
	}
	if files.input != "" || files.output != "" {
		return nil, false, errors.New("-manifest is mutually exclusive with -in and -out")
	}
	if options.inputRoot == "" || options.outputRoot == "" {
		return nil, false, errors.New("batch mode requires -input-root and -output-root")
	}

	manifest, err := readBatchManifest(options.manifestPath, options.maxFiles)
	if err != nil {
		return nil, false, err
	}
	inputRoot, err := resolveBatchRoot(options.inputRoot, "input")
	if err != nil {
		return nil, false, err
	}
	outputRoot, err := resolveBatchRoot(options.outputRoot, "output")
	if err != nil {
		return nil, false, err
	}
	prepared, err := prepareDecodedBatch(manifest, inputRoot, outputRoot, options.maxFiles, options.workers)
	if err != nil {
		return nil, false, err
	}
	return prepared, true, nil
}

func validateBatchLimits(maxFiles, workers int) error {
	if maxFiles <= 0 {
		return errors.New("-max-files must be positive")
	}
	if maxFiles > absoluteMaxBatchFiles {
		return fmt.Errorf("-max-files must not exceed %d", absoluteMaxBatchFiles)
	}
	if workers < 0 {
		return errors.New("-workers must be zero or positive")
	}
	return nil
}

func readBatchManifest(path string, maxFiles int) (batchManifest, error) {
	file, err := os.Open(path)
	if err != nil {
		return batchManifest{}, fmt.Errorf("open manifest: %w", err)
	}
	data, readErr := io.ReadAll(io.LimitReader(file, maxManifestBytes+1))
	closeErr := file.Close()
	if readErr != nil {
		return batchManifest{}, fmt.Errorf("read manifest: %w", readErr)
	}
	if closeErr != nil {
		return batchManifest{}, fmt.Errorf("close manifest: %w", closeErr)
	}
	if int64(len(data)) > maxManifestBytes {
		return batchManifest{}, errors.New("manifest exceeds 1 MiB")
	}
	manifest, err := decodeBatchManifest(bytes.NewReader(data))
	if err != nil {
		return batchManifest{}, err
	}
	if err := validateBatchManifest(manifest, maxFiles); err != nil {
		return batchManifest{}, err
	}
	return manifest, nil
}

func decodeBatchManifest(reader io.Reader) (batchManifest, error) {
	var manifest batchManifest
	decoder := json.NewDecoder(reader)
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&manifest); err != nil {
		return batchManifest{}, fmt.Errorf("decode manifest: %w", err)
	}
	var trailing any
	if err := decoder.Decode(&trailing); !errors.Is(err, io.EOF) {
		if err == nil {
			return batchManifest{}, errors.New("manifest contains trailing JSON")
		}
		return batchManifest{}, fmt.Errorf("decode trailing manifest data: %w", err)
	}
	return manifest, nil
}

func validateBatchManifest(manifest batchManifest, maxFiles int) error {
	if manifest.Version != 1 {
		return fmt.Errorf("unsupported manifest version %d", manifest.Version)
	}
	if len(manifest.Files) == 0 {
		return errors.New("manifest files must not be empty")
	}
	if len(manifest.Files) > maxFiles {
		return fmt.Errorf("manifest has %d files, exceeding -max-files %d", len(manifest.Files), maxFiles)
	}
	return nil
}

func prepareDecodedBatch(manifest batchManifest, inputRoot, outputRoot string, maxFiles, workers int) (*preparedBatch, error) {
	if err := validateBatchLimits(maxFiles, workers); err != nil {
		return nil, err
	}
	if err := validateBatchManifest(manifest, maxFiles); err != nil {
		return nil, err
	}

	prepared := make([]preparedBatchFile, len(manifest.Files))
	ids := make(map[string]struct{}, len(manifest.Files))
	outputs := make(map[string]struct{}, len(manifest.Files))
	for index, entry := range manifest.Files {
		id := strings.TrimSpace(entry.ID)
		if id == "" {
			return nil, fmt.Errorf("manifest file %d has an empty id", index)
		}
		if len(id) > maxBatchIDBytes {
			return nil, fmt.Errorf("manifest file %q id exceeds %d bytes", id, maxBatchIDBytes)
		}
		if _, exists := ids[id]; exists {
			return nil, fmt.Errorf("manifest contains duplicate id %q", id)
		}
		ids[id] = struct{}{}
		entry.ID = id

		if err := validateManifestPath(entry.Input, "input"); err != nil {
			return nil, fmt.Errorf("manifest file %q: %w", id, err)
		}
		if err := validateManifestPath(entry.Output, "output"); err != nil {
			return nil, fmt.Errorf("manifest file %q: %w", id, err)
		}
		validated, err := validateFileOptions(fileOptions{
			input:  filepath.Join(inputRoot, entry.Input),
			output: filepath.Join(outputRoot, entry.Output),
		})
		if err != nil {
			return nil, fmt.Errorf("manifest file %q: %w", id, err)
		}
		if !pathWithinRoot(inputRoot, validated.input) {
			return nil, fmt.Errorf("manifest file %q input resolves outside -input-root", id)
		}
		if !pathWithinRoot(outputRoot, validated.output) {
			return nil, fmt.Errorf("manifest file %q output resolves outside -output-root", id)
		}
		if _, exists := outputs[validated.output]; exists {
			return nil, fmt.Errorf("manifest contains duplicate canonical output path for file %q", id)
		}
		outputs[validated.output] = struct{}{}
		prepared[index] = preparedBatchFile{manifest: entry, files: validated}
	}

	return &preparedBatch{
		files:    prepared,
		maxFiles: maxFiles,
		workers:  effectiveWorkers(workers, len(prepared)),
	}, nil
}

func effectiveWorkers(workers, fileCount int) int {
	gomaxprocs := runtime.GOMAXPROCS(0)
	if workers == 0 || workers > gomaxprocs {
		workers = gomaxprocs
	}
	if workers > fileCount {
		workers = fileCount
	}
	if workers < 1 {
		workers = 1
	}
	return workers
}

func resolveBatchRoot(path, name string) (string, error) {
	resolved, err := filepath.EvalSymlinks(path)
	if err != nil {
		return "", fmt.Errorf("resolve %s root: %w", name, err)
	}
	resolved, err = filepath.Abs(resolved)
	if err != nil {
		return "", fmt.Errorf("make %s root absolute: %w", name, err)
	}
	info, err := os.Stat(resolved)
	if err != nil {
		return "", fmt.Errorf("inspect %s root: %w", name, err)
	}
	if !info.IsDir() {
		return "", fmt.Errorf("%s root is not a directory", name)
	}
	return filepath.Clean(resolved), nil
}

func validateManifestPath(path, name string) error {
	if path == "" {
		return fmt.Errorf("%s path must not be empty", name)
	}
	if strings.IndexByte(path, 0) >= 0 {
		return fmt.Errorf("%s path contains a NUL byte", name)
	}
	if filepath.IsAbs(path) || filepath.VolumeName(path) != "" {
		return fmt.Errorf("%s path must be relative", name)
	}
	for _, component := range strings.Split(path, string(filepath.Separator)) {
		if component == ".." {
			return fmt.Errorf("%s path must not contain traversal", name)
		}
	}
	if filepath.Clean(path) == "." {
		return fmt.Errorf("%s path must name a file", name)
	}
	return nil
}

func pathWithinRoot(root, path string) bool {
	relative, err := filepath.Rel(root, path)
	if err != nil {
		return false
	}
	return relative != ".." && !strings.HasPrefix(relative, ".."+string(filepath.Separator))
}

func runBatch(operation string, batch *preparedBatch, transform func(io.Writer, io.Reader) error) error {
	report := executeBatch(context.Background(), operation, batch, transform, true)
	encoder := json.NewEncoder(os.Stdout)
	encoder.SetEscapeHTML(false)
	if err := encoder.Encode(report); err != nil {
		return fmt.Errorf("write batch result: %w", err)
	}
	if failed := failedBatchResults(report); failed != 0 {
		return batchOperationError{failed: failed}
	}
	return nil
}

func executeBatch(ctx context.Context, operation string, batch *preparedBatch, transform func(io.Writer, io.Reader) error, detailedErrors bool) batchReport {
	results := make([]batchResult, len(batch.files))
	for index, file := range batch.files {
		results[index] = batchResult{
			ID:        file.manifest.ID,
			Input:     file.manifest.Input,
			Output:    file.manifest.Output,
			Status:    "failed",
			ErrorCode: "operation_failed",
			Error:     batchErrorMessage(ctx.Err(), detailedErrors),
		}
	}

	jobs := make(chan int)
	done := make(chan struct{}, batch.workers)
	for worker := 0; worker < batch.workers; worker++ {
		go func() {
			defer func() { done <- struct{}{} }()
			for index := range jobs {
				err := transformFileContext(ctx, batch.files[index].files, transform)
				if err == nil {
					results[index].Status = "success"
					results[index].ErrorCode = ""
					results[index].Error = ""
					continue
				}
				results[index].Error = batchErrorMessage(err, detailedErrors)
			}
		}()
	}

dispatch:
	for index := range batch.files {
		select {
		case jobs <- index:
		case <-ctx.Done():
			break dispatch
		}
	}
	close(jobs)
	for worker := 0; worker < batch.workers; worker++ {
		<-done
	}

	return batchReport{
		Version:   1,
		Operation: operation,
		MaxFiles:  batch.maxFiles,
		Workers:   batch.workers,
		Results:   results,
	}
}

func failedBatchResults(report batchReport) int {
	failed := 0
	for _, result := range report.Results {
		if result.Status == "failed" {
			failed++
		}
	}
	return failed
}

func batchErrorMessage(err error, detailed bool) string {
	if !detailed || err == nil {
		return "operation failed"
	}
	return sanitizeBatchError(err)
}

func sanitizeBatchError(err error) string {
	message := strings.Map(func(r rune) rune {
		if unicode.IsControl(r) {
			return ' '
		}
		return r
	}, err.Error())
	message = strings.Join(strings.Fields(message), " ")
	if message == "" {
		return "operation failed"
	}
	if len(message) <= maxBatchErrorBytes {
		return message
	}
	var truncated strings.Builder
	for _, r := range message {
		width := utf8.RuneLen(r)
		if truncated.Len()+width > maxBatchErrorBytes {
			break
		}
		truncated.WriteRune(r)
	}
	return truncated.String()
}
