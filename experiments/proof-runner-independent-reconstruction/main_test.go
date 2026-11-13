package main

import (
	"crypto/ed25519"
	"encoding/hex"
	"encoding/json"
	"os"
	"strings"
	"os/exec"
	"path/filepath"
	"testing"

	metadata "github.com/kier73/in-formation-space/bridges/observation-path/cross_language_verifier"
)

func fixturePaths(t *testing.T) Paths {
	t.Helper()
	root := t.TempDir()
	command := exec.Command("python3", "host_evidence.py", "fixture", "--out-dir", root)
	output, err := command.CombinedOutput()
	if err != nil {
		t.Fatalf("produce deterministic Python fixture: %v\n%s", err, output)
	}
	return Paths{
		Ledger: filepath.Join(root, "authority", "route-ledger.json"),
		Request: filepath.Join(root, "authority", "request.json"),
		AuthorityAttestation: filepath.Join(root, "authority", "authority-attestation.json"),
		AuthorityKey: filepath.Join(root, "authority", "authority-public-key.json"),
		AuthorityHistory: filepath.Join(root, "authority", "store-history.json"),
		AuthorityStore: filepath.Join(root, "authority", "authority-store-fixture.bin"),
		ProcessEvidence: filepath.Join(root, "authority", "process-evidence.json"),
		StaleOwnerAttempt: filepath.Join(root, "authority", "stale-owner-attempt.json"),
		Result: filepath.Join(root, "runner", "result.json"),
		Receipt: filepath.Join(root, "runner", "completion-receipt.json"),
		RunnerKey: filepath.Join(root, "runner", "runner-public-key.json"),
		VerifierHost: filepath.Join(root, "verifier-host.json"),
		SQLiteStoreReopenedVerified: false,
	}
}

func readMutable(t *testing.T, path string) object {
	t.Helper()
	value, _, err := metadata.ReadCanonicalFile(path)
	if err != nil {
		t.Fatalf("read %s: %v", path, err)
	}
	return value
}

func writeMutable(t *testing.T, path string, value object) {
	t.Helper()
	raw, err := metadata.CanonicalBytes(value)
	if err != nil {
		t.Fatalf("canonicalize %s: %v", path, err)
	}
	if err := os.WriteFile(path, append(raw, '\n'), 0o600); err != nil {
		t.Fatalf("write %s: %v", path, err)
	}
}

func rehashEvent(t *testing.T, event object) {
	t.Helper()
	value, err := digest(cloneWithout(event, "event_digest"))
	if err != nil {
		t.Fatalf("digest event: %v", err)
	}
	event["event_digest"] = value
}

func rehashLedger(t *testing.T, ledger object) {
	t.Helper()
	value, err := digest(cloneWithout(ledger, "ledger_digest"))
	if err != nil {
		t.Fatalf("digest ledger: %v", err)
	}
	ledger["ledger_digest"] = value
}

func TestThreeHostFixtureReconstructsInGo(t *testing.T) {
	paths := fixturePaths(t)
	report, err := Verify(paths)
	if err != nil {
		t.Fatalf("verify fixture: %v", err)
	}
	if report["status"] != "verified" {
		t.Fatalf("unexpected report status: %v", report["status"])
	}
	if report["key_provenance_verified_by_github"] != false {
		t.Fatal("offline fixture must not claim GitHub key attestations")
	}
	hostSeparation, ok := report["host_separation"].(object)
	if !ok || hostSeparation["distinct_jobs"] != true ||
		hostSeparation["distinct_actor_ids"] != true ||
		hostSeparation["combined_cross_host_elapsed_ns"] != nil {
		t.Fatalf("host separation or unknown duration was not preserved: %#v", report["host_separation"])
	}
}

func TestRejectsTamperedSQLiteIntermediateRevision(t *testing.T) {
	paths := fixturePaths(t)
	historyDocument := readMutable(t, paths.AuthorityHistory)
	rows := historyDocument["entries"].([]any)
	second := rows[1].(map[string]any)
	second["ledger_digest"] = strings.Repeat("0", 64)
	third := rows[2].(map[string]any)
	third["previous_ledger_digest"] = strings.Repeat("0", 64)
	writeMutable(t, paths.AuthorityHistory, historyDocument)
	if _, err := Verify(paths); err == nil {
		t.Fatal("altered intermediate SQLite revision was accepted")
	}
}

func TestRejectsTamperedStaleOwnerProcessEvidence(t *testing.T) {
	paths := fixturePaths(t)
	process := readMutable(t, paths.ProcessEvidence)
	phases := process["phases"].([]any)
	stale := phases[2].(map[string]any)
	stale["accepted"] = true
	writeMutable(t, paths.ProcessEvidence, process)
	if _, err := Verify(paths); err == nil {
		t.Fatal("process evidence claiming stale-owner acceptance was accepted")
	}
}

func TestRejectsTamperedSQLiteDatabaseBytes(t *testing.T) {
	paths := fixturePaths(t)
	file, err := os.OpenFile(paths.AuthorityStore, os.O_APPEND|os.O_WRONLY, 0)
	if err != nil {
		t.Fatalf("open SQLite fixture bytes: %v", err)
	}
	if _, err := file.Write([]byte("tamper")); err != nil {
		t.Fatalf("tamper SQLite fixture bytes: %v", err)
	}
	if err := file.Close(); err != nil {
		t.Fatalf("close tampered SQLite fixture: %v", err)
	}
	if _, err := Verify(paths); err == nil {
		t.Fatal("tampered SQLite authority database bytes were accepted")
	}
}

func TestRejectsChangedRunnerSignature(t *testing.T) {
	paths := fixturePaths(t)
	receipt := readMutable(t, paths.Receipt)
	signature := receipt["signature"].(string)
	replacement := "0"
	if signature[:1] == "0" {
		replacement = "1"
	}
	receipt["signature"] = replacement + signature[1:]
	writeMutable(t, paths.Receipt, receipt)
	if _, err := Verify(paths); err == nil {
		t.Fatal("tampered completion signature was accepted")
	}
}

func TestRejectsDifferentRunnerPublicKeyWithValidFingerprint(t *testing.T) {
	paths := fixturePaths(t)
	document := readMutable(t, paths.RunnerKey)
	seed := make([]byte, ed25519.SeedSize)
	for index := range seed {
		seed[index] = 0x33
	}
	public := ed25519.NewKeyFromSeed(seed).Public().(ed25519.PublicKey)
	document["public_key_hex"] = hex.EncodeToString(public)
	document["key_id"] = keyFingerprint(public)
	writeMutable(t, paths.RunnerKey, document)
	if _, err := Verify(paths); err == nil {
		t.Fatal("different runner key was accepted")
	}
}

func TestRejectsRehashedButSemanticallyBrokenAdmissionChain(t *testing.T) {
	paths := fixturePaths(t)
	ledger := readMutable(t, paths.Ledger)
	entries := ledger["entries"].([]any)
	admission := entries[2].(map[string]any)
	admissionDetails := admission["details"].(map[string]any)
	admissionDetails["request_sequence"] = json.Number("2")
	rehashEvent(t, admission)

	authorization := entries[3].(map[string]any)
	authorization["previous_event_digest"] = admission["event_digest"]
	rehashEvent(t, authorization)
	rehashLedger(t, ledger)
	writeMutable(t, paths.Ledger, ledger)

	// Keep the independent SQLite append index and every prefix digest
	// internally consistent, so the rejection must come from route semantics:
	// execution_authorized still names the old admission event digest.
	historyDocument := readMutable(t, paths.AuthorityHistory)
	rows := historyDocument["entries"].([]any)
	third := rows[2].(map[string]any)
	third["appended_event_digests"] = []any{admission["event_digest"]}
	third["ledger_digest"], _ = digest(object{
		"format": ledger["format"],
		"entries": entries[:3],
	})
	fourth := rows[3].(map[string]any)
	fourth["previous_ledger_digest"] = third["ledger_digest"]
	fourth["appended_event_digests"] = []any{authorization["event_digest"]}
	fourth["ledger_digest"], _ = digest(object{
		"format": ledger["format"],
		"entries": entries[:4],
	})
	writeMutable(t, paths.AuthorityHistory, historyDocument)

	if _, err := Verify(paths); err == nil {
		t.Fatal("fully re-hashed ledger and SQLite history with a stale admission binding was accepted")
	}
}

func TestRejectsSelfConsistentResultReplacement(t *testing.T) {
	paths := fixturePaths(t)
	result := readMutable(t, paths.Result)
	trace := result["proof_trace"].(map[string]any)
	transitions := trace["transitions"].([]any)
	transition := transitions[0].(map[string]any)
	transition["status"] = "rejected"
	result["result_digest"], _ = digest(cloneWithout(result, "result_digest"))
	writeMutable(t, paths.Result, result)

	if _, err := Verify(paths); err == nil {
		t.Fatal("replacement result with recomputed digest was accepted without a matching runner signature")
	}
}

func TestRejectsAuthoritySignatureTampering(t *testing.T) {
	paths := fixturePaths(t)
	attestation := readMutable(t, paths.AuthorityAttestation)
	signature := attestation["signature"].(string)
	replacement := "0"
	if signature[:1] == "0" {
		replacement = "1"
	}
	attestation["signature"] = replacement + signature[1:]
	writeMutable(t, paths.AuthorityAttestation, attestation)
	if _, err := Verify(paths); err == nil {
		t.Fatal("tampered authority signature was accepted")
	}
}

func TestRejectsVerifierIdentityReusingRunnerActor(t *testing.T) {
	paths := fixturePaths(t)
	verifier := readMutable(t, paths.VerifierHost)
	runner := readMutable(t, paths.RunnerKey)
	runnerHost := runner["host"].(map[string]any)
	verifierHost := verifier["host"].(map[string]any)
	verifierHost["actor_id"] = runnerHost["actor_id"]
	writeMutable(t, paths.VerifierHost, verifier)
	if _, err := Verify(paths); err == nil {
		t.Fatal("third-host actor reuse was accepted")
	}
}

func TestRejectsChangedRequestBeforeAcceptingResult(t *testing.T) {
	paths := fixturePaths(t)
	request := readMutable(t, paths.Request)
	request["query_label"] = "a different intention"
	writeMutable(t, paths.Request, request)
	if _, err := Verify(paths); err == nil {
		t.Fatal("request mutation was accepted")
	}
}
