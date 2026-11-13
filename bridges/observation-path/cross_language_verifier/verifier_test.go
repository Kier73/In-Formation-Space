package verifier

import (
	"bytes"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

const fixtureDir = "testdata/ihp-001-run-43360810370"

func fixture(t *testing.T, name string) (Object, []byte) {
	t.Helper()
	obj, raw, err := ReadCanonicalFile(filepath.Join(fixtureDir, name))
	if err != nil {
		t.Fatalf("read fixture %s: %v", name, err)
	}
	return obj, raw
}

func testIdentity(t *testing.T, source Object) VerifierIdentity {
	t.Helper()
	host := source["host"].(map[string]any)
	return VerifierIdentity{
		Repository:        host["repository"].(string),
		RunID:             host["run_id"].(string),
		RunAttempt:        host["run_attempt"].(string),
		RunNumber:         host["run_number"].(string),
		WorkflowRef:       host["workflow_ref"].(string),
		WorkflowSHA:       host["workflow_sha"].(string),
		GitRef:            host["git_ref"].(string),
		GitSHA:            host["git_sha"].(string),
		Job:               VerifierRole,
		RunnerName:        "Go conformance fixture runner",
		RunnerOS:          "Linux",
		RunnerArch:        "X64",
		RunnerEnvironment: "github-hosted",
	}
}

func cloneObject(t *testing.T, value Object) Object {
	t.Helper()
	encoded, err := CanonicalBytes(value)
	if err != nil {
		t.Fatal(err)
	}
	clone, err := DecodeObject(encoded)
	if err != nil {
		t.Fatal(err)
	}
	return clone
}

func reseal(t *testing.T, object Object, digestField string) {
	t.Helper()
	digest, err := Digest(cloneWithout(object, digestField))
	if err != nil {
		t.Fatal(err)
	}
	object[digestField] = digest
}

func artifactBytes(t *testing.T, object Object) []byte {
	t.Helper()
	encoded, err := CanonicalBytes(object)
	if err != nil {
		t.Fatal(err)
	}
	return append(encoded, '\n')
}

func TestLiveIHP001RecordsReconstructAndMatchPythonDiverseReport(t *testing.T) {
	source, sourceBytes := fixture(t, "host-a.json")
	receiver, receiverBytes := fixture(t, "host-b.json")
	pythonReport, _, err := ReadCanonicalFile(filepath.Join(fixtureDir, "diverse-report.json"))
	if err != nil {
		t.Fatal(err)
	}

	if got := BytesDigest(sourceBytes); got != "e238d820e2ee77863c4f8bc312ed639a47c47d2e7b5607da1951d1a6717f8856" {
		t.Fatalf("source artifact digest = %s", got)
	}
	if got := BytesDigest(receiverBytes); got != "37d4fce52c56d20f2bb0f0a58534d5ba92b21a391cc73d6d99d5226cb279e069" {
		t.Fatalf("receiver artifact digest = %s", got)
	}
	if source["record_digest"] != "3b9195df4797e106ab3408ca55a832d5e5d142b7a28fcd5d2b8c1d8c775895df" {
		t.Fatal("source fixture record digest changed")
	}
	if receiver["record_digest"] != "494795bf17a1927fc27fa3e4a6a1e32ea82e6bab1848a7751bb5d67e1c47100d" {
		t.Fatal("receiver fixture record digest changed")
	}

	report, err := Reconstruct(source, sourceBytes, receiver, receiverBytes, testIdentity(t, source))
	if err != nil {
		t.Fatal(err)
	}
	causal := report["causal_reconstruction"].(map[string]any)
	if causal["handoff_digest"] != "1a7155a5450d7ba07a783f54db3639ec7d451b6712419ebd5403dec251697e7e" {
		t.Fatal("Go handoff digest differs from preserved live evidence")
	}
	if causal["vector_relation"] != "before" || causal["edge_count"] != 1 {
		t.Fatalf("unexpected causal reconstruction: %#v", causal)
	}
	if err := ValidateReportParity(report, pythonReport); err != nil {
		t.Fatalf("Go and Python evidence projections differ: %v", err)
	}
}

func TestCanonicalBytesMatchPythonUTF8AndSortedObjectProfile(t *testing.T) {
	value := Object{
		"z":         "<>&",
		"a":         "café",
		"line":      "a\nb",
		"separator": "left\u2028right",
	}
	got, err := CanonicalBytes(value)
	if err != nil {
		t.Fatal(err)
	}
	want := []byte("{\"a\":\"café\",\"line\":\"a\\nb\",\"separator\":\"left\u2028right\",\"z\":\"<>&\"}")
	if !bytes.Equal(got, want) {
		t.Fatalf("canonical JSON mismatch\n got: %s\nwant: %s", got, want)
	}
}

func TestDecimalJSONNumberIsRejectedUntilPortableNumberProfileExists(t *testing.T) {
	value, err := DecodeObject([]byte("{\"value\":1.25}"))
	if err != nil {
		t.Fatal(err)
	}
	if _, err := CanonicalBytes(value); err == nil || !strings.Contains(err.Error(), "integer JSON numbers only") {
		t.Fatalf("expected an explicit unsupported-number error, got %v", err)
	}
}

func TestRecordDigestMutationIsRejected(t *testing.T) {
	source, _ := fixture(t, "host-a.json")
	receiver, receiverBytes := fixture(t, "host-b.json")
	changed := cloneObject(t, source)
	changed["host"].(map[string]any)["runner_os"] = "InventedOS"
	_, err := Reconstruct(changed, artifactBytes(t, changed), receiver, receiverBytes, testIdentity(t, source))
	if err == nil || !strings.Contains(err.Error(), "record_digest") {
		t.Fatalf("expected stale source record digest rejection, got %v", err)
	}
}

func TestPayloadDigestMutationIsRejectedAfterRecordReseal(t *testing.T) {
	source, _ := fixture(t, "host-a.json")
	receiver, receiverBytes := fixture(t, "host-b.json")
	changed := cloneObject(t, source)
	changed["handoff_payload"].(map[string]any)["path_id"] = "another-path"
	reseal(t, changed["handoff_payload"].(map[string]any), "payload_digest")
	reseal(t, changed, "record_digest")
	_, err := Reconstruct(changed, artifactBytes(t, changed), receiver, receiverBytes, testIdentity(t, source))
	if err == nil || !strings.Contains(err.Error(), "predecessor span") && !strings.Contains(err.Error(), "attempt") {
		t.Fatalf("expected altered payload binding to be rejected, got %v", err)
	}
}

func TestReceiverMustBindExactSourceArtifactBytes(t *testing.T) {
	source, sourceBytes := fixture(t, "host-a.json")
	receiver, _ := fixture(t, "host-b.json")
	changed := cloneObject(t, receiver)
	changed["source_record_sha256"] = strings.Repeat("f", 64)
	reseal(t, changed, "record_digest")
	_, err := Reconstruct(source, sourceBytes, changed, artifactBytes(t, changed), testIdentity(t, source))
	if err == nil || !strings.Contains(err.Error(), "exact source artifact bytes") {
		t.Fatalf("expected source artifact binding rejection, got %v", err)
	}
}

func TestConcurrentVectorClocksAreNotPromotedToCausalEdge(t *testing.T) {
	source, sourceBytes := fixture(t, "host-a.json")
	receiver, _ := fixture(t, "host-b.json")
	changed := cloneObject(t, receiver)
	host := changed["host"].(map[string]any)
	receiverActor := host["actor_id"].(string)
	frame := changed["temporal_frame"].(map[string]any)
	causal := frame["causal"].(map[string]any)
	causal["lamport"] = json.Number("1")
	causal["vector"] = Object{receiverActor: json.Number("1")}
	witness := changed["handoff_witness"].(map[string]any)
	witness["receiver_start_frame"] = cloneObject(t, frame)
	reseal(t, witness, "handoff_digest")
	reseal(t, changed, "record_digest")
	_, err := Reconstruct(source, sourceBytes, changed, artifactBytes(t, changed), testIdentity(t, source))
	if err == nil || !strings.Contains(err.Error(), "does not strictly follow") {
		t.Fatalf("expected concurrent vector-clock rejection, got %v", err)
	}
}

func TestCrossRunReceiverIsRejectedAfterRecordReseal(t *testing.T) {
	source, sourceBytes := fixture(t, "host-a.json")
	receiver, _ := fixture(t, "host-b.json")
	changed := cloneObject(t, receiver)
	changed["host"].(map[string]any)["run_attempt"] = "2"
	reseal(t, changed, "record_digest")
	_, err := Reconstruct(source, sourceBytes, changed, artifactBytes(t, changed), testIdentity(t, source))
	if err == nil || !strings.Contains(err.Error(), "run_attempt") {
		t.Fatalf("expected run-attempt mismatch rejection, got %v", err)
	}
}

func TestNonCanonicalArtifactBytesAreRejected(t *testing.T) {
	source, sourceBytes := fixture(t, "host-a.json")
	receiver, receiverBytes := fixture(t, "host-b.json")
	bad := append([]byte(nil), sourceBytes...)
	bad = bytes.TrimSuffix(bad, []byte("\n"))
	bad = append(bad, ' ', '\n')
	_, err := Reconstruct(source, bad, receiver, receiverBytes, testIdentity(t, source))
	if err == nil || !strings.Contains(err.Error(), "canonical JSON") {
		t.Fatalf("expected noncanonical input rejection, got %v", err)
	}
}

func TestReportPredicateBindsExactReportBytesAndJobIdentity(t *testing.T) {
	source, sourceBytes := fixture(t, "host-a.json")
	receiver, receiverBytes := fixture(t, "host-b.json")
	identity := testIdentity(t, source)
	report, err := Reconstruct(source, sourceBytes, receiver, receiverBytes, identity)
	if err != nil {
		t.Fatal(err)
	}
	path := filepath.Join(t.TempDir(), "report.json")
	if err := WriteJSON(path, report); err != nil {
		t.Fatal(err)
	}
	reportBytes, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	parsed, _, err := ReadCanonicalFile(path)
	if err != nil {
		t.Fatal(err)
	}
	predicate, err := BuildPredicate(parsed, reportBytes, identity)
	if err != nil {
		t.Fatal(err)
	}
	if predicate["report_sha256"] != BytesDigest(reportBytes) {
		t.Fatal("predicate does not bind exact report bytes")
	}
	if predicate["job"] != VerifierRole {
		t.Fatal("predicate does not bind cross-language verifier job")
	}
	if outputDir := os.Getenv("IHP004_TEST_OUTPUT_DIR"); outputDir != "" {
		if err := os.MkdirAll(outputDir, 0755); err != nil {
			t.Fatal(err)
		}
		if err := WriteJSON(filepath.Join(outputDir, "report.json"), parsed); err != nil {
			t.Fatal(err)
		}
		if err := WriteJSON(filepath.Join(outputDir, "predicate.json"), predicate); err != nil {
			t.Fatal(err)
		}
	}
}

func TestIdentityActorIsDistinctAndStable(t *testing.T) {
	id := VerifierIdentity{Repository: Repository, RunID: "42", RunAttempt: "2", Job: VerifierRole, RunnerName: "go-runner"}
	want := fmt.Sprintf("%s#run-42.attempt-2.%s.go-runner", Repository, VerifierRole)
	if id.ActorID() != want {
		t.Fatalf("actor ID = %q, want %q", id.ActorID(), want)
	}
}
