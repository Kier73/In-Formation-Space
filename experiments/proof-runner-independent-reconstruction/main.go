package main

import (
	"crypto/ed25519"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"strconv"
	"strings"

	metadata "github.com/kier73/in-formation-space/bridges/observation-path/cross_language_verifier"
)

const (
	ledgerFormat = "in-formation.proof-action-route-ledger/0.1"
	authorityAttestationFormat = "in-formation.proof-action-route-ledger-attestation/0.1"
	requestFormat = "in-formation.proof-action-request/0.1"
	resultFormat = "in-formation.proof-action-result/0.1"
	receiptFormat = "in-formation.proof-runner-completion-receipt/0.1"
	keyFormat = "in-formation.proof-runner-participant-key/0.1"
	verifierHostFormat = "in-formation.proof-runner-verifier-host/0.1"
	reportFormat = "in-formation.proof-runner-independent-reconstruction-report/0.1"
)

type object = map[string]any

type Paths struct {
	Ledger, Request, AuthorityAttestation, AuthorityKey string
	Result, Receipt, RunnerKey, VerifierHost string
	KeyAttestationsVerified bool
}

type participant struct {
	ID string
	Role string
	KeyID string
	PublicKey ed25519.PublicKey
	Host object
}

type activeRoute struct {
	EpochID string
	EpochNumber int64
	Route object
	RouteDigest string
	OwnerID string
	OwnerGeneration int64
}

type admission struct {
	EventDigest string
	RequestDigest string
	RequestSequence int64
}

func fail(format string, args ...any) error {
	return fmt.Errorf(format, args...)
}

func readObject(path string) (object, error) {
	value, _, err := metadata.ReadCanonicalFile(path)
	if err != nil {
		return nil, err
	}
	return value, nil
}

func writeObject(path string, value object) error {
	raw, err := metadata.CanonicalBytes(value)
	if err != nil {
		return err
	}
	if err := os.MkdirAll(dirName(path), 0o755); err != nil {
		return err
	}
	return os.WriteFile(path, append(raw, '\n'), 0o644)
}

func dirName(path string) string {
	index := strings.LastIndex(path, string(os.PathSeparator))
	if index < 0 {
		return "."
	}
	if index == 0 {
		return string(os.PathSeparator)
	}
	return path[:index]
}

func asObject(value any, label string) (object, error) {
	result, ok := value.(map[string]any)
	if !ok {
		return nil, fail("%s must be an object", label)
	}
	return result, nil
}

func asArray(value any, label string) ([]any, error) {
	result, ok := value.([]any)
	if !ok {
		return nil, fail("%s must be an array", label)
	}
	return result, nil
}

func textValue(value any, label string) (string, error) {
	result, ok := value.(string)
	if !ok || strings.TrimSpace(result) == "" || strings.ContainsRune(result, '\x00') {
		return "", fail("%s must be non-empty text without NUL", label)
	}
	return result, nil
}

func validGitSHA(value any) bool {
	s, ok := value.(string)
	if !ok || len(s) != 40 || strings.ToLower(s) != s {
		return false
	}
	_, err := hex.DecodeString(s)
	return err == nil
}

func integerValue(value any, label string, minimum int64) (int64, error) {
	number, ok := value.(json.Number)
	if !ok {
		return 0, fail("%s must be an integer >= %d", label, minimum)
	}
	result, err := strconv.ParseInt(string(number), 10, 64)
	if err != nil || result < minimum {
		return 0, fail("%s must be an integer >= %d", label, minimum)
	}
	return result, nil
}

func sha256Value(value any, label string) (string, error) {
	result, err := textValue(value, label)
	if err != nil {
		return "", err
	}
	if len(result) != 64 {
		return "", fail("%s must be a lowercase SHA-256 digest", label)
	}
	if _, err := hex.DecodeString(result); err != nil || strings.ToLower(result) != result {
		return "", fail("%s must be a lowercase SHA-256 digest", label)
	}
	return result, nil
}

func exactFields(value object, fields ...string) error {
	if len(value) != len(fields) {
		return fail("object has %d fields; expected exactly %d", len(value), len(fields))
	}
	for _, field := range fields {
		if _, ok := value[field]; !ok {
			return fail("object is missing required field %q", field)
		}
	}
	return nil
}

func cloneWithout(value object, excluded ...string) object {
	skip := make(map[string]bool, len(excluded))
	for _, key := range excluded {
		skip[key] = true
	}
	core := make(object, len(value)-len(skip))
	for key, member := range value {
		if !skip[key] {
			core[key] = member
		}
	}
	return core
}

func digest(value any) (string, error) {
	return metadata.Digest(value)
}

func keyFingerprint(raw []byte) string {
	sum := sha256.Sum256(raw)
	return "sha256:" + hex.EncodeToString(sum[:])
}

func validateRoute(value any) (object, string, error) {
	route, err := asObject(value, "event.route")
	if err != nil {
		return nil, "", err
	}
	if err := exactFields(route, "host_id", "worker_id", "request_channel", "result_channel", "policy"); err != nil {
		return nil, "", fail("route fields are invalid: %v", err)
	}
	host, err := textValue(route["host_id"], "route.host_id")
	if err != nil { return nil, "", err }
	worker, err := textValue(route["worker_id"], "route.worker_id")
	if err != nil { return nil, "", err }
	requestChannel, err := textValue(route["request_channel"], "route.request_channel")
	if err != nil { return nil, "", err }
	resultChannel, err := textValue(route["result_channel"], "route.result_channel")
	if err != nil { return nil, "", err }
	if host == worker || requestChannel == resultChannel {
		return nil, "", fail("route endpoint identities and channel names must differ")
	}
	policy, err := asObject(route["policy"], "route.policy")
	if err != nil { return nil, "", err }
	if err := exactFields(policy, "lease_ticks", "max_attempts", "window_size"); err != nil {
		return nil, "", fail("route reliability policy is invalid: %v", err)
	}
	for _, field := range []string{"lease_ticks", "max_attempts", "window_size"} {
		if _, err := integerValue(policy[field], "route.policy."+field, 1); err != nil { return nil, "", err }
	}
	routeDigest, err := digest(route)
	if err != nil { return nil, "", err }
	return route, routeDigest, nil
}

func verifyLedger(value object) (object, string, int64, error) {
	if err := exactFields(value, "format", "entries", "ledger_digest"); err != nil {
		return nil, "", 0, fail("route ledger fields are invalid: %v", err)
	}
	if value["format"] != ledgerFormat {
		return nil, "", 0, fail("unsupported route-ledger format")
	}
	ledgerDigest, err := sha256Value(value["ledger_digest"], "ledger_digest")
	if err != nil { return nil, "", 0, err }
	if computed, err := digest(cloneWithout(value, "ledger_digest")); err != nil || computed != ledgerDigest {
		return nil, "", 0, fail("route ledger digest mismatch")
	}
	entries, err := asArray(value["entries"], "route ledger entries")
	if err != nil { return nil, "", 0, err }
	if len(entries) < 3 || len(entries) > 10000 {
		return nil, "", 0, fail("route ledger event count is outside the supported range")
	}

	var active *activeRoute
	usedEpochs := map[string]bool{}
	usedOwnerIDs := map[string]bool{}
	admissions := map[string]admission{}
	admittedSequences := map[int64]bool{}
	authorizations := make([]object, 0, 1)
	previousDigest := strings.Repeat("0", 64)

	for index, raw := range entries {
		event, err := asObject(raw, fmt.Sprintf("route ledger event %d", index+1))
		if err != nil { return nil, "", 0, err }
		if err := exactFields(event,
			"sequence", "event_type", "epoch_id", "epoch_number", "route",
			"route_digest", "details", "previous_event_digest", "event_digest",
		); err != nil {
			return nil, "", 0, fail("route event %d fields are invalid: %v", index+1, err)
		}
		sequence, err := integerValue(event["sequence"], "event.sequence", 1)
		if err != nil || sequence != int64(index+1) {
			return nil, "", 0, fail("route ledger sequence is not contiguous")
		}
		epochNumber, err := integerValue(event["epoch_number"], "event.epoch_number", 1)
		if err != nil { return nil, "", 0, err }
		epochID, err := textValue(event["epoch_id"], "event.epoch_id")
		if err != nil { return nil, "", 0, err }
		route, routeDigest, err := validateRoute(event["route"])
		if err != nil { return nil, "", 0, err }
		suppliedRouteDigest, err := sha256Value(event["route_digest"], "event.route_digest")
		if err != nil || suppliedRouteDigest != routeDigest {
			return nil, "", 0, fail("route event digest differs from its route")
		}
		suppliedPrevious, err := sha256Value(event["previous_event_digest"], "event.previous_event_digest")
		if err != nil || suppliedPrevious != previousDigest {
			return nil, "", 0, fail("route event %d has a broken predecessor link", index+1)
		}
		eventDigest, err := sha256Value(event["event_digest"], "event.event_digest")
		if err != nil { return nil, "", 0, err }
		computedEventDigest, err := digest(cloneWithout(event, "event_digest"))
		if err != nil || computedEventDigest != eventDigest {
			return nil, "", 0, fail("route event %d self-digest mismatch", index+1)
		}
		details, err := asObject(event["details"], "event.details")
		if err != nil { return nil, "", 0, err }
		eventType, err := textValue(event["event_type"], "event.event_type")
		if err != nil { return nil, "", 0, err }

		switch eventType {
		case "opened":
			if err := exactFields(details, "predecessor_close_digest", "owner_generation", "owner_id"); err != nil {
				return nil, "", 0, fail("opened event details are invalid: %v", err)
			}
			if active != nil || len(usedEpochs) != 0 || epochNumber != 1 || details["predecessor_close_digest"] != nil {
				return nil, "", 0, fail("only one initial open route is supported by this reconstruction profile")
			}
			if usedEpochs[epochID] { return nil, "", 0, fail("route epoch ID is reused") }
			generation, err := integerValue(details["owner_generation"], "opened.owner_generation", 1)
			if err != nil || generation != 1 { return nil, "", 0, fail("new route must start at owner generation one") }
			ownerID, err := textValue(details["owner_id"], "opened.owner_id")
			if err != nil { return nil, "", 0, err }
			if usedOwnerIDs[ownerID] { return nil, "", 0, fail("route owner ID is reused") }
			usedEpochs[epochID] = true
			usedOwnerIDs[ownerID] = true
			active = &activeRoute{
				EpochID: epochID, EpochNumber: epochNumber, Route: route,
				RouteDigest: routeDigest, OwnerID: ownerID, OwnerGeneration: generation,
			}

		case "claimed":
			if err := exactFields(details, "owner_generation", "previous_owner_id", "owner_id"); err != nil {
				return nil, "", 0, fail("claimed event details are invalid: %v", err)
			}
			if active == nil || epochID != active.EpochID || epochNumber != active.EpochNumber || routeDigest != active.RouteDigest {
				return nil, "", 0, fail("route claim targets a different active epoch")
			}
			generation, err := integerValue(details["owner_generation"], "claimed.owner_generation", 1)
			if err != nil || generation != active.OwnerGeneration+1 {
				return nil, "", 0, fail("route owner generation is not monotonic")
			}
			priorOwner, err := textValue(details["previous_owner_id"], "claimed.previous_owner_id")
			if err != nil || priorOwner != active.OwnerID {
				return nil, "", 0, fail("route claim does not identify the previous owner")
			}
			newOwner, err := textValue(details["owner_id"], "claimed.owner_id")
			if err != nil { return nil, "", 0, err }
			if usedOwnerIDs[newOwner] { return nil, "", 0, fail("route owner ID is reused") }
			usedOwnerIDs[newOwner] = true
			active.OwnerID = newOwner
			active.OwnerGeneration = generation

		case "admitted":
			if err := exactFields(details, "owner_id", "owner_generation", "attempt_id", "request_digest", "request_sequence"); err != nil {
				return nil, "", 0, fail("admitted event details are invalid: %v", err)
			}
			if active == nil || epochID != active.EpochID || epochNumber != active.EpochNumber || routeDigest != active.RouteDigest {
				return nil, "", 0, fail("request admission targets a different active route")
			}
			ownerID, err := textValue(details["owner_id"], "admitted.owner_id")
			if err != nil { return nil, "", 0, err }
			generation, err := integerValue(details["owner_generation"], "admitted.owner_generation", 1)
			if err != nil { return nil, "", 0, err }
			if ownerID != active.OwnerID || generation != active.OwnerGeneration {
				return nil, "", 0, fail("request admission was recorded by a stale owner")
			}
			attemptID, err := textValue(details["attempt_id"], "admitted.attempt_id")
			if err != nil { return nil, "", 0, err }
			requestDigest, err := sha256Value(details["request_digest"], "admitted.request_digest")
			if err != nil { return nil, "", 0, err }
			requestSequence, err := integerValue(details["request_sequence"], "admitted.request_sequence", 1)
			if err != nil { return nil, "", 0, err }
			key := epochID + "\x00" + attemptID
			if _, exists := admissions[key]; exists || admittedSequences[requestSequence] {
				return nil, "", 0, fail("duplicate route admission or ReliableChannel sequence")
			}
			admissions[key] = admission{
				EventDigest: eventDigest, RequestDigest: requestDigest,
				RequestSequence: requestSequence,
			}
			admittedSequences[requestSequence] = true

		case "execution_authorized":
			if err := exactFields(details,
				"owner_id", "owner_generation", "attempt_id", "request_digest",
				"request_sequence", "admission_event_digest", "execution_id", "runner_id",
			); err != nil {
				return nil, "", 0, fail("execution authorization details are invalid: %v", err)
			}
			if active == nil || epochID != active.EpochID || epochNumber != active.EpochNumber || routeDigest != active.RouteDigest {
				return nil, "", 0, fail("execution authorization targets a different active route")
			}
			ownerID, err := textValue(details["owner_id"], "execution.owner_id")
			if err != nil { return nil, "", 0, err }
			generation, err := integerValue(details["owner_generation"], "execution.owner_generation", 1)
			if err != nil { return nil, "", 0, err }
			if ownerID != active.OwnerID || generation != active.OwnerGeneration {
				return nil, "", 0, fail("execution authorization was recorded by a stale owner")
			}
			attemptID, err := textValue(details["attempt_id"], "execution.attempt_id")
			if err != nil { return nil, "", 0, err }
			requestDigest, err := sha256Value(details["request_digest"], "execution.request_digest")
			if err != nil { return nil, "", 0, err }
			requestSequence, err := integerValue(details["request_sequence"], "execution.request_sequence", 1)
			if err != nil { return nil, "", 0, err }
			admissionDigest, err := sha256Value(details["admission_event_digest"], "execution.admission_event_digest")
			if err != nil { return nil, "", 0, err }
			if _, err := textValue(details["runner_id"], "execution.runner_id"); err != nil {
				return nil, "", 0, err
			}
			admitted, ok := admissions[epochID+"\x00"+attemptID]
			if !ok || admitted.EventDigest != admissionDigest || admitted.RequestDigest != requestDigest || admitted.RequestSequence != requestSequence {
				return nil, "", 0, fail("execution authorization does not bind its preceding request admission")
			}
			expectedExecutionID, err := digest(object{
				"epoch_id": epochID, "attempt_id": attemptID, "request_digest": requestDigest,
			})
			if err != nil { return nil, "", 0, err }
			expectedExecutionID = "urn:sha256:" + expectedExecutionID
			if details["execution_id"] != expectedExecutionID {
				return nil, "", 0, fail("execution ID is not the deterministic route ticket")
			}
			for _, prior := range authorizations {
				priorDetails, _ := asObject(prior["details"], "prior execution details")
				if priorDetails["attempt_id"] == attemptID {
					return nil, "", 0, fail("attempt has more than one execution authorization")
				}
			}
			authorizations = append(authorizations, event)

		default:
			return nil, "", 0, fail("event type %q is outside the supported open-route reconstruction profile", eventType)
		}
		previousDigest = eventDigest
	}

	if active == nil || len(authorizations) != 1 || len(admissions) != 1 {
		return nil, "", 0, fail("profile requires one active route, one admission, and one execution authorization")
	}
	return authorizations[0], ledgerDigest, int64(len(entries)), nil
}

func verifyRequest(value object, event object) (string, string, error) {
	if value["format"] != requestFormat {
		return "", "", fail("unsupported proof-action request format")
	}
	attemptID, err := textValue(value["attempt_id"], "request.attempt_id")
	if err != nil { return "", "", err }
	requestDigest, err := sha256Value(value["request_digest"], "request.request_digest")
	if err != nil { return "", "", err }
	computed, err := digest(cloneWithout(value, "request_digest"))
	if err != nil || computed != requestDigest {
		return "", "", fail("proof-action request digest mismatch")
	}
	details, err := asObject(event["details"], "authorization event details")
	if err != nil { return "", "", err }
	if details["attempt_id"] != attemptID || details["request_digest"] != requestDigest {
		return "", "", fail("proof-action request differs from route authorization")
	}
	return attemptID, requestDigest, nil
}

func verifyResult(value object, attemptID, requestDigest string) (string, string, string, error) {
	if err := exactFields(value, "format", "attempt_id", "request_digest", "return_evidence", "proof_trace", "result_digest"); err != nil {
		return "", "", "", fail("proof-action result fields are invalid: %v", err)
	}
	if value["format"] != resultFormat {
		return "", "", "", fail("unsupported proof-action result format")
	}
	resultAttempt, err := textValue(value["attempt_id"], "result.attempt_id")
	if err != nil { return "", "", "", err }
	resultRequest, err := sha256Value(value["request_digest"], "result.request_digest")
	if err != nil { return "", "", "", err }
	if resultAttempt != attemptID || resultRequest != requestDigest {
		return "", "", "", fail("proof-action result is not correlated to the authorized request")
	}
	evidence, err := asObject(value["return_evidence"], "result.return_evidence")
	if err != nil { return "", "", "", err }
	if err := exactFields(evidence, "evidence_ref", "encounter_id", "payload_digest", "canonicalization"); err != nil {
		return "", "", "", fail("result return-evidence fields are invalid: %v", err)
	}
	if _, err := textValue(evidence["evidence_ref"], "return_evidence.evidence_ref"); err != nil { return "", "", "", err }
	if _, err := textValue(evidence["encounter_id"], "return_evidence.encounter_id"); err != nil { return "", "", "", err }
	if _, err := sha256Value(evidence["payload_digest"], "return_evidence.payload_digest"); err != nil { return "", "", "", err }
	if _, err := textValue(evidence["canonicalization"], "return_evidence.canonicalization"); err != nil { return "", "", "", err }
	trace, err := asObject(value["proof_trace"], "result.proof_trace")
	if err != nil { return "", "", "", err }
	resultDigest, err := sha256Value(value["result_digest"], "result.result_digest")
	if err != nil { return "", "", "", err }
	computed, err := digest(cloneWithout(value, "result_digest"))
	if err != nil || computed != resultDigest {
		return "", "", "", fail("proof-action result digest mismatch")
	}
	evidenceDigest, err := digest(evidence)
	if err != nil { return "", "", "", err }
	traceDigest, err := digest(trace)
	if err != nil { return "", "", "", err }
	return resultDigest, evidenceDigest, traceDigest, nil
}

func verifyParticipantKey(document object, expectedRole string) (participant, error) {
	if err := exactFields(document, "format", "participant_id", "role", "key_algorithm", "key_id", "public_key_hex", "host"); err != nil {
		return participant{}, fail("participant key document fields are invalid: %v", err)
	}
	if document["format"] != keyFormat || document["key_algorithm"] != "Ed25519" || document["role"] != expectedRole {
		return participant{}, fail("participant key document format, algorithm, or role is invalid")
	}
	id, err := textValue(document["participant_id"], "participant_id")
	if err != nil { return participant{}, err }
	keyID, err := textValue(document["key_id"], "key_id")
	if err != nil { return participant{}, err }
	rawHex, err := textValue(document["public_key_hex"], "public_key_hex")
	if err != nil { return participant{}, err }
	raw, err := hex.DecodeString(rawHex)
	if err != nil || len(raw) != ed25519.PublicKeySize || strings.ToLower(rawHex) != rawHex {
		return participant{}, fail("Ed25519 public key must be 32-byte lowercase hex")
	}
	if keyFingerprint(raw) != keyID {
		return participant{}, fail("participant public-key fingerprint mismatch")
	}
	host, err := asObject(document["host"], "participant host identity")
	if err != nil { return participant{}, err }
	if err := exactFields(host,
		"repository", "run_id", "run_attempt", "run_number", "workflow_ref",
		"workflow_sha", "git_ref", "git_sha", "job", "runner_name",
		"runner_os", "runner_arch", "runner_environment", "actor_id",
	); err != nil {
		return participant{}, fail("participant host identity fields are invalid: %v", err)
	}
	if host["repository"] != "Kier73/In-Formation-Space" || host["job"] != expectedRole ||
		host["git_ref"] != "refs/heads/main" ||
		host["workflow_ref"] != "Kier73/In-Formation-Space/.github/workflows/proof-runner-three-host-reconstruction.yml@refs/heads/main" ||
		host["runner_environment"] != "github-hosted" {
		return participant{}, fail("participant host identity does not match the protected hosted role")
	}
	if !validGitSHA(host["workflow_sha"]) || !validGitSHA(host["git_sha"]) {
		return participant{}, fail("participant host commit identities must be 40-character lowercase Git object IDs")
	}
	for _, field := range []string{"run_id", "run_attempt", "run_number", "workflow_ref", "workflow_sha", "git_sha", "runner_name", "runner_os", "runner_arch", "actor_id"} {
		if _, err := textValue(host[field], "host."+field); err != nil { return participant{}, err }
	}
	return participant{
		ID: id, Role: expectedRole, KeyID: keyID,
		PublicKey: ed25519.PublicKey(raw), Host: host,
	}, nil
}

func verifyAuthorityAttestation(
	value object,
	authority participant,
	ledgerDigest string,
	ledgerSequence int64,
	event object,
	attemptID, requestDigest string,
) error {
	if err := exactFields(value,
		"format", "signature_algorithm", "authority_id", "authority_key_id",
		"ledger_digest", "ledger_sequence", "authorization_event_digest",
		"execution_id", "attempt_id", "request_digest", "runner_id",
		"attestation_digest", "signature",
	); err != nil {
		return fail("authority attestation fields are invalid: %v", err)
	}
	if value["format"] != authorityAttestationFormat || value["signature_algorithm"] != "Ed25519" {
		return fail("unsupported authority attestation format or signature algorithm")
	}
	details, err := asObject(event["details"], "authorization event details")
	if err != nil { return err }
	expected := object{
		"format": authorityAttestationFormat,
		"signature_algorithm": "Ed25519",
		"authority_id": authority.ID,
		"authority_key_id": authority.KeyID,
		"ledger_digest": ledgerDigest,
		"ledger_sequence": json.Number(strconv.FormatInt(ledgerSequence, 10)),
		"authorization_event_digest": event["event_digest"],
		"execution_id": details["execution_id"],
		"attempt_id": attemptID,
		"request_digest": requestDigest,
		"runner_id": details["runner_id"],
	}
	for key, expectedValue := range expected {
		if value[key] != expectedValue {
			return fail("authority attestation %s does not match reconstructed evidence", key)
		}
	}
	attestationDigest, err := sha256Value(value["attestation_digest"], "authority.attestation_digest")
	if err != nil { return err }
	computedDigest, err := digest(expected)
	if err != nil || computedDigest != attestationDigest {
		return fail("authority attestation digest mismatch")
	}
	signatureHex, err := textValue(value["signature"], "authority.signature")
	if err != nil { return err }
	signature, err := hex.DecodeString(signatureHex)
	if err != nil || len(signature) != ed25519.SignatureSize {
		return fail("authority signature must be 64-byte hex")
	}
	signedPayload := object{}
	for key, member := range expected { signedPayload[key] = member }
	signedPayload["attestation_digest"] = attestationDigest
	canonical, err := metadata.CanonicalBytes(signedPayload)
	if err != nil { return err }
	if !ed25519.Verify(authority.PublicKey, canonical, signature) {
		return fail("authority ledger checkpoint signature verification failed")
	}
	return nil
}

func verifyRunnerReceipt(
	value object,
	runner participant,
	event object,
	attemptID, requestDigest, resultFormat, resultDigest, evidenceDigest, traceDigest string,
) (string, error) {
	details, err := asObject(event["details"], "authorization event details")
	if err != nil { return "", err }
	if details["runner_id"] != runner.ID {
		return "", fail("authorized runner identity differs from pinned runner key")
	}
	expected := object{
		"format": receiptFormat,
		"signature_algorithm": "Ed25519",
		"authorization_event_digest": event["event_digest"],
		"route_epoch_id": event["epoch_id"],
		"execution_id": details["execution_id"],
		"attempt_id": attemptID,
		"request_digest": requestDigest,
		"runner_id": runner.ID,
		"runner_key_id": runner.KeyID,
		"completion_status": "result_produced",
		"result_format": resultFormat,
		"result_digest": resultDigest,
		"return_evidence_digest": evidenceDigest,
		"proof_trace_digest": traceDigest,
	}
	if err := exactFields(value,
		"format", "signature_algorithm", "authorization_event_digest",
		"route_epoch_id", "execution_id", "attempt_id", "request_digest",
		"runner_id", "runner_key_id", "completion_status", "result_format",
		"result_digest", "return_evidence_digest", "proof_trace_digest",
		"receipt_digest", "signature",
	); err != nil {
		return "", fail("completion receipt fields are invalid: %v", err)
	}
	for key, expectedValue := range expected {
		if value[key] != expectedValue {
			return "", fail("completion receipt %s mismatch", key)
		}
	}
	receiptDigest, err := sha256Value(value["receipt_digest"], "receipt.receipt_digest")
	if err != nil { return "", err }
	computedDigest, err := digest(expected)
	if err != nil || computedDigest != receiptDigest {
		return "", fail("completion receipt digest mismatch")
	}
	signatureHex, err := textValue(value["signature"], "receipt.signature")
	if err != nil { return "", err }
	signature, err := hex.DecodeString(signatureHex)
	if err != nil || len(signature) != ed25519.SignatureSize {
		return "", fail("completion receipt signature must be 64-byte hex")
	}
	signedPayload := object{}
	for key, member := range expected { signedPayload[key] = member }
	signedPayload["receipt_digest"] = receiptDigest
	canonical, err := metadata.CanonicalBytes(signedPayload)
	if err != nil { return "", err }
	if !ed25519.Verify(runner.PublicKey, canonical, signature) {
		return "", fail("runner completion receipt signature verification failed")
	}
	return receiptDigest, nil
}

func verifyVerifierHost(value object, authority, runner participant) (object, error) {
	if err := exactFields(value, "format", "host"); err != nil {
		return nil, fail("verifier host document fields are invalid: %v", err)
	}
	if value["format"] != verifierHostFormat {
		return nil, fail("unsupported verifier host document format")
	}
	host, err := asObject(value["host"], "verifier host")
	if err != nil { return nil, err }
	if err := exactFields(host,
		"repository", "run_id", "run_attempt", "run_number", "workflow_ref",
		"workflow_sha", "git_ref", "git_sha", "job", "runner_name",
		"runner_os", "runner_arch", "runner_environment", "actor_id",
	); err != nil {
		return nil, fail("verifier host identity fields are invalid: %v", err)
	}
	if host["repository"] != "Kier73/In-Formation-Space" ||
		host["job"] != "independent_verifier_host" ||
		host["git_ref"] != "refs/heads/main" ||
		host["workflow_ref"] != "Kier73/In-Formation-Space/.github/workflows/proof-runner-three-host-reconstruction.yml@refs/heads/main" ||
		host["runner_environment"] != "github-hosted" {
		return nil, fail("verifier identity does not match the protected hosted verifier job")
	}
	if !validGitSHA(host["workflow_sha"]) || !validGitSHA(host["git_sha"]) {
		return nil, fail("verifier host commit identities must be 40-character lowercase Git object IDs")
	}
	for _, field := range []string{"run_id", "run_attempt", "workflow_ref", "workflow_sha", "git_sha", "runner_name", "actor_id"} {
		if _, err := textValue(host[field], "verifier.host."+field); err != nil { return nil, err }
	}
	participants := []participant{authority, runner}
	for _, p := range participants {
		for _, field := range []string{"repository", "run_id", "run_attempt", "run_number", "workflow_ref", "workflow_sha", "git_ref", "git_sha"} {
			if host[field] != p.Host[field] {
				return nil, fail("verifier and %s host differ in %s", p.Role, field)
			}
		}
		if host["job"] == p.Host["job"] || host["actor_id"] == p.Host["actor_id"] {
			return nil, fail("verifier is not a distinct job actor from %s", p.Role)
		}
	}
	if authority.Host["job"] == runner.Host["job"] || authority.Host["actor_id"] == runner.Host["actor_id"] {
		return nil, fail("authority and runner are not distinct job actors")
	}
	return host, nil
}

func Verify(paths Paths) (object, error) {
	ledger, err := readObject(paths.Ledger)
	if err != nil { return nil, fmt.Errorf("read route ledger: %w", err) }
	request, err := readObject(paths.Request)
	if err != nil { return nil, fmt.Errorf("read request: %w", err) }
	authorityAttestation, err := readObject(paths.AuthorityAttestation)
	if err != nil { return nil, fmt.Errorf("read authority attestation: %w", err) }
	authorityKeyDoc, err := readObject(paths.AuthorityKey)
	if err != nil { return nil, fmt.Errorf("read authority public key: %w", err) }
	result, err := readObject(paths.Result)
	if err != nil { return nil, fmt.Errorf("read result: %w", err) }
	receipt, err := readObject(paths.Receipt)
	if err != nil { return nil, fmt.Errorf("read completion receipt: %w", err) }
	runnerKeyDoc, err := readObject(paths.RunnerKey)
	if err != nil { return nil, fmt.Errorf("read runner public key: %w", err) }
	verifierHostDoc, err := readObject(paths.VerifierHost)
	if err != nil { return nil, fmt.Errorf("read verifier host: %w", err) }

	authority, err := verifyParticipantKey(authorityKeyDoc, "authority_host")
	if err != nil { return nil, fmt.Errorf("authority key: %w", err) }
	runner, err := verifyParticipantKey(runnerKeyDoc, "runner_host")
	if err != nil { return nil, fmt.Errorf("runner key: %w", err) }
	verifierHost, err := verifyVerifierHost(verifierHostDoc, authority, runner)
	if err != nil { return nil, fmt.Errorf("third-host separation: %w", err) }

	for _, field := range []string{"repository", "run_id", "run_attempt", "workflow_ref", "workflow_sha", "git_ref", "git_sha"} {
		if authority.Host[field] != runner.Host[field] {
			return nil, fail("authority and runner hosts differ in %s", field)
		}
	}

	event, ledgerDigest, ledgerSequence, err := verifyLedger(ledger)
	if err != nil { return nil, fmt.Errorf("route ledger reconstruction: %w", err) }
	attemptID, requestDigest, err := verifyRequest(request, event)
	if err != nil { return nil, err }
	resultDigest, evidenceDigest, traceDigest, err := verifyResult(result, attemptID, requestDigest)
	if err != nil { return nil, err }
	if err := verifyAuthorityAttestation(
		authorityAttestation, authority, ledgerDigest, ledgerSequence,
		event, attemptID, requestDigest,
	); err != nil {
		return nil, fmt.Errorf("authority signature: %w", err)
	}
	receiptDigest, err := verifyRunnerReceipt(
		receipt, runner, event, attemptID, requestDigest,
		resultFormat, resultDigest, evidenceDigest, traceDigest,
	)
	if err != nil { return nil, fmt.Errorf("runner receipt: %w", err) }

	details, _ := asObject(event["details"], "authorization details")
	return object{
		"schema": reportFormat,
		"status": "verified",
		"route_epoch_id": event["epoch_id"],
		"route_ledger_digest": ledgerDigest,
		"route_ledger_sequence": ledgerSequence,
		"authorization_event_digest": event["event_digest"],
		"execution_id": details["execution_id"],
		"attempt_id": attemptID,
		"request_digest": requestDigest,
		"authority": object{
			"participant_id": authority.ID,
			"role": authority.Role,
			"key_id": authority.KeyID,
			"job": authority.Host["job"],
			"actor_id": authority.Host["actor_id"],
		},
		"runner": object{
			"participant_id": runner.ID,
			"role": runner.Role,
			"key_id": runner.KeyID,
			"job": runner.Host["job"],
			"actor_id": runner.Host["actor_id"],
			"completion_status": "result_produced",
		},
		"verifier": object{
			"job": verifierHost["job"],
			"actor_id": verifierHost["actor_id"],
			"runner_name": verifierHost["runner_name"],
		},
		"host_separation": object{
			"distinct_jobs": true,
			"distinct_actor_ids": true,
			"all_github_hosted": true,
			"same_workflow_run": true,
			"artifact_relay": "GitHub Actions artifact storage",
			"combined_cross_host_elapsed_ns": nil,
		},
		"result_digest": resultDigest,
		"return_evidence_digest": evidenceDigest,
		"proof_trace_digest": traceDigest,
		"completion_receipt_digest": receiptDigest,
		"key_provenance_verified_by_github": paths.KeyAttestationsVerified,
		"verified_layers": []any{
			"full route-ledger head digest and supported event hash chain",
			"open-route ownership, request admission, and execution-ticket replay",
			"authority Ed25519 signature over the exact ledger head and authorization event",
			"portable request digest and exact attempt correlation",
			"portable result digest and request correlation",
			"runner Ed25519 signature over the exact result and authorization event",
			"three distinct GitHub-hosted workflow job identities in one run",
		},
		"not_established": []any{
			"external shared-CAS linearizability or the live state at admission; this experiment uses an authority-signed synthetic ledger checkpoint",
			"honest computation, actual Lean execution, or theorem correctness",
			"VGI kernel acceptance; that remains a separate VerifiedKernelReceipt boundary",
			"direct peer-to-peer transport; these records travel through GitHub Actions artifacts",
			"distinct physical servers or independent administrative fault domains",
			"combined cross-host duration or transport latency",
		},
	}, nil
}

func main() {
	if len(os.Args) < 2 || os.Args[1] != "verify" {
		fmt.Fprintln(os.Stderr, "usage: go run . verify --ledger ... --request ... --authority-attestation ... --authority-key ... --result ... --receipt ... --runner-key ... --verifier-host ... [--key-attestations-verified]")
		os.Exit(2)
	}
	flags := flag.NewFlagSet("verify", flag.ExitOnError)
	paths := Paths{}
	output := flags.String("output", "reconstruction-report.json", "output report path")
	flags.StringVar(&paths.Ledger, "ledger", "", "canonical route-ledger document")
	flags.StringVar(&paths.Request, "request", "", "canonical proof-action request")
	flags.StringVar(&paths.AuthorityAttestation, "authority-attestation", "", "authority-signed ledger checkpoint")
	flags.StringVar(&paths.AuthorityKey, "authority-key", "", "separately attested authority public-key document")
	flags.StringVar(&paths.Result, "result", "", "canonical proof-action result")
	flags.StringVar(&paths.Receipt, "receipt", "", "runner-signed completion receipt")
	flags.StringVar(&paths.RunnerKey, "runner-key", "", "separately attested runner public-key document")
	flags.StringVar(&paths.VerifierHost, "verifier-host", "", "third-host identity document")
	flags.BoolVar(&paths.KeyAttestationsVerified, "key-attestations-verified", false, "caller has verified both key-document GitHub attestations")
	if err := flags.Parse(os.Args[2:]); err != nil { os.Exit(2) }
	for name, path := range map[string]string{
		"ledger": paths.Ledger, "request": paths.Request,
		"authority-attestation": paths.AuthorityAttestation, "authority-key": paths.AuthorityKey,
		"result": paths.Result, "receipt": paths.Receipt,
		"runner-key": paths.RunnerKey, "verifier-host": paths.VerifierHost,
	} {
		if path == "" { fmt.Fprintf(os.Stderr, "missing --%s\n", name); os.Exit(2) }
	}
	report, err := Verify(paths)
	if err != nil {
		fmt.Fprintln(os.Stderr, "reconstruction rejected:", err)
		os.Exit(1)
	}
	if err := writeObject(*output, report); err != nil {
		fmt.Fprintln(os.Stderr, "write report:", err)
		os.Exit(1)
	}
	fmt.Printf("independent reconstruction verified: %s\n", report["completion_receipt_digest"])
}

