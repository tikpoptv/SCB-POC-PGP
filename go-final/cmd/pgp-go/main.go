// Command pgp-go encrypts and decrypts files with the pgpcrypto package.
package main

import (
	"context"
	"errors"
	"flag"
	"fmt"
	"io"
	"os"
	"path/filepath"

	"github.com/poc-encryption/pgp-go/pgpcrypto"
)

const maxPassphraseFileBytes int64 = 1 << 20

func main() {
	if err := run(os.Args[1:]); err != nil {
		fmt.Fprintf(os.Stderr, "pgp-go: %v\n", err)
		os.Exit(1)
	}
}

func run(args []string) error {
	if len(args) == 0 {
		return errors.New("usage: pgp-go <encrypt|decrypt|serve> [options]")
	}
	switch args[0] {
	case "encrypt":
		return runEncrypt(args[1:])
	case "decrypt":
		return runDecrypt(args[1:])
	case "serve":
		return runServe(args[1:])
	default:
		return fmt.Errorf("unknown command %q (use encrypt, decrypt, or serve)", args[0])
	}
}

type fileOptions struct {
	input  string
	output string
}

func addFileFlags(flags *flag.FlagSet, options *fileOptions) {
	flags.StringVar(&options.input, "in", "", "input file")
	flags.StringVar(&options.output, "out", "", "output file (must not already exist)")
}

func runEncrypt(args []string) error {
	flags := flag.NewFlagSet("encrypt", flag.ContinueOnError)
	flags.SetOutput(io.Discard)
	var files fileOptions
	var batch batchOptions
	var publicKeyPath string
	addFileFlags(flags, &files)
	addBatchFlags(flags, &batch)
	flags.StringVar(&publicKeyPath, "public-key", "", "armored or binary public key file")
	if err := flags.Parse(args); err != nil {
		return fmt.Errorf("encrypt options: %w", err)
	}
	if flags.NArg() != 0 {
		return errors.New("encrypt does not accept positional arguments")
	}
	if publicKeyPath == "" {
		return errors.New("encrypt requires -public-key")
	}
	prepared, batchMode, err := prepareBatch(files, batch)
	if err != nil {
		return err
	}
	var validatedFiles fileOptions
	if !batchMode {
		validatedFiles, err = validateFileOptions(files)
		if err != nil {
			return err
		}
	}

	keyFile, err := os.Open(publicKeyPath)
	if err != nil {
		return fmt.Errorf("open public key file: %w", err)
	}
	encryptor, createErr := pgpcrypto.NewEncryptor(keyFile)
	closeErr := keyFile.Close()
	if createErr != nil {
		return createErr
	}
	if closeErr != nil {
		return fmt.Errorf("close public key file: %w", closeErr)
	}
	if batchMode {
		return runBatch("encrypt", prepared, encryptor.Encrypt)
	}
	return transformFile(validatedFiles, encryptor.Encrypt)
}

func runDecrypt(args []string) error {
	flags := flag.NewFlagSet("decrypt", flag.ContinueOnError)
	flags.SetOutput(io.Discard)
	var files fileOptions
	var batch batchOptions
	var privateKeyPath, passphrasePath string
	var maxOutputBytes int64
	addFileFlags(flags, &files)
	addBatchFlags(flags, &batch)
	flags.StringVar(&privateKeyPath, "private-key", "", "armored or binary private key file")
	flags.StringVar(&passphrasePath, "passphrase-file", "", "file containing the private-key passphrase")
	flags.Int64Var(&maxOutputBytes, "max-output-bytes", pgpcrypto.DefaultMaxOutputBytes, "maximum decrypted bytes per file")
	if err := flags.Parse(args); err != nil {
		return fmt.Errorf("decrypt options: %w", err)
	}
	if flags.NArg() != 0 {
		return errors.New("decrypt does not accept positional arguments")
	}
	if privateKeyPath == "" {
		return errors.New("decrypt requires -private-key")
	}
	prepared, batchMode, err := prepareBatch(files, batch)
	if err != nil {
		return err
	}
	var validatedFiles fileOptions
	if !batchMode {
		validatedFiles, err = validateFileOptions(files)
		if err != nil {
			return err
		}
	}

	passphrase, err := readPassphrase(passphrasePath)
	if err != nil {
		return err
	}
	if passphrase != nil {
		defer clear(passphrase)
	}
	keyFile, err := os.Open(privateKeyPath)
	if err != nil {
		return fmt.Errorf("open private key file: %w", err)
	}
	decryptor, createErr := pgpcrypto.NewDecryptor(keyFile, passphrase, &pgpcrypto.DecryptConfig{
		MaxOutputBytes: maxOutputBytes,
	})
	closeErr := keyFile.Close()
	clear(passphrase)
	if createErr != nil {
		return createErr
	}
	if closeErr != nil {
		return fmt.Errorf("close private key file: %w", closeErr)
	}
	if batchMode {
		return runBatch("decrypt", prepared, decryptor.Decrypt)
	}
	return transformFile(validatedFiles, decryptor.Decrypt)
}
func validateFileOptions(options fileOptions) (fileOptions, error) {
	if options.input == "" || options.output == "" {
		return fileOptions{}, errors.New("-in and -out are required")
	}

	resolvedInput, err := filepath.EvalSymlinks(options.input)
	if err != nil {
		return fileOptions{}, fmt.Errorf("resolve input path: %w", err)
	}
	resolvedInput, err = filepath.Abs(resolvedInput)
	if err != nil {
		return fileOptions{}, fmt.Errorf("make input path absolute: %w", err)
	}

	// Refuse any existing destination, including a symlink, before resolving its
	// parent. Publishing is intentionally no-clobber; there is no overwrite mode.
	if _, err := os.Lstat(options.output); err == nil {
		return fileOptions{}, errors.New("output path already exists")
	} else if !errors.Is(err, os.ErrNotExist) {
		return fileOptions{}, fmt.Errorf("inspect output path: %w", err)
	}
	resolvedParent, err := filepath.EvalSymlinks(filepath.Dir(options.output))
	if err != nil {
		return fileOptions{}, fmt.Errorf("resolve output directory: %w", err)
	}
	resolvedParent, err = filepath.Abs(resolvedParent)
	if err != nil {
		return fileOptions{}, fmt.Errorf("make output directory absolute: %w", err)
	}
	resolvedOutput := filepath.Join(resolvedParent, filepath.Base(options.output))
	if _, err := os.Lstat(resolvedOutput); err == nil {
		return fileOptions{}, errors.New("resolved output path already exists")
	} else if !errors.Is(err, os.ErrNotExist) {
		return fileOptions{}, fmt.Errorf("inspect resolved output path: %w", err)
	}
	if resolvedInput == resolvedOutput {
		return fileOptions{}, errors.New("input and output resolve to the same path")
	}

	return fileOptions{input: resolvedInput, output: resolvedOutput}, nil
}

func transformFile(options fileOptions, transform func(io.Writer, io.Reader) error) error {
	return transformFileContext(context.Background(), options, transform)
}

func transformFileContext(ctx context.Context, options fileOptions, transform func(io.Writer, io.Reader) error) error {
	if err := ctx.Err(); err != nil {
		return err
	}
	input, err := os.Open(options.input)
	if err != nil {
		return fmt.Errorf("open input file: %w", err)
	}
	defer input.Close()

	directory := filepath.Dir(options.output)
	temporary, err := os.CreateTemp(directory, "."+filepath.Base(options.output)+".tmp-*")
	if err != nil {
		return fmt.Errorf("create temporary output: %w", err)
	}
	temporaryPath := temporary.Name()
	// Always remove the temporary name on return. After publication the hard
	// link is the commit point, so cleanup must never roll back the final path.
	defer func() {
		_ = temporary.Close()
		_ = os.Remove(temporaryPath)
	}()
	if err := temporary.Chmod(0o600); err != nil {
		return fmt.Errorf("set temporary output permissions: %w", err)
	}
	reader := &contextReader{ctx: ctx, reader: input}
	writer := &contextWriter{ctx: ctx, writer: temporary}
	if err := transform(writer, reader); err != nil {
		return err
	}
	if err := ctx.Err(); err != nil {
		return err
	}
	if err := temporary.Sync(); err != nil {
		return fmt.Errorf("sync temporary output: %w", err)
	}
	if err := temporary.Close(); err != nil {
		return fmt.Errorf("close temporary output: %w", err)
	}
	if err := ctx.Err(); err != nil {
		return err
	}
	if err := publish(temporaryPath, options.output); err != nil {
		return err
	}
	return nil
}

type contextReader struct {
	ctx    context.Context
	reader io.Reader
}

func (reader *contextReader) Read(buffer []byte) (int, error) {
	if err := reader.ctx.Err(); err != nil {
		return 0, err
	}
	n, err := reader.reader.Read(buffer)
	if err == nil {
		if contextErr := reader.ctx.Err(); contextErr != nil {
			return n, contextErr
		}
	}
	return n, err
}

type contextWriter struct {
	ctx    context.Context
	writer io.Writer
}

func (writer *contextWriter) Write(buffer []byte) (int, error) {
	if err := writer.ctx.Err(); err != nil {
		return 0, err
	}
	n, err := writer.writer.Write(buffer)
	if err == nil {
		if contextErr := writer.ctx.Err(); contextErr != nil {
			return n, contextErr
		}
	}
	return n, err
}
func publish(temporaryPath, outputPath string) error {
	// A hard link is the commit point: it publishes atomically without
	// replacing a destination created concurrently. The caller removes the
	// temporary name and never rolls the committed output back by pathname.
	if err := os.Link(temporaryPath, outputPath); err != nil {
		if errors.Is(err, os.ErrExist) {
			return errors.New("output path already exists")
		}
		return fmt.Errorf("publish output file: %w", err)
	}
	return nil
}

func readPassphrase(path string) ([]byte, error) {
	if path == "" {
		return nil, nil
	}
	file, err := os.Open(path)
	if err != nil {
		return nil, fmt.Errorf("open passphrase file: %w", err)
	}
	defer file.Close()
	passphrase, err := io.ReadAll(io.LimitReader(file, maxPassphraseFileBytes+1))
	if err != nil {
		clear(passphrase)
		return nil, fmt.Errorf("read passphrase file: %w", err)
	}
	if int64(len(passphrase)) > maxPassphraseFileBytes {
		clear(passphrase)
		return nil, errors.New("passphrase file exceeds 1 MiB")
	}
	if len(passphrase) > 0 && passphrase[len(passphrase)-1] == '\n' {
		passphrase = passphrase[:len(passphrase)-1]
		if len(passphrase) > 0 && passphrase[len(passphrase)-1] == '\r' {
			passphrase = passphrase[:len(passphrase)-1]
		}
	}
	return passphrase, nil
}
