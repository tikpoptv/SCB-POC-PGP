package main

import (
	"context"
	"crypto/sha256"
	"crypto/subtle"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"mime"
	"net"
	"net/http"
	"os"
	"os/signal"
	"strings"
	"syscall"
	"time"

	"github.com/poc-encryption/pgp-go/pgpcrypto"
)

const (
	defaultListenAddress         = "127.0.0.1:8080"
	defaultMaxConcurrentJobs     = 1
	absoluteMaxConcurrentJobs    = 100
	defaultJobTimeout            = 30 * time.Minute
	maxBearerTokenFileBytes      = 4 << 10
	serverReadHeaderTimeout      = 5 * time.Second
	serverReadTimeout            = 30 * time.Second
	serverIdleTimeout            = 60 * time.Second
	serverShutdownTimeout        = 10 * time.Second
	serverWriteResponseAllowance = 30 * time.Second
	serverMaxHeaderBytes         = 16 << 10
)

type serveOptions struct {
	listen            string
	tlsCertFile       string
	tlsKeyFile        string
	operation         string
	inputRoot         string
	outputRoot        string
	apiTokenFile      string
	maxFiles          int
	workers           int
	maxConcurrentJobs int
	jobTimeout        time.Duration
	publicKeyPath     string
	privateKeyPath    string
	passphrasePath    string
	maxOutputBytes    int64
}

type serviceConfig struct {
	operation   string
	inputRoot   string
	outputRoot  string
	tokenDigest [sha256.Size]byte
	maxFiles    int
	workers     int
	jobTimeout  time.Duration
	transform   func(io.Writer, io.Reader) error
	jobs        chan struct{}
}

type apiErrorResponse struct {
	Version int      `json:"version"`
	Error   apiError `json:"error"`
}

type apiError struct {
	Code    string `json:"code"`
	Message string `json:"message"`
}

func runServe(args []string) error {
	flags := flag.NewFlagSet("serve", flag.ContinueOnError)
	flags.SetOutput(io.Discard)
	options := serveOptions{}
	flags.StringVar(&options.listen, "listen", defaultListenAddress, "HTTP listen address")
	flags.StringVar(&options.tlsCertFile, "tls-cert-file", "", "TLS certificate file for non-loopback service")
	flags.StringVar(&options.tlsKeyFile, "tls-key-file", "", "TLS private key file for non-loopback service")
	flags.StringVar(&options.operation, "operation", "", "fixed service operation: encrypt or decrypt")
	flags.StringVar(&options.inputRoot, "input-root", "", "root directory for service inputs")
	flags.StringVar(&options.outputRoot, "output-root", "", "root directory for service outputs")
	flags.StringVar(&options.apiTokenFile, "api-token-file", "", "file containing the bearer token")
	flags.IntVar(&options.maxFiles, "max-files", defaultMaxBatchFiles, "maximum files allowed in a job")
	flags.IntVar(&options.workers, "workers", 0, "workers per job (0 uses GOMAXPROCS)")
	flags.IntVar(&options.maxConcurrentJobs, "max-concurrent-jobs", defaultMaxConcurrentJobs, "maximum in-flight jobs")
	flags.DurationVar(&options.jobTimeout, "job-timeout", defaultJobTimeout, "maximum duration of each job")
	flags.StringVar(&options.publicKeyPath, "public-key", "", "armored or binary public key file")
	flags.StringVar(&options.privateKeyPath, "private-key", "", "armored or binary private key file")
	flags.StringVar(&options.passphrasePath, "passphrase-file", "", "file containing the private-key passphrase")
	flags.Int64Var(&options.maxOutputBytes, "max-output-bytes", pgpcrypto.DefaultMaxOutputBytes, "maximum decrypted bytes per file")
	if err := flags.Parse(args); err != nil {
		return fmt.Errorf("serve options: %w", err)
	}
	if flags.NArg() != 0 {
		return errors.New("serve does not accept positional arguments")
	}
	config, err := loadServiceConfig(options, flags)
	if err != nil {
		return err
	}
	return serveHTTP(options.listen, options.tlsCertFile, options.tlsKeyFile, config)
}

func loadServiceConfig(options serveOptions, flags *flag.FlagSet) (*serviceConfig, error) {
	if options.listen == "" {
		return nil, errors.New("serve requires a non-empty -listen")
	}
	if (options.tlsCertFile == "") != (options.tlsKeyFile == "") {
		return nil, errors.New("-tls-cert-file and -tls-key-file must be provided together")
	}
	if options.tlsCertFile == "" && !isLoopbackListenAddress(options.listen) {
		return nil, errors.New("non-loopback -listen requires -tls-cert-file and -tls-key-file")
	}
	if options.operation != "encrypt" && options.operation != "decrypt" {
		return nil, errors.New("serve requires -operation encrypt or -operation decrypt")
	}
	if options.inputRoot == "" || options.outputRoot == "" {
		return nil, errors.New("serve requires -input-root and -output-root")
	}
	if options.apiTokenFile == "" {
		return nil, errors.New("serve requires -api-token-file")
	}
	if err := validateBatchLimits(options.maxFiles, options.workers); err != nil {
		return nil, err
	}
	if options.maxConcurrentJobs <= 0 {
		return nil, errors.New("-max-concurrent-jobs must be positive")
	}
	if options.maxConcurrentJobs > absoluteMaxConcurrentJobs {
		return nil, fmt.Errorf("-max-concurrent-jobs must not exceed %d", absoluteMaxConcurrentJobs)
	}
	if options.jobTimeout <= 0 {
		return nil, errors.New("-job-timeout must be positive")
	}

	inputRoot, err := resolveBatchRoot(options.inputRoot, "input")
	if err != nil {
		return nil, err
	}
	outputRoot, err := resolveBatchRoot(options.outputRoot, "output")
	if err != nil {
		return nil, err
	}
	token, err := readBearerToken(options.apiTokenFile)
	if err != nil {
		return nil, err
	}
	tokenDigest := sha256.Sum256(token)
	clear(token)

	transform, err := loadServiceTransform(options, flags)
	if err != nil {
		return nil, err
	}
	return &serviceConfig{
		operation:   options.operation,
		inputRoot:   inputRoot,
		outputRoot:  outputRoot,
		tokenDigest: tokenDigest,
		maxFiles:    options.maxFiles,
		workers:     options.workers,
		jobTimeout:  options.jobTimeout,
		transform:   transform,
		jobs:        make(chan struct{}, options.maxConcurrentJobs),
	}, nil
}

func loadServiceTransform(options serveOptions, flags *flag.FlagSet) (func(io.Writer, io.Reader) error, error) {
	if options.operation == "encrypt" {
		if options.publicKeyPath == "" {
			return nil, errors.New("serve encrypt requires -public-key")
		}
		if options.privateKeyPath != "" || options.passphrasePath != "" || flagWasSet(flags, "max-output-bytes") {
			return nil, errors.New("serve encrypt does not accept decrypt key options")
		}
		keyFile, err := os.Open(options.publicKeyPath)
		if err != nil {
			return nil, fmt.Errorf("open public key file: %w", err)
		}
		encryptor, createErr := pgpcrypto.NewEncryptor(keyFile)
		closeErr := keyFile.Close()
		if createErr != nil {
			return nil, createErr
		}
		if closeErr != nil {
			return nil, fmt.Errorf("close public key file: %w", closeErr)
		}
		return encryptor.Encrypt, nil
	}

	if options.privateKeyPath == "" {
		return nil, errors.New("serve decrypt requires -private-key")
	}
	if options.publicKeyPath != "" {
		return nil, errors.New("serve decrypt does not accept -public-key")
	}
	passphrase, err := readPassphrase(options.passphrasePath)
	if err != nil {
		return nil, err
	}
	if passphrase != nil {
		defer clear(passphrase)
	}
	keyFile, err := os.Open(options.privateKeyPath)
	if err != nil {
		return nil, fmt.Errorf("open private key file: %w", err)
	}
	decryptor, createErr := pgpcrypto.NewDecryptor(keyFile, passphrase, &pgpcrypto.DecryptConfig{
		MaxOutputBytes: options.maxOutputBytes,
	})
	closeErr := keyFile.Close()
	clear(passphrase)
	if createErr != nil {
		return nil, createErr
	}
	if closeErr != nil {
		return nil, fmt.Errorf("close private key file: %w", closeErr)
	}
	return decryptor.Decrypt, nil
}

func flagWasSet(flags *flag.FlagSet, name string) bool {
	set := false
	flags.Visit(func(item *flag.Flag) {
		if item.Name == name {
			set = true
		}
	})
	return set
}

func readBearerToken(path string) ([]byte, error) {
	file, err := os.Open(path)
	if err != nil {
		return nil, fmt.Errorf("open API token file: %w", err)
	}
	data, readErr := io.ReadAll(io.LimitReader(file, maxBearerTokenFileBytes+1))
	closeErr := file.Close()
	if readErr != nil {
		clear(data)
		return nil, fmt.Errorf("read API token file: %w", readErr)
	}
	if closeErr != nil {
		clear(data)
		return nil, fmt.Errorf("close API token file: %w", closeErr)
	}
	if len(data) > maxBearerTokenFileBytes {
		clear(data)
		return nil, errors.New("API token file exceeds 4 KiB")
	}
	if len(data) > 0 && data[len(data)-1] == '\n' {
		data = data[:len(data)-1]
		if len(data) > 0 && data[len(data)-1] == '\r' {
			data = data[:len(data)-1]
		}
	}
	if len(data) == 0 {
		return nil, errors.New("API token must not be empty")
	}
	for _, character := range data {
		if character == '\r' || character == '\n' {
			clear(data)
			return nil, errors.New("API token must be a single line")
		}
	}
	return data, nil
}

func isLoopbackListenAddress(address string) bool {
	host, _, err := net.SplitHostPort(address)
	if err != nil {
		return false
	}
	if strings.EqualFold(host, "localhost") {
		return true
	}
	ip := net.ParseIP(host)
	return ip != nil && ip.IsLoopback()
}

func serveHTTP(listen, tlsCertFile, tlsKeyFile string, service *serviceConfig) error {
	serviceContext, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()

	mux := http.NewServeMux()
	mux.HandleFunc("/healthz", service.handleHealth)
	mux.HandleFunc("/v1/jobs", service.handleJobs)
	mux.HandleFunc("/", handleNotFound)
	writeTimeout := service.jobTimeout
	if writeTimeout < time.Duration(1<<63-1)-serverWriteResponseAllowance {
		writeTimeout += serverWriteResponseAllowance
	}
	server := &http.Server{
		Addr:              listen,
		Handler:           mux,
		ReadHeaderTimeout: serverReadHeaderTimeout,
		ReadTimeout:       serverReadTimeout,
		WriteTimeout:      writeTimeout,
		IdleTimeout:       serverIdleTimeout,
		MaxHeaderBytes:    serverMaxHeaderBytes,
		BaseContext: func(_ net.Listener) context.Context {
			return serviceContext
		},
	}

	serverErrors := make(chan error, 1)
	go func() {
		if tlsCertFile != "" {
			serverErrors <- server.ListenAndServeTLS(tlsCertFile, tlsKeyFile)
			return
		}
		serverErrors <- server.ListenAndServe()
	}()

	select {
	case err := <-serverErrors:
		if errors.Is(err, http.ErrServerClosed) {
			return nil
		}
		return fmt.Errorf("serve HTTP: %w", err)
	case <-serviceContext.Done():
		shutdownContext, cancel := context.WithTimeout(context.Background(), serverShutdownTimeout)
		defer cancel()
		shutdownErr := server.Shutdown(shutdownContext)
		serveErr := <-serverErrors
		if shutdownErr != nil {
			return fmt.Errorf("shut down HTTP server: %w", shutdownErr)
		}
		if serveErr != nil && !errors.Is(serveErr, http.ErrServerClosed) {
			return fmt.Errorf("serve HTTP: %w", serveErr)
		}
		return nil
	}
}

func (service *serviceConfig) handleHealth(response http.ResponseWriter, request *http.Request) {
	if request.Method != http.MethodGet {
		response.Header().Set("Allow", http.MethodGet)
		writeAPIError(response, http.StatusMethodNotAllowed, "method_not_allowed", "method not allowed")
		return
	}
	writeJSON(response, http.StatusOK, struct {
		Status string `json:"status"`
	}{Status: "ok"})
}

func (service *serviceConfig) handleJobs(response http.ResponseWriter, request *http.Request) {
	if request.Method != http.MethodPost {
		response.Header().Set("Allow", http.MethodPost)
		writeAPIError(response, http.StatusMethodNotAllowed, "method_not_allowed", "method not allowed")
		return
	}
	if !service.authorized(request.Header.Get("Authorization")) {
		response.Header().Set("WWW-Authenticate", "Bearer")
		writeAPIError(response, http.StatusUnauthorized, "unauthorized", "unauthorized")
		return
	}
	mediaType, _, err := mime.ParseMediaType(request.Header.Get("Content-Type"))
	if err != nil || !strings.EqualFold(mediaType, "application/json") {
		writeAPIError(response, http.StatusUnsupportedMediaType, "unsupported_media_type", "Content-Type must be application/json")
		return
	}
	select {
	case service.jobs <- struct{}{}:
		defer func() { <-service.jobs }()
	default:
		writeAPIError(response, http.StatusTooManyRequests, "busy", "server is busy")
		return
	}

	jobContext, cancel := context.WithTimeout(request.Context(), service.jobTimeout)
	defer cancel()
	request.Body = http.MaxBytesReader(response, request.Body, maxManifestBytes)
	manifest, err := decodeBatchManifest(request.Body)
	if err != nil {
		var maxBytesError *http.MaxBytesError
		if errors.As(err, &maxBytesError) {
			writeAPIError(response, http.StatusRequestEntityTooLarge, "payload_too_large", "request body exceeds 1 MiB")
			return
		}
		writeAPIError(response, http.StatusBadRequest, "malformed_json", "request body must be one valid manifest JSON object")
		return
	}
	prepared, err := prepareDecodedBatch(
		manifest,
		service.inputRoot,
		service.outputRoot,
		service.maxFiles,
		service.workers,
	)
	if err != nil {
		writeAPIError(response, http.StatusUnprocessableEntity, "invalid_job", "job validation failed")
		return
	}
	report := executeBatch(jobContext, service.operation, prepared, service.transform, false)
	status := http.StatusOK
	if failedBatchResults(report) != 0 {
		status = http.StatusMultiStatus
	}
	writeJSON(response, status, report)
}

func (service *serviceConfig) authorized(header string) bool {
	const prefix = "Bearer "
	if !strings.HasPrefix(header, prefix) {
		return false
	}
	candidate := sha256.Sum256([]byte(header[len(prefix):]))
	return subtle.ConstantTimeCompare(candidate[:], service.tokenDigest[:]) == 1
}

func handleNotFound(response http.ResponseWriter, _ *http.Request) {
	writeAPIError(response, http.StatusNotFound, "not_found", "not found")
}

func writeAPIError(response http.ResponseWriter, status int, code, message string) {
	writeJSON(response, status, apiErrorResponse{
		Version: 1,
		Error: apiError{
			Code:    code,
			Message: message,
		},
	})
}

func writeJSON(response http.ResponseWriter, status int, value any) {
	var encoded strings.Builder
	encoder := json.NewEncoder(&encoded)
	encoder.SetEscapeHTML(false)
	if err := encoder.Encode(value); err != nil {
		response.Header().Set("Content-Type", "application/json")
		response.WriteHeader(http.StatusInternalServerError)
		_, _ = io.WriteString(response, "{\"version\":1,\"error\":{\"code\":\"internal_error\",\"message\":\"internal server error\"}}\n")
		return
	}
	response.Header().Set("Content-Type", "application/json")
	response.WriteHeader(status)
	_, _ = io.WriteString(response, encoded.String())
}
