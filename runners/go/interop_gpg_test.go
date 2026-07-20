package main

// interop_gpg_test.go proves that ciphertext produced by the Go runner through
// the FORKED go-crypto (which compresses with klauspost/compress/zlib instead
// of the standard library) is still a spec-compliant OpenPGP message: the
// reference implementation `gpg` must be able to decrypt it back byte-for-byte.
//
// If gpg can read a klauspost-compressed ZLIB packet, so can Java BouncyCastle
// and any other RFC 4880 / RFC 1950 consumer — that is the whole interop claim.
//
// The test is hermetic: it uses an ephemeral GNUPGHOME (t.TempDir) so it never
// touches the developer's real keyring. It skips (not fails) when gpg or the
// repo key set is unavailable.

import (
	"bytes"
	"os"
	"os/exec"
	"path/filepath"
	"testing"
)

func TestInteropKlauspostCiphertextDecryptsWithGPG(t *testing.T) {
	gpg, err := exec.LookPath("gpg")
	if err != nil {
		t.Skip("gpg not installed; skipping cross-implementation interop check")
	}

	keys := loadRepoKeys(t)
	if !keys.HasKeyFor("RSA-2048") {
		t.Skip("RSA-2048 key unavailable in repo key set")
	}

	// A highly compressible payload so the ZLIB Compressed Data Packet is
	// actually exercised (this is the packet klauspost now produces).
	plain := makeCompressibleText(32 * 1024)

	// 1) Encrypt with the Go runner (forked go-crypto -> klauspost zlib).
	eng := inmemSingleEngine{}
	profile := aes256Zlib("RSA-2048")
	var ct bytes.Buffer
	if _, err := eng.Encrypt(bytes.NewReader(plain), &ct, profile, keys); err != nil {
		t.Fatalf("go encrypt: %v", err)
	}

	tmp := t.TempDir()
	ctPath := filepath.Join(tmp, "message.bin.pgp")
	if err := os.WriteFile(ctPath, ct.Bytes(), 0o600); err != nil {
		t.Fatalf("write ciphertext: %v", err)
	}

	// 2) Import the RSA-2048 private key into an ephemeral gpg keyring.
	// NOTE: GNUPGHOME must live at a SHORT path: gpg-agent's unix socket path
	// has a ~104-char limit, and macOS t.TempDir() paths (/var/folders/...) blow
	// past it ("File name too long"). Use a short /tmp base instead.
	gnupgHome, err := os.MkdirTemp("/tmp", "kpgpg")
	if err != nil {
		t.Fatalf("mkdir short gnupg home: %v", err)
	}
	t.Cleanup(func() { _ = os.RemoveAll(gnupgHome) })
	if err := os.Chmod(gnupgHome, 0o700); err != nil {
		t.Fatalf("chmod gnupg home: %v", err)
	}
	privKey := filepath.Join("..", "..", "keys", "rsa2048-private.asc")

	runGPG := func(args ...string) ([]byte, error) {
		full := append([]string{"--homedir", gnupgHome, "--batch", "--yes",
			"--pinentry-mode", "loopback", "--passphrase", ""}, args...)
		cmd := exec.Command(gpg, full...)
		var out, errBuf bytes.Buffer
		cmd.Stdout = &out
		cmd.Stderr = &errBuf
		if err := cmd.Run(); err != nil {
			return nil, &gpgError{err: err, stderr: errBuf.String()}
		}
		return out.Bytes(), nil
	}

	if _, err := runGPG("--import", privKey); err != nil {
		t.Fatalf("gpg import private key: %v", err)
	}

	// 3) Decrypt with gpg and compare byte-for-byte.
	got, err := runGPG("--decrypt", ctPath)
	if err != nil {
		t.Fatalf("gpg decrypt of klauspost-compressed message failed: %v", err)
	}
	if !bytes.Equal(got, plain) {
		t.Fatalf("interop mismatch: gpg decrypted %d bytes, want %d bytes", len(got), len(plain))
	}
	t.Logf("interop OK: gpg decrypted %d-byte klauspost-ZLIB message byte-for-byte", len(plain))
}

type gpgError struct {
	err    error
	stderr string
}

func (e *gpgError) Error() string {
	return e.err.Error() + ": " + e.stderr
}
