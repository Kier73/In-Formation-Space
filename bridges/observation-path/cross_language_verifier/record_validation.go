package verifier

import (
	"fmt"
	"math"
	"strings"
)

func validateFrame(value any, label string) (Object, error) {
	f, err := exactFields(value, frameFields, label)
	if err != nil {
		return nil, err
	}
	actor, err := textValue(f["actor_id"], label+".actor_id")
	if err != nil {
		return nil, err
	}
	if raw := f["monotonic"]; raw != nil {
		m, e := exactFields(raw, []string{"actor_id", "segment", "elapsed_ns"}, label+".monotonic")
		if e != nil {
			return nil, e
		}
		a, e := textValue(m["actor_id"], label+".monotonic.actor_id")
		if e != nil {
			return nil, e
		}
		if a != actor {
			return nil, fail("%s monotonic actor mismatch", label)
		}
		if _, e = uintValue(m["segment"], label+".monotonic.segment", 0); e != nil {
			return nil, e
		}
		if _, e = uintValue(m["elapsed_ns"], label+".monotonic.elapsed_ns", 0); e != nil {
			return nil, e
		}
	}
	if raw := f["wall"]; raw != nil {
		w, e := exactFields(raw, []string{"actor_id", "utc_ns", "sample_index"}, label+".wall")
		if e != nil {
			return nil, e
		}
		a, e := textValue(w["actor_id"], label+".wall.actor_id")
		if e != nil {
			return nil, e
		}
		if a != actor {
			return nil, fail("%s wall actor mismatch", label)
		}
		if _, e = intValue(w["utc_ns"], label+".wall.utc_ns"); e != nil {
			return nil, e
		}
		if _, e = uintValue(w["sample_index"], label+".wall.sample_index", 0); e != nil {
			return nil, e
		}
	}
	if raw := f["causal"]; raw != nil {
		c, e := exactFields(raw, []string{"actor_id", "lamport", "vector"}, label+".causal")
		if e != nil {
			return nil, e
		}
		a, e := textValue(c["actor_id"], label+".causal.actor_id")
		if e != nil {
			return nil, e
		}
		if a != actor {
			return nil, fail("%s causal actor mismatch", label)
		}
		lamport, e := uintValue(c["lamport"], label+".causal.lamport", 0)
		if e != nil {
			return nil, e
		}
		v, ok := c["vector"].(map[string]any)
		if !ok || len(v) == 0 {
			return nil, fail("%s causal vector must be a non-empty object", label)
		}
		own := false
		for k, n := range v {
			if strings.TrimSpace(k) == "" {
				return nil, fail("%s causal vector contains empty actor", label)
			}
			counter, e := uintValue(n, label+".causal.vector["+k+"]", 0)
			if e != nil {
				return nil, e
			}
			if counter > lamport {
				return nil, fail("%s causal vector exceeds Lamport value", label)
			}
			if k == actor {
				own = true
			}
		}
		if !own {
			return nil, fail("%s causal vector omits its own actor", label)
		}
	}
	if raw := f["scheduler"]; raw != nil {
		s, e := exactFields(raw, []string{"scheduler_id", "tick"}, label+".scheduler")
		if e != nil {
			return nil, e
		}
		if _, e = textValue(s["scheduler_id"], label+".scheduler.scheduler_id"); e != nil {
			return nil, e
		}
		if _, e = uintValue(s["tick"], label+".scheduler.tick", 0); e != nil {
			return nil, e
		}
	}
	if f["event_lambda"] != nil {
		if _, e := uintValue(f["event_lambda"], label+".event_lambda", 0); e != nil {
			return nil, e
		}
	}
	if f["chronon_phase"] != nil {
		p, ok := f["chronon_phase"].([]any)
		if !ok || len(p) != 2 {
			return nil, fail("%s chronon_phase must be a pair", label)
		}
		// Integer-only canonical number profile. This supports exact [1,0]/[0,1]
		// phases, but not decimal representations until a shared numeric profile exists.
		x, e := intValue(p[0], label+".chronon_phase[0]")
		if e != nil {
			return nil, e
		}
		y, e := intValue(p[1], label+".chronon_phase[1]")
		if e != nil {
			return nil, e
		}
		if math.Abs(math.Hypot(float64(x), float64(y))-1.0) > 1e-9 {
			return nil, fail("%s chronon_phase must lie on unit circle", label)
		}
	}
	if f["chemical_tau"] != nil {
		if _, e := uintValue(f["chemical_tau"], label+".chemical_tau", 0); e != nil {
			return nil, e
		}
	}
	return f, nil
}

func validateSpan(value any, label string) (Object, error) {
	s, err := exactFields(value, spanFields, label)
	if err != nil {
		return nil, err
	}
	if s["format"] != SpanFormat || s["schema"] != SpanSchema {
		return nil, fail("%s format or schema unsupported", label)
	}
	for _, k := range []string{"attempt_id", "span_id", "operation_id", "clock_actor_id", "clock_segment_id"} {
		if _, err = textValue(s[k], label+"."+k); err != nil {
			return nil, err
		}
	}
	start, err := uintValue(s["monotonic_start_ns"], label+".monotonic_start_ns", 0)
	if err != nil {
		return nil, err
	}
	end, err := uintValue(s["monotonic_end_ns"], label+".monotonic_end_ns", 0)
	if err != nil {
		return nil, err
	}
	elapsed, err := uintValue(s["elapsed_ns"], label+".elapsed_ns", 0)
	if err != nil {
		return nil, err
	}
	if end < start || elapsed != end-start || s["clock_status"] != "measured" {
		return nil, fail("%s must contain an exact measured monotonic interval", label)
	}
	if s["outcome"] != "succeeded" || s["exception_type"] != nil {
		return nil, fail("%s must describe a successful callable", label)
	}
	if s["measurement_scope"] != MeasurementScope {
		return nil, fail("%s measurement scope unrecognized", label)
	}
	if _, ok := s["context"].(map[string]any); !ok {
		return nil, fail("%s context must be an object", label)
	}
	if err := digestWithout(s, "span_digest", label+".span_digest"); err != nil {
		return nil, err
	}
	return s, nil
}

func validateHost(value any, role string) (Object, error) {
	h, err := exactFields(value, hostFields, role+".host")
	if err != nil {
		return nil, err
	}
	for _, k := range hostFields {
		if _, err = textValue(h[k], role+".host."+k); err != nil {
			return nil, err
		}
	}
	if h["role"] != role || h["job"] != role {
		return nil, fail("%s host role and job do not match", role)
	}
	if h["repository"] != Repository {
		return nil, fail("%s repository mismatch", role)
	}
	if h["workflow_ref"] != WorkflowRef || h["git_ref"] != "refs/heads/main" {
		return nil, fail("%s host not bound to protected main workflow", role)
	}
	if h["runner_environment"] != "github-hosted" {
		return nil, fail("%s host not GitHub-hosted", role)
	}
	return h, nil
}

func validateRecord(value any, role string) (Object, error) {
	r, err := exactFields(value, recordFields, role+" record")
	if err != nil {
		return nil, err
	}
	if r["format"] != RecordFormat || r["schema"] != RecordSchema {
		return nil, fail("%s record format or schema unsupported", role)
	}
	if r["role"] != role {
		return nil, fail("expected %s, got %v", role, r["role"])
	}
	if err := digestWithout(r, "record_digest", role+".record_digest"); err != nil {
		return nil, err
	}
	host, err := validateHost(r["host"], role)
	if err != nil {
		return nil, err
	}
	span, err := validateSpan(r["operation_span"], role+".operation_span")
	if err != nil {
		return nil, err
	}
	frame, err := validateFrame(r["temporal_frame"], role+".temporal_frame")
	if err != nil {
		return nil, err
	}
	actor := host["actor_id"].(string)
	if span["clock_actor_id"] != actor || frame["actor_id"] != actor {
		return nil, fail("%s actor identity does not bind span and frame", role)
	}
	if span["clock_segment_id"] != host["clock_segment_id"] {
		return nil, fail("%s span segment does not bind host metadata", role)
	}
	mono, ok := frame["monotonic"].(map[string]any)
	if !ok {
		return nil, fail("%s frame requires monotonic coordinate", role)
	}
	causal, ok := frame["causal"].(map[string]any)
	if !ok {
		return nil, fail("%s frame requires causal coordinate", role)
	}
	segment, err := uintValue(mono["segment"], role+" frame segment", 0)
	if err != nil {
		return nil, err
	}
	if fmt.Sprint(segment) != host["clock_segment_id"] {
		return nil, fail("%s frame segment does not bind host metadata", role)
	}
	_ = causal
	if role == "source_host" {
		if r["source_record_sha256"] != nil || r["handoff_witness"] != nil {
			return nil, fail("source record cannot claim predecessor or receiver witness")
		}
		p, err := exactFields(r["handoff_payload"], payloadFields, "source handoff payload")
		if err != nil {
			return nil, err
		}
		if p["schema"] != PayloadSchema {
			return nil, fail("source payload schema unsupported")
		}
		if err := digestWithout(p, "payload_digest", "source payload_digest"); err != nil {
			return nil, err
		}
		if p["sender_actor_id"] != actor || p["attempt_id"] != span["attempt_id"] || p["predecessor_span_digest"] != span["span_digest"] {
			return nil, fail("source payload does not bind source host/span")
		}
		pf, err := validateFrame(p["sender_completion_frame"], "source payload frame")
		if err != nil {
			return nil, err
		}
		if !sameJSON(pf, frame) {
			return nil, fail("source payload frame differs from source record frame")
		}
		pmono := pf["monotonic"].(map[string]any)
		pElapsed, _ := uintValue(pmono["elapsed_ns"], "source payload frame elapsed", 0)
		spanEnd, _ := uintValue(span["monotonic_end_ns"], "source span end", 0)
		if pElapsed < spanEnd {
			return nil, fail("source completion frame predates operation completion")
		}
		if _, err = textValue(p["path_id"], "source payload.path_id"); err != nil {
			return nil, err
		}
	} else {
		if _, err = digestValue(r["source_record_sha256"], "receiver.source_record_sha256"); err != nil {
			return nil, err
		}
		if r["handoff_payload"] != nil {
			return nil, fail("receiver must not contain handoff payload")
		}
		w, ok := r["handoff_witness"].(map[string]any)
		if !ok {
			return nil, fail("receiver must contain handoff witness")
		}
		if w["attempt_id"] != span["attempt_id"] || w["successor_span_digest"] != span["span_digest"] {
			return nil, fail("receiver witness does not bind receiver span")
		}
	}
	return r, nil
}
