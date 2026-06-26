package main

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"github.com/ProtonMail/go-crypto/openpgp"
)

// KeySet holds the shared OpenPGP keys loaded from the Key_Set directory.
type KeySet struct {
	Path string
	byID map[string]*keyPair // keyed by file id prefix, e.g. "rsa2048"
}

type keyPair struct {
	id      string
	public  openpgp.EntityList
	private openpgp.EntityList
}

// pubAlgToKeyID maps a Crypto_Profile public-key algorithm label onto the key
// file id prefix on disk (see keys/KEYINFO.md).
func pubAlgToKeyID(pubAlg string) (string, bool) {
	switch strings.ToUpper(strings.ReplaceAll(pubAlg, "_", "-")) {
	case "RSA-2048", "RSA2048":
		return "rsa2048", true
	case "RSA-4096", "RSA4096":
		return "rsa4096", true
	case "CURVE25519", "ECC-CURVE25519", "CV25519", "ED25519", "ECC":
		return "cv25519", true
	default:
		return "", false
	}
}

// LoadKeySet parses every "<id>-public.asc" / "<id>-private.asc" pair in dir.
func LoadKeySet(dir string) (*KeySet, error) {
	entries, err := os.ReadDir(dir)
	if err != nil {
		return nil, fmt.Errorf("read key set dir: %w", err)
	}

	ks := &KeySet{Path: dir, byID: map[string]*keyPair{}}
	for _, e := range entries {
		if e.IsDir() {
			continue
		}
		name := e.Name()
		var id string
		var isPublic bool
		switch {
		case strings.HasSuffix(name, "-public.asc"):
			id = strings.TrimSuffix(name, "-public.asc")
			isPublic = true
		case strings.HasSuffix(name, "-private.asc"):
			id = strings.TrimSuffix(name, "-private.asc")
			isPublic = false
		default:
			continue
		}

		list, err := readArmoredKeyRing(filepath.Join(dir, name))
		if err != nil {
			return nil, fmt.Errorf("parse key file %q: %w", name, err)
		}
		kp := ks.byID[id]
		if kp == nil {
			kp = &keyPair{id: id}
			ks.byID[id] = kp
		}
		if isPublic {
			kp.public = list
		} else {
			kp.private = list
		}
	}

	if len(ks.byID) == 0 {
		return nil, fmt.Errorf("no OpenPGP key files (*-public.asc/*-private.asc) found in %q", dir)
	}
	return ks, nil
}

func readArmoredKeyRing(path string) (openpgp.EntityList, error) {
	f, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer f.Close()
	return openpgp.ReadArmoredKeyRing(f)
}

// EncryptionKeys returns the public EntityList for the given pubAlg.
func (k *KeySet) EncryptionKeys(pubAlg string) (openpgp.EntityList, error) {
	kp, err := k.pairFor(pubAlg)
	if err != nil {
		return nil, err
	}
	if len(kp.public) == 0 {
		return nil, fmt.Errorf("no public key loaded for %q", pubAlg)
	}
	return kp.public, nil
}

// DecryptionKeys returns the private EntityList for the given pubAlg.
func (k *KeySet) DecryptionKeys(pubAlg string) (openpgp.EntityList, error) {
	kp, err := k.pairFor(pubAlg)
	if err != nil {
		return nil, err
	}
	if len(kp.private) == 0 {
		return nil, fmt.Errorf("no private key loaded for %q", pubAlg)
	}
	return kp.private, nil
}

func (k *KeySet) pairFor(pubAlg string) (*keyPair, error) {
	id, ok := pubAlgToKeyID(pubAlg)
	if !ok {
		return nil, fmt.Errorf("unknown public-key algorithm %q", pubAlg)
	}
	kp := k.byID[id]
	if kp == nil {
		return nil, fmt.Errorf("no key loaded for %q (expected file id %q)", pubAlg, id)
	}
	return kp, nil
}

// HasKeyFor reports whether both a public and private key are present for pubAlg.
func (k *KeySet) HasKeyFor(pubAlg string) bool {
	kp, err := k.pairFor(pubAlg)
	if err != nil {
		return false
	}
	return len(kp.public) > 0 && len(kp.private) > 0
}
