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
	"sort"
	"strconv"
	"strings"
	"unicode/utf8"
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

// CanonicalBytes implements the shared canonical metadata v1 profile:
// ASCII object keys sort bytewise, whitespace is omitted, strings are UTF-8,
// HTML characters are not escaped, and only interoperable safe integers are
// accepted. Floating-point and noncanonical numeric tokens are rejected.
// CanonicalBytes implements the shared canonical metadata v1 profile. It
// writes strings directly rather than rewriting encoded byte sequences, which
// keeps literal "\u2028" text distinct from the U+2028 code point.
func CanonicalBytes(value any) ([]byte, error) {
	if err := validateIntegerNumberDomain(value, "$"); err != nil {
		return nil, err
	}
	var buf bytes.Buffer
	if err := appendCanonicalJSON(&buf, value); err != nil {
		return nil, err
	}
	return buf.Bytes(), nil
}

func appendCanonicalString(buf *bytes.Buffer, value string) {
	buf.WriteByte('"')
	for _, r := range value {
		switch r {
		case '"':
			buf.WriteString("\\\"")
		case '\\':
			buf.WriteString("\\\\")
		case '\b':
			buf.WriteString("\\b")
		case '\f':
			buf.WriteString("\\f")
		case '\n':
			buf.WriteString("\\n")
		case '\r':
			buf.WriteString("\\r")
		case '\t':
			buf.WriteString("\\t")
		default:
			if r < 0x20 {
				fmt.Fprintf(buf, "\\u%04x", r)
			} else {
				buf.WriteRune(r)
			}
		}
	}
	buf.WriteByte('"')
}

func appendCanonicalJSON(buf *bytes.Buffer, value any) error {
	switch v := value.(type) {
	case nil:
		buf.WriteString("null")
	case bool:
		if v {
			buf.WriteString("true")
		} else {
			buf.WriteString("false")
		}
	case string:
		appendCanonicalString(buf, v)
	case json.Number:
		buf.WriteString(string(v))
	case int:
		buf.Write(strconv.AppendInt(nil, int64(v), 10))
	case int8:
		buf.Write(strconv.AppendInt(nil, int64(v), 10))
	case int16:
		buf.Write(strconv.AppendInt(nil, int64(v), 10))
	case int32:
		buf.Write(strconv.AppendInt(nil, int64(v), 10))
	case int64:
		buf.Write(strconv.AppendInt(nil, v, 10))
	case uint:
		buf.Write(strconv.AppendUint(nil, uint64(v), 10))
	case uint8:
		buf.Write(strconv.AppendUint(nil, uint64(v), 10))
	case uint16:
		buf.Write(strconv.AppendUint(nil, uint64(v), 10))
	case uint32:
		buf.Write(strconv.AppendUint(nil, uint64(v), 10))
	case uint64:
		buf.Write(strconv.AppendUint(nil, v, 10))
	case map[string]any:
		keys := make([]string, 0, len(v))
		for key := range v {
			keys = append(keys, key)
		}
		sort.Strings(keys)
		buf.WriteByte('{')
		for index, key := range keys {
			if index > 0 {
				buf.WriteByte(',')
			}
			appendCanonicalString(buf, key)
			buf.WriteByte(':')
			if err := appendCanonicalJSON(buf, v[key]); err != nil {
				return err
			}
		}
		buf.WriteByte('}')
	case []any:
		buf.WriteByte('[')
		for index, item := range v {
			if index > 0 {
				buf.WriteByte(',')
			}
			if err := appendCanonicalJSON(buf, item); err != nil {
				return err
			}
		}
		buf.WriteByte(']')
	case []string:
		buf.WriteByte('[')
		for index, item := range v {
			if index > 0 {
				buf.WriteByte(',')
			}
			appendCanonicalString(buf, item)
		}
		buf.WriteByte(']')
	default:
		return fail("canonical metadata contains unsupported value %T", value)
	}
	return nil
}

const maxSafeInteger = int64(1<<53 - 1)

func validateUnicodeScalarString(value, path string) error {
	if !utf8.ValidString(value) {
		return fail("%s contains invalid Unicode scalar data", path)
	}
	for _, r := range value {
		if r >= 0xd800 && r <= 0xdfff {
			return fail("%s contains a non-scalar Unicode surrogate", path)
		}
	}
	return nil
}

func validateSafeInteger(value *big.Int, path string) error {
	limit := big.NewInt(maxSafeInteger)
	negativeLimit := new(big.Int).Neg(new(big.Int).Set(limit))
	if value.Cmp(negativeLimit) < 0 || value.Cmp(limit) > 0 {
		return fail("%s is outside the canonical metadata safe-integer range", path)
	}
	return nil
}

func validateIntegerNumberDomain(value any, path string) error {
	switch v := value.(type) {
	case nil, bool:
		return nil
	case string:
		return validateUnicodeScalarString(v, path)
	case float32, float64:
		return fail("%s floating-point values are not supported by canonical metadata v1", path)
	case json.Number:
		s := string(v)
		if !integerPattern.MatchString(s) || s == "-0" {
			return fail("%s must be a canonical safe-integer token, got %q", path, s)
		}
		integer, ok := new(big.Int).SetString(s, 10)
		if !ok {
			return fail("%s contains an invalid integer", path)
		}
		return validateSafeInteger(integer, path)
	case int:
		return validateSafeInteger(big.NewInt(int64(v)), path)
	case int8:
		return validateSafeInteger(big.NewInt(int64(v)), path)
	case int16:
		return validateSafeInteger(big.NewInt(int64(v)), path)
	case int32:
		return validateSafeInteger(big.NewInt(int64(v)), path)
	case int64:
		return validateSafeInteger(big.NewInt(v), path)
	case uint:
		return validateSafeInteger(new(big.Int).SetUint64(uint64(v)), path)
	case uint8:
		return validateSafeInteger(new(big.Int).SetUint64(uint64(v)), path)
	case uint16:
		return validateSafeInteger(new(big.Int).SetUint64(uint64(v)), path)
	case uint32:
		return validateSafeInteger(new(big.Int).SetUint64(uint64(v)), path)
	case uint64:
		return validateSafeInteger(new(big.Int).SetUint64(v), path)
	case map[string]any:
		for k, item := range v {
			if err := validateUnicodeScalarString(k, path+" object key"); err != nil {
				return err
			}
			for i := 0; i < len(k); i++ {
				if k[i] > 0x7f {
					return fail("%s object keys must be ASCII for canonical metadata v1", path)
				}
			}
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
	case []string:
		for i, item := range v {
			if err := validateUnicodeScalarString(item, fmt.Sprintf("%s[%d]", path, i)); err != nil {
				return err
			}
		}
	default:
		return fail("%s contains a value unsupported by canonical metadata v1 (%T)", path, value)
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
