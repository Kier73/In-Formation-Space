package verifier

import (
    "bytes"
    "testing"
)

func TestDecodeObjectRejectsUnpairedUnicodeSurrogateEscapes(t *testing.T) {
    cases := []struct {
        name  string
        input string
    }{
        {name: "unpaired high surrogate", input: `{"value":"\ud800"}`},
        {name: "unpaired low surrogate", input: `{"value":"\udc00"}`},
        {name: "high surrogate followed by non-low escape", input: `{"value":"\ud800\u0061"}`},
        {name: "two high surrogates", input: `{"value":"\ud800\ud801"}`},
    }
    for _, tc := range cases {
        t.Run(tc.name, func(t *testing.T) {
            if _, err := DecodeObject([]byte(tc.input)); err == nil {
                t.Fatal("invalid surrogate sequence was accepted")
            }
        })
    }
}

func TestDecodeObjectAcceptsValidUnicodeSurrogatePair(t *testing.T) {
    object, err := DecodeObject([]byte(`{"value":"\ud83d\ude80"}`))
    if err != nil {
        t.Fatalf("valid surrogate pair was rejected: %v", err)
    }
    canonical, err := CanonicalBytes(object)
    if err != nil {
        t.Fatalf("canonical encoding failed: %v", err)
    }
    if !bytes.Equal(canonical, []byte(`{"value":"🚀"}`)) {
        t.Fatalf("unexpected canonical JSON: %s", canonical)
    }
}

func TestDecodeObjectPreservesLiteralUnicodeEscapeText(t *testing.T) {
    object, err := DecodeObject([]byte(`{"value":"\\ud800"}`))
    if err != nil {
        t.Fatalf("literal backslash-u text was rejected: %v", err)
    }
    canonical, err := CanonicalBytes(object)
    if err != nil {
        t.Fatalf("canonical encoding failed: %v", err)
    }
    if !bytes.Equal(canonical, []byte(`{"value":"\\ud800"}`)) {
        t.Fatalf("literal escape text changed during canonicalization: %s", canonical)
    }
}

func TestDecodeObjectRejectsInvalidUTF8BeforeParsing(t *testing.T) {
    raw := []byte{'{', '"', 'v', '"', ':', '"', 0xff, '"', '}'}
    if _, err := DecodeObject(raw); err == nil {
        t.Fatal("invalid UTF-8 was accepted")
    }
}
