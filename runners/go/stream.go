package main

import (
	"bufio"
	"fmt"
	"io"

	"github.com/ProtonMail/go-crypto/openpgp"
)

// streamSingleEngine is the "go-stream-single" variant: it processes the
// plaintext/ciphertext as a stream through buffered reader/writer pairs bridged
// by an io.Pipe, single-threaded. Unlike go-inmem-single it never loads the
// whole file into memory, so peak memory stays roughly constant regardless of
// file size.
type streamSingleEngine struct{}

const streamSingleVariantID = "go-stream-single"

// streamBufferSize bounds the per-stage buffers. It is the knob that keeps peak
// memory constant: it does not depend on file size.
const streamBufferSize = 32 * 1024

func init() {
	RegisterEngine(streamSingleVariantID, func() CryptoEngine { return streamSingleEngine{} })
}

func (streamSingleEngine) VariantID() string { return streamSingleVariantID }

// Encrypt streams the plaintext through the OpenPGP encryptor running in a
// goroutine that writes into one end of an io.Pipe; the caller drains the other
// end. Data only flows through fixed-size buffers, so peak memory does not grow
// with file size. The streamed I/O and crypto are interleaved and cannot be
// isolated, so the timed region covers the full pipeline.
func (e streamSingleEngine) Encrypt(plaintext io.Reader, out io.Writer, profile CryptoProfile, keys *KeySet) (Timing, error) {
	config, err := buildPacketConfig(profile)
	if err != nil {
		return Timing{}, err
	}
	recipients, err := keys.EncryptionKeys(profile.PubAlg)
	if err != nil {
		return Timing{}, fmt.Errorf("encryption keys: %w", err)
	}

	bufOut := bufio.NewWriterSize(out, streamBufferSize)
	pr, pw := io.Pipe()
	prodErr := make(chan error, 1)

	nanos, cryptoErr := MeasureNanos(func() error {
		go func() {
			err := func() error {
				bw := bufio.NewWriterSize(pw, streamBufferSize)
				encW, encErr := openpgp.Encrypt(bw, recipients, nil, binaryHints, config)
				if encErr != nil {
					return encErr
				}
				buf := make([]byte, streamBufferSize)
				if _, encErr = io.CopyBuffer(encW, bufio.NewReaderSize(plaintext, streamBufferSize), buf); encErr != nil {
					_ = encW.Close()
					return encErr
				}
				if encErr = encW.Close(); encErr != nil {
					return encErr
				}
				return bw.Flush()
			}()
			prodErr <- err
			_ = pw.CloseWithError(err)
		}()

		copyBuf := make([]byte, streamBufferSize)
		if _, err := io.CopyBuffer(bufOut, pr, copyBuf); err != nil {
			return err
		}
		if err := bufOut.Flush(); err != nil {
			return err
		}
		return <-prodErr
	})
	if cryptoErr != nil {
		return Timing{}, fmt.Errorf("openpgp encrypt: %w", cryptoErr)
	}

	return Timing{
		TotalNanos:    nanos,
		AsymNanos:     NotSeparable,
		SymNanos:      NotSeparable,
		HardwareAccel: hardwareAccelFor(profile.Cipher),
	}, nil
}

// Decrypt streams the ciphertext through the OpenPGP decryptor. ReadMessage is
// lazy, so the symmetric decryption happens as md.UnverifiedBody is drained;
// that drain runs in a goroutine writing into an io.Pipe while the caller copies
// the recovered plaintext out. Peak memory is bounded by the fixed buffers.
func (e streamSingleEngine) Decrypt(ciphertext io.Reader, out io.Writer, profile CryptoProfile, keys *KeySet) (Timing, error) {
	config, err := buildPacketConfig(profile)
	if err != nil {
		return Timing{}, err
	}
	decryptKeys, err := keys.DecryptionKeys(profile.PubAlg)
	if err != nil {
		return Timing{}, fmt.Errorf("decryption keys: %w", err)
	}

	bufOut := bufio.NewWriterSize(out, streamBufferSize)
	pr, pw := io.Pipe()
	prodErr := make(chan error, 1)

	nanos, cryptoErr := MeasureNanos(func() error {
		go func() {
			err := func() error {
				md, readErr := openpgp.ReadMessage(bufio.NewReaderSize(ciphertext, streamBufferSize), decryptKeys, nil, config)
				if readErr != nil {
					return readErr
				}
				buf := make([]byte, streamBufferSize)
				_, readErr = io.CopyBuffer(pw, md.UnverifiedBody, buf)
				return readErr
			}()
			prodErr <- err
			_ = pw.CloseWithError(err)
		}()

		copyBuf := make([]byte, streamBufferSize)
		if _, err := io.CopyBuffer(bufOut, pr, copyBuf); err != nil {
			return err
		}
		if err := bufOut.Flush(); err != nil {
			return err
		}
		return <-prodErr
	})
	if cryptoErr != nil {
		return Timing{}, fmt.Errorf("openpgp decrypt: %w", cryptoErr)
	}

	return Timing{
		TotalNanos:    nanos,
		AsymNanos:     NotSeparable,
		SymNanos:      NotSeparable,
		HardwareAccel: hardwareAccelFor(profile.Cipher),
	}, nil
}

func (streamSingleEngine) SupportsProfile(profile CryptoProfile) error {
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
