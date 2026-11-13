package verifier

import (
	"encoding/binary"
	"encoding/hex"
	"encoding/json"
	"math"
	"math/big"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

type temporalIntegerVector struct {
	Name    string `json:"name"`
	Decimal string `json:"decimal"`
}
type temporalFloatVector struct {
	Name  string `json:"name"`
	BEHex string `json:"be_hex"`
}
type temporalTauVector struct {
	Name     string `json:"name"`
	BEHex    string `json:"be_hex"`
	Accepted bool   `json:"accepted"`
}
type temporalPhaseVector struct {
	Name       string `json:"name"`
	RealBEHex  string `json:"real_be_hex"`
	ImagBEHex  string `json:"imag_be_hex"`
	Accepted   bool   `json:"accepted"`
}
type temporalV2Vectors struct {
	Profile          string                  `json:"profile"`
	Integers         []temporalIntegerVector `json:"integers"`
	Binary64         []temporalFloatVector   `json:"binary64"`
	InvalidInteger   []string                `json:"invalid_integer_tokens"`
	InvalidBinary64  []temporalFloatVector   `json:"invalid_binary64_tokens"`
	ChemicalTau      []temporalTauVector     `json:"chemical_tau_cases"`
	ChrononPhase     []temporalPhaseVector   `json:"chronon_phase_cases"`
}

func readTemporalV2Vectors(t *testing.T) temporalV2Vectors {
	t.Helper()
	path := filepath.Join("..", "..", "..", "formats", "temporal-coordinate-v2", "vectors.json")
	raw, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read temporal v2 vectors: %v", err)
	}
	var vectors temporalV2Vectors
	if err := json.Unmarshal(raw, &vectors); err != nil {
		t.Fatalf("decode temporal v2 vectors: %v", err)
	}
	if vectors.Profile != TemporalNumericSchema {
		t.Fatalf("unexpected temporal numeric profile %q", vectors.Profile)
	}
	return vectors
}

func floatFromTemporalHex(t *testing.T, raw string) float64 {
	t.Helper()
	b, err := hex.DecodeString(raw)
	if err != nil || len(b) != 8 {
		t.Fatalf("invalid test binary64 hex %q", raw)
	}
	return math.Float64frombits(binary.BigEndian.Uint64(b))
}

func TestTemporalV2IntegerVectorsAreExactBeyondSafeAndInt64Ranges(t *testing.T) {
	vectors := readTemporalV2Vectors(t)
	for _, vector := range vectors.Integers {
		t.Run(vector.Name, func(t *testing.T) {
			want, ok := new(big.Int).SetString(vector.Decimal, 10)
			if !ok {
				t.Fatal("bad vector integer")
			}
			envelope, err := EncodeTemporalInteger(want)
			if err != nil {
				t.Fatal(err)
			}
			got, err := DecodeTemporalInteger(envelope, nil, nil)
			if err != nil {
				t.Fatal(err)
			}
			if got.Cmp(want) != 0 {
				t.Fatalf("got %s, want %s", got, want)
			}
			if envelope["value"] != vector.Decimal {
				t.Fatalf("decimal encoding %v does not preserve token %s", envelope["value"], vector.Decimal)
			}
		})
	}
}

func TestTemporalV2RejectsNoncanonicalIntegerTokens(t *testing.T) {
	vectors := readTemporalV2Vectors(t)
	for _, token := range vectors.InvalidInteger {
		t.Run(token, func(t *testing.T) {
			envelope := Object{
				"format": TemporalNumericFormat,
				"schema": TemporalNumericSchema,
				"kind": "integer",
				"encoding": TemporalIntegerEncoding,
				"value": token,
			}
			if _, err := DecodeTemporalInteger(envelope, nil, nil); err == nil {
				t.Fatalf("accepted invalid integer token %q", token)
			}
		})
	}
}

func TestTemporalV2Binary64VectorsPreserveExactBits(t *testing.T) {
	vectors := readTemporalV2Vectors(t)
	for _, vector := range vectors.Binary64 {
		t.Run(vector.Name, func(t *testing.T) {
			want := floatFromTemporalHex(t, vector.BEHex)
			envelope, err := EncodeTemporalBinary64(want)
			if err != nil {
				t.Fatal(err)
			}
			if envelope["value"] != vector.BEHex {
				t.Fatalf("got bits %v, want %s", envelope["value"], vector.BEHex)
			}
			got, err := DecodeTemporalBinary64(envelope)
			if err != nil {
				t.Fatal(err)
			}
			if math.Float64bits(got) != math.Float64bits(want) {
				t.Fatalf("binary64 bits changed: got %016x, want %016x", math.Float64bits(got), math.Float64bits(want))
			}
		})
	}
}

func TestTemporalV2RejectsMalformedAndNonfiniteBinary64(t *testing.T) {
	vectors := readTemporalV2Vectors(t)
	for _, vector := range vectors.InvalidBinary64 {
		t.Run(vector.Name, func(t *testing.T) {
			envelope := Object{
				"format": TemporalNumericFormat,
				"schema": TemporalNumericSchema,
				"kind": "binary64",
				"encoding": TemporalFloatEncoding,
				"value": vector.BEHex,
			}
			if _, err := DecodeTemporalBinary64(envelope); err == nil {
				t.Fatalf("accepted invalid binary64 token %q", vector.BEHex)
			}
		})
	}
}

func TestTemporalV2ChemicalTauRulesAndNegativeZeroPreservation(t *testing.T) {
	vectors := readTemporalV2Vectors(t)
	for _, vector := range vectors.ChemicalTau {
		t.Run(vector.Name, func(t *testing.T) {
			value := floatFromTemporalHex(t, vector.BEHex)
			wire, err := EncodeTemporalBinary64(value)
			if err != nil {
				t.Fatal(err)
			}
			decoded, err := DecodeTemporalBinary64(wire)
			if err != nil {
				t.Fatal(err)
			}
			accepted := decoded >= 0
			if accepted != vector.Accepted {
				t.Fatalf("chemical tau accepted=%v, expected %v", accepted, vector.Accepted)
			}
			if math.Float64bits(decoded) != math.Float64bits(value) {
				t.Fatal("chemical tau bits changed")
			}
		})
	}
}

func TestTemporalV2ChrononPhaseValidation(t *testing.T) {
	vectors := readTemporalV2Vectors(t)
	for _, vector := range vectors.ChrononPhase {
		t.Run(vector.Name, func(t *testing.T) {
			real := floatFromTemporalHex(t, vector.RealBEHex)
			imaginary := floatFromTemporalHex(t, vector.ImagBEHex)
			err := v2CheckTemporalPhase(real, imaginary)
			if vector.Accepted && err != nil {
				t.Fatalf("valid phase rejected: %v", err)
			}
			if !vector.Accepted && err == nil {
				t.Fatal("invalid phase accepted")
			}
		})
	}
}

func TestTemporalFrameV2RoundtripWithWideCountersAndBinary64Domains(t *testing.T) {
	actor := "host-α"
	other := "host-B"
	sqrtHalf := floatFromTemporalHex(t, "3fe6a09e667f3bcd")
	frame := Object{
		"actor_id": actor,
		"monotonic": Object{"actor_id": actor, "segment": json.Number("18446744073709551615"), "elapsed_ns": json.Number("18446744073709551616000")},
		"wall": Object{"actor_id": actor, "utc_ns": json.Number("-9223372036854775808"), "sample_index": json.Number("9007199254740992")},
		"causal": Object{"actor_id": actor, "lamport": json.Number("18446744073709551616"), "vector": Object{actor: json.Number("18446744073709551616"), other: json.Number("18446744073709551615")}},
		"scheduler": Object{"scheduler_id": "mailcpu", "tick": json.Number("123456789012345678901234567890")},
		"event_lambda": json.Number("9007199254740993"),
		"chronon_phase": []any{sqrtHalf, sqrtHalf},
		"chemical_tau": math.Copysign(0, -1),
	}
	wire, err := EncodeTemporalFrameV2(frame)
	if err != nil {
		t.Fatal(err)
	}
	canonical, err := CanonicalBytes(wire)
	if err != nil {
		t.Fatal(err)
	}
	restored, err := DecodeTemporalFrameV2(wire)
	if err != nil {
		t.Fatal(err)
	}
	mono := restored["monotonic"].(map[string]any)
	elapsed := mono["elapsed_ns"].(*big.Int)
	wantElapsed, _ := new(big.Int).SetString("18446744073709551616000", 10)
	if elapsed.Cmp(wantElapsed) != 0 {
		t.Fatalf("elapsed_ns=%s, want %s", elapsed, wantElapsed)
	}
	wall := restored["wall"].(map[string]any)
	utc := wall["utc_ns"].(*big.Int)
	wantUTC := big.NewInt(-9223372036854775808)
	if utc.Cmp(wantUTC) != 0 {
		t.Fatalf("utc_ns=%s, want %s", utc, wantUTC)
	}
	if !math.Signbit(restored["chemical_tau"].(float64)) {
		t.Fatal("negative zero chemical time sign bit was not preserved")
	}
	reencoded, err := EncodeTemporalFrameV2(restored)
	if err != nil {
		t.Fatal(err)
	}
	canonicalAgain, err := CanonicalBytes(reencoded)
	if err != nil {
		t.Fatal(err)
	}
	if string(canonical) != string(canonicalAgain) {
		t.Fatalf("frame roundtrip changed canonical bytes
%s
%s", canonical, canonicalAgain)
	}
}

func TestTemporalFrameV2RejectsMissingCausalSelfEntryAndActorMismatch(t *testing.T) {
	frame := Object{
		"actor_id": "host-a",
		"monotonic": nil,
		"wall": nil,
		"causal": Object{"actor_id": "host-a", "lamport": json.Number("1"), "vector": Object{"host-b": json.Number("1")}},
		"scheduler": nil,
		"event_lambda": nil,
		"chronon_phase": nil,
		"chemical_tau": nil,
	}
	if _, err := EncodeTemporalFrameV2(frame); err == nil || !strings.Contains(err.Error(), "include its own actor") {
		t.Fatalf("expected missing self actor rejection, got %v", err)
	}
	frame["causal"].(Object)["vector"].(Object)["host-a"] = json.Number("1")
	frame["monotonic"] = Object{"actor_id": "other", "segment": json.Number("0"), "elapsed_ns": json.Number("0")}
	if _, err := EncodeTemporalFrameV2(frame); err == nil {
		t.Fatal("accepted monotonic actor mismatch")
	}
}

func TestOperationSpanV2RoundtripForUnsafeNanosecondEndpoints(t *testing.T) {
	span := Object{
		"format": TemporalSpanFormat,
		"schema": SpanSchema,
		"attempt_id": "attempt-1",
		"span_id": "span-1",
		"operation_id": "host.prepare",
		"clock_actor_id": "host-a",
		"clock_segment_id": "0",
		"monotonic_start_ns": json.Number("18446744073709551616"),
		"monotonic_end_ns": json.Number("18446744073709551999"),
		"elapsed_ns": json.Number("383"),
		"clock_status": "measured",
		"outcome": "succeeded",
		"exception_type": nil,
		"context": Object{"role": "source_host"},
		"measurement_scope": "synchronous-call",
		"span_digest": strings.Repeat("0", 64),
	}
	wire, err := EncodeOperationSpanV2(span)
	if err != nil {
		t.Fatal(err)
	}
	restored, err := DecodeOperationSpanV2(wire)
	if err != nil {
		t.Fatal(err)
	}
	got := restored["monotonic_start_ns"].(*big.Int)
	want, _ := new(big.Int).SetString("18446744073709551616", 10)
	if got.Cmp(want) != 0 {
		t.Fatalf("decoded start=%s, want %s", got, want)
	}
	reencoded, err := EncodeOperationSpanV2(restored)
	if err != nil {
		t.Fatal(err)
	}
	a, _ := CanonicalBytes(wire)
	b, _ := CanonicalBytes(reencoded)
	if string(a) != string(b) {
		t.Fatal("operation span v2 roundtrip changed canonical bytes")
	}
}

func TestOperationSpanV2RejectsMismatchedMeasuredDuration(t *testing.T) {
	span := Object{
		"format": TemporalSpanFormat,
		"schema": SpanSchema,
		"attempt_id": "attempt-1",
		"span_id": "span-1",
		"operation_id": "host.prepare",
		"clock_actor_id": "host-a",
		"clock_segment_id": "0",
		"monotonic_start_ns": json.Number("10"),
		"monotonic_end_ns": json.Number("20"),
		"elapsed_ns": json.Number("9"),
		"clock_status": "measured",
		"outcome": "succeeded",
		"exception_type": nil,
		"context": Object{},
		"measurement_scope": "synchronous-call",
		"span_digest": strings.Repeat("0", 64),
	}
	if _, err := EncodeOperationSpanV2(span); err == nil {
		t.Fatal("accepted measured span with mismatched elapsed")
	}
}
