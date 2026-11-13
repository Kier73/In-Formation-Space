// Package verifier independently reconstructs IHP-001 evidence in Go.
// It intentionally uses only the Go standard library and does not invoke or
// import either Python verifier.
package verifier

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"math/big"
	"os"
	"regexp"
	"strings"
)

const (
	Repository       = "Kier73/In-Formation-Space"
	WorkflowPath     = ".github/workflows/independent-host-operation-path.yml"
	WorkflowRef      = Repository + "/" + WorkflowPath + "@refs/heads/main"
	RecordFormat     = "in-formation.independent-host-operation-record"
	RecordSchema     = "in-formation.independent-host-operation-record/0.1"
	SpanFormat       = "in-formation.operation-span"
	SpanSchema       = "in-formation.operation-span/0.1"
	PayloadSchema    = "in-formation.operation-path.handoff-payload/0.1"
	HandoffSchema    = "in-formation.operation-path.causal-handoff/0.1"
	RelayChannel     = "github-actions-artifact-relay/v1"
	ReportSchema     = "in-formation.cross-language-host-operation-report/0.1"
	PredicateSchema  = "in-formation.cross-language-host-operation-report-predicate/0.1"
	PredicateType    = "https://kier73.github.io/in-formation-space/cross-language-host-operation-report/v1"
	MeasurementScope = "Elapsed monotonic time between the recorder's immediately-before and immediately-after samples around one synchronous callable invocation; includes blocking within the call and excludes later work."
	VerifierRole     = "cross_language_verifier_host"
)

var (
	digestPattern  = regexp.MustCompile("^[0-9a-f]{64}$")
	integerPattern = regexp.MustCompile("^-?(0|[1-9][0-9]*)$")
)

type Object = map[string]any

type VerificationError struct{ Message string }

func (e *VerificationError) Error() string { return e.Message }
func fail(format string, args ...any) error {
	return &VerificationError{Message: fmt.Sprintf(format, args...)}
}

var recordFields = []string{"format", "schema", "role", "host", "operation_span", "temporal_frame", "handoff_payload", "source_record_sha256", "handoff_witness", "record_digest"}
var hostFields = []string{"role", "repository", "run_id", "run_attempt", "run_number", "workflow_ref", "workflow_sha", "git_ref", "git_sha", "job", "runner_name", "runner_os", "runner_arch", "runner_environment", "actor_id", "clock_segment_id"}
var spanFields = []string{"format", "schema", "attempt_id", "span_id", "operation_id", "clock_actor_id", "clock_segment_id", "monotonic_start_ns", "monotonic_end_ns", "elapsed_ns", "clock_status", "outcome", "exception_type", "context", "measurement_scope", "span_digest"}
var frameFields = []string{"actor_id", "monotonic", "wall", "causal", "scheduler", "event_lambda", "chronon_phase", "chemical_tau"}
var payloadFields = []string{"schema", "path_id", "attempt_id", "predecessor_span_digest", "sender_actor_id", "sender_completion_frame", "payload_digest"}
var handoffFields = []string{"schema", "path_id", "attempt_id", "predecessor_span_digest", "successor_span_digest", "channel_id", "message_sequence", "received_sequence", "sender_actor_id", "receiver_actor_id", "payload_digest", "sender_completion_frame", "receiver_start_frame", "handoff_digest"}

func DecodeObject(raw []byte) (Object, error) {
	dec := json.NewDecoder(bytes.NewReader(raw))
	dec.UseNumber()
	var value any
	if err := dec.Decode(&value); err != nil {
		return nil, fail("invalid JSON: %v", err)
	}
	if _, err := dec.Token(); err != io.EOF {
		return nil, fail("input must contain exactly one JSON value")
	}
	obj, ok := value.(map[string]any)
	if !ok {
		return nil, fail("top-level JSON value must be an object")
	}
	return obj, nil
}

// CanonicalBytes reproduces the IHP-001 Python canonical-JSON profile for the
// integer-valued evidence domain. Object keys are sorted, whitespace is omitted,
// UTF-8 is retained, and HTML characters are not escaped. Floating-point and
// exponent-form JSON number tokens are rejected rather than silently normalized
// differently by two runtimes.
func CanonicalBytes(value any) ([]byte, error) {
	if err := validateIntegerNumberDomain(value, "$"); err != nil {
		return nil, err
	}
	var buf bytes.Buffer
	enc := json.NewEncoder(&buf)
	enc.SetEscapeHTML(false)
	if err := enc.Encode(value); err != nil {
		return nil, fail("cannot encode canonical JSON: %v", err)
	}
	out := bytes.TrimSuffix(buf.Bytes(), []byte("\n"))
	// encoding/json always escapes these two Unicode separators; Python's
	// ensure_ascii=False leaves them as UTF-8, so restore the literal codepoints.
	out = bytes.ReplaceAll(out, []byte("\\u2028"), []byte("\u2028"))
	out = bytes.ReplaceAll(out, []byte("\\u2029"), []byte("\u2029"))
	return append([]byte(nil), out...), nil
}

func validateIntegerNumberDomain(value any, path string) error {
	switch v := value.(type) {
	case float32, float64:
		return fail("unsupported floating-point Go value at %s; use canonical integer JSON values", path)
	case json.Number:
		s := string(v)
		if !integerPattern.MatchString(s) || s == "-0" {
			return fail("unsupported non-integer or non-canonical JSON number at %s: %q; IHP-004 currently accepts integer JSON numbers only", path, s)
		}
		if _, ok := new(big.Int).SetString(s, 10); !ok {
			return fail("invalid integer at %s", path)
		}
	case map[string]any:
		for k, item := range v {
			if err := validateIntegerNumberDomain(item, path+"."+k); err != nil {
				return err
			}
		}
	case []any:
		for i, item := range v {
			if err := validateIntegerNumberDomain(item, fmt.Sprintf("%s[%d]", path, i)); err != nil {
				return err
			}
		}
	}
	return nil
}

func Digest(value any) (string, error) {
	b, err := CanonicalBytes(value)
	if err != nil {
		return "", err
	}
	sum := sha256.Sum256(b)
	return hex.EncodeToString(sum[:]), nil
}
func BytesDigest(value []byte) string { sum := sha256.Sum256(value); return hex.EncodeToString(sum[:]) }

func ReadCanonicalFile(path string) (Object, []byte, error) {
	raw, err := os.ReadFile(path)
	if err != nil {
		return nil, nil, err
	}
	if !bytes.HasSuffix(raw, []byte("\n")) || bytes.HasSuffix(raw, []byte("\n\n")) {
		return nil, nil, fail("%s must end in exactly one LF", path)
	}
	obj, err := DecodeObject(bytes.TrimSuffix(raw, []byte("\n")))
	if err != nil {
		return nil, nil, err
	}
	canonical, err := CanonicalBytes(obj)
	if err != nil {
		return nil, nil, err
	}
	if !bytes.Equal(append(canonical, '\n'), raw) {
		return nil, nil, fail("%s is not canonical JSON plus one LF", path)
	}
	return obj, raw, nil
}

func exactFields(value any, fields []string, label string) (Object, error) {
	obj, ok := value.(map[string]any)
	if !ok {
		return nil, fail("%s must be an object", label)
	}
	if len(obj) != len(fields) {
		return nil, fail("%s must contain exactly fields %v", label, fields)
	}
	allowed := make(map[string]bool, len(fields))
	for _, f := range fields {
		allowed[f] = true
	}
	for k := range obj {
		if !allowed[k] {
			return nil, fail("%s contains unexpected field %q", label, k)
		}
	}
	for _, f := range fields {
		if _, ok := obj[f]; !ok {
			return nil, fail("%s is missing field %q", label, f)
		}
	}
	return obj, nil
}
func textValue(v any, label string) (string, error) {
	s, ok := v.(string)
	if !ok || strings.TrimSpace(s) == "" || strings.ContainsRune(s, '\x00') {
		return "", fail("%s must be non-empty text without NUL", label)
	}
	return s, nil
}
func uintValue(v any, label string, min uint64) (uint64, error) {
	n, ok := v.(json.Number)
	if !ok {
		return 0, fail("%s must be an integer >= %d", label, min)
	}
	i, ok := new(big.Int).SetString(string(n), 10)
	if !ok || i.Sign() < 0 || !i.IsUint64() || i.Uint64() < min {
		return 0, fail("%s must be an integer >= %d", label, min)
	}
	return i.Uint64(), nil
}
func intValue(v any, label string) (int64, error) {
	n, ok := v.(json.Number)
	if !ok {
		return 0, fail("%s must be an integer", label)
	}
	i, ok := new(big.Int).SetString(string(n), 10)
	if !ok || !i.IsInt64() {
		return 0, fail("%s must be an int64", label)
	}
	return i.Int64(), nil
}
func digestValue(v any, label string) (string, error) {
	s, err := textValue(v, label)
	if err != nil {
		return "", err
	}
	if !digestPattern.MatchString(s) {
		return "", fail("%s must be a lowercase SHA-256 digest", label)
	}
	return s, nil
}
func digestWithout(obj Object, omit string, label string) error {
	core := make(Object, len(obj)-1)
	for k, v := range obj {
		if k != omit {
			core[k] = v
		}
	}
	got, err := Digest(core)
	if err != nil {
		return err
	}
	expected, err := digestValue(obj[omit], label)
	if err != nil {
		return err
	}
	if got != expected {
		return fail("%s does not match object contents", label)
	}
	return nil
}
func cloneWithout(obj Object, omit string) Object {
	c := make(Object, len(obj)-1)
	for k, v := range obj {
		if k != omit {
			c[k] = v
		}
	}
	return c
}
func sameJSON(a, b any) bool {
	x, e1 := CanonicalBytes(a)
	y, e2 := CanonicalBytes(b)
	return e1 == nil && e2 == nil && bytes.Equal(x, y)
}
