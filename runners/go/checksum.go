package main

import (
	"crypto/sha256"
	"encoding/hex"
	"io"
	"io/fs"
	"os"
	"path/filepath"
	"sort"
	"strings"
)

func fileChecksumHex(path string) (string, error) {
	f, err := os.Open(path)
	if err != nil {
		return "", err
	}
	defer f.Close()
	h := sha256.New()
	if _, err := io.Copy(h, f); err != nil {
		return "", err
	}
	return hex.EncodeToString(h.Sum(nil)), nil
}

func fileChecksum(path string) (string, error) {
	hexsum, err := fileChecksumHex(path)
	if err != nil {
		return "", err
	}
	return "sha256:" + hexsum, nil
}

// ComputeKeySetChecksum reproduces harness keys._aggregate_checksum: a sorted,
// newline-joined list of "<filename>:sha256:<hex>" lines, hashed as a whole.
func ComputeKeySetChecksum(dir string) (string, error) {
	entries, err := os.ReadDir(dir)
	if err != nil {
		return "", err
	}
	var lines []string
	for _, e := range entries {
		if e.IsDir() {
			continue
		}
		name := e.Name()
		if !strings.HasSuffix(name, "-public.asc") && !strings.HasSuffix(name, "-private.asc") {
			continue
		}
		sum, err := fileChecksum(filepath.Join(dir, name))
		if err != nil {
			return "", err
		}
		lines = append(lines, name+":"+sum)
	}
	sort.Strings(lines)
	digest := sha256.Sum256([]byte(strings.Join(lines, "\n")))
	return "sha256:" + hex.EncodeToString(digest[:]), nil
}

// ComputeCorpusChecksum reproduces harness corpus._aggregate_checksum: for each
// regular file (sorted by relative path) it feeds "<relpath>\x00<hex>\n" into a
// single hasher and returns the digest.
func ComputeCorpusChecksum(root string) (string, error) {
	type entry struct {
		rel string
		hex string
	}
	var entries []entry
	err := filepath.WalkDir(root, func(p string, d fs.DirEntry, err error) error {
		if err != nil {
			return err
		}
		if d.IsDir() {
			return nil
		}
		rel, err := filepath.Rel(root, p)
		if err != nil {
			return err
		}
		hexsum, err := fileChecksumHex(p)
		if err != nil {
			return err
		}
		entries = append(entries, entry{rel: filepath.ToSlash(rel), hex: hexsum})
		return nil
	})
	if err != nil {
		return "", err
	}
	sort.Slice(entries, func(i, j int) bool { return entries[i].rel < entries[j].rel })

	h := sha256.New()
	for _, e := range entries {
		h.Write([]byte(e.rel))
		h.Write([]byte{0})
		h.Write([]byte(e.hex))
		h.Write([]byte("\n"))
	}
	return "sha256:" + hex.EncodeToString(h.Sum(nil)), nil
}

// checksumEqual compares two "sha256:<hex>" strings, case-insensitive on hex.
func checksumEqual(a, b string) bool {
	return strings.EqualFold(a, b)
}
