package verifier

import (
	"bytes"
	"fmt"
	"os"
	"strings"
)

func vectorRelation(left, right map[string]any) (string, error) {
	actors := map[string]bool{}
	for k := range left {
		actors[k] = true
	}
	for k := range right {
		actors[k] = true
	}
	less, greater := false, false
	for actor := range actors {
		lv := uint64(0)
		rv := uint64(0)
		var err error
		if v, ok := left[actor]; ok {
			lv, err = uintValue(v, "left vector["+actor+"]", 0)
			if err != nil {
				return "", err
			}
		}
		if v, ok := right[actor]; ok {
			rv, err = uintValue(v, "right vector["+actor+"]", 0)
			if err != nil {
				return "", err
			}
		}
		if lv < rv {
			less = true
		}
		if lv > rv {
			greater = true
		}
	}
	if less && greater {
		return "concurrent", nil
	}
	if less {
		return "before", nil
	}
	if greater {
		return "after", nil
	}
	return "equal", nil
}

// VerifierIdentity is the current GitHub-hosted fifth-job identity captured by CI.
type VerifierIdentity struct{ Repository, RunID, RunAttempt, RunNumber, WorkflowRef, WorkflowSHA, GitRef, GitSHA, Job, RunnerName, RunnerOS, RunnerArch, RunnerEnvironment string }

func IdentityFromEnv() (VerifierIdentity, error) {
	get := func(k string) (string, error) {
		v := os.Getenv(k)
		if strings.TrimSpace(v) == "" {
			return "", fail("missing environment variable %s", k)
		}
		return v, nil
	}
	var i VerifierIdentity
	var err error
	pairs := []struct {
		k string
		p *string
	}{{"GITHUB_REPOSITORY", &i.Repository}, {"GITHUB_RUN_ID", &i.RunID}, {"GITHUB_RUN_ATTEMPT", &i.RunAttempt}, {"GITHUB_RUN_NUMBER", &i.RunNumber}, {"GITHUB_WORKFLOW_REF", &i.WorkflowRef}, {"GITHUB_WORKFLOW_SHA", &i.WorkflowSHA}, {"GITHUB_REF", &i.GitRef}, {"GITHUB_SHA", &i.GitSHA}, {"GITHUB_JOB", &i.Job}, {"RUNNER_NAME", &i.RunnerName}, {"RUNNER_OS", &i.RunnerOS}, {"RUNNER_ARCH", &i.RunnerArch}, {"RUNNER_ENVIRONMENT", &i.RunnerEnvironment}}
	for _, p := range pairs {
		*p.p, err = get(p.k)
		if err != nil {
			return i, err
		}
	}
	if i.Repository != Repository || i.Job != VerifierRole || i.WorkflowRef != WorkflowRef || i.GitRef != "refs/heads/main" || i.RunnerEnvironment != "github-hosted" {
		return i, fail("Go verifier must run as the GitHub-hosted %s job on main", VerifierRole)
	}
	return i, nil
}
func (i VerifierIdentity) ActorID() string {
	return fmt.Sprintf("%s#run-%s.attempt-%s.%s.%s", i.Repository, i.RunID, i.RunAttempt, VerifierRole, i.RunnerName)
}

func Reconstruct(source Object, sourceBytes []byte, receiver Object, receiverBytes []byte, identity VerifierIdentity) (Object, error) {
	cs, err := CanonicalBytes(source)
	if err != nil {
		return nil, err
	}
	if !bytes.Equal(append(cs, '\n'), sourceBytes) {
		return nil, fail("source record bytes are not canonical JSON plus LF")
	}
	cr, err := CanonicalBytes(receiver)
	if err != nil {
		return nil, err
	}
	if !bytes.Equal(append(cr, '\n'), receiverBytes) {
		return nil, fail("receiver record bytes are not canonical JSON plus LF")
	}
	s, err := validateRecord(source, "source_host")
	if err != nil {
		return nil, err
	}
	r, err := validateRecord(receiver, "receiver_host")
	if err != nil {
		return nil, err
	}
	sh := s["host"].(map[string]any)
	rh := r["host"].(map[string]any)
	shared := []string{"repository", "run_id", "run_attempt", "run_number", "workflow_ref", "workflow_sha", "git_ref", "git_sha"}
	for _, k := range shared {
		if sh[k] != rh[k] {
			return nil, fail("source and receiver differ in %s", k)
		}
	}
	for _, k := range shared {
		var value string
		switch k {
		case "repository":
			value = identity.Repository
		case "run_id":
			value = identity.RunID
		case "run_attempt":
			value = identity.RunAttempt
		case "run_number":
			value = identity.RunNumber
		case "workflow_ref":
			value = identity.WorkflowRef
		case "workflow_sha":
			value = identity.WorkflowSHA
		case "git_ref":
			value = identity.GitRef
		case "git_sha":
			value = identity.GitSHA
		}
		if sh[k] != value {
			return nil, fail("Go verifier differs from host records in %s", k)
		}
	}
	if sh["job"] == rh["job"] || sh["actor_id"] == rh["actor_id"] || sh["job"] == VerifierRole || rh["job"] == VerifierRole {
		return nil, fail("source, receiver, and Go verifier must have distinct jobs and actors")
	}
	sp := s["operation_span"].(map[string]any)
	rp := r["operation_span"].(map[string]any)
	payload := s["handoff_payload"].(map[string]any)
	w, err := exactFields(r["handoff_witness"], handoffFields, "receiver handoff witness")
	if err != nil {
		return nil, err
	}
	if err := digestWithout(w, "handoff_digest", "handoff witness digest"); err != nil {
		return nil, err
	}
	pf, _ := validateFrame(payload["sender_completion_frame"], "payload sender frame")
	wf, err := validateFrame(w["sender_completion_frame"], "witness sender frame")
	if err != nil {
		return nil, err
	}
	rf, err := validateFrame(w["receiver_start_frame"], "witness receiver frame")
	if err != nil {
		return nil, err
	}
	if !sameJSON(pf, s["temporal_frame"]) || !sameJSON(wf, pf) {
		return nil, fail("handoff witness does not preserve exact sender completion frame")
	}
	if !sameJSON(rf, r["temporal_frame"]) {
		return nil, fail("receiver record does not preserve exact receiver start frame")
	}
	pathID, err := textValue(payload["path_id"], "payload.path_id")
	if err != nil {
		return nil, err
	}
	attemptID, err := textValue(payload["attempt_id"], "payload.attempt_id")
	if err != nil {
		return nil, err
	}
	if w["path_id"] != pathID || w["attempt_id"] != attemptID || sp["attempt_id"] != attemptID || rp["attempt_id"] != attemptID {
		return nil, fail("handoff path/attempt mismatch")
	}
	if w["predecessor_span_digest"] != sp["span_digest"] || w["successor_span_digest"] != rp["span_digest"] || w["payload_digest"] != payload["payload_digest"] {
		return nil, fail("handoff endpoint or payload digest mismatch")
	}
	senderID := sh["actor_id"].(string)
	receiverID := rh["actor_id"].(string)
	if w["sender_actor_id"] != senderID || w["receiver_actor_id"] != receiverID || senderID == receiverID {
		return nil, fail("handoff actor identities mismatch")
	}
	sm := pf["monotonic"].(map[string]any)
	rm := rf["monotonic"].(map[string]any)
	sw := pf["causal"].(map[string]any)
	rw := rf["causal"].(map[string]any)
	ss, _ := uintValue(sm["segment"], "sender segment", 0)
	rs, _ := uintValue(rm["segment"], "receiver segment", 0)
	if fmt.Sprint(ss) != sp["clock_segment_id"] || fmt.Sprint(rs) != rp["clock_segment_id"] {
		return nil, fail("handoff frame and span clock segments differ")
	}
	smElapsed, _ := uintValue(sm["elapsed_ns"], "sender elapsed", 0)
	rStart, _ := uintValue(rm["elapsed_ns"], "receiver start", 0)
	spEnd, _ := uintValue(sp["monotonic_end_ns"], "source operation end", 0)
	rpStart, _ := uintValue(rp["monotonic_start_ns"], "receiver operation start", 0)
	if smElapsed < spEnd {
		return nil, fail("sender completion predates source operation end")
	}
	if rStart > rpStart {
		return nil, fail("receiver start follows receiver operation start")
	}
	if w["channel_id"] != RelayChannel {
		return nil, fail("handoff relay channel mismatch")
	}
	sent, err := uintValue(w["message_sequence"], "message sequence", 1)
	if err != nil {
		return nil, err
	}
	received, err := uintValue(w["received_sequence"], "received sequence", 1)
	if err != nil {
		return nil, err
	}
	if sent != received {
		return nil, fail("artifact relay sequences differ")
	}
	sv := sw["vector"].(map[string]any)
	rv := rw["vector"].(map[string]any)
	relation, err := vectorRelation(sv, rv)
	if err != nil {
		return nil, err
	}
	sl, _ := uintValue(sw["lamport"], "sender Lamport", 0)
	rl, _ := uintValue(rw["lamport"], "receiver Lamport", 0)
	if relation != "before" || sl >= rl {
		return nil, fail("receiver vector clock does not strictly follow sender completion")
	}
	if _, err := digestValue(r["source_record_sha256"], "receiver.source_record_sha256"); err != nil {
		return nil, err
	}
	if r["source_record_sha256"] != BytesDigest(sourceBytes) {
		return nil, fail("receiver does not bind exact source artifact bytes")
	}
	verifierActor := identity.ActorID()
	sourceReport := Object{"job": sh["job"], "actor_id": senderID, "runner_name": sh["runner_name"], "runner_os": sh["runner_os"], "runner_arch": sh["runner_arch"], "local_elapsed_ns": sp["elapsed_ns"], "span_digest": sp["span_digest"], "record_digest": s["record_digest"], "artifact_sha256": BytesDigest(sourceBytes)}
	receiverReport := Object{"job": rh["job"], "actor_id": receiverID, "runner_name": rh["runner_name"], "runner_os": rh["runner_os"], "runner_arch": rh["runner_arch"], "local_elapsed_ns": rp["elapsed_ns"], "span_digest": rp["span_digest"], "record_digest": r["record_digest"], "artifact_sha256": BytesDigest(receiverBytes), "source_artifact_sha256": BytesDigest(sourceBytes)}
	verifierReport := Object{"role": VerifierRole, "job": VerifierRole, "actor_id": verifierActor, "runner_name": identity.RunnerName, "runner_os": identity.RunnerOS, "runner_arch": identity.RunnerArch, "runner_environment": identity.RunnerEnvironment}
	checks := Object{"canonical_source_bytes": true, "canonical_receiver_bytes": true, "source_record_digest": true, "receiver_record_digest": true, "source_artifact_bytes_bound_by_receiver": true, "both_operation_span_digests": true, "host_actor_and_clock_segment_bindings": true, "sender_payload_digest_reconstructed": true, "receiver_handoff_digest_reconstructed": true, "handoff_endpoint_digests_and_attempt": true, "sender_and_receiver_frame_bindings": true, "local_monotonic_endpoint_constraints": true, "strict_vector_clock_happens_before": true, "artifact_relay_sequence_matches": true}
	causal := Object{"status": "reconstructed_from_independent_go_implementation", "edge_count": 1, "edge_basis": "message-linked vector-clock handoff and local monotonic endpoint checks", "relay_channel_id": w["channel_id"], "message_sequence": sent, "received_sequence": received, "vector_relation": relation, "sender_vector": sv, "receiver_vector": rv, "sender_lamport": sl, "receiver_lamport": rl, "predecessor_span_digest": sp["span_digest"], "successor_span_digest": rp["span_digest"], "payload_digest": payload["payload_digest"], "handoff_digest": w["handoff_digest"], "topological_order": []any{sp["span_digest"], rp["span_digest"]}}
	duration := Object{"source_local_elapsed_ns": sp["elapsed_ns"], "receiver_local_elapsed_ns": rp["elapsed_ns"], "combined_cross_host_elapsed_ns": nil, "status": "not_computed_independent_unaligned_clock_domains"}
	scope := []any{"This is an independently implemented content and causal-consistency reconstruction in Go; it is not a cryptographic attestation verifier.", "This job does not authenticate Sigstore signatures on the source or receiver artifacts. The primary Python verifier remains responsible for input-attestation verification.", "Host, runner, operating-system, architecture, actor, and job fields are checked as record claims and are not independent hardware identity attestations.", "The causal edge is reconstructed from participant-declared vector-clock frames, local monotonic endpoint constraints, and message-linked digests; a participant may still misrepresent its local operation.", "The channel sequence is the GitHub Actions artifact-relay contract, not E-CPU ReliableChannel or direct TCP/mTLS evidence.", "Local callable durations belong to separate monotonic clock domains; no combined cross-host duration or network latency is inferred.", "Canonical numeric values in this implementation are restricted to JSON integers. Decimal and exponent-form number tokens are rejected until the cross-language number canonicalization profile is standardized."}
	report := Object{"schema": ReportSchema, "path_id": pathID, "attempt_id": attemptID, "repository": identity.Repository, "run_id": identity.RunID, "run_attempt": identity.RunAttempt, "workflow_ref": identity.WorkflowRef, "workflow_sha": identity.WorkflowSHA, "source": sourceReport, "receiver": receiverReport, "cross_language_verifier": verifierReport, "checks": checks, "causal_reconstruction": causal, "duration": duration, "scope": scope}
	reportDigest, err := Digest(report)
	if err != nil {
		return nil, err
	}
	report["report_digest"] = reportDigest
	return report, nil
}
