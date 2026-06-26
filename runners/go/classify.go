package main

import (
	"path/filepath"
	"strings"
)

// Classification is how a file name maps onto the file-type rules.
type Classification int

const (
	ClassSupported Classification = iota
	ClassSkip
	ClassUnsupported
)

// supportedExtensions are the file types the benchmark encrypts. Output naming
// appends ".pgp" to the full name (e.g. "x.zip" -> "x.zip.pgp").
var supportedExtensions = map[string]bool{
	".txt":  true,
	".xlsx": true,
	".xls":  true,
	".csv":  true,
	".pdf":  true,
	".zip":  true,
	".7z":   true,
	".dat":  true,
	".gz":   true,
}

// skipExtensions are control files that are never encrypted.
var skipExtensions = map[string]bool{".ctrl": true, ".ctl": true}

const (
	skipReasonControlFile = "control_file"
	skipReasonUnsupported = "unsupported"
)

// fileExtension returns the lower-cased extension including the dot ("" if none).
func fileExtension(name string) string {
	return strings.ToLower(filepath.Ext(name))
}

// classifyFile classifies name as supported, skip (.ctrl/.ctl), or unsupported.
// Control files take precedence over the unsupported fallback.
func classifyFile(name string) Classification {
	ext := fileExtension(name)
	if skipExtensions[ext] {
		return ClassSkip
	}
	if supportedExtensions[ext] {
		return ClassSupported
	}
	return ClassUnsupported
}

// skipReasonFor returns the skip reason for a non-supported classification, or
// "" for a supported file.
func skipReasonFor(c Classification) string {
	switch c {
	case ClassSkip:
		return skipReasonControlFile
	case ClassUnsupported:
		return skipReasonUnsupported
	default:
		return ""
	}
}

// isControlFile reports whether name is a .ctrl/.ctl file that must be skipped.
func isControlFile(name string) bool {
	return classifyFile(name) == ClassSkip
}

// outputName returns the encrypted output name (name + ".pgp") for a supported
// file. The bool is false when name is not a supported file type.
func outputName(name string) (string, bool) {
	if classifyFile(name) != ClassSupported {
		return "", false
	}
	return name + ".pgp", true
}
