package verifier

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"testing"
)

type canonicalMetadataCorpus struct {
	Profile               string                    `json:"profile"`
	Valid                 []canonicalMetadataVector `json:"valid"`
	InvalidValues         []canonicalMetadataVector `json:"invalid_values"`
	NoncanonicalDocuments []canonicalMetadataVector `json:"noncanonical_documents"`
}

type canonicalMetadataVector struct {
	Name          string `json:"name"`
	InputJSON     string `json:"input_json"`
	CanonicalUTF8 string `json:"canonical_utf8"`
	SHA256        string `json:"sha256"`
}

func decodeCanonicalMetadataValue(source string) (any, error) {
	decoder := json.NewDecoder(bytes.NewBufferString(source))
	decoder.UseNumber()
	var value any
	if err := decoder.Decode(&value); err != nil {
		return nil, err
	}
	if _, err := decoder.Token(); err != io.EOF {
		return nil, fmt.Errorf("expected exactly one JSON value")
	}
	return value, nil
}

func readCanonicalMetadataCorpus(t *testing.T) canonicalMetadataCorpus {
	t.Helper()
	path := filepath.Join("..", "..", "..", "formats", "canonical-metadata-v1", "test-vectors.json")
	raw, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read shared canonical metadata vectors: %v", err)
	}
	var corpus canonicalMetadataCorpus
	if err := json.Unmarshal(raw, &corpus); err != nil {
		t.Fatalf("decode shared canonical metadata vectors: %v", err)
	}
	if corpus.Profile != "in-formation-space.canonical-metadata.v1" {
		t.Fatalf("unexpected profile identifier %q", corpus.Profile)
	}
	return corpus
}

func TestSharedCanonicalMetadataV1ValidVectors(t *testing.T) {
	corpus := readCanonicalMetadataCorpus(t)
	for _, vector := range corpus.Valid {
		t.Run(vector.Name, func(t *testing.T) {
			value, err := decodeCanonicalMetadataValue(vector.InputJSON)
			if err != nil {
				t.Fatalf("decode valid vector: %v", err)
			}
			actual, err := CanonicalBytes(value)
			if err != nil {
				t.Fatalf("canonical encoder rejected valid vector: %v", err)
			}
			if !bytes.Equal(actual, []byte(vector.CanonicalUTF8)) {
				t.Fatalf("canonical bytes differ\ngot:  %q\nwant: %q", actual, vector.CanonicalUTF8)
			}
			if got := BytesDigest(actual); got != vector.SHA256 {
				t.Fatalf("SHA-256 mismatch: got %s, want %s", got, vector.SHA256)
			}
		})
	}
}

func TestSharedCanonicalMetadataV1InvalidValues(t *testing.T) {
	corpus := readCanonicalMetadataCorpus(t)
	for _, vector := range corpus.InvalidValues {
		t.Run(vector.Name, func(t *testing.T) {
			value, err := decodeCanonicalMetadataValue(vector.InputJSON)
			if err == nil {
				_, err = CanonicalBytes(value)
			}
			if err == nil {
				t.Fatal("invalid metadata value was accepted")
			}
		})
	}
}

func TestSharedCanonicalMetadataV1NoncanonicalDocuments(t *testing.T) {
	corpus := readCanonicalMetadataCorpus(t)
	for _, vector := range corpus.NoncanonicalDocuments {
		t.Run(vector.Name, func(t *testing.T) {
			value, err := decodeCanonicalMetadataValue(vector.InputJSON)
			if err != nil {
				// Some runtimes reject noncanonical numeric lexemes at parse time.
				return
			}
			actual, err := CanonicalBytes(value)
			if err != nil {
				return
			}
			if !bytes.Equal(actual, []byte(vector.CanonicalUTF8)) {
				t.Fatalf("canonical bytes differ\ngot:  %q\nwant: %q", actual, vector.CanonicalUTF8)
			}
			if bytes.Equal(actual, []byte(vector.InputJSON)) {
				t.Fatal("noncanonical source bytes unexpectedly equal canonical bytes")
			}
		})
	}
}

func TestReadCanonicalFileRequiresExactCanonicalBytes(t *testing.T) {
	corpus := readCanonicalMetadataCorpus(t)
	if len(corpus.Valid) == 0 {
		t.Fatal("valid corpus must not be empty")
	}
	vector := corpus.Valid[0]
	canonicalPath := filepath.Join(t.TempDir(), "canonical.json")
	if err := os.WriteFile(canonicalPath, append([]byte(vector.CanonicalUTF8), '\n'), 0600); err != nil {
		t.Fatal(err)
	}
	if _, _, err := ReadCanonicalFile(canonicalPath); err != nil {
		t.Fatalf("canonical artifact rejected: %v", err)
	}

	noncanonicalPath := filepath.Join(t.TempDir(), "noncanonical.json")
	if err := os.WriteFile(noncanonicalPath, append([]byte(vector.InputJSON), '\n'), 0600); err != nil {
		t.Fatal(err)
	}
	if _, _, err := ReadCanonicalFile(noncanonicalPath); err == nil {
		t.Fatal("noncanonical artifact unexpectedly accepted")
	}
}
