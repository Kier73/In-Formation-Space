package verifier

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"testing"
)

type canonicalVectorCorpus struct {
	Schema   string                 `json:"schema"`
	Profile  string                 `json:"profile"`
	Vectors  []canonicalVectorEntry `json:"vectors"`
}

type canonicalVectorEntry struct {
	ID             string `json:"id"`
	InputJSON      string `json:"input_json"`
	LineEnding     string `json:"line_ending"`
	PrefixBOM      bool   `json:"prefix_bom"`
	Accept         bool   `json:"accept"`
	CanonicalSHA256 string `json:"canonical_sha256"`
}

func canonicalVectorArtifact(vector canonicalVectorEntry) ([]byte, error) {
	var raw []byte
	if vector.PrefixBOM {
		raw = append(raw, 0xef, 0xbb, 0xbf)
	}
	raw = append(raw, []byte(vector.InputJSON)...)
	switch vector.LineEnding {
	case "lf":
		raw = append(raw, '\n')
	case "double_lf":
		raw = append(raw, '\n', '\n')
	case "crlf":
		raw = append(raw, '\r', '\n')
	case "none":
	case "":
		return nil, fmt.Errorf("line_ending is required")
	default:
		return nil, fmt.Errorf("unknown line_ending %q", vector.LineEnding)
	}
	return raw, nil
}

func TestSharedCanonicalMetadataV1Vectors(t *testing.T) {
	corpusPath := filepath.Join("..", "..", "..", "formats", "canonical-metadata-v1", "vectors.json")
	rawCorpus, err := os.ReadFile(corpusPath)
	if err != nil {
		t.Fatalf("read shared canonical metadata corpus: %v", err)
	}
	var corpus canonicalVectorCorpus
	if err := json.Unmarshal(rawCorpus, &corpus); err != nil {
		t.Fatalf("decode shared canonical metadata corpus: %v", err)
	}
	if corpus.Schema != "in-formation.canonical-metadata-conformance-vectors/1" {
		t.Fatalf("unexpected corpus schema: %q", corpus.Schema)
	}
	if corpus.Profile != "canonical-metadata-v1" {
		t.Fatalf("unexpected profile: %q", corpus.Profile)
	}
	if len(corpus.Vectors) == 0 {
		t.Fatal("shared canonical metadata corpus must not be empty")
	}

	for _, vector := range corpus.Vectors {
		t.Run(vector.ID, func(t *testing.T) {
			raw, err := canonicalVectorArtifact(vector)
			if err != nil {
				t.Fatal(err)
			}
			path := filepath.Join(t.TempDir(), "artifact.json")
			if err := os.WriteFile(path, raw, 0600); err != nil {
				t.Fatal(err)
			}
			object, _, readErr := ReadCanonicalFile(path)
			if vector.Accept {
				if readErr != nil {
					t.Fatalf("valid vector rejected: %v", readErr)
				}
				canonical, err := CanonicalBytes(object)
				if err != nil {
					t.Fatalf("canonical encoding failed: %v", err)
				}
				if !bytes.Equal(canonical, []byte(vector.InputJSON)) {
					t.Fatalf("canonical bytes mismatch\n got: %q\nwant: %q", canonical, vector.InputJSON)
				}
				sum := sha256.Sum256(canonical)
				got := hex.EncodeToString(sum[:])
				if got != vector.CanonicalSHA256 {
					t.Fatalf("canonical SHA-256 mismatch: got %s, want %s", got, vector.CanonicalSHA256)
				}
			} else if readErr == nil {
				t.Fatalf("invalid vector unexpectedly accepted: %#v", object)
			}
		})
	}
}
