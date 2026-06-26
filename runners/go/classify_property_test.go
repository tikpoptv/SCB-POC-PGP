package main

import (
	"strings"
	"testing"

	"pgregory.net/rapid"
)

// Feature: pgp-encryption-benchmark-go-java, Property 3: กฎการจำแนกชนิดไฟล์และการตั้งชื่อผลลัพธ์
//
// Validates: Requirements 32.2, 32.3, 32.4, 32.7

// supportedExtList mirrors the canonical supported allow-list.
var supportedExtList = []string{".txt", ".xlsx", ".xls", ".csv", ".pdf", ".zip", ".7z", ".dat", ".gz"}

// skipExtList are the control-file extensions that are always skipped.
var skipExtList = []string{".ctrl", ".ctl"}

// unsupportedExtList are example extensions that are skipped with reason "unsupported".
var unsupportedExtList = []string{".png", ".mp4", ".sh", ".docx", ".json", ".exe", ".md", ".bin", ".tar", ".log"}

// baseNameGen generates a non-empty file base name (no extension) that may
// include nested directory separators.
func baseNameGen() *rapid.Generator[string] {
	return rapid.Custom(func(t *rapid.T) string {
		segs := rapid.SliceOfN(
			rapid.StringMatching(`[A-Za-z0-9_-]{1,8}`),
			1, 3,
		).Draw(t, "segments")
		return strings.Join(segs, "/")
	})
}

// randomCase randomly varies the case of each letter in s to exercise the
// case-insensitive extension matching.
func randomCase(t *rapid.T, s string) string {
	var b strings.Builder
	for i, r := range s {
		upper := rapid.Bool().Draw(t, "upper")
		if upper && r >= 'a' && r <= 'z' {
			b.WriteString(strings.ToUpper(string(r)))
		} else {
			_ = i
			b.WriteRune(r)
		}
	}
	return b.String()
}

func TestProperty3_SupportedNaming(t *testing.T) {
	rapid.Check(t, func(t *rapid.T) {
		base := baseNameGen().Draw(t, "base")
		ext := rapid.SampledFrom(supportedExtList).Draw(t, "ext")
		ext = randomCase(t, ext)
		name := base + ext

		if got := classifyFile(name); got != ClassSupported {
			t.Fatalf("classifyFile(%q) = %v, want ClassSupported", name, got)
		}
		out, ok := outputName(name)
		if !ok {
			t.Fatalf("outputName(%q) ok = false, want true", name)
		}
		if want := name + ".pgp"; out != want {
			t.Fatalf("outputName(%q) = %q, want %q", name, out, want)
		}
		if r := skipReasonFor(classifyFile(name)); r != "" {
			t.Fatalf("skipReasonFor(supported) = %q, want \"\"", r)
		}
	})
}

func TestProperty3_ZipOfManyNaming(t *testing.T) {
	rapid.Check(t, func(t *rapid.T) {
		base := baseNameGen().Draw(t, "base")
		// zip-of-many: a ".zip" file must become "<name>.zip.pgp".
		ext := randomCase(t, ".zip")
		name := base + ext

		out, ok := outputName(name)
		if !ok {
			t.Fatalf("outputName(%q) ok = false, want true", name)
		}
		if want := name + ".pgp"; out != want {
			t.Fatalf("outputName(%q) = %q, want %q", name, out, want)
		}
		if !strings.HasSuffix(strings.ToLower(out), ".zip.pgp") {
			t.Fatalf("outputName(%q) = %q, want suffix .zip.pgp", name, out)
		}
	})
}

func TestProperty3_ControlFilesSkipped(t *testing.T) {
	rapid.Check(t, func(t *rapid.T) {
		base := baseNameGen().Draw(t, "base")
		ext := rapid.SampledFrom(skipExtList).Draw(t, "ext")
		ext = randomCase(t, ext)
		name := base + ext

		if got := classifyFile(name); got != ClassSkip {
			t.Fatalf("classifyFile(%q) = %v, want ClassSkip", name, got)
		}
		if r := skipReasonFor(classifyFile(name)); r != skipReasonControlFile {
			t.Fatalf("skipReasonFor(%q) = %q, want %q", name, r, skipReasonControlFile)
		}
		if out, ok := outputName(name); ok {
			t.Fatalf("outputName(%q) = (%q, true), want ok=false", name, out)
		}
	})
}

func TestProperty3_UnsupportedSkipped(t *testing.T) {
	rapid.Check(t, func(t *rapid.T) {
		base := baseNameGen().Draw(t, "base")
		ext := rapid.SampledFrom(unsupportedExtList).Draw(t, "ext")
		ext = randomCase(t, ext)
		name := base + ext

		if got := classifyFile(name); got != ClassUnsupported {
			t.Fatalf("classifyFile(%q) = %v, want ClassUnsupported", name, got)
		}
		if r := skipReasonFor(classifyFile(name)); r != skipReasonUnsupported {
			t.Fatalf("skipReasonFor(%q) = %q, want %q", name, r, skipReasonUnsupported)
		}
		if out, ok := outputName(name); ok {
			t.Fatalf("outputName(%q) = (%q, true), want ok=false", name, out)
		}
	})
}
