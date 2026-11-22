"""BENCH-01: bounded, evidence-accounted direct 3-SAT benchmark of IFS SFI.

It is a benchmark/orchestrator, NOT a new unrestricted SAT solver. Native
SFI-002/003 constructs and independently checks the interpreter. This layer
provides strict DIMACS input, one-process-per-instance timeouts, complete
source model validation, exact small references and explicit UNKNOWN results.
"""
from __future__ import annotations

import argparse
import gzip
import lzma
import hashlib
import json
from pathlib import Path
import random
import subprocess
import sys
from time import perf_counter_ns

VERSION = "ifs.bench01.3sat.v1"
HERE = Path(__file__).resolve().parent
SOURCE_DIR = HERE.parent
if str(SOURCE_DIR) not in sys.path:
    sys.path.insert(0, str(SOURCE_DIR))


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf8")


def sha(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def check_cnf(n, clauses, *, max_vars=100_000, max_clauses=300_000, width=3):
    if type(n) is not int or not 1 <= n <= max_vars:
        raise ValueError("invalid declared source variable count")
    if type(clauses) not in (list, tuple) or len(clauses) > max_clauses:
        raise ValueError("invalid or over-budget clause collection")
    for clause in clauses:
        if type(clause) not in (list, tuple) or len(clause) > width:
            raise ValueError("clause exceeds declared width")
        if any(type(lit) is not int or lit == 0 or abs(lit) > n for lit in clause):
            raise ValueError("invalid literal identity")
    return True


def parse_dimacs(raw: bytes, *, max_bytes=8 << 20, max_literals=600_000,
                 allow_wide=False):
    """Strict DIMACS parser; clauses may span lines, and zero ends a clause.

    It accepts comments and unused declared variables, but rejects missing
    headers, incomplete clauses and inconsistent declared counts. The raw
    source byte digest is retained separately from semantic CNF identity.
    """
    if not isinstance(raw, bytes) or not raw or len(raw) > max_bytes:
        raise ValueError("empty or over-budget DIMACS input")
    try:
        content = raw.decode("ascii")
    except UnicodeDecodeError as exc:
        raise ValueError("DIMACS must be ASCII") from exc
    declared = None
    clauses, current = [], []
    literal_count = 0
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("c"):
            continue
        if line.startswith("p"):
            bits = line.split()
            if declared is not None or current or clauses or len(bits) != 4 or bits[:2] != ["p", "cnf"]:
                raise ValueError("duplicate, malformed, or displaced DIMACS header")
            try:
                n, count = int(bits[2]), int(bits[3])
            except ValueError as exc:
                raise ValueError("non-numeric DIMACS header") from exc
            if n < 1 or n > 100_000 or count < 0 or count > 300_000:
                raise ValueError("DIMACS header outside finite admission bounds")
            declared = (n, count)
            continue
        if declared is None:
            raise ValueError("DIMACS clauses precede header")
        for word in line.split():
            try:
                v = int(word)
            except ValueError as exc:
                raise ValueError("invalid DIMACS token") from exc
            if v == 0:
                clauses.append(current)
                current = []
                if len(clauses) > declared[1]:
                    raise ValueError("extra clauses beyond DIMACS header")
            else:
                literal_count += 1
                if abs(v) > declared[0] or literal_count > max_literals:
                    raise ValueError("literal or total literal budget exceeded")
                current.append(v)
                if not allow_wide and len(current) > 3:
                    raise ValueError("not a 3-CNF; use explicit --convert-wide")
                if len(current) > 200_000:
                    raise ValueError("individual clause too large")
    if declared is None or current or len(clauses) != declared[1]:
        raise ValueError("incomplete DIMACS problem")
    return {"n": declared[0], "clauses": clauses,
            "source_sha256": sha({"n": declared[0], "clauses": clauses}),
            "bytes_sha256": hashlib.sha256(raw).hexdigest()}


def read_cnf_file(path: Path, *, max_bytes=8 << 20):
    """Read plain, gzip or xz DIMACS, bounding *decompressed* bytes."""
    name=path.name.lower()
    opener=(gzip.open if name.endswith(".cnf.gz") else
            lzma.open if name.endswith(".cnf.xz") else open)
    with opener(path,"rb") as stream:
        data=stream.read(max_bytes+1)
    if len(data)>max_bytes:
        raise ValueError("decompressed DIMACS exceeds finite input budget")
    return data


def as_dimacs(n, clauses):
    check_cnf(n, clauses, width=100_000)
    return (f"p cnf {n} {len(clauses)}\n" +
            "".join(" ".join(map(str, row)) + " 0\n" for row in clauses)).encode("ascii")


def to_three_cnf(n, clauses):
    """Standard satisfiability-preserving chain, not model-count preserving.

    Every source model extends to an auxiliary assignment, and every model
    of the transformed 3-CNF restricts to a model of the source formula.
    """
    check_cnf(n, clauses, width=100_000)
    output = []
    next_var = n
    for row in clauses:
        if len(row) <= 3:
            output.append(list(row))
            continue
        fresh = next_var + 1
        next_var = fresh
        output.append([row[0], row[1], fresh])
        for pos in range(2, len(row) - 2):
            another = next_var + 1
            next_var = another
            output.append([-fresh, row[pos], another])
            fresh = another
        output.append([-fresh, row[-2], row[-1]])
    check_cnf(next_var, output)
    return next_var, output


def satisfies(clauses, bits):
    return all(any(((bits >> (abs(lit) - 1)) & 1) == int(lit > 0)
                   for lit in clause) for clause in clauses)


def exhaustive_reference(n, clauses, *, maximum_vars=15):
    if n > maximum_vars:
        return {"status": "NOT_RUN", "reason": "independent exhaustive bound"}
    count = 0
    witness = None
    for bits in range(1 << n):
        if satisfies(clauses, bits):
            count += 1
            if witness is None:
                witness = bits
    return {"status": "SAT" if count else "UNSAT", "model_count": count,
            "witness": str(witness) if witness is not None else None,
            "candidate_count": 1 << n}


def parity3(a, b, c, rhs):
    """Four 3-literal clauses, forbidding the four wrong parity assignments."""
    ans=[]
    for bits in range(8):
        if ((bits & 1) ^ ((bits >> 1) & 1) ^ ((bits >> 2) & 1)) != rhs:
            ans.append([(-v if bits & (1 << i) else v)
                        for i, v in enumerate((a, b, c))])
    return ans


def pigeonhole(pigeons, holes):
    if not 1 <= holes < pigeons or pigeons * holes > 250:
        raise ValueError("invalid bounded pigeonhole family")
    index = lambda i, j: i * holes + j + 1
    clauses = [[index(i, j) for j in range(holes)] for i in range(pigeons)]
    for i in range(pigeons):
        for j in range(holes):
            for k in range(j+1, holes):
                clauses.append([-index(i, j), -index(i, k)])
    for i in range(pigeons):
        for k in range(i + 1, pigeons):
            for j in range(holes):
                clauses.append([-index(i, j), -index(k, j)])
    return pigeons * holes, clauses


def coloring_clique(vertices, colors=3):
    n = vertices * colors
    var = lambda v, col: v * colors + col + 1
    clauses=[]
    for v in range(vertices):
        clauses.append([var(v,c) for c in range(colors)])
        for a in range(colors):
            for b in range(a+1,colors):
                clauses.append([-var(v,a),-var(v,b)])
    for v in range(vertices):
        for w in range(v+1, vertices):
            for c in range(colors):
                clauses.append([-var(v,c),-var(w,c)])
    return n, clauses


def planted_random(n, m, seed, *, signed_witness=None):
    if n < 3 or m < 1:
        raise ValueError("invalid random CNF shape")
    rng = random.Random(seed)
    witness = rng.getrandbits(n) if signed_witness is None else signed_witness
    clauses=[]
    for _ in range(m):
        xs=rng.sample(range(1,n+1),3)
        row=[x if rng.randrange(2) else -x for x in xs]
        if not satisfies([row], witness):
            row[0] = xs[0] if (witness >> (xs[0]-1)) & 1 else -xs[0]
        clauses.append(row)
    return n, clauses, witness


def suite():
    """Seed-locked cases; the labels are hypotheses checked by execution."""
    items=[]
    def add(name,n,clauses,origin,known=None,witness=None):
        check_cnf(n,clauses, width=100_000)
        if any(len(clause)>3 for clause in clauses):
            n,clauses=to_three_cnf(n,clauses)
            origin += "-3cnf-chain"
            if witness is not None:
                raise ValueError("converted fixture needs an explicit lifted witness")
        items.append({"id":name,"n":n,"clauses":clauses,"origin":origin,
                      "expected":known,"known_witness":str(witness) if witness is not None else None})
    add("unit-sat",4,[[1],[-2],[3,-4]],"bounded-unit", "SAT", 1|4)
    add("unit-unsat",3,[[1],[-1]],"unit-contradiction", "UNSAT")
    for holes in (2,3,4):
        n, cs=pigeonhole(holes+1,holes)
        add(f"php-{holes+1}-into-{holes}",n,cs,"pigeonhole", "UNSAT")
    for v in (3,4):
        n,cs=coloring_clique(v)
        add(f"clique-{v}-3color",n,cs,"graph-coloring", "SAT" if v<=3 else "UNSAT")
    n,cs,w=planted_random(12,50,1009)
    add("planted-3sat-12",n,cs,"planted-random-3cnf", "SAT",w)
    n,cs,w=planted_random(16,68,1013)
    add("planted-3sat-16",n,cs,"planted-random-3cnf", "SAT",w)
    n,cs,w=planted_random(24,102,1031)
    add("planted-3sat-24",n,cs,"planted-random-3cnf", "SAT",w)
    for size,seed in ((32,1049),(60,1061),(80,1087)):
        n,cs,w=planted_random(size,round(size*4.25),seed)
        add(f"planted-3sat-{size}",n,cs,"planted-random-near-threshold", "SAT",w)
    clauses=parity3(1,2,3,0)+parity3(1,2,3,1)
    add("parity3-conflict",3,clauses,"xor-contradiction", "UNSAT")
    clauses=[]
    for i in range(1,10,3): clauses+=parity3(i,i+1,i+2,i//3%2)
    add("parity3-independent",9,clauses,"xor-independent", "SAT")
    # Mixed source illustrates direct SAT on intentionally non-affine machine.
    # The original SFI-002 generator is used only to create the fixture.
    from morphic_sat import seeded_circuit
    for gates in (8,16):
        cs,n,_ = seeded_circuit(17+gates, source_bits=5,gates=gates,mixed=False)
        # Mixed gates have width four: convert with named, checked projection.
        n3, cs3=to_three_cnf(n,cs)
        add(f"circuit-{gates}-3cnf",n3,cs3,"nonaffine-tseitin", "SAT")
    return items


def normalize_native_witness(witness, n):
    """Source check uses one canonical decimal bitset for both SFI backends."""
    if type(witness) is list:
        if len(witness) != n or any(type(b) is not int or b not in (0, 1) for b in witness):
            raise ValueError("native affine witness is not an exact n-bit model")
        return str(sum(bit << i for i, bit in enumerate(witness)))
    if type(witness) is int and witness >= 0:
        return str(witness)
    if isinstance(witness, str) and witness.isdecimal() and witness == str(int(witness)):
        return witness
    if witness is None:
        return None
    raise ValueError("invalid native SAT witness representation")


def _spn_worker(payload, *, previous=None):
    """Use existing SPN-008 DPLL/XOR certificates as a second native engine.

    This is NOT an unchecked external SAT result: the original SPN verifier
    independently replays all complete conflict trees and XOR dependencies.
    """
    spn_path = SOURCE_DIR / "spectral_phase_navigation"
    if str(spn_path) not in sys.path:
        sys.path.insert(0, str(spn_path))
    from direct_sat_compiler import produce_direct_sat, verify_direct_sat
    n,clauses=payload["n"],payload["clauses"]
    start=perf_counter_ns()
    receipt=produce_direct_sat(clauses,n,node_budget=payload["spn_nodes"])
    status=verify_direct_sat(clauses,n,receipt)
    elapsed=(perf_counter_ns()-start)/1e6
    proof=receipt["proof"]
    witness=normalize_native_witness(proof.get("witness"),n) if status=="SAT" else None
    if witness is not None and not satisfies(clauses,int(witness)):
        raise ValueError("SPN result fails source CNF")
    attempts=receipt["producer_ledger"]["attempts"]
    nodes=sum(x.get("nodes",0) for x in attempts)
    return {"status":status,"reason":proof.get("reason", ""),
            "selected":"spn-008-source-verified" if previous is None else "sfi-to-spn-008-fallback",
            "checked":0 if previous is None else previous.get("checked",0),
            "spn_nodes":nodes,"spn_proof_kind":proof["kind"],
            "spn_proof_bytes":len(canonical(receipt)),
            "construction_ms":round(elapsed,5),"execution_ms":0,
            "witness":witness,"spn_original_proof_verified":True,
            "prior_machine":None if previous is None else previous.get("selected"),
            "prior_construction_ms":0 if previous is None else previous.get("construction_ms",0)}


def _native_worker(payload):
    from self_selecting_sat import choose, realize, choose_composite
    n=payload["n"]
    clauses=payload["clauses"]
    if n > payload["max_source_vars"] or len(clauses) > payload["max_source_clauses"]:
        if payload.get("spn_fallback") and n <= payload["max_spn_vars"] and len(clauses) <= payload["max_spn_clauses"]:
            return _spn_worker(payload)
        return {"status":"UNKNOWN","reason":"native-input-admission-budget",
                "selected":"none","checked":0,"construction_ms":0,"execution_ms":0}
    if any(not clause for clause in clauses):
        return {"status":"UNSAT","reason":"explicit-original-empty-clause",
                "selected":"source-empty-clause","checked":0,"construction_ms":0,"execution_ms":0}
    start=perf_counter_ns()
    kwargs={"intention":"SAT", "maximum_coordinates":payload["max_coordinates"],
            "maximum_free":payload["max_free"],
            "partition_size":payload["partition_size"],
            "resolution_attempts":payload["resolution_attempts"],
            "self_refine":payload["self_refine"]}
    if payload["composite"]:
        # Composite native SAT returns component witnesses; only the entire
        # recomposed source assignment is accepted for a SAT certificate.
        ans=choose_composite(clauses,n,**kwargs)
        construct_ms=(perf_counter_ns()-start)/1e6
        if ans["status"] == "SAT":
            assignment=0
            for comp in ans["components"]:
                part=comp["local_result"]
                if part["status"] != "SAT" or part["witness"] is None:
                    raise ValueError("unqualified composite SAT component")
                raw=int(normalize_native_witness(part["witness"],len(comp["source_variables"])))
                for local,global_v in enumerate(comp["source_variables"]):
                    assignment |= ((raw>>local)&1) << (global_v-1)
            if not satisfies(clauses,assignment):
                raise ValueError("composite witness violates original CNF")
            witness=str(assignment)
        else: witness=None
        if ans["status"]=="UNKNOWN" and payload.get("spn_fallback"):
            return _spn_worker(payload, previous={"selected":"heterogeneous-composite",
                "checked":sum(c["local_result"]["checked"] for c in ans.get("components",[])),
                "construction_ms":construct_ms})
        return {"status":ans["status"],"reason":ans.get("reason",""),
                "selected":"composite:"+",".join(ans.get("selected",[])),
                "checked":sum(c["local_result"]["checked"] for c in ans.get("components",[])),
                "construction_ms":round(construct_ms,5),"execution_ms":0,
                "witness":witness,"components":len(ans.get("components",[])),
                "checked_source":True}
    plan=choose(clauses,n,**kwargs)
    constructed_ms=(perf_counter_ns()-start)/1e6
    start=perf_counter_ns()
    result=realize(plan,maximum_coordinates=payload["max_coordinates"],
                   partition_size=payload["partition_size"])
    execution_ms=(perf_counter_ns()-start)/1e6
    if result["status"]=="UNKNOWN" and payload.get("spn_fallback"):
        return _spn_worker(payload, previous={"selected":plan["selected"],
                "checked":result["checked"],"construction_ms":round(constructed_ms,5),
                "execution_ms":round(execution_ms,5)})
    return {"status":result["status"],"reason":result.get("reason",""),
            "selected":plan["selected"],"checked":result["checked"],
            "construction_ms":round(constructed_ms,5),
            "execution_ms":round(execution_ms,5),
            "witness":normalize_native_witness(result.get("witness"),n),
            "candidate_architectures":{k:{"status":v["status"],
                "registers":v["registers"],"coordinate_count":v["candidate_coordinates"]}
                for k,v in plan["constructive_candidates"].items()},
            "source_ground_verified":True}


def run_case(item, *, timeout=8.0, max_coords=65536, max_free=16,
             partition_size=1024, max_source_vars=64,
             max_source_clauses=400, self_refine=False, composite=False,
             exhaustive_n=15, resolution_attempts=500, spn_fallback=False,
             spn_nodes=8192, max_spn_vars=1024, max_spn_clauses=5000):
    n,clauses=item["n"],item["clauses"]
    check_cnf(n,clauses)
    known_witness=item.get("known_witness")
    if known_witness is not None and not satisfies(clauses,int(known_witness)):
        raise ValueError("fixture's planted witness fails source CNF")
    if type(timeout) not in (int,float) or timeout<=0:
        raise ValueError("worker timeout must be positive")
    source_id=sha({"n":n,"clauses":clauses})
    baseline_start=perf_counter_ns()
    reference=exhaustive_reference(n,clauses,maximum_vars=exhaustive_n)
    reference_ms=(perf_counter_ns()-baseline_start)/1e6
    if reference["status"] != "NOT_RUN" and item.get("expected") not in (None,reference["status"]):
        raise ValueError("fixture known status disagrees with exhaustive reference")
    payload={"n":n,"clauses":clauses,"max_coordinates":max_coords,"max_free":max_free,
             "partition_size":partition_size,"max_source_vars":max_source_vars,
             "max_source_clauses":max_source_clauses,"self_refine":self_refine,
             "composite":composite,"resolution_attempts":resolution_attempts,
             "spn_fallback":spn_fallback,"spn_nodes":spn_nodes,
             "max_spn_vars":max_spn_vars,"max_spn_clauses":max_spn_clauses}
    start=perf_counter_ns()
    if (n>max_source_vars or len(clauses)>max_source_clauses) and not (spn_fallback and n<=max_spn_vars and len(clauses)<=max_spn_clauses):
        result={"status":"UNKNOWN","reason":"native-input-admission-budget",
                "selected":"none","checked":0,"construction_ms":0,"execution_ms":0}
        elapsed_ms=(perf_counter_ns()-start)/1e6
    else:
      try:
        proc=subprocess.run([sys.executable, str(Path(__file__).resolve()),"_worker"],
                            input=json.dumps(payload),text=True,capture_output=True,
                            timeout=timeout,check=False)
        elapsed_ms=(perf_counter_ns()-start)/1e6
        if proc.returncode != 0:
            result={"status":"ERROR","reason":proc.stderr[-800:] or f"worker exit {proc.returncode}"}
        else:
            try: result=json.loads(proc.stdout)
            except (json.JSONDecodeError, TypeError):
                result={"status":"ERROR","reason":"worker did not provide JSON receipt"}
      except subprocess.TimeoutExpired:
        elapsed_ms=(perf_counter_ns()-start)/1e6
        result={"status":"UNKNOWN","reason":"worker-wallclock-timeout"}
    status=result["status"]
    if status not in ("SAT","UNSAT","UNKNOWN","ERROR"):
        raise ValueError("worker returned unsupported status")
    witness=result.get("witness")
    if status=="SAT":
        if witness is None or not isinstance(witness,str) or not witness.isdecimal():
            raise ValueError("SAT result without a canonical full source witness")
        bits=int(witness)
        if bits >= (1<<n) or not satisfies(clauses,bits):
            raise ValueError("SAT witness does not satisfy the original source")
    elif witness is not None:
        raise ValueError("non-SAT result carries a witness")
    if reference["status"] in ("SAT","UNSAT") and status in ("SAT","UNSAT") and reference["status"]!=status:
        raise ValueError("native result contradicts independent exhaustive source reference")
    if item.get("expected") in ("SAT","UNSAT") and status in ("SAT","UNSAT") and item["expected"]!=status:
        raise ValueError("native result contradicts independently constructed fixture")
    verified=("source-witness+exhaustive-reference" if status=="SAT" and reference["status"]=="SAT"
              else "source-witness" if status=="SAT"
              else "native-proof-replay+exhaustive-reference" if status=="UNSAT" and reference["status"]=="UNSAT"
              else "native-proof-or-complete-search-replay" if status=="UNSAT"
              else "no-decision-claim")
    if result.get("selected")=="source-empty-clause": verified="source-empty-clause"
    return {"id":item["id"],"origin":item.get("origin","external-DIMACS"),
            "source_variables":n,"source_clauses":len(clauses),
            "source_sha256":source_id,"expected_fixture_status":item.get("expected"),
            "status":status,"verification":verified,
            "wall_ms":round(elapsed_ms,5),"reference_ms":round(reference_ms,5),
            "reference_status":reference["status"],
            "reference_models":reference.get("model_count"),
            **result}


def run_suite(*, timeout=6., max_coords=65536, max_free=16,
              max_source_vars=64, max_source_clauses=400, self_refine=False,
              composite=False, ids=None, spn_fallback=False,spn_nodes=8192):
    cases=suite()
    if ids is not None:
        cases=[r for r in cases if r["id"] in set(ids)]
    records=[]
    started=perf_counter_ns()
    for item in cases:
        records.append(run_case(item,timeout=timeout,max_coords=max_coords,
                 max_free=max_free,max_source_vars=max_source_vars,
                 max_source_clauses=max_source_clauses,self_refine=self_refine,
                 composite=composite,spn_fallback=spn_fallback,spn_nodes=spn_nodes))
    return {"schema":VERSION,"suite":"seeded-3sat-challenge-01",
            "test_time_kind":"wall-clock single run; subprocess timeout; not a calibrated speedup",
            "configuration":{"timeout_seconds":timeout,"max_coordinates":max_coords,
                "max_free":max_free,"max_source_vars":max_source_vars,
                "max_source_clauses":max_source_clauses,"self_refine":self_refine,
                "composite":composite,"spn_fallback":spn_fallback,
                "spn_nodes":spn_nodes,"exhaustive_ref_vars":15},
            "elapsed_ms":round((perf_counter_ns()-started)/1e6,5),
            "results":records,
            "summary":{k:sum(1 for row in records if row["status"]==k)
                       for k in ("SAT","UNSAT","UNKNOWN","ERROR")}}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest="command",required=True)
    runner=sub.add_parser("suite",help="Run the deterministic bounded 3-SAT suite")
    runner.add_argument("--timeout",type=float,default=6.)
    runner.add_argument("--max-coordinates",type=int,default=65536)
    runner.add_argument("--max-free",type=int,default=16)
    runner.add_argument("--max-source-vars",type=int,default=64)
    runner.add_argument("--max-source-clauses",type=int,default=400)
    runner.add_argument("--refine",action="store_true")
    runner.add_argument("--composite",action="store_true")
    runner.add_argument("--spn-fallback",action="store_true",help="Recheck direct SPN-008 DPLL/XOR proof after SFI refuses")
    runner.add_argument("--spn-nodes",type=int,default=8192)
    runner.add_argument("--id",action="append",default=None)
    runner.add_argument("--output",type=Path)
    single=sub.add_parser("instance",help="Read DIMACS and try an exact source-verified decision")
    single.add_argument("file",type=Path)
    single.add_argument("--convert-wide",action="store_true")
    single.add_argument("--timeout",type=float,default=8.)
    single.add_argument("--max-coordinates",type=int,default=65536)
    single.add_argument("--max-source-vars",type=int,default=64)
    single.add_argument("--max-source-clauses",type=int,default=400)
    single.add_argument("--refine",action="store_true")
    single.add_argument("--composite",action="store_true")
    single.add_argument("--spn-fallback",action="store_true")
    single.add_argument("--spn-nodes",type=int,default=8192)
    single.add_argument("--output",type=Path)
    corpus=sub.add_parser("corpus",help="Benchmark bounded external DIMACS corpus")
    corpus.add_argument("folder",type=Path)
    corpus.add_argument("--limit",type=int,default=20)
    corpus.add_argument("--timeout",type=float,default=6.)
    corpus.add_argument("--max-coordinates",type=int,default=65536)
    corpus.add_argument("--max-source-vars",type=int,default=64)
    corpus.add_argument("--max-source-clauses",type=int,default=400)
    corpus.add_argument("--refine",action="store_true")
    corpus.add_argument("--composite",action="store_true")
    corpus.add_argument("--spn-fallback",action="store_true")
    corpus.add_argument("--spn-nodes",type=int,default=8192)
    corpus.add_argument("--output",type=Path)
    sub.add_parser("_worker",help=argparse.SUPPRESS)
    args=parser.parse_args(argv)
    if args.command=="_worker":
        body=json.load(sys.stdin)
        print(json.dumps(_native_worker(body),sort_keys=True))
        return 0
    if args.command=="suite":
        result=run_suite(timeout=args.timeout,max_coords=args.max_coordinates,
             max_free=args.max_free,max_source_vars=args.max_source_vars,
             max_source_clauses=args.max_source_clauses,
             self_refine=args.refine,composite=args.composite,ids=args.id,
             spn_fallback=args.spn_fallback,spn_nodes=args.spn_nodes)
    elif args.command=="corpus":
        if not 1<=args.limit<=500 or not args.folder.is_dir():
            raise ValueError("corpus requires a directory and 1..500 file limit")
        paths=sorted(p for p in args.folder.rglob("*") if p.is_file() and not p.is_symlink()
                     and p.name.lower().endswith((".cnf",".cnf.gz",".cnf.xz")))[:args.limit]
        rows=[]
        for path in paths:
            try:
                raw=parse_dimacs(read_cnf_file(path))
                row=run_case({"id":str(path.relative_to(args.folder)),"origin":"external-DIMACS",
                    "n":raw["n"],"clauses":raw["clauses"]},timeout=args.timeout,
                    max_coords=args.max_coordinates,max_source_vars=args.max_source_vars,
                    max_source_clauses=args.max_source_clauses,
                    self_refine=args.refine,composite=args.composite,
                    spn_fallback=args.spn_fallback,spn_nodes=args.spn_nodes)
                row["source_bytes_sha256"]=raw["bytes_sha256"]
            except (ValueError,OSError,EOFError,lzma.LZMAError) as exc:
                row={"id":str(path.relative_to(args.folder)),"status":"ERROR",
                     "reason":"input rejection: "+str(exc)}
            rows.append(row)
        result={"schema":VERSION,"corpus_root":str(args.folder),"profile":"native-source-qualified",
                "results":rows,"summary":{k:sum(r["status"]==k for r in rows)
                for k in ("SAT","UNSAT","UNKNOWN","ERROR")}}
    else:
        raw=parse_dimacs(read_cnf_file(args.file),allow_wide=args.convert_wide)
        n,clauses=raw["n"],raw["clauses"]
        original_n=n;original_clauses=clauses
        if args.convert_wide:
            n,clauses=to_three_cnf(n,clauses)
        result=run_case({"id":args.file.name,"origin":"input-DIMACS",
              "n":n,"clauses":clauses},timeout=args.timeout,
              max_coords=args.max_coordinates,max_source_vars=args.max_source_vars,
              max_source_clauses=args.max_source_clauses,
              self_refine=args.refine,composite=args.composite,
              spn_fallback=args.spn_fallback,spn_nodes=args.spn_nodes)
        if result["status"]=="SAT" and args.convert_wide:
            # Source projection must be explicit; the native witness is on 3-CNF.
            # Native result has 'witness' in the nested result record.
            witness=result["witness"]
            if witness is None or not satisfies(original_clauses,int(witness)&((1<<original_n)-1)):
                raise ValueError("transformed SAT model fails original source projection")
        result={"schema":VERSION,"source_bytes_sha256":raw["bytes_sha256"],
                "original_source_sha256":raw["source_sha256"],
                "source_original_vars":original_n,"converted_to_3cnf":args.convert_wide,
                "result":result}
    encoded=json.dumps(result,indent=2,sort_keys=True)+"\n"
    if args.output: args.output.write_text(encoded,encoding="utf8")
    else: print(encoded,end="")
    if (args.command in ("suite","corpus") and result["summary"]["ERROR"]):
        return 1
    if args.command=="instance" and result["result"]["status"]=="ERROR":
        return 1
    return 0


if __name__=="__main__":
    raise SystemExit(main())
