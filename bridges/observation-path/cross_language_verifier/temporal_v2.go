package verifier

import (
	"encoding/binary"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"math"
	"math/big"
	"regexp"
	"sort"
	"strings"
)

const (
	TemporalNumericFormat   = "in-formation.temporal-numeric"
	TemporalNumericSchema  = "in-formation.temporal-numeric/2.0"
	TemporalIntegerEncoding = "canonical-decimal-string"
	TemporalFloatEncoding   = "ieee754-binary64-be-hex"
	TemporalFrameFormat    = "in-formation.temporal-frame"
	TemporalFrameSchema    = "in-formation.temporal-frame/0.2"
	TemporalSpanFormat     = "in-formation.operation-span"
	TemporalSpanSchema     = "in-formation.operation-span/0.2"
)

var temporalDecimal = regexp.MustCompile(`^(0|-?[1-9][0-9]*)$`)
var temporalHex64 = regexp.MustCompile(`^[0-9a-f]{16}$`)

func EncodeTemporalInteger(value any) (Object, error) {
	n, err := temporalBigInt(value, "temporal integer")
	if err != nil {
		return nil, err
	}
	return Object{
		"format":   TemporalNumericFormat,
		"schema":   TemporalNumericSchema,
		"kind":     "integer",
		"encoding": TemporalIntegerEncoding,
		"value":    n.String(),
	}, nil
}

func DecodeTemporalInteger(value any, minimum *big.Int, maximum *big.Int) (*big.Int, error) {
	raw, err := exactFields(value, []string{"format", "schema", "kind", "encoding", "value"}, "temporal integer")
	if err != nil {
		return nil, err
	}
	if raw["format"] != TemporalNumericFormat || raw["schema"] != TemporalNumericSchema || raw["kind"] != "integer" || raw["encoding"] != TemporalIntegerEncoding {
		return nil, fail("temporal integer format, schema, kind, or encoding mismatch")
	}
	token, ok := raw["value"].(string)
	if !ok || !temporalDecimal.MatchString(token) {
		return nil, fail("temporal integer value must be canonical decimal text")
	}
	n, ok := new(big.Int).SetString(token, 10)
	if !ok {
		return nil, fail("temporal integer is invalid")
	}
	if minimum != nil && n.Cmp(minimum) < 0 {
		return nil, fail("temporal integer is below its field minimum")
	}
	if maximum != nil && n.Cmp(maximum) > 0 {
		return nil, fail("temporal integer is above its field maximum")
	}
	return n, nil
}

func EncodeTemporalBinary64(value float64) (Object, error) {
	if math.IsNaN(value) || math.IsInf(value, 0) {
		return nil, fail("temporal binary64 value must be finite")
	}
	var raw [8]byte
	binary.BigEndian.PutUint64(raw[:], math.Float64bits(value))
	return Object{
		"format":   TemporalNumericFormat,
		"schema":   TemporalNumericSchema,
		"kind":     "binary64",
		"encoding": TemporalFloatEncoding,
		"value":    hex.EncodeToString(raw[:]),
	}, nil
}

func DecodeTemporalBinary64(value any) (float64, error) {
	raw, err := exactFields(value, []string{"format", "schema", "kind", "encoding", "value"}, "temporal binary64")
	if err != nil {
		return 0, err
	}
	if raw["format"] != TemporalNumericFormat || raw["schema"] != TemporalNumericSchema || raw["kind"] != "binary64" || raw["encoding"] != TemporalFloatEncoding {
		return 0, fail("temporal binary64 format, schema, kind, or encoding mismatch")
	}
	token, ok := raw["value"].(string)
	if !ok || !temporalHex64.MatchString(token) {
		return 0, fail("temporal binary64 value must be 16 lowercase hexadecimal digits")
	}
	bits, err := hex.DecodeString(token)
	if err != nil || len(bits) != 8 {
		return 0, fail("temporal binary64 bit string is invalid")
	}
	value64 := math.Float64frombits(binary.BigEndian.Uint64(bits))
	if math.IsNaN(value64) || math.IsInf(value64, 0) {
		return 0, fail("temporal binary64 value must be finite")
	}
	return value64, nil
}

func temporalBigInt(value any, label string) (*big.Int, error) {
	switch v := value.(type) {
	case *big.Int:
		if v == nil {
			return nil, fail("%s is nil", label)
		}
		return new(big.Int).Set(v), nil
	case big.Int:
		return new(big.Int).Set(&v), nil
	case json.Number:
		if !temporalDecimal.MatchString(string(v)) {
			return nil, fail("%s is not canonical decimal integer text", label)
		}
		n, ok := new(big.Int).SetString(string(v), 10)
		if !ok {
			return nil, fail("%s is invalid", label)
		}
		return n, nil
	case int:
		return big.NewInt(int64(v)), nil
	case int8:
		return big.NewInt(int64(v)), nil
	case int16:
		return big.NewInt(int64(v)), nil
	case int32:
		return big.NewInt(int64(v)), nil
	case int64:
		return big.NewInt(v), nil
	case uint:
		return new(big.Int).SetUint64(uint64(v)), nil
	case uint8:
		return new(big.Int).SetUint64(uint64(v)), nil
	case uint16:
		return new(big.Int).SetUint64(uint64(v)), nil
	case uint32:
		return new(big.Int).SetUint64(uint64(v)), nil
	case uint64:
		return new(big.Int).SetUint64(v), nil
	default:
		return nil, fail("%s has unsupported integer type %T", label, value)
	}
}

func temporalMinimumZero() *big.Int { return big.NewInt(0) }

func temporalText(value any, label string) (string, error) {
	return textValue(value, label)
}

func temporalObject(value any, fields []string, label string) (Object, error) {
	return exactFields(value, fields, label)
}

func temporalArray(value any, label string) ([]any, error) {
	switch v := value.(type) {
	case []any:
		return v, nil
	case []Object:
		result := make([]any, len(v))
		for i := range v {
			result[i] = v[i]
		}
		return result, nil
	default:
		return nil, fail("%s must be an array", label)
	}
}

func temporalFloatInput(value any, label string) (float64, error) {
	switch v := value.(type) {
	case float64:
		if math.IsNaN(v) || math.IsInf(v, 0) {
			return 0, fail("%s must be finite", label)
		}
		return v, nil
	case float32:
		f := float64(v)
		if math.IsNaN(f) || math.IsInf(f, 0) {
			return 0, fail("%s must be finite", label)
		}
		return f, nil
	default:
		return 0, fail("%s must be a binary64 value, not %T", label, value)
	}
}

func checkTemporalPhase(real, imaginary float64) error {
	if math.IsNaN(real) || math.IsNaN(imaginary) || math.IsInf(real, 0) || math.IsInf(imaginary, 0) {
		return fail("chronon_phase must contain finite binary64 values")
	}
	if !math.IsClose(math.Hypot(real, imaginary), 1.0, 1e-9) {
		return fail("chronon_phase must lie on the unit circle")
	}
	return nil
}

func EncodeTemporalFrameV2(frame Object) (Object, error) {
	required := []string{"actor_id", "monotonic", "wall", "causal", "scheduler", "event_lambda", "chronon_phase", "chemical_tau"}
	raw, err := exactFields(frame, required, "temporal frame")
	if err != nil {
		return nil, err
	}
	actor, err := temporalText(raw["actor_id"], "frame.actor_id")
	if err != nil {
		return nil, err
	}
	out := Object{
		"format": TemporalFrameFormat,
		"schema": TemporalFrameSchema,
		"numeric_profile": TemporalNumericSchema,
		"actor_id": actor,
	}

	if raw["monotonic"] == nil {
		out["monotonic"] = nil
	} else {
		m, err := temporalObject(raw["monotonic"], []string{"actor_id", "segment", "elapsed_ns"}, "frame.monotonic")
		if err != nil {
			return nil, err
		}
		a, err := temporalText(m["actor_id"], "monotonic.actor_id")
		if err != nil || a != actor {
			return nil, fail("monotonic actor does not match frame actor")
		}
		segment, err := temporalBigInt(m["segment"], "monotonic.segment")
		if err != nil || segment.Sign() < 0 {
			return nil, fail("monotonic segment must be non-negative")
		}
		elapsed, err := temporalBigInt(m["elapsed_ns"], "monotonic.elapsed_ns")
		if err != nil || elapsed.Sign() < 0 {
			return nil, fail("monotonic elapsed_ns must be non-negative")
		}
		s, _ := EncodeTemporalInteger(segment)
		e, _ := EncodeTemporalInteger(elapsed)
		out["monotonic"] = Object{"actor_id": a, "segment": s, "elapsed_ns": e}
	}

	if raw["wall"] == nil {
		out["wall"] = nil
	} else {
		w, err := temporalObject(raw["wall"], []string{"actor_id", "utc_ns", "sample_index"}, "frame.wall")
		if err != nil {
			return nil, err
		}
		a, err := temporalText(w["actor_id"], "wall.actor_id")
		if err != nil || a != actor {
			return nil, fail("wall actor does not match frame actor")
		}
		utc, err := EncodeTemporalInteger(w["utc_ns"])
		if err != nil {
			return nil, err
		}
		index, err := temporalBigInt(w["sample_index"], "wall.sample_index")
		if err != nil || index.Sign() < 0 {
			return nil, fail("wall sample_index must be non-negative")
		}
		si, _ := EncodeTemporalInteger(index)
		out["wall"] = Object{"actor_id": a, "utc_ns": utc, "sample_index": si}
	}

	if raw["causal"] == nil {
		out["causal"] = nil
	} else {
		c, err := temporalObject(raw["causal"], []string{"actor_id", "lamport", "vector"}, "frame.causal")
		if err != nil {
			return nil, err
		}
		a, err := temporalText(c["actor_id"], "causal.actor_id")
		if err != nil || a != actor {
			return nil, fail("causal actor does not match frame actor")
		}
		lamport, err := temporalBigInt(c["lamport"], "causal.lamport")
		if err != nil || lamport.Sign() < 0 {
			return nil, fail("causal Lamport value must be non-negative")
		}
		v, ok := c["vector"].(map[string]any)
		if !ok || len(v) == 0 {
			return nil, fail("causal vector must be a non-empty object")
		}
		actors := make([]string, 0, len(v))
		for k := range v {
			actors = append(actors, k)
		}
		sort.Strings(actors)
		entries := make([]any, 0, len(actors))
		own := false
		for _, vectorActor := range actors {
			if strings.TrimSpace(vectorActor) == "" {
				return nil, fail("causal vector actor is empty")
			}
			counter, err := temporalBigInt(v[vectorActor], "causal vector counter")
			if err != nil || counter.Sign() < 0 || counter.Cmp(lamport) > 0 {
				return nil, fail("causal vector counter must be non-negative and <= Lamport")
			}
			encoded, _ := EncodeTemporalInteger(counter)
			entries = append(entries, Object{"actor_id": vectorActor, "counter": encoded})
			if vectorActor == actor {
				own = true
			}
		}
		if !own {
			return nil, fail("causal vector must include its own actor")
		}
		l, _ := EncodeTemporalInteger(lamport)
		out["causal"] = Object{"actor_id": a, "lamport": l, "vector": entries}
	}

	if raw["scheduler"] == nil {
		out["scheduler"] = nil
	} else {
		s, err := temporalObject(raw["scheduler"], []string{"scheduler_id", "tick"}, "frame.scheduler")
		if err != nil {
			return nil, err
		}
		id, err := temporalText(s["scheduler_id"], "scheduler.scheduler_id")
		if err != nil {
			return nil, err
		}
		tick, err := temporalBigInt(s["tick"], "scheduler.tick")
		if err != nil || tick.Sign() < 0 {
			return nil, fail("scheduler tick must be non-negative")
		}
		t, _ := EncodeTemporalInteger(tick)
		out["scheduler"] = Object{"scheduler_id": id, "tick": t}
	}

	if raw["event_lambda"] == nil {
		out["event_lambda"] = nil
	} else {
		value, err := temporalBigInt(raw["event_lambda"], "event_lambda")
		if err != nil || value.Sign() < 0 {
			return nil, fail("event_lambda must be non-negative")
		}
		e, _ := EncodeTemporalInteger(value)
		out["event_lambda"] = e
	}

	if raw["chronon_phase"] == nil {
		out["chronon_phase"] = nil
	} else {
		phase, err := temporalArray(raw["chronon_phase"], "chronon_phase")
		if err != nil || len(phase) != 2 {
			return nil, fail("chronon_phase must be a pair")
		}
		real, err := temporalFloatInput(phase[0], "chronon_phase real")
		if err != nil {
			return nil, err
		}
		imaginary, err := temporalFloatInput(phase[1], "chronon_phase imaginary")
		if err != nil {
			return nil, err
		}
		if err := checkTemporalPhase(real, imaginary); err != nil {
			return nil, err
		}
		r, _ := EncodeTemporalBinary64(real)
		i, _ := EncodeTemporalBinary64(imaginary)
		out["chronon_phase"] = []any{r, i}
	}

	if raw["chemical_tau"] == nil {
		out["chemical_tau"] = nil
	} else {
		tau, err := temporalFloatInput(raw["chemical_tau"], "chemical_tau")
		if err != nil || tau < 0 {
			return nil, fail("chemical_tau must be finite and non-negative")
		}
		t, _ := EncodeTemporalBinary64(tau)
		out["chemical_tau"] = t
	}
	if _, err := CanonicalBytes(out); err != nil {
		return nil, err
	}
	return out, nil
}

func DecodeTemporalFrameV2(value any) (Object, error) {
	required := []string{"format", "schema", "numeric_profile", "actor_id", "monotonic", "wall", "causal", "scheduler", "event_lambda", "chronon_phase", "chemical_tau"}
	raw, err := exactFields(value, required, "temporal frame v0.2")
	if err != nil {
		return nil, err
	}
	if raw["format"] != TemporalFrameFormat || raw["schema"] != TemporalFrameSchema || raw["numeric_profile"] != TemporalNumericSchema {
		return nil, fail("temporal frame v2 format/schema/profile mismatch")
	}
	actor, err := temporalText(raw["actor_id"], "frame.actor_id")
	if err != nil {
		return nil, err
	}
	out := Object{"actor_id": actor}

	if raw["monotonic"] == nil {
		out["monotonic"] = nil
	} else {
		m, err := temporalObject(raw["monotonic"], []string{"actor_id", "segment", "elapsed_ns"}, "frame.monotonic")
		if err != nil {
			return nil, err
		}
		if m["actor_id"] != actor {
			return nil, fail("monotonic actor does not match frame actor")
		}
		s, err := DecodeTemporalInteger(m["segment"], temporalMinimumZero(), nil)
		if err != nil {
			return nil, err
		}
		e, err := DecodeTemporalInteger(m["elapsed_ns"], temporalMinimumZero(), nil)
		if err != nil {
			return nil, err
		}
		out["monotonic"] = Object{"actor_id": actor, "segment": s, "elapsed_ns": e}
	}

	if raw["wall"] == nil {
		out["wall"] = nil
	} else {
		w, err := temporalObject(raw["wall"], []string{"actor_id", "utc_ns", "sample_index"}, "frame.wall")
		if err != nil {
			return nil, err
		}
		if w["actor_id"] != actor {
			return nil, fail("wall actor does not match frame actor")
		}
		utc, err := DecodeTemporalInteger(w["utc_ns"], nil, nil)
		if err != nil {
			return nil, err
		}
		index, err := DecodeTemporalInteger(w["sample_index"], temporalMinimumZero(), nil)
		if err != nil {
			return nil, err
		}
		out["wall"] = Object{"actor_id": actor, "utc_ns": utc, "sample_index": index}
	}

	if raw["causal"] == nil {
		out["causal"] = nil
	} else {
		c, err := temporalObject(raw["causal"], []string{"actor_id", "lamport", "vector"}, "frame.causal")
		if err != nil {
			return nil, err
		}
		if c["actor_id"] != actor {
			return nil, fail("causal actor does not match frame actor")
		}
		lamport, err := DecodeTemporalInteger(c["lamport"], temporalMinimumZero(), nil)
		if err != nil {
			return nil, err
		}
		entries, err := temporalArray(c["vector"], "causal.vector")
		if err != nil || len(entries) == 0 {
			return nil, fail("causal vector must be a non-empty array")
		}
		vector := Object{}
		prior := ""
		own := false
		for i, entry := range entries {
			e, err := temporalObject(entry, []string{"actor_id", "counter"}, "causal vector entry")
			if err != nil {
				return nil, err
			}
			id, err := temporalText(e["actor_id"], "causal vector actor")
			if err != nil {
				return nil, err
			}
			if i > 0 && id <= prior {
				return nil, fail("causal vector actor IDs must be unique and sorted")
			}
			prior = id
			counter, err := DecodeTemporalInteger(e["counter"], temporalMinimumZero(), nil)
			if err != nil || counter.Cmp(lamport) > 0 {
				return nil, fail("causal vector counter must be <= Lamport")
			}
			vector[id] = counter
			if id == actor {
				own = true
			}
		}
		if !own {
			return nil, fail("causal vector must include its own actor")
		}
		out["causal"] = Object{"actor_id": actor, "lamport": lamport, "vector": vector}
	}

	if raw["scheduler"] == nil {
		out["scheduler"] = nil
	} else {
		s, err := temporalObject(raw["scheduler"], []string{"scheduler_id", "tick"}, "frame.scheduler")
		if err != nil {
			return nil, err
		}
		id, err := temporalText(s["scheduler_id"], "scheduler.scheduler_id")
		if err != nil {
			return nil, err
		}
		tick, err := DecodeTemporalInteger(s["tick"], temporalMinimumZero(), nil)
		if err != nil {
			return nil, err
		}
		out["scheduler"] = Object{"scheduler_id": id, "tick": tick}
	}

	if raw["event_lambda"] == nil {
		out["event_lambda"] = nil
	} else {
		n, err := DecodeTemporalInteger(raw["event_lambda"], temporalMinimumZero(), nil)
		if err != nil {
			return nil, err
		}
		out["event_lambda"] = n
	}

	if raw["chronon_phase"] == nil {
		out["chronon_phase"] = nil
	} else {
		phase, err := temporalArray(raw["chronon_phase"], "chronon_phase")
		if err != nil || len(phase) != 2 {
			return nil, fail("chronon_phase must contain two binary64 envelopes")
		}
		real, err := DecodeTemporalBinary64(phase[0])
		if err != nil {
			return nil, err
		}
		imaginary, err := DecodeTemporalBinary64(phase[1])
		if err != nil {
			return nil, err
		}
		if err := checkTemporalPhase(real, imaginary); err != nil {
			return nil, err
		}
		out["chronon_phase"] = []any{real, imaginary}
	}

	if raw["chemical_tau"] == nil {
		out["chemical_tau"] = nil
	} else {
		tau, err := DecodeTemporalBinary64(raw["chemical_tau"])
		if err != nil || tau < 0 {
			return nil, fail("chemical_tau must be finite and non-negative")
		}
		out["chemical_tau"] = tau
	}
	return out, nil
}

func EncodeOperationSpanV2(span Object) (Object, error) {
	fields := []string{"format", "schema", "attempt_id", "span_id", "operation_id", "clock_actor_id", "clock_segment_id", "monotonic_start_ns", "monotonic_end_ns", "elapsed_ns", "clock_status", "outcome", "exception_type", "context", "measurement_scope", "span_digest"}
	raw, err := exactFields(span, fields, "operation span")
	if err != nil {
		return nil, err
	}
	if raw["format"] != TemporalSpanFormat || (raw["schema"] != SpanSchema && raw["schema"] != TemporalSpanSchema) {
		return nil, fail("operation span format/source schema mismatch")
	}
	if _, ok := raw["context"].(map[string]any); !ok {
		return nil, fail("operation span context must be object")
	}
	start, err := temporalBigInt(raw["monotonic_start_ns"], "monotonic_start_ns")
	if err != nil || start.Sign() < 0 {
		return nil, fail("monotonic_start_ns must be non-negative")
	}
	end, err := temporalBigInt(raw["monotonic_end_ns"], "monotonic_end_ns")
	if err != nil || end.Sign() < 0 {
		return nil, fail("monotonic_end_ns must be non-negative")
	}
	var elapsed *big.Int
	if raw["elapsed_ns"] != nil {
		elapsed, err = temporalBigInt(raw["elapsed_ns"], "elapsed_ns")
		if err != nil || elapsed.Sign() < 0 {
			return nil, fail("elapsed_ns must be non-negative or null")
		}
	}
	switch raw["clock_status"] {
	case "measured":
		if end.Cmp(start) < 0 || elapsed == nil || new(big.Int).Sub(end, start).Cmp(elapsed) != 0 {
			return nil, fail("measured operation span endpoints and elapsed disagree")
		}
	case "regressed":
		if elapsed != nil {
			return nil, fail("regressed operation span elapsed must be null")
		}
	default:
		return nil, fail("unsupported operation span clock status")
	}
	out := Object{}
	for k, v := range raw {
		out[k] = v
	}
	out["schema"] = TemporalSpanSchema
	out["monotonic_start_ns"], _ = EncodeTemporalInteger(start)
	out["monotonic_end_ns"], _ = EncodeTemporalInteger(end)
	if elapsed == nil {
		out["elapsed_ns"] = nil
	} else {
		out["elapsed_ns"], _ = EncodeTemporalInteger(elapsed)
	}
	core := cloneWithout(out, "span_digest")
	digest, err := Digest(core)
	if err != nil {
		return nil, err
	}
	out["span_digest"] = digest
	return out, nil
}

func DecodeOperationSpanV2(value any) (Object, error) {
	fields := []string{"format", "schema", "attempt_id", "span_id", "operation_id", "clock_actor_id", "clock_segment_id", "monotonic_start_ns", "monotonic_end_ns", "elapsed_ns", "clock_status", "outcome", "exception_type", "context", "measurement_scope", "span_digest"}
	raw, err := exactFields(value, fields, "operation span v0.2")
	if err != nil {
		return nil, err
	}
	if raw["format"] != TemporalSpanFormat || raw["schema"] != TemporalSpanSchema {
		return nil, fail("operation span v2 format or schema mismatch")
	}
	core := cloneWithout(raw, "span_digest")
	digest, err := Digest(core)
	if err != nil {
		return nil, err
	}
	if digest != raw["span_digest"] {
		return nil, fail("operation span v2 digest mismatch")
	}
	start, err := DecodeTemporalInteger(raw["monotonic_start_ns"], temporalMinimumZero(), nil)
	if err != nil {
		return nil, err
	}
	end, err := DecodeTemporalInteger(raw["monotonic_end_ns"], temporalMinimumZero(), nil)
	if err != nil {
		return nil, err
	}
	var elapsed *big.Int
	if raw["elapsed_ns"] != nil {
		elapsed, err = DecodeTemporalInteger(raw["elapsed_ns"], temporalMinimumZero(), nil)
		if err != nil {
			return nil, err
		}
	}
	switch raw["clock_status"] {
	case "measured":
		if end.Cmp(start) < 0 || elapsed == nil || new(big.Int).Sub(end, start).Cmp(elapsed) != 0 {
			return nil, fail("measured operation span endpoints and elapsed disagree")
		}
	case "regressed":
		if elapsed != nil {
			return nil, fail("regressed operation span elapsed must be null")
		}
	default:
		return nil, fail("unsupported operation span clock status")
	}
	out := Object{}
	for k, v := range raw {
		out[k] = v
	}
	out["monotonic_start_ns"] = start
	out["monotonic_end_ns"] = end
	out["elapsed_ns"] = elapsed
	return out, nil
}
