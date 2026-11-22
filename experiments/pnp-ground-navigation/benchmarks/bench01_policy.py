"""BENCH-01F: bounded, source-only SAT policy synthesized using native SAT machinery.

This is *algorithm-selection research*, NOT an alternative SAT solver or a
proof that a performance observation is correct. Each selected backend remains
responsible for its own source-bound SAT/UNSAT proof; UNKNOWN is preserved.
Untrusted performance reports never authorize a mathematical verdict.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
from itertools import combinations, product
import json
import math
from pathlib import Path
import sys
from time import perf_counter_ns

from bench01_3sat import check_cnf, run_case, satisfies, exhaustive_reference, sha as source_hash

SCHEMA = "ifs.bench01.adaptive-3sat-policy.v1"
RULES = ("small_source", "sparse", "repeated_scope", "unit_clause",
         "high_hub", "many_components")
MAX_TRAIN = 128
MAX_META_VARS = 16


def _hash(obj):
    return sha256(json.dumps(obj, sort_keys=True, separators=(",", ":"),
                             allow_nan=False).encode()).hexdigest()


def source_features(n, clauses):
    """Cheap structural observations only; no call to a solver or source labels."""
    check_cnf(n, clauses)
    t0 = perf_counter_ns()
    scopes = {}
    activity = [0] * (n + 1)
    roots = list(range(n + 1))
    def find(a):
        while roots[a] != a:
            roots[a] = roots[roots[a]]
            a = roots[a]
        return a
    for row in clauses:
        scope = tuple(sorted({abs(x) for x in row}))
        scopes[scope] = scopes.get(scope, 0) + 1
        for k in scope: activity[k] += 1
        if scope:
            p = find(scope[0])
            for k in scope[1:]: roots[find(k)] = p
    components = len({find(v) for v in range(1, n + 1)})
    m = len(clauses)
    features = {
        "small_source": n <= 18,
        "sparse": m <= 2 * n,
        "repeated_scope": any(v >= 2 for v in scopes.values()),
        "unit_clause": any(len(c) <= 1 for c in clauses),
        "high_hub": bool(m and max(activity) * 6 >= m),
        "many_components": components >= 2,
    }
    return features, (perf_counter_ns() - t0) / 1e6


def _validate_observation(record):
    if not isinstance(record, dict) or set(record) != {"id", "n", "clauses", "source_sha256", "formed", "direct"}:
        raise ValueError("invalid observation shape")
    n, clauses = record["n"], record["clauses"]
    check_cnf(n, clauses)
    if record["source_sha256"] != source_hash({"n": n, "clauses": clauses}):
        raise ValueError("source observation identity changed")
    if not isinstance(record["id"], str) or not record["id"]:
        raise ValueError("missing observation name")
    for key in ("formed", "direct"):
        r = record[key]
        if not isinstance(r, dict) or set(r) != {"status", "wall_ms", "witness", "source_checked", "proof"}:
            raise ValueError("unqualified result shape")
        if r["status"] not in ("SAT", "UNSAT", "UNKNOWN") or r["source_checked"] is not True:
            raise ValueError("unqualified source observation")
        ms = r["wall_ms"]
        if type(ms) not in (int, float) or not math.isfinite(ms) or not 0 <= ms < 1e6:
            raise ValueError("bad measured execution cost")
        witness = r["witness"]
        if r["status"] == "SAT":
            if not isinstance(witness, str) or not witness.isdecimal() or str(int(witness)) != witness or int(witness) >= (1 << n) or not satisfies(clauses, int(witness)):
                raise ValueError("invalid claimed SAT model")
        elif witness is not None:
            raise ValueError("non-SAT observation carries a model")
        if r["status"] == "UNSAT":
            # The training file is untrusted; a worker assertion is never a proof.
            if n <= 14:
                ref = exhaustive_reference(n, clauses, maximum_vars=14)
                if ref["status"] != "UNSAT":
                    raise ValueError("false UNSAT observation in training data")
            else:
                proof = r["proof"]
                if not isinstance(proof, dict):
                    raise ValueError("UNSAT observation lacks portable proof")
                spn = Path(__file__).resolve().parents[1] / "spectral_phase_navigation"
                if str(spn) not in sys.path: sys.path.insert(0, str(spn))
                from direct_sat_compiler import verify_direct_sat
                if verify_direct_sat(clauses, n, proof) != "UNSAT":
                    raise ValueError("wrong UNSAT source proof")
        elif r["proof"] is not None:
            # SAT is checked directly; refuse unattested extra authority metadata.
            raise ValueError("unexpected non-UNSAT proof data")
    if {record["formed"]["status"], record["direct"]["status"]} == {"SAT", "UNSAT"}:
        raise ValueError("backends contradict each other")
    return True


def observed(item, *, timeout=9.0, nodes=8192, max_source_vars=80):
    """Obtain both source-checked backend outcomes from real BENCH-01 workers."""
    check_cnf(item["n"], item["clauses"])
    base = {"timeout": timeout, "spn_nodes": nodes,
            "max_source_vars": max_source_vars, "max_source_clauses": 400,
            "max_spn_vars": 1024, "max_spn_clauses": 5000,
            "export_spn_proof": True}
    # Native direct SPN path, intentionally refusing costly SFI admission.
    direct = run_case(item, spn_fallback=True, max_source_vars=0, **base)
    # Problem-formed interpreter, followed by SPN only after an UNKNOWN result.
    formed = run_case(item, spn_fallback=True, **base)
    def capsule(r):
        if r["status"] == "ERROR":
            raise RuntimeError("native worker failed: " + str(r.get("reason", "")))
        if r["status"] == "UNSAT" and r["verification"] not in (
                "native-proof-or-complete-search-replay", "native-proof-replay+exhaustive-reference", "source-empty-clause"):
            raise ValueError("unqualified UNSAT source observation")
        return {"status": r["status"], "wall_ms": r["wall_ms"],
                "witness": r.get("witness"), "source_checked": True,
                "proof": r.get("spn_receipt") if r["status"] == "UNSAT" else None}
    record = {"id": item["id"], "n": item["n"], "clauses": item["clauses"],
              "source_sha256": source_hash({"n": item["n"], "clauses": item["clauses"]}),
              "formed": capsule(formed), "direct": capsule(direct)}
    _validate_observation(record)
    return record


def _encode_or(cnf, terms, next_var):
    """Exact Tseitin OR chain in clauses of width <=3."""
    terms = list(terms)
    if len(terms) <= 3:
        cnf.append(terms)
        return next_var
    left = terms[0]
    for term in terms[1:]:
        z = next_var
        next_var += 1
        cnf.extend([[-left, z], [-term, z], [left, term, -z]])
        left = z
    cnf.append([left])
    return next_var


def _preference(record, margin):
    formed, direct = record["formed"], record["direct"]
    a, b = formed["status"], direct["status"]
    if a in ("SAT", "UNSAT") and b == "UNKNOWN": return "formed"
    if b in ("SAT", "UNSAT") and a == "UNKNOWN": return "direct"
    if a not in ("SAT", "UNSAT") or b not in ("SAT", "UNSAT"): return "neutral"
    if formed["wall_ms"] < direct["wall_ms"] * (1 - margin): return "formed"
    if direct["wall_ms"] < formed["wall_ms"] * (1 - margin): return "direct"
    return "neutral"


def meta_problem(training, *, margin=0.15, max_rules=2):
    if not isinstance(training, list) or not 1 <= len(training) <= MAX_TRAIN:
        raise ValueError("bad training cohort")
    if type(margin) not in (float, int) or not 0 <= margin <= 0.5 or max_rules != 2:
        raise ValueError("unsupported bounded policy construction budget")
    names = set(); sources = set(); clauses = []
    next_var = len(RULES) + 1
    for item in training:
        _validate_observation(item)
        if item["id"] in names or item["source_sha256"] in sources:
            raise ValueError("duplicate training observation or source")
        names.add(item["id"]); sources.add(item["source_sha256"])
        flags, _ = source_features(item["n"], item["clauses"])
        active = [i + 1 for i, name in enumerate(RULES) if flags[name]]
        preference = _preference(item, margin)
        if preference == "formed":
            next_var = _encode_or(clauses, active, next_var)
        elif preference == "direct":
            clauses.extend([[-v] for v in active])
    for t in combinations(range(1, len(RULES) + 1), max_rules + 1):
        clauses.append([-v for v in t])
    if next_var - 1 > MAX_META_VARS:
        raise ValueError("meta SAT exceeds fixed size budget")
    return {"n": next_var - 1, "clauses": clauses,
            "training_sha256": _hash(training), "training_sources": sorted(sources),
            "margin": margin, "max_rules": max_rules}


def _satisfies_meta(clauses, assignment):
    return all(any(((assignment >> (abs(lit) - 1)) & 1) == (lit > 0) for lit in row)
               for row in clauses)


def _satisfiable_mask(problem, mask):
    n = problem["n"]
    free = n - len(RULES)
    # Exhaust auxiliary variables only; the rule assignments are fixed.
    for aux in range(1 << free):
        if _satisfies_meta(problem["clauses"], mask | (aux << len(RULES))):
            return True
    return False


def _solve_meta(problem):
    """Prefer the real SPN-008 solver + independent verifier; small exhaustive fallback."""
    spn = Path(__file__).resolve().parents[1] / "spectral_phase_navigation"
    if (spn / "direct_sat_compiler.py").is_file():
        if str(spn) not in sys.path: sys.path.insert(0, str(spn))
        from direct_sat_compiler import produce_direct_sat, verify_direct_sat
        receipt = produce_direct_sat(problem["clauses"], problem["n"], node_budget=8192)
        result = verify_direct_sat(problem["clauses"], problem["n"], receipt)
        return {"backend": "SPN-008-verified-DPLL/XOR", "result": result, "proof": receipt}
    if problem["n"] > MAX_META_VARS:
        raise ValueError("exhaustive meta proof budget")
    sat = any(_satisfies_meta(problem["clauses"], bits) for bits in range(1 << problem["n"]))
    return {"backend": "complete-exhaustive-meta-oracle", "result": "SAT" if sat else "UNSAT",
            "proof": {"enumerated": 1 << problem["n"]}}


def _verify_meta(problem, evidence):
    backend = evidence.get("backend")
    if backend == "SPN-008-verified-DPLL/XOR":
        path = Path(__file__).resolve().parents[1] / "spectral_phase_navigation"
        if str(path) not in sys.path: sys.path.insert(0, str(path))
        from direct_sat_compiler import verify_direct_sat
        result = verify_direct_sat(problem["clauses"], problem["n"], evidence["proof"])
    elif backend == "complete-exhaustive-meta-oracle":
        if problem["n"] > MAX_META_VARS or evidence.get("proof") != {"enumerated": 1 << problem["n"]}:
            raise ValueError("invalid complete meta-enumeration certificate")
        result = "SAT" if any(_satisfies_meta(problem["clauses"], bits)
                              for bits in range(1 << problem["n"])) else "UNSAT"
    else:
        raise ValueError("unsupported meta proof backend")
    if result != evidence.get("result") or result not in ("SAT", "UNSAT"):
        raise ValueError("meta proof is invalid or incomplete")
    return result


def _best_mask(problem, training):
    candidates=[]
    for mask in range(1 << len(RULES)):
        if mask.bit_count() > problem["max_rules"] or not _satisfiable_mask(problem, mask):
            continue
        total=0.
        for o in training:
            flags, _=source_features(o["n"], o["clauses"])
            formed = any(flags[rule] and mask >> i & 1 for i, rule in enumerate(RULES))
            total += o["formed" if formed else "direct"]["wall_ms"]
        candidates.append((total, mask.bit_count(), mask))
    return min(candidates, default=None)


def train_policy(training, *, margin=0.15):
    started=perf_counter_ns()
    problem=meta_problem(training, margin=margin)
    evidence=_solve_meta(problem)
    _verify_meta(problem, evidence)
    best=_best_mask(problem,training)
    if (best is None) != (evidence["result"] == "UNSAT"):
        raise ValueError("meta SAT producer disagrees with independently enumerated legal policies")
    mask = best[2] if best else 0
    record={"schema":SCHEMA, "kind":"candidate", "rules":list(RULES),
            "selected_rules":sorted(name for i,name in enumerate(RULES) if mask >> i & 1),
            "training_sha256":problem["training_sha256"],
            "training_sources":problem["training_sources"],
            "margin": margin,"max_rules":2,"meta":evidence,
            "meta_sha256":_hash({"n":problem["n"], "clauses":problem["clauses"]}),
            "estimated_training_execution_ms": None if best is None else round(best[0],5),
            "training_observations_ms":round(sum(r[k]["wall_ms"] for r in training for k in ("direct","formed")),5),
            "producer_train_ms":round((perf_counter_ns()-started)/1e6,5)}
    record["digest"]=_hash(record)
    audit_policy(record,training)
    return record


def audit_policy(policy,training):
    if not isinstance(policy,dict) or policy.get("schema")!=SCHEMA or policy.get("kind") not in ("candidate", "frozen"):
        raise ValueError("invalid policy record")
    if policy.get("digest")!=_hash({k:v for k,v in policy.items() if k!="digest"}):
        raise ValueError("changed policy record")
    if policy.get("rules")!=list(RULES) or policy.get("max_rules")!=2:
        raise ValueError("invalid policy grammar")
    if policy.get("selected_rules")!=sorted(set(policy["selected_rules"])):
        raise ValueError("noncanonical selected source-only rules")
    problem=meta_problem(training,margin=policy["margin"])
    if (problem["training_sha256"] != policy["training_sha256"] or
            problem["training_sources"] != policy["training_sources"] or
            policy.get("meta_sha256")!=_hash({"n":problem["n"], "clauses":problem["clauses"]})):
        raise ValueError("policy training bindings changed")
    result=_verify_meta(problem,policy["meta"])
    best=_best_mask(problem,training)
    if (best is None)!=(result=="UNSAT"):
        raise ValueError("policy feasibility does not match independently checked meta problem")
    optimal=[] if best is None else sorted(name for i,name in enumerate(RULES) if best[2] >> i & 1)
    if policy["kind"]=="candidate" and policy["selected_rules"]!=optimal:
        raise ValueError("selected policy not optimal among qualified candidate masks")
    if policy["kind"]=="frozen" and policy["selected_rules"] not in ([],optimal):
        raise ValueError("frozen policy cannot invent untrained rules")
    return True


def selection(policy,n,clauses):
    if policy.get("digest")!=_hash({k:v for k,v in policy.items() if k!="digest"}):
        raise ValueError("changed policy identity")
    if policy.get("rules")!=list(RULES):
        raise ValueError("unknown policy vocabulary")
    if source_hash({"n":n,"clauses":clauses}) in policy.get("training_sources",[]):
        raise ValueError("source leakage: training case cannot be held out")
    flags, elapsed=source_features(n,clauses)
    engine="formed" if any(flags[k] for k in policy["selected_rules"]) else "direct"
    return engine, elapsed


def _evaluation(policy,observations):
    if not observations:
        raise ValueError("empty validation cohort")
    ids=set(); sources=set(); before=after=0.; lost=0; decided_baseline=0; selected=[]
    for o in observations:
        _validate_observation(o)
        if o["id"] in ids or o["source_sha256"] in sources or o["source_sha256"] in policy["training_sources"]:
            raise ValueError("reused or training-source validation observation")
        ids.add(o["id"]);sources.add(o["source_sha256"])
        action,cost=selection(policy,o["n"],o["clauses"])
        source_status=o[action]["status"];baseline=o["direct"]["status"]
        if baseline in ("SAT","UNSAT"):
            decided_baseline+=1
            if source_status not in ("SAT","UNSAT"):
                lost+=1
        before+=o["direct"]["wall_ms"]
        after+=o[action]["wall_ms"]+cost
        selected.append({"id":o["id"],"engine":action,"baseline":baseline,
                         "outcome":source_status,"source_only_policy_ms":round(cost,5)})
    return {"direct_total_ms":round(before,5), "selected_total_ms":round(after,5),
            "coverage_losses":lost,"decided_baseline":decided_baseline,"selected":selected,"sources":sorted(sources)}


def validate_and_freeze(candidate,training,validation,*,min_gain=0.05):
    audit_policy(candidate,training)
    started=perf_counter_ns()
    results=_evaluation(candidate,validation)
    min_gain=float(min_gain)
    train_cost=candidate["producer_train_ms"]+candidate["training_observations_ms"]
    # Both backend measurements, meta SAT training and qualification are charged.
    gained=(results["direct_total_ms"]-results["selected_total_ms"])
    admitted=(bool(candidate["selected_rules"]) and results["coverage_losses"]==0
              and results["decided_baseline"]>0 and gained>train_cost and gained >= min_gain*results["direct_total_ms"])
    frozen={**{k:v for k,v in candidate.items() if k!="digest"}, "kind":"frozen",
            "selected_rules":candidate["selected_rules"] if admitted else [],
            "validation_sha256":_hash(validation), "admission":"ADMITTED" if admitted else "REJECTED",
            "validation":results, "verified_net_gain_ms":round(gained-train_cost,5),
            "validation_audit_ms":round((perf_counter_ns()-started)/1e6,5),
            "training_all_in_ms":round(train_cost,5)}
    frozen["digest"]=_hash(frozen)
    audit_policy(frozen,training)
    return frozen


def evaluate_final(frozen,training,validation,final):
    audit_policy(frozen,training)
    if frozen.get("kind")!="frozen" or frozen.get("validation_sha256")!=_hash(validation):
        raise ValueError("policy was not frozen against this validation cohort")
    validation_sources={o["source_sha256"] for o in validation}
    for o in final:
        if o["source_sha256"] in validation_sources:
            raise ValueError("validation and final cohorts overlap")
    return _evaluation(frozen,final)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("observations",type=Path,help="JSON object with disjoint training, validation and final arrays")
    parser.add_argument("--output",type=Path)
    args=parser.parse_args(argv)
    data=json.loads(args.observations.read_text())
    training,validation,final=(data[k] for k in ("training","validation","final"))
    candidate=train_policy(training)
    frozen=validate_and_freeze(candidate,training,validation)
    final_result=evaluate_final(frozen,training,validation,final)
    result={"schema":SCHEMA, "candidate":candidate,"frozen":frozen, "final":final_result,
            "provenance":"paired source-checked BENCH-01 observations; timing evidence observational"}
    serialized=json.dumps(result,indent=2,sort_keys=True)+"\n"
    if args.output:args.output.write_text(serialized)
    else: print(serialized,end="")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
