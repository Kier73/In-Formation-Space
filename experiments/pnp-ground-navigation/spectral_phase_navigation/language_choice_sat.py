#!/usr/bin/env python3
"""SPN-009: intention-sensitive, source-checked computational-language selection.

The selector is not an oracle. It pays for feature discovery and can refuse.
Decision SAT accepts only source-checked witnesses/refutations; exact #SAT
requires independently recomputable counting evidence (or a checked affine
interpreter with complete original-source evaluation). All backends are
existing classical algorithms; this module is a cost-accounting experiment.

Place next to the SPN-008 modules under pnp-ground-navigation/.
"""
from __future__ import annotations
from collections import defaultdict
from hashlib import sha256
from pathlib import Path
from time import perf_counter
import json
import sys

HERE=Path(__file__).resolve().parent
PARENT=HERE.parent
if str(PARENT) not in sys.path:
    sys.path.insert(0,str(PARENT))

from direct_sat_compiler import (
    validate_cnf,source_digest,check_assignment,spectral_form,parity_blocks,
    _verify_xor_encoding_by_truth_table,produce_direct_sat,verify_direct_sat)
from adaptive_ground_compiler import produce_adaptive_receipt,verify_adaptive_receipt
from direct_sum_grounds import fundamental_components,gf2_rank
from walsh_phase_navigation_probe import spectral_coefficients

VERSION="SPN-009-language-choice-v1"


def _all_xor_count(equations,n):
    """Independent GF(2) consistency/rank reconstruction (not producer trace)."""
    rows={}
    for mask,rhs in equations:
        v,bit=int(mask),int(rhs)
        while v:
            pivot=(v&-v).bit_length()-1
            if pivot not in rows:
                rows[pivot]=(v,bit)
                break
            w,c=rows[pivot]
            v^=w;bit^=c
        if v==0 and bit:
            return 0
    return 1<<(n-len(rows))


def _twin_pairs(clauses):
    normalized={frozenset(c) for c in clauses if not any(-v in c for v in c)}
    found=0
    for clause in normalized:
        for lit in clause:
            if lit>0 and frozenset((set(clause)-{lit})|{-lit}) in normalized:
                found+=1
    return found


def _projected_factor_cost(clauses,n):
    """Overestimate emitted separator cells using source primal scopes.

    Estimation includes fill and disconnected/free variables; counts are
    cardinalities, not runtime, and do not certify satisfiability.
    """
    neighbors={v:set() for v in range(1,n+1)}
    initial=sum(1<<len({abs(l) for l in clause}) for clause in clauses)
    for clause in clauses:
        vs={abs(l) for l in clause}
        for v in vs: neighbors[v].update(vs-{v})
    cost=0;highest=0;order=[]
    while neighbors:
        # Exact (deterministic) min-fill score; charge construction time.
        def score(v):
            ns=neighbors[v]
            seq=sorted(ns)
            missing=sum(b not in neighbors[a] for i,a in enumerate(seq)
                        for b in seq[i+1:])
            return missing,len(ns),v
        pivot=min(neighbors,key=score)
        ns=sorted(neighbors[pivot]);highest=max(highest,len(ns))
        cost+=1<<len(ns)
        for i,a in enumerate(ns):
            for b in ns[i+1:]:
                neighbors[a].add(b);neighbors[b].add(a)
            neighbors[a].discard(pivot)
        del neighbors[pivot]
        order.append(pivot)
    return {"projected_entries":cost,"initial_entries":initial,
            "max_scope":highest,"order":order}


def _frontier_independent_count(clauses,n,cell_cap):
    """Checker-side count: independent factor tabulation and bucket elimination.

    Does not trust a producer's elimination order, tables or counts. This is
    a *source recomputation certificate* (verification costs real work).
    """
    estimate=_projected_factor_cost(clauses,n)
    if estimate["projected_entries"]+estimate["initial_entries"]>cell_cap:
        raise ValueError("frontier verifier refuses oversized computation")
    tables=[]
    for clause in clauses:
        scope=tuple(sorted({abs(v) for v in clause}))
        values={}
        for t in range(1<<len(scope)):
            a={v:(t>>i)&1 for i,v in enumerate(scope)}
            values[t]=int(any(a[abs(l)]==int(l>0) for l in clause))
        tables.append((scope,values))
    for pivot in estimate["order"]:
        active=[f for f in tables if pivot in f[0]]
        tables=[f for f in tables if pivot not in f[0]]
        scope=tuple(sorted({v for vs,_ in active for v in vs if v!=pivot}))
        generated={}
        for t in range(1<<len(scope)):
            assignment={v:(t>>i)&1 for i,v in enumerate(scope)}
            total=0
            for bit in (0,1):
                assignment[pivot]=bit
                value=1
                for variables,lookup in active:
                    key=sum(assignment[v]<<i for i,v in enumerate(variables))
                    value*=lookup[key]
                total+=value
            generated[t]=total
        tables.append((scope,generated))
    result=1
    for scope,values in tables:
        if scope: raise AssertionError("non-scalar final factor")
        result*=values[0]
    return result


def _sfi_available():
    try:
        from derived_ground import compile_proven_ground
        from derived_verifier import canonical
        from self_forming_sat import form, verify_program,execute_partition, aggregate
        return (compile_proven_ground,canonical,form,verify_program,
                execute_partition,aggregate)
    except ImportError:
        return None


def _produce_sfi(clauses,n,free_cap,part_cap):
    imported=_sfi_available()
    if imported is None:
        return None,"SFI-001 dependencies not installed in this environment"
    compile_proven_ground,_,form,verify_program,execute_partition,aggregate=imported
    source=compile_proven_ground(clauses,n,
            max_contracts=1500,max_resolution_attempts=2000,
            max_resolution_added=350,max_learned=24)
    # form independently checks its PNG-003 evidence; work is not free.
    program,formation=form(source,intention="#SAT",
             maximum_free=min(free_cap,16),partition_size=part_cap,verifier_free=16)
    if program["mode"]=="undetermined":
        return None,"SFI interpreter had insufficient admitted coordinate capacity"
    if len(program["partitions"])>32:
        return None,"SFI interpreter needs more than 32 partitions"
    parts=[execute_partition(program,i) for i in range(len(program["partitions"]))]
    result=aggregate(program,parts,source_receipt=source)
    if result["status"]=="UNDETERMINED":
        return None,"SFI partition search inconclusive"
    # Store the evidence as canonical JSON-compatible objects. This avoids
    # Python tuple/list identity becoming an accidental transport contract.
    return json.loads(json.dumps({
            "kind":"sfi_count","count":str(result["count"]),
            "source_receipt":source,"program":program,"parts":parts,
            "formation":formation})),None


def verify_language_receipt(clauses,n,receipt,*,frontier_cell_cap=200000):
    """Source verifier: ignore all producer choices, timing and rankings."""
    validate_cnf(clauses,n)
    if (not isinstance(receipt,dict) or receipt.get("version")!=VERSION
            or receipt.get("source_sha256")!=source_digest(clauses,n)
            or receipt.get("goal") not in ("decision","count")):
        raise ValueError("invalid source-bound compiler receipt")
    goal=receipt["goal"]
    proof=receipt.get("proof")
    if not isinstance(proof,dict):raise ValueError("missing proof")
    kind=proof.get("kind")
    count=None
    if kind=="empty_clause":
        if not any(len(c)==0 for c in clauses) or proof.get("count")!="0":
            raise ValueError("false empty-clause certificate")
        count=0
    elif kind=="xor_count":
        eq=_verify_xor_encoding_by_truth_table(clauses,n)
        if eq is None:raise ValueError("source CNF is not a complete XOR encoding")
        count=_all_xor_count(eq,n)
        if proof.get("count")!=str(count):raise ValueError("forged XOR count")
        if count and goal=="decision":
            bits=proof.get("witness")
            if (not isinstance(bits,list) or len(bits)!=n
                or any(type(b) is not int or b not in (0,1) for b in bits)
                or not check_assignment(clauses,bits)):
                raise ValueError("bad XOR decision witness")
    elif kind=="spectral_exact":
        spec=spectral_form(clauses,n)
        if spec is None: raise ValueError("ineligible spectral source")
        nested=proof.get("receipt")
        if not isinstance(nested,dict):raise ValueError("missing spectral certificate")
        answer=verify_adaptive_receipt(spec,n,nested)
        if not isinstance(nested.get("ground_degeneracy"),str) or nested.get("ground_energy") is None:
            raise ValueError("a decision alone cannot certify exact count")
        count=int(nested["ground_degeneracy"]) if answer=="SAT" else 0
        if proof.get("count")!=str(count):raise ValueError("bad spectral count")
    elif kind=="frontier_replay":
        count=_frontier_independent_count(clauses,n,frontier_cell_cap)
        if proof.get("count")!=str(count):raise ValueError("forged factor count")
        if count:
            bits=proof.get("witness")
            if (not isinstance(bits,list) or len(bits)!=n
                    or any(type(b) is not int or b not in (0,1) for b in bits)
                    or not check_assignment(clauses,bits)):
                raise ValueError("incorrect factor witness")
    elif kind=="sfi_count":
        imported=_sfi_available()
        if imported is None:raise ValueError("cannot check unavailable SFI runtime")
        _,canonical,form,_,_,aggregate=imported
        source=proof.get("source_receipt");program=proof.get("program");parts=proof.get("parts")
        if (not isinstance(source,dict) or not isinstance(program,dict)
                or not isinstance(parts,list)):
            raise ValueError("missing source interpreter evidence")
        if canonical(clauses,n)!=canonical(source.get("original_clauses",[]),n):
            raise ValueError("SFI source CNF differs from requested input")
        if program.get("intention")!="#SAT":raise ValueError("SFI not a counting interpreter")
        budgets=program.get("budgets")
        if not isinstance(budgets,dict):raise ValueError("missing formation budgets")
        built,_=form(source,intention="#SAT",
                     maximum_free=budgets["maximum_free"],
                     partition_size=budgets["partition_size"],verifier_free=16)
        # Compare canonical JSON representations, not Python-only tuple/list
        # identities. The source proof is independently replayed by `form`.
        if json.dumps(built,sort_keys=True)!=json.dumps(program,sort_keys=True):
            raise ValueError("SFI source-bound program does not reconstruct")
        if len(parts)>32 or len(parts)!=len(program["partitions"]):
            raise ValueError("missing or excessive SFI partitions")
        # `aggregate` reexecutes every segment against the original CNF.
        # For a refutation it additionally calls the native proof checker,
        # so use the freshly reconstructed, typed program.
        outcome=aggregate(built,parts,source_receipt=source)
        if outcome["status"]=="UNDETERMINED":raise ValueError("cannot admit undetermined count")
        count=outcome["count"]
        if proof.get("count")!=str(count):raise ValueError("false SFI count")
    elif kind=="direct_decision":
        if goal!="decision":raise ValueError("a decision cannot prove #SAT")
        status=verify_direct_sat(clauses,n,proof.get("receipt"))
        if status!=receipt.get("result"):raise ValueError("wrong direct decision")
    elif kind=="unknown":
        if receipt.get("result")!="UNKNOWN" or proof.get("reason") not in (
            "decision_budget_exhausted","count_budget_exhausted"):
            raise ValueError("invalid explicit refusal")
    else:raise ValueError("unknown proof language")
    if kind in ("empty_clause","xor_count","spectral_exact","frontier_replay","sfi_count"):
        if goal=="count":
            if receipt.get("result")!=str(count):raise ValueError("count mismatch")
        else:
            if receipt.get("result")!=("SAT" if count else "UNSAT"):
                raise ValueError("SAT result inconsistent with exact count")
    return receipt["result"]


def compile_language(clauses,n,*,goal="decision",node_budget=512,
                     rank_cap=3,spectral_state_cap=512,frontier_cell_cap=200000,
                     sfi_free_cap=12,sfi_partition_size=512,allow_sfi=True):
    """Compile a cost-accounted choice, never conflating a cheap label with proof."""
    validate_cnf(clauses,n)
    if goal not in ("decision","count"):raise ValueError("invalid intention")
    if (type(node_budget) is not int or node_budget<1
        or type(rank_cap) is not int or not 1<=rank_cap<=8
        or type(spectral_state_cap) is not int or spectral_state_cap<1
        or type(frontier_cell_cap) is not int or frontier_cell_cap<1
        or type(sfi_free_cap) is not int or not 0<=sfi_free_cap<=16
        or type(sfi_partition_size) is not int or not 1<=sfi_partition_size<=65536
        or type(allow_sfi) is not bool):
        raise ValueError("invalid resource budget")
    started=perf_counter()
    attempts=[];proof=None;language=None
    def mark(name,start,outcome,**extra):
        attempts.append({"language":name,"outcome":outcome,
                         "observed_ms":round((perf_counter()-start)*1000,4),**extra})
    # The original CNF alone immediately proves a contradiction when it
    # contains an empty clause, including for the #SAT observer.
    if any(len(c)==0 for c in clauses):
        proof={"kind":"empty_clause","count":"0"}
        language="source_empty_clause"
    # Next cheapest structural candidate: complete source-scope XOR encoding.
    if proof is None:
        t=perf_counter();eq=parity_blocks(clauses,n)
        mark("source_xor_recognition",t,"recognized" if eq is not None else "refused")
    else:
        eq=None
    if eq is not None:
        from direct_sat_compiler import gaussian_ground
        t=perf_counter();g,rank=gaussian_ground(eq,n)
        count=0 if g["kind"]=="xor_unsat" else 1<<(n-rank)
        proof={"kind":"xor_count","count":str(count)}
        if count and goal=="decision":proof["witness"]=g["witness"]
        language="source_xor"
        mark("source_xor",t,"exact",equations=len(eq),rank=rank)

    # Cheap direct-execution pilot for strongly hub-concentrated sources.
    # In this class the spectral decomposition can be compact, but DPLL can
    # often prove a local obstruction even more cheaply. A failed pilot is
    # evidence of *no result within budget*, not an UNSAT certificate.
    if proof is None and goal=="decision" and n>=20 and clauses:
        t=perf_counter()
        freq=defaultdict(int)
        for clause in clauses:
            for v in {abs(lit) for lit in clause}:
                freq[v]+=1
        peak=max(freq.values(),default=0)
        highly_concentrated=8*peak>=len(clauses)
        mark("source_hub_probe",t,"eligible" if highly_concentrated else "refused",
             peak_occurrences=peak,total_clauses=len(clauses))
        if highly_concentrated:
            t=perf_counter()
            candidate=produce_direct_sat(clauses,n,node_budget=min(16,node_budget),
                                         skip_complete_xor=True)
            mark("bounded_direct_pilot",t,candidate["result"],
                 node_budget=min(16,node_budget))
            if candidate["result"] in ("SAT","UNSAT"):
                proof={"kind":"direct_decision","receipt":candidate}
                language="source_dpll_pilot"

    # A source-only guard must run BEFORE constructing an expensive encoding.
    # Prior implementation computed spectral_form once even on small decision
    # problems where no spectral method could be selected, then AGAIN on
    # eligible sources. This reuses the source transform exactly once.
    if proof is None and len(clauses)<=2500 and (goal=="count" or n>=20):
        t=perf_counter();converted=spectral_form(clauses,n)
        if converted is not None:
            coeff=spectral_coefficients(converted)
            groups,_=fundamental_components(s for s,a in coeff.items() if s and a)
            ranks=[gf2_rank(g) for g in groups]
            states=sum(1<<r for r in ranks)
            ok=max(ranks,default=0)<=rank_cap and states<=spectral_state_cap
            mark("spectral_preflight",t,"admit" if ok else "refused",
                components=len(groups),largest_rank=max(ranks,default=0),
                enumerated_state_ceiling=states)
            if ok and (goal=="count" or len(groups)>=4):
                t=perf_counter()
                nested=produce_adaptive_receipt(converted,n,goal="exact_ground",rank_cap=rank_cap)
                if nested["result"] in ("SAT","UNSAT"):
                    count=int(nested["ground_degeneracy"]) if nested["result"]=="SAT" else 0
                    proof={"kind":"spectral_exact","receipt":nested,"count":str(count)}
                    language="spectral_direct_sum"
                mark("spectral_ground",t,"exact" if proof else "refused")

    # SFI interpreter construction is more expensive; admit only source
    # syntax with actual consensus twins, and only for counting.
    if proof is None and goal=="count" and allow_sfi and n<=32:
        t=perf_counter();twins=_twin_pairs(clauses)
        mark("consensus_twin_probe",t,"eligible" if twins>=2 else "refused",pairs=twins)
        if twins>=2:
            t=perf_counter()
            candidate,why=_produce_sfi(clauses,n,sfi_free_cap,sfi_partition_size)
            if candidate:
                proof=candidate;language="source_formed_interpreter"
            mark("sfi_formation_and_source_evaluation",t,
                 "exact" if candidate else "refused",refusal=why)

    if proof is None and goal=="count":
        t=perf_counter();estimate=_projected_factor_cost(clauses,n)
        estimated=estimate["projected_entries"]+estimate["initial_entries"]
        allowed=estimated<=frontier_cell_cap
        mark("frontier_preflight",t,"admit" if allowed else "refused",
             estimated_cells=estimated,max_scope=estimate["max_scope"])
        if allowed:
            import frontier_ground as png
            t=perf_counter();count,witness,ledger=png.solve(clauses,n)
            if witness is not None:
                bits=[int(witness[i]) for i in range(1,n+1)]
            else:bits=None
            proof={"kind":"frontier_replay","count":str(count),"witness":bits}
            language="factor_frontier"
            mark("frontier_producer",t,"exact",projected_entries=ledger["projected_entries"])

    if proof is None and goal=="decision":
        t=perf_counter();nested=produce_direct_sat(clauses,n,node_budget=node_budget,
                                 skip_complete_xor=True)
        proof={"kind":"direct_decision","receipt":nested}
        language="source_dpll"
        mark("direct_sat",t,nested["result"],
             nodes=next((x["nodes"] for x in nested["producer_ledger"]["attempts"]
                 if x["method"]=="source_dpll"),0))
    if proof is None:
        proof={"kind":"unknown","reason":"count_budget_exhausted"}
        language="explicit_refusal"
    if goal=="count":
        result=proof.get("count","UNKNOWN")
    elif proof["kind"] in ("empty_clause","xor_count","spectral_exact","frontier_replay","sfi_count"):
        result="SAT" if int(proof["count"]) else "UNSAT"
    else:
        result=proof["receipt"]["result"]
    receipt={"version":VERSION,"source_sha256":source_digest(clauses,n),
             "goal":goal,"result":result,"language":language,
             "proof":proof, "cost_ledger":{"attempts":attempts}}
    t=perf_counter()
    verified=verify_language_receipt(clauses,n,receipt,frontier_cell_cap=frontier_cell_cap)
    receipt["cost_ledger"]["independent_check_ms"]=round((perf_counter()-t)*1000,4)
    receipt["cost_ledger"]["total_ms"]=round((perf_counter()-started)*1000,4)
    if verified!=result:raise AssertionError("self-check changed result")
    return receipt
