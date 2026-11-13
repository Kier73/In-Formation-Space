package verifier

import (
	"errors"
	"os"
)

func WriteJSON(path string, value any) error {
	b, err := CanonicalBytes(value)
	if err != nil {
		return err
	}
	return os.WriteFile(path, append(b, '\n'), 0644)
}

func BuildPredicate(report Object, reportBytes []byte, id VerifierIdentity) (Object, error) {
	if report["schema"] != ReportSchema {
		return nil, fail("unsupported Go reconstruction report schema")
	}
	if err := digestWithout(report, "report_digest", "report_digest"); err != nil {
		return nil, err
	}
	vr, ok := report["cross_language_verifier"].(map[string]any)
	if !ok {
		return nil, fail("report is missing Go verifier identity")
	}
	expected := Object{"role": VerifierRole, "job": VerifierRole, "actor_id": id.ActorID(), "runner_name": id.RunnerName, "runner_os": id.RunnerOS, "runner_arch": id.RunnerArch, "runner_environment": id.RunnerEnvironment}
	if !sameJSON(vr, expected) {
		return nil, fail("report does not identify current Go verifier job")
	}
	source := report["source"].(map[string]any)
	receiver := report["receiver"].(map[string]any)
	causal := report["causal_reconstruction"].(map[string]any)
	return Object{"schema": PredicateSchema, "repository": id.Repository, "run_id": id.RunID, "run_attempt": id.RunAttempt, "workflow_ref": id.WorkflowRef, "workflow_sha": id.WorkflowSHA, "git_ref": id.GitRef, "git_sha": id.GitSHA, "job": VerifierRole, "runner_name": id.RunnerName, "runner_os": id.RunnerOS, "runner_arch": id.RunnerArch, "runner_environment": id.RunnerEnvironment, "actor_id": id.ActorID(), "report_sha256": BytesDigest(reportBytes), "report_digest": report["report_digest"], "source_record_sha256": source["artifact_sha256"], "receiver_record_sha256": receiver["artifact_sha256"], "path_id": report["path_id"], "causal_handoff_digest": causal["handoff_digest"]}, nil
}

// ValidateReportParity checks the evidence-bearing projection shared with the
// Python diverse verifier. It intentionally ignores verifier-specific metadata.
func ValidateReportParity(goReport, pythonReport Object) error {
	pairs := [][]string{{"path_id"}, {"attempt_id"}, {"repository"}, {"run_id"}, {"run_attempt"}, {"workflow_ref"}, {"workflow_sha"}}
	for _, p := range pairs {
		if !sameJSON(goReport[p[0]], pythonReport[p[0]]) {
			return fail("report mismatch in %s", p[0])
		}
	}
	for _, section := range []string{"source", "receiver"} {
		g, ok1 := goReport[section].(map[string]any)
		p, ok2 := pythonReport[section].(map[string]any)
		if !ok1 || !ok2 {
			return fail("report missing %s section", section)
		}
		for _, k := range []string{"job", "actor_id", "runner_name", "runner_os", "runner_arch", "local_elapsed_ns", "span_digest", "record_digest"} {
			if !sameJSON(g[k], p[k]) {
				return fail("report mismatch in %s.%s", section, k)
			}
		}
		if !sameJSON(g["artifact_sha256"], p["artifact_sha256"]) {
			return fail("report mismatch in %s.artifact_sha256", section)
		}
		if section == "receiver" && !sameJSON(g["source_artifact_sha256"], p["source_artifact_sha256"]) {
			return fail("report mismatch in receiver.source_artifact_sha256")
		}
	}
	gc, ok1 := goReport["causal_reconstruction"].(map[string]any)
	pc, ok2 := pythonReport["causal_reconstruction"].(map[string]any)
	if !ok1 || !ok2 {
		return errors.New("report causal reconstruction missing")
	}
	for _, k := range []string{"edge_count", "predecessor_span_digest", "successor_span_digest", "payload_digest", "handoff_digest", "relay_channel_id", "message_sequence", "received_sequence", "vector_relation", "sender_vector", "receiver_vector", "sender_lamport", "receiver_lamport", "topological_order"} {
		if !sameJSON(gc[k], pc[k]) {
			return fail("report mismatch in causal_reconstruction.%s", k)
		}
	}
	gd, _ := goReport["duration"].(map[string]any)
	pd, _ := pythonReport["duration"].(map[string]any)
	for _, k := range []string{"source_local_elapsed_ns", "receiver_local_elapsed_ns", "combined_cross_host_elapsed_ns", "status"} {
		if !sameJSON(gd[k], pd[k]) {
			return fail("report mismatch in duration.%s", k)
		}
	}
	return nil
}
