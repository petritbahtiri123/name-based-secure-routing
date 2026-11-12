package main

import (
	"crypto/ecdsa"
	"crypto/elliptic"
	"crypto/rand"
	"crypto/x509"
	"crypto/x509/pkix"
	"errors"
	"flag"
	"fmt"
	"math/big"
	"os"
	"path/filepath"
	"time"
)

func main() {
	output := flag.String("output", "", "absolute fresh private fixture directory")
	flag.Parse()
	if flag.NArg() != 0 {
		fmt.Fprintln(os.Stderr, "unexpected arguments")
		os.Exit(2)
	}
	if err := generate(*output, time.Now().UTC()); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}

func generate(output string, now time.Time) error {
	if !filepath.IsAbs(output) || filepath.Clean(output) != output {
		return errors.New("output must be an absolute clean fresh path")
	}
	// Refuse aliases at every existing ancestor. No recursive directory creation.
	for current := filepath.Dir(output); ; current = filepath.Dir(current) {
		info, err := os.Lstat(current)
		if err != nil {
			return err
		}
		resolved, err := filepath.EvalSymlinks(current)
		if err != nil || resolved != current || !info.IsDir() || info.Mode()&os.ModeSymlink != 0 {
			return errors.New("output ancestor is an alias or non-directory")
		}
		if filepath.Dir(current) == current {
			break
		}
	}
	if err := privateDirectory(output); err != nil {
		return err
	}
	// Root-relative creation refuses escapes even if another process changes paths.
	root, err := os.OpenRoot(output)
	if err != nil {
		return err
	}
	defer root.Close()
	write := func(name string, data []byte) error {
		f, err := root.OpenFile(name, os.O_WRONLY|os.O_CREATE|os.O_EXCL, 0600)
		if err != nil {
			return err
		}
		_, writeErr := f.Write(data)
		closeErr := f.Close()
		return errors.Join(writeErr, closeErr)
	}
	serial := func() (*big.Int, error) { return rand.Int(rand.Reader, new(big.Int).Lsh(big.NewInt(1), 128)) }
	caKey, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	if err != nil {
		return err
	}
	number, err := serial()
	if err != nil {
		return err
	}
	ca := &x509.Certificate{SerialNumber: number, Subject: pkix.Name{CommonName: "NBSR Demo CA"}, NotBefore: now.Add(-time.Minute), NotAfter: now.Add(2 * time.Hour), IsCA: true, BasicConstraintsValid: true}
	der, err := x509.CreateCertificate(rand.Reader, ca, ca, &caKey.PublicKey, caKey)
	if err != nil {
		return err
	}
	if err := write("ca.der", der); err != nil {
		return err
	}
	for _, name := range []string{"source", "destination"} {
		key, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
		if err != nil {
			return err
		}
		number, err := serial()
		if err != nil {
			return err
		}
		leaf := &x509.Certificate{SerialNumber: number, Subject: pkix.Name{CommonName: name + ".edge"}, DNSNames: []string{name + ".edge"}, NotBefore: now.Add(-time.Minute), NotAfter: now.Add(time.Hour), ExtKeyUsage: []x509.ExtKeyUsage{x509.ExtKeyUsageServerAuth, x509.ExtKeyUsageClientAuth}}
		cert, err := x509.CreateCertificate(rand.Reader, leaf, ca, &key.PublicKey, caKey)
		if err != nil {
			return err
		}
		encoded, err := x509.MarshalPKCS8PrivateKey(key)
		if err != nil {
			return err
		}
		if err := write(name+".der", cert); err != nil {
			return err
		}
		if err := write(name+"-key.der", encoded); err != nil {
			return err
		}
	}
	return nil
}
