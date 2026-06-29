package main

import (
	"bytes"
	"crypto"
	"fmt"
	"io"
	"runtime"
	"strings"

	"github.com/ProtonMail/go-crypto/openpgp"
	"github.com/ProtonMail/go-crypto/openpgp/packet"
	"golang.org/x/sys/cpu"
)

// inmemSingleEngine is the "go-inmem-single" variant: it loads the whole file
// into a buffer and runs OpenPGP encrypt/decrypt single-threaded.
type inmemSingleEngine struct{}

const inmemSingleVariantID = "go-inmem-single"

// binaryHints forces a binary literal-data packet ('b'). Without it go-crypto
// defaults to text mode ('u'), which makes consumers like gpg canonicalize line
// endings (e.g. a lone CR is dropped), breaking byte-for-byte round-trips.
var binaryHints = &openpgp.FileHints{IsBinary: true}

func init() {
	RegisterEngine(inmemSingleVariantID, func() CryptoEngine { return inmemSingleEngine{} })
}

func (inmemSingleEngine) VariantID() string { return inmemSingleVariantID }

func (e inmemSingleEngine) Encrypt(plaintext io.Reader, out io.Writer, profile CryptoProfile, keys *KeySet) (Timing, error) {
	plainBytes, err := io.ReadAll(plaintext)
	if err != nil {
		return Timing{}, fmt.Errorf("read plaintext: %w", err)
	}

	config, err := buildPacketConfig(profile)
	if err != nil {
		return Timing{}, err
	}
	recipients, err := keys.EncryptionKeys(profile.PubAlg)
	if err != nil {
		return Timing{}, fmt.Errorf("encryption keys: %w", err)
	}

	var ct bytes.Buffer
	ct.Grow(len(plainBytes) + 512)
	nanos, cryptoErr := MeasureNanos(func() error {
		w, encErr := openpgp.Encrypt(&ct, recipients, nil, binaryHints, config)
		if encErr != nil {
			return encErr
		}
		if _, encErr = w.Write(plainBytes); encErr != nil {
			_ = w.Close()
			return encErr
		}
		return w.Close()
	})
	if cryptoErr != nil {
		return Timing{}, fmt.Errorf("openpgp encrypt: %w", cryptoErr)
	}

	if _, err := out.Write(ct.Bytes()); err != nil {
		return Timing{}, fmt.Errorf("write ciphertext: %w", err)
	}

	return Timing{
		TotalNanos:    nanos,
		AsymNanos:     NotSeparable,
		SymNanos:      NotSeparable,
		HardwareAccel: hardwareAccelFor(profile.Cipher),
	}, nil
}

func (e inmemSingleEngine) Decrypt(ciphertext io.Reader, out io.Writer, profile CryptoProfile, keys *KeySet) (Timing, error) {
	cipherBytes, err := io.ReadAll(ciphertext)
	if err != nil {
		return Timing{}, fmt.Errorf("read ciphertext: %w", err)
	}

	config, err := buildPacketConfig(profile)
	if err != nil {
		return Timing{}, err
	}
	decryptKeys, err := keys.DecryptionKeys(profile.PubAlg)
	if err != nil {
		return Timing{}, fmt.Errorf("decryption keys: %w", err)
	}

	// ReadMessage is lazy; the symmetric decryption happens as UnverifiedBody is
	// drained, so that read must stay inside the timed region.
	var pt bytes.Buffer
	pt.Grow(len(cipherBytes))
	nanos, cryptoErr := MeasureNanos(func() error {
		md, readErr := openpgp.ReadMessage(bytes.NewReader(cipherBytes), decryptKeys, nil, config)
		if readErr != nil {
			return readErr
		}
		_, readErr = io.Copy(&pt, md.UnverifiedBody)
		return readErr
	})
	if cryptoErr != nil {
		return Timing{}, fmt.Errorf("openpgp decrypt: %w", cryptoErr)
	}

	if _, err := out.Write(pt.Bytes()); err != nil {
		return Timing{}, fmt.Errorf("write plaintext: %w", err)
	}

	return Timing{
		TotalNanos:    nanos,
		AsymNanos:     NotSeparable,
		SymNanos:      NotSeparable,
		HardwareAccel: hardwareAccelFor(profile.Cipher),
	}, nil
}

func (inmemSingleEngine) SupportsProfile(profile CryptoProfile) error {
	if _, err := mapCipher(profile.Cipher); err != nil {
		return err
	}
	if _, err := mapCompression(profile.Compression); err != nil {
		return err
	}
	if _, err := mapHash(profile.Hash); err != nil {
		return err
	}
	return nil
}

// buildPacketConfig translates a Crypto_Profile into a go-crypto packet.Config.
func buildPacketConfig(profile CryptoProfile) (*packet.Config, error) {
	cipherFn, err := mapCipher(profile.Cipher)
	if err != nil {
		return nil, err
	}
	compAlgo, err := mapCompression(profile.Compression)
	if err != nil {
		return nil, err
	}
	hashFn, err := mapHash(profile.Hash)
	if err != nil {
		return nil, err
	}
	return &packet.Config{
		DefaultCipher:          cipherFn,
		DefaultCompressionAlgo: compAlgo,
		CompressionConfig:      &packet.CompressionConfig{Level: -1},
		DefaultHash:            hashFn,
	}, nil
}

// normalizeAlg upper-cases and strips spaces, underscores and dashes so labels
// like "AES-256", "aes_256" and "AES256" all compare equal.
func normalizeAlg(s string) string {
	r := strings.ToUpper(strings.TrimSpace(s))
	r = strings.ReplaceAll(r, "-", "")
	r = strings.ReplaceAll(r, "_", "")
	r = strings.ReplaceAll(r, " ", "")
	return r
}

func mapCipher(cipher string) (packet.CipherFunction, error) {
	switch normalizeAlg(cipher) {
	case "AES256":
		return packet.CipherAES256, nil
	case "AES192":
		return packet.CipherAES192, nil
	case "AES128":
		return packet.CipherAES128, nil
	default:
		return 0, errWithCode(exitUnsupportedProf,
			"unsupported cipher %q (supported: AES-256, AES-192, AES-128)", cipher)
	}
}

func mapCompression(compression string) (packet.CompressionAlgo, error) {
	switch normalizeAlg(compression) {
	case "ZLIB":
		return packet.CompressionZLIB, nil
	case "ZIP":
		return packet.CompressionZIP, nil
	case "NONE", "":
		return packet.CompressionNone, nil
	default:
		return 0, errWithCode(exitUnsupportedProf,
			"unsupported compression %q (supported: ZLIB, ZIP, NONE)", compression)
	}
}

func mapHash(hash string) (crypto.Hash, error) {
	switch normalizeAlg(hash) {
	case "SHA256":
		return crypto.SHA256, nil
	case "SHA384":
		return crypto.SHA384, nil
	case "SHA512":
		return crypto.SHA512, nil
	case "SHA224":
		return crypto.SHA224, nil
	default:
		return 0, errWithCode(exitUnsupportedProf,
			"unsupported hash %q (supported: SHA-256, SHA-384, SHA-512, SHA-224)", hash)
	}
}

// hardwareAccelFor reports whether the chosen cipher benefits from a hardware
// implementation on this CPU. Non-AES ciphers and undetectable flags report false.
func hardwareAccelFor(cipher string) bool {
	switch normalizeAlg(cipher) {
	case "AES256", "AES192", "AES128":
		return aesHardwareAvailable()
	default:
		return false
	}
}

func aesHardwareAvailable() bool {
	switch runtime.GOARCH {
	case "amd64", "386":
		return cpu.X86.HasAES
	case "arm64":
		return cpu.ARM64.HasAES
	default:
		return false
	}
}
