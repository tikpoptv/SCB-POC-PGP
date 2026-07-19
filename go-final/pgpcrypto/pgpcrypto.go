// Package pgpcrypto provides streaming OpenPGP encryption and decryption.
// Payload copies use a reusable 64 KiB buffer; dependency parsing of OpenPGP
// and key metadata is outside that payload-buffer guarantee.
package pgpcrypto

import (
	"bufio"
	"bytes"
	"crypto"
	"errors"
	"fmt"
	"io"
	"sync"
	"time"

	"github.com/ProtonMail/go-crypto/openpgp"
	"github.com/ProtonMail/go-crypto/openpgp/packet"
)

const (
	// BufferSize is the reusable streaming buffer size used per operation.
	BufferSize = 64 * 1024
	// MaxKeyRingBytes bounds public or private key input parsed by a constructor.
	MaxKeyRingBytes int64 = 16 << 20
	// DefaultMaxOutputBytes is the inclusive plaintext limit (1 GiB).
	DefaultMaxOutputBytes int64 = 1 << 30
)

var (
	// ErrOutputLimitExceeded indicates that decrypted plaintext exceeded its limit.
	ErrOutputLimitExceeded = errors.New("decrypted plaintext exceeds maximum output size")
	// ErrKeyRingTooLarge indicates that key input exceeded MaxKeyRingBytes.
	ErrKeyRingTooLarge = errors.New("OpenPGP key ring exceeds maximum input size")
)

var copyBuffers = sync.Pool{New: func() any {
	buffer := make([]byte, BufferSize)
	return &buffer
}}

// DecryptConfig controls resource limits for decryption.
type DecryptConfig struct {
	// MaxOutputBytes must be positive. Use nil config for the 1 GiB default.
	MaxOutputBytes int64
}

// Encryptor encrypts binary literal data to its configured recipients.
type Encryptor struct {
	recipients openpgp.EntityList
}

// Decryptor decrypts data with its configured private keys.
type Decryptor struct {
	keyRing       openpgp.EntityList
	maxOutputSize int64
}

// NewEncryptor parses an armored or binary public key ring. Private keys are
// neither required nor used for encryption.
func NewEncryptor(publicKeys io.Reader) (*Encryptor, error) {
	keyRing, err := readKeyRing(publicKeys)
	if err != nil {
		return nil, fmt.Errorf("read public key ring: %w", err)
	}

	now := time.Now()
	for i, entity := range keyRing {
		if entity == nil {
			return nil, errors.New("public key ring contains a nil entity")
		}
		if _, ok := entity.EncryptionKey(now); !ok {
			return nil, fmt.Errorf("public key entity %d has no usable encryption key", i)
		}
	}
	return &Encryptor{recipients: keyRing}, nil
}

// NewDecryptor parses an armored or binary private key ring. A nil passphrase
// requires an entirely unencrypted ring. If a passphrase is supplied, every
// encrypted primary key and subkey in the ring must unlock with that passphrase.
// An empty, non-nil passphrase supports keys encrypted with an empty passphrase.
func NewDecryptor(privateKeys io.Reader, passphrase []byte, config *DecryptConfig) (*Decryptor, error) {
	maxOutputSize := DefaultMaxOutputBytes
	if config != nil {
		if config.MaxOutputBytes <= 0 {
			return nil, errors.New("max output bytes must be positive")
		}
		maxOutputSize = config.MaxOutputBytes
	}

	keyRing, err := readKeyRing(privateKeys)
	if err != nil {
		return nil, fmt.Errorf("read private key ring: %w", err)
	}
	for _, entity := range keyRing {
		if entity == nil {
			return nil, errors.New("private key ring contains a nil entity")
		}
		if hasEncryptedPrivateKey(entity) {
			if passphrase == nil {
				return nil, errors.New("private key ring is encrypted but no passphrase was provided")
			}
			if err := entity.DecryptPrivateKeys(passphrase); err != nil {
				return nil, fmt.Errorf("decrypt private key ring: %w", err)
			}
		}
	}
	if !hasPrivateKey(keyRing) {
		return nil, errors.New("private key ring contains no private key")
	}
	return &Decryptor{keyRing: keyRing, maxOutputSize: maxOutputSize}, nil
}

func readKeyRing(reader io.Reader) (openpgp.EntityList, error) {
	if reader == nil {
		return nil, errors.New("key reader is nil")
	}
	limited := &limitErrorReader{
		reader:    reader,
		remaining: MaxKeyRingBytes,
		limitErr:  ErrKeyRingTooLarge,
	}
	buffered := bufio.NewReader(limited)
	prefix, _ := buffered.Peek(64)
	var (
		keyRing openpgp.EntityList
		err     error
	)
	if bytes.HasPrefix(bytes.TrimSpace(prefix), []byte("-----BEGIN PGP")) {
		keyRing, err = openpgp.ReadArmoredKeyRing(buffered)
	} else {
		keyRing, err = openpgp.ReadKeyRing(buffered)
	}
	if err != nil {
		return nil, err
	}
	if len(keyRing) == 0 {
		return nil, errors.New("key ring is empty")
	}
	return keyRing, nil
}
func hasEncryptedPrivateKey(entity *openpgp.Entity) bool {
	if entity.PrivateKey != nil && entity.PrivateKey.Encrypted {
		return true
	}
	for _, subkey := range entity.Subkeys {
		if subkey.PrivateKey != nil && subkey.PrivateKey.Encrypted {
			return true
		}
	}
	return false
}

func hasPrivateKey(keyRing openpgp.EntityList) bool {
	for _, entity := range keyRing {
		if entity.PrivateKey != nil && !entity.PrivateKey.Dummy() {
			return true
		}
		for _, subkey := range entity.Subkeys {
			if subkey.PrivateKey != nil && !subkey.PrivateKey.Dummy() {
				return true
			}
		}
	}
	return false
}

func packetConfig(maxDecompressedSize *int64) *packet.Config {
	return &packet.Config{
		DefaultHash:                crypto.SHA256,
		DefaultCipher:              packet.CipherAES256,
		DefaultCompressionAlgo:     packet.CompressionZLIB,
		CompressionConfig:          &packet.CompressionConfig{Level: -1},
		MaxDecompressedMessageSize: maxDecompressedSize,
	}
}

var binaryHints = &openpgp.FileHints{IsBinary: true}

// Encrypt streams src into an OpenPGP message written to dst. The destination
// may contain partial data if an error occurs.
func (encryptor *Encryptor) Encrypt(dst io.Writer, src io.Reader) error {
	if encryptor == nil || len(encryptor.recipients) == 0 {
		return errors.New("encryptor has no recipients")
	}
	if dst == nil || src == nil {
		return errors.New("source and destination must not be nil")
	}

	plaintext, err := openpgp.Encrypt(dst, encryptor.recipients, nil, binaryHints, packetConfig(nil))
	if err != nil {
		return fmt.Errorf("initialize OpenPGP encryption: %w", err)
	}
	buffer := acquireBuffer()
	defer releaseBuffer(buffer)
	if _, err := io.CopyBuffer(plaintext, src, *buffer); err != nil {
		return errors.Join(fmt.Errorf("stream plaintext: %w", err), plaintext.Close())
	}
	if err := plaintext.Close(); err != nil {
		return fmt.Errorf("finalize OpenPGP encryption: %w", err)
	}
	return nil
}

// Decrypt streams an OpenPGP message from src to dst, enforcing both the
// decompression and output limits. It drains through EOF so MDC errors surface.
// The destination may contain partial data if an error occurs.
func (decryptor *Decryptor) Decrypt(dst io.Writer, src io.Reader) error {
	if decryptor == nil || len(decryptor.keyRing) == 0 || decryptor.maxOutputSize <= 0 {
		return errors.New("decryptor is not configured")
	}
	if dst == nil || src == nil {
		return errors.New("source and destination must not be nil")
	}

	decompressedLimit := decompressionBudget(decryptor.maxOutputSize)
	message, err := openpgp.ReadMessage(src, decryptor.keyRing, nil, packetConfig(&decompressedLimit))
	if err != nil {
		return fmt.Errorf("read OpenPGP message: %w", err)
	}
	if !message.IsEncrypted {
		return errors.New("OpenPGP message is not encrypted")
	}
	buffer := acquireBuffer()
	defer releaseBuffer(buffer)
	limited := &limitWriter{writer: dst, remaining: decryptor.maxOutputSize}
	if _, err := io.CopyBuffer(limited, message.UnverifiedBody, *buffer); err != nil {
		return fmt.Errorf("stream decrypted plaintext: %w", err)
	}
	return nil
}

func acquireBuffer() *[]byte {
	return copyBuffers.Get().(*[]byte)
}

func releaseBuffer(buffer *[]byte) {
	clear(*buffer)
	copyBuffers.Put(buffer)
}

// decompressionBudget allows for OpenPGP literal-packet framing, which the
// dependency counts in addition to plaintext. The output writer remains the
// exact, inclusive plaintext limit.
func decompressionBudget(maxOutput int64) int64 {
	headroom := maxOutput / 100
	if maxOutput%100 != 0 {
		headroom++
	}
	if headroom < 1<<20 {
		headroom = 1 << 20
	}
	const maxInt64 = int64(^uint64(0) >> 1)
	if maxOutput > maxInt64-headroom {
		return maxInt64
	}
	return maxOutput + headroom
}

type limitErrorReader struct {
	reader    io.Reader
	remaining int64
	limitErr  error
}

func (reader *limitErrorReader) Read(data []byte) (int, error) {
	if reader.remaining == 0 {
		var probe [1]byte
		n, err := reader.reader.Read(probe[:])
		if n > 0 {
			return 0, reader.limitErr
		}
		return 0, err
	}
	if int64(len(data)) > reader.remaining+1 {
		data = data[:reader.remaining+1]
	}
	n, err := reader.reader.Read(data)
	if int64(n) > reader.remaining {
		allowed := int(reader.remaining)
		reader.remaining = 0
		return allowed, reader.limitErr
	}
	reader.remaining -= int64(n)
	return n, err
}

type limitWriter struct {
	writer    io.Writer
	remaining int64
}

func (writer *limitWriter) Write(data []byte) (int, error) {
	if int64(len(data)) > writer.remaining {
		allowed := int(writer.remaining)
		n, err := writer.writer.Write(data[:allowed])
		writer.remaining -= int64(n)
		if err != nil {
			return n, err
		}
		if n != allowed {
			return n, io.ErrShortWrite
		}
		return n, ErrOutputLimitExceeded
	}
	n, err := writer.writer.Write(data)
	writer.remaining -= int64(n)
	return n, err
}
