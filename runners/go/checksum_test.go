package main

import (
	"crypto/sha256"
	"encoding/hex"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"testing"
)

// expectedKeySetChecksum independently reproduces harness keys._aggregate_checksum.
func expectedKeySetChecksum(t *testing.T, dir string) string {
	t.Helper()
	entries, err := os.ReadDir(dir)
	if err != nil {
		t.Fatal(err)
	}
	var lines []string
	for _, e := range entries {
		name := e.Name()
		if !strings.HasSuffix(name, "-public.asc") && !strings.HasSuffix(name, "-private.asc") {
			continue
		}
		b, err := os.ReadFile(filepath.Join(dir, name))
		if err != nil {
			t.Fatal(err)
		}
		sum := sha256.Sum256(b)
		lines = append(lines, name+":sha256:"+hex.EncodeToString(sum[:]))
	}
	sort.Strings(lines)
	d := sha256.Sum256([]byte(strings.Join(lines, "\n")))
	return "sha256:" + hex.EncodeToString(d[:])
}

// expectedCorpusChecksum independently reproduces harness corpus._aggregate_checksum.
func expectedCorpusChecksum(t *testing.T, root string) string {
	t.Helper()
	type ent struct{ rel, hx string }
	var ents []ent
	err := filepath.Walk(root, func(p string, fi os.FileInfo, err error) error {
		if err != nil {
			return err
		}
		if fi.IsDir() {
			return nil
		}
		b, err := os.ReadFile(p)
		if err != nil {
			return err
		}
		rel, _ := filepath.Rel(root, p)
		sum := sha256.Sum256(b)
		ents = append(ents, ent{filepath.ToSlash(rel), hex.EncodeToString(sum[:])})
		return nil
	})
	if err != nil {
		t.Fatal(err)
	}
	sort.Slice(ents, func(i, j int) bool { return ents[i].rel < ents[j].rel })
	h := sha256.New()
	for _, e := range ents {
		h.Write([]byte(e.rel))
		h.Write([]byte{0})
		h.Write([]byte(e.hx))
		h.Write([]byte("\n"))
	}
	return "sha256:" + hex.EncodeToString(h.Sum(nil))
}

func writeFile(t *testing.T, path string, content []byte) {
	t.Helper()
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(path, content, 0o644); err != nil {
		t.Fatal(err)
	}
}

func TestComputeKeySetChecksumMatchesAlgorithm(t *testing.T) {
	dir := t.TempDir()
	writeFile(t, filepath.Join(dir, "rsa2048-public.asc"), []byte("PUB-A"))
	writeFile(t, filepath.Join(dir, "rsa2048-private.asc"), []byte("PRIV-A"))
	writeFile(t, filepath.Join(dir, "cv25519-public.asc"), []byte("PUB-B"))
	writeFile(t, filepath.Join(dir, "cv25519-private.asc"), []byte("PRIV-B"))
	writeFile(t, filepath.Join(dir, "KEYINFO.md"), []byte("ignored"))

	got, err := ComputeKeySetChecksum(dir)
	if err != nil {
		t.Fatal(err)
	}
	want := expectedKeySetChecksum(t, dir)
	if got != want {
		t.Errorf("key-set checksum = %s, want %s", got, want)
	}

	// Determinism: recomputing yields the same value.
	again, _ := ComputeKeySetChecksum(dir)
	if again != got {
		t.Errorf("non-deterministic key-set checksum: %s vs %s", got, again)
	}
}

func TestComputeCorpusChecksumMatchesAlgorithm(t *testing.T) {
	root := t.TempDir()
	writeFile(t, filepath.Join(root, "small", "a.txt"), []byte("hello"))
	writeFile(t, filepath.Join(root, "small", "b.csv"), []byte("1,2,3"))
	writeFile(t, filepath.Join(root, "skip", "control.ctrl"), []byte("ctrl"))

	got, err := ComputeCorpusChecksum(root)
	if err != nil {
		t.Fatal(err)
	}
	want := expectedCorpusChecksum(t, root)
	if got != want {
		t.Errorf("corpus checksum = %s, want %s", got, want)
	}
}

func TestChecksumDetectsSingleByteChange(t *testing.T) {
	root := t.TempDir()
	target := filepath.Join(root, "data.dat")
	writeFile(t, target, []byte("original-content"))
	before, _ := ComputeCorpusChecksum(root)

	// Change exactly one byte; the aggregate must change.
	writeFile(t, target, []byte("Original-content"))
	after, _ := ComputeCorpusChecksum(root)
	if before == after {
		t.Errorf("checksum did not change after a one-byte edit: %s", before)
	}
}

func TestChecksumEqualCaseInsensitive(t *testing.T) {
	a := "sha256:ABCDEF" + strings.Repeat("0", 58)
	b := "sha256:abcdef" + strings.Repeat("0", 58)
	if !checksumEqual(a, b) {
		t.Errorf("expected case-insensitive checksum equality")
	}
	if checksumEqual(a, "sha256:"+strings.Repeat("0", 64)) {
		t.Errorf("expected mismatch to be detected")
	}
}
