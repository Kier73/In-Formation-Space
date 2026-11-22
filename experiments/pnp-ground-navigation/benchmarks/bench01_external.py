"""BENCH-01E: source-pinned external 3-SAT and production-CDCL comparison.

A reproducible comparison wrapper around existing BENCH-01/SFI/SPN execution,
not an independent SAT solver. SAT verdicts require original-CNF witnesses;
UNSAT claims from an external CDCL library are *not* proof-qualified unless
an independently checked SFI/SPN refutation is available. Timeouts are UNKNOWN.

Corpus pin: third-party GitHub commit + per-file Git blob SHA-1, plus downloaded
byte SHA-256 recorded in each run. Public sources are not part of the repo.
2026 SAT Competition official manifest is separately pinned as a *candidate*
source, not asserted to have been executed by this fixed small corpus campaign.
"""
from __future__ import annotations

import argparse
from hashlib import sha1, sha256
from importlib.metadata import PackageNotFoundError, version as package_version
import json
from pathlib import Path
import subprocess
import sys
from time import perf_counter_ns
from urllib.request import Request, urlopen

from bench01_3sat import parse_dimacs, read_cnf_file, run_case, satisfies

SCHEMA = "ifs.bench01.external-cdcl.v1"
CORPUS_REPO = "TimurIbrayev/SATsolver"
CORPUS_COMMIT = "b285082ead7a89f51f50c0dc3a937ddefa3328ee"
OFFICIAL_2026_REPO = "satcompetition/2026"
OFFICIAL_2026_COMMIT = "d2f8f186dacc48b9bab7e4374aef0a3f46b96582"
OFFICIAL_2026_MANIFEST = "downloads/track_main_2026.uri"
OFFICIAL_2026_BLOB = "2b86a4d685b492a844646f378ac3f3415fd131d5"
CDCL_PACKAGE = "python-sat"
CDCL_PACKAGE_VERSION = "1.9.dev13"
CDCL_ENGINE = "cadical195"
MAX_BYTES = 64_000
SOURCES = (
    ("sat50-a", "sat_50_218/01.cnf", "9732bcb915dbb788fc6db5f336e9481e15cb4b8d", "SAT"),
    ("unsat50-a", "unsat_50_218/01.cnf", "9aa88f52c8a2bd54c58b0244861633b37d3ddffe", "UNSAT"),
    ("sat50-b", "sat_50_218/02.cnf", "a37dfc28f0c7266cd4f6e00615ad35934b24b30e", "SAT"),
    ("unsat50-b", "unsat_50_218/02.cnf", "23b7c16f4bf468ba89a92c242dbcd7f5614d5a1c", "UNSAT"),
    ("sat75-a", "sat_75_325/01.cnf", "5c224b84323ba90291a2c73275be488c87c182d8", "SAT"),
    ("unsat75-a", "unsat_75_325/01.cnf", "25bda60ac44c0188b3c044f90f3708067c0fc572", "UNSAT"),
)


def manifest():
    return [dict(id=i, path=f"benchmarks/uniform_random_3-sat/{p}",
                 github_blob_sha1=h, publisher_label=label)
            for i,p,h,label in SOURCES]


def git_blob_sha1(raw: bytes) -> str:
    return sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()


def verify_source(raw: bytes, entry: dict):
    if not isinstance(raw, bytes) or len(raw) > MAX_BYTES or not raw:
        raise ValueError("over-budget or empty external source")
    if git_blob_sha1(raw) != entry["github_blob_sha1"]:
        raise ValueError("external source does not match GitHub's pinned blob")
    parsed = parse_dimacs(raw, max_bytes=MAX_BYTES)
    if parsed["n"] not in (50, 75) or len(parsed["clauses"]) not in (218,325):
        raise ValueError("pinned instance does not satisfy declared cohort shape")
    return parsed


def raw_url(entry):
    allowed = {x["path"] for x in manifest()}
    if entry["path"] not in allowed:
        raise ValueError("requested URL is not a pinned source")
    return f"https://raw.githubusercontent.com/{CORPUS_REPO}/{CORPUS_COMMIT}/{entry['path']}"


def fetch_one(entry: dict, directory: Path, *, timeout=20.):
    destination = directory / f"{entry['id']}.cnf"
    directory.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        parsed = verify_source(destination.read_bytes(), entry)
        return destination, parsed
    request = Request(raw_url(entry), headers={"User-Agent": "IFS-BENCH01-reproducible-source/1.0"})
    with urlopen(request, timeout=timeout) as response:
        raw = response.read(MAX_BYTES + 1)
    parsed = verify_source(raw, entry)
    temp = destination.with_suffix(".cnf.partial")
    try:
        temp.write_bytes(raw)
        temp.replace(destination)
    finally:
        temp.unlink(missing_ok=True)
    return destination, parsed


def model_to_bitset(model, n):
    """Never infer SAT from the solver's status or a partial invalid model."""
    if not isinstance(model, list) or not model:
        raise ValueError("CDCL SAT status has no valid model")
    seen = {}
    for lit in model:
        if type(lit) is not int or lit == 0 or abs(lit) > n:
            raise ValueError("CDCL returned a non-source variable")
        var = abs(lit)
        if var in seen and seen[var] != (lit > 0):
            raise ValueError("CDCL returned a contradictory model")
        seen[var] = lit > 0
    return sum(1 << (var-1) for var, val in seen.items() if val)


def _cdcl_worker(payload):
    """Worker does not verify its own UNSAT; parent decides publication status."""
    if payload.get("solver") != CDCL_ENGINE or set(payload) != {"solver", "n", "clauses"}:
        raise ValueError("invalid baseline worker protocol")
    n, clauses = payload["n"], payload["clauses"]
    # Native parser's strict semantics must cover the exact problem solved.
    from bench01_3sat import check_cnf
    check_cnf(n, clauses)
    try:
        import pysat.solvers
        installed = package_version(CDCL_PACKAGE)
    except (ModuleNotFoundError, PackageNotFoundError) as exc:
        raise RuntimeError("pinned python-sat package not installed") from exc
    if installed != CDCL_PACKAGE_VERSION:
        raise RuntimeError(f"unpinned CDCL package version: {installed}")
    start=perf_counter_ns()
    with pysat.solvers.Solver(name=CDCL_ENGINE, bootstrap_with=clauses) as solver:
        answer=solver.solve()
        model=solver.get_model() if answer is True else None
    elapsed=(perf_counter_ns()-start)/1e6
    if answer is True:
        bits=model_to_bitset(model, n)
        if not satisfies(clauses, bits):
            raise ValueError("CDCL model violates original source")
        return {"claim":"SAT", "model":str(bits), "engine_ms":round(elapsed,5),
                "worker_source_checked":True, "solver":CDCL_ENGINE, "package":installed}
    if answer is False:
        return {"claim":"UNSAT", "model":None, "engine_ms":round(elapsed,5),
                "worker_source_checked":False, "solver":CDCL_ENGINE, "package":installed}
    return {"claim":"UNKNOWN", "model":None, "engine_ms":round(elapsed,5),
            "worker_source_checked":False, "solver":CDCL_ENGINE, "package":installed}


def parent_accept_cdcl(payload, n, clauses, independently_verified_unsat=False):
    """Source-validate a CDCL result; never accept a bare UNSAT exit as a proof."""
    if not isinstance(payload,dict):
        raise ValueError("malformed CDCL worker output")
    claim=payload.get("claim")
    if claim not in ("SAT","UNSAT","UNKNOWN"):
        raise ValueError("CDCL worker did not return a supported result")
    if claim=="SAT":
        bit_text=payload.get("model")
        if (not isinstance(bit_text,str) or not bit_text.isdecimal() or
                bit_text!=str(int(bit_text)) or int(bit_text)>=(1<<n) or
                not satisfies(clauses,int(bit_text))):
            raise ValueError("parent refuses unsupported SAT witness")
        return "SAT", "original-source-witness"
    if payload.get("model") is not None:
        raise ValueError("non-SAT CDCL status carries a spurious model")
    if claim=="UNSAT":
        return ("UNSAT","independent-source-proof") if independently_verified_unsat else ("UNVERIFIED_UNSAT","no-independent-CDCL-UNSAT-proof")
    return "UNKNOWN", "no-decision-claim"


def run_cdcl(n, clauses, *, timeout=8.):
    payload={"solver":CDCL_ENGINE,"n":n,"clauses":clauses}
    start=perf_counter_ns()
    try:
        child=subprocess.run([sys.executable,str(Path(__file__).resolve()),"_cdcl_worker"],
              input=json.dumps(payload),text=True,capture_output=True,
              timeout=timeout,check=False)
    except subprocess.TimeoutExpired:
        return {"claim":"UNKNOWN","accepted":"UNKNOWN","reason":"subprocess-deadline",
                "wall_ms":round((perf_counter_ns()-start)/1e6,5)}
    wall=(perf_counter_ns()-start)/1e6
    if child.returncode:
        return {"claim":"ERROR","accepted":"ERROR", "reason":child.stderr[-1000:],
                "wall_ms":round(wall,5)}
    try:
        answer=json.loads(child.stdout)
        accepted,reason=parent_accept_cdcl(answer,n,clauses)
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        return {"claim":"ERROR","accepted":"ERROR", "reason":str(exc),
                "wall_ms":round(wall,5)}
    return {**answer,"accepted":accepted,"reason":reason,"wall_ms":round(wall,5)}


def compare_one(entry, raw, *, sfi_timeout=6., spn_timeout=8., cdcl_timeout=6.,
                spn_nodes=8192):
    source=verify_source(raw, entry)
    n,clauses=source["n"],source["clauses"]
    item={"id":entry["id"],"origin":"third-party-pinned-CNF", "n":n,"clauses":clauses}
    sfi=run_case(item,timeout=sfi_timeout,max_source_vars=80,max_source_clauses=400,
                 spn_fallback=False)
    spn=run_case(item,timeout=spn_timeout,max_source_vars=80,max_source_clauses=400,
                 spn_fallback=True,spn_nodes=spn_nodes)
    cdcl=run_cdcl(n,clauses,timeout=cdcl_timeout)
    if cdcl["accepted"] == "UNVERIFIED_UNSAT" and spn["status"]=="UNSAT":
        cdcl["accepted"]="UNSAT"
        cdcl["reason"]="corroborated-by-independent-SPN-proof"
    reference={"sfi":sfi["status"],"sfi_spn":spn["status"],"cdcl":cdcl["accepted"]}
    valid={x for x in reference.values() if x in ("SAT","UNSAT")}
    if len(valid)>1:
        raise ValueError("source-qualified SAT and UNSAT results conflict")
    return {"id":entry["id"],"source":{
               "repository":CORPUS_REPO,"commit":CORPUS_COMMIT,"path":entry["path"],
               "git_blob_sha1":entry["github_blob_sha1"],"sha256":source["bytes_sha256"],
               "semantic_sha256":source["source_sha256"],"variables":n,"clauses":len(clauses),
               "publisher_label_untrusted":entry["publisher_label"]},
            "sfi":sfi,"sfi_spn":spn,"cdcl":cdcl,
            "qualified_decisions":reference}


def campaign(directory, *, limit=4, timeout=6., nodes=8192, download=False):
    if not 1<=limit<=len(SOURCES):
        raise ValueError("invalid corpus limit")
    rows=[]
    for entry in manifest()[:limit]:
        destination=directory / f"{entry['id']}.cnf"
        if download:
            _,source=fetch_one(entry,directory)
            raw=destination.read_bytes()
        else:
            raw=destination.read_bytes()
            source=verify_source(raw,entry)
        rows.append(compare_one(entry,raw,sfi_timeout=timeout,
                                spn_timeout=timeout,cdcl_timeout=timeout,spn_nodes=nodes))
    return {"schema":SCHEMA,
            "sources":{"external_repository":CORPUS_REPO,"commit":CORPUS_COMMIT,
                       "official_2026_not_executed":{"repository":OFFICIAL_2026_REPO,
                           "commit":OFFICIAL_2026_COMMIT,
                           "manifest_path":OFFICIAL_2026_MANIFEST,
                           "git_blob_sha1":OFFICIAL_2026_BLOB}},
            "package":{"name":CDCL_PACKAGE,"version":CDCL_PACKAGE_VERSION,"solver":CDCL_ENGINE},
            "configuration":{"limit":limit,"timeout_each_seconds":timeout,
                             "spn_nodes":nodes,"source_limit_bytes":MAX_BYTES},
            "results":rows,
            "summary":{name:{k:sum(row[name]["status" if name!="cdcl" else "accepted"]==k for row in rows)
                      for k in ("SAT","UNSAT","UNKNOWN","UNVERIFIED_UNSAT","ERROR")}
                       for name in ("sfi","sfi_spn","cdcl")}}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest="mode",required=True)
    fetch=sub.add_parser("fetch",help="Download exact pinned third-party raw GitHub corpus")
    fetch.add_argument("directory",type=Path)
    fetch.add_argument("--limit",type=int,default=4)
    bench=sub.add_parser("compare",help="Run native SFI, SFI→SPN and pinned PySAT CaDiCaL")
    bench.add_argument("directory",type=Path)
    bench.add_argument("--limit",type=int,default=4)
    bench.add_argument("--timeout",type=float,default=6.)
    bench.add_argument("--spn-nodes",type=int,default=8192)
    bench.add_argument("--download",action="store_true")
    bench.add_argument("--output",type=Path)
    sub.add_parser("_cdcl_worker",help=argparse.SUPPRESS)
    args=parser.parse_args(argv)
    if args.mode=="_cdcl_worker":
        result=_cdcl_worker(json.load(sys.stdin));print(json.dumps(result,sort_keys=True));return 0
    if args.mode=="fetch":
        if not 1<=args.limit<=len(SOURCES):
            raise ValueError("invalid source limit")
        for entry in manifest()[:args.limit]:
            file,parsed=fetch_one(entry,args.directory)
            print(entry["id"],parsed["bytes_sha256"],parsed["n"],len(parsed["clauses"]),file)
        return 0
    if args.timeout<=0 or args.timeout>120 or args.spn_nodes<1:
        raise ValueError("invalid finite execution budget")
    answer=campaign(args.directory,limit=args.limit,timeout=args.timeout,
                    nodes=args.spn_nodes,download=args.download)
    encoded=json.dumps(answer,indent=2,sort_keys=True)+"\n"
    if args.output:
        args.output.write_text(encoded,encoding="utf-8")
    else:
        print(encoded,end="")
    if any("ERROR" in a.values() and a["ERROR"] for a in answer["summary"].values()):
        return 1
    return 0


if __name__=="__main__":
    raise SystemExit(main())
