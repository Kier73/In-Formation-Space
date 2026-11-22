"""BENCH-01F pinned, disjoint external-cohort policy-admission campaign.

All twelve sources are from one exact upstream commit and Git blob identity.
Labels embedded in upstream paths are not solver evidence. First cohort trains,
second admits/rejects without final access, third is untouched until frozen.
"""
from __future__ import annotations
import argparse
from hashlib import sha256
import json
from pathlib import Path
from time import perf_counter_ns
from urllib.request import Request, urlopen
from bench01_3sat import parse_dimacs
from bench01_external import (CORPUS_REPO, CORPUS_COMMIT, git_blob_sha1,
                              run_cdcl, parent_accept_cdcl)
from bench01_policy import observed, train_policy, validate_and_freeze, evaluate_final, SCHEMA

SOURCE_TABLE = (
    # Training, selected before the policy is fitted.
    ("train-sat50-01", "sat_50_218/01.cnf", "9732bcb915dbb788fc6db5f336e9481e15cb4b8d", "training"),
    ("train-unsat50-01", "unsat_50_218/01.cnf", "9aa88f52c8a2bd54c58b0244861633b37d3ddffe", "training"),
    ("train-sat75-01", "sat_75_325/01.cnf", "5c224b84323ba90291a2c73275be488c87c182d8", "training"),
    ("train-unsat75-01", "unsat_75_325/01.cnf", "25bda60ac44c0188b3c044f90f3708067c0fc572", "training"),
    # Validation; train_policy must not inspect these.
    ("valid-sat50-02", "sat_50_218/02.cnf", "a37dfc28f0c7266cd4f6e00615ad35934b24b30e", "validation"),
    ("valid-unsat50-02", "unsat_50_218/02.cnf", "23b7c16f4bf468ba89a92c242dbcd7f5614d5a1c", "validation"),
    ("valid-sat75-02", "sat_75_325/02.cnf", "0a3d3b51d182d27b04e7a87f78bffaa5586c3518", "validation"),
    ("valid-unsat75-02", "unsat_75_325/02.cnf", "be3b6172bf86c25abfebe1690a0aca799207b675", "validation"),
    # Final untouched cohort.
    ("final-sat50-03", "sat_50_218/03.cnf", "b5496d32177b01757cedecf5a9ff6b81451075a1", "final"),
    ("final-unsat50-03", "unsat_50_218/03.cnf", "6c0fff4f0efc2230aeb28ebb2554967ae727303f", "final"),
    ("final-sat75-03", "sat_75_325/03.cnf", "30616616b63800da598c4558e29a3102b83fd9ac", "final"),
    ("final-unsat75-03", "unsat_75_325/03.cnf", "20495de1d6bfdeac99f4511c19cb8bd2dfc9d52c", "final"),
)

def catalog():
    return [dict(id=key,path=f"benchmarks/uniform_random_3-sat/{relative}",
                 blob_sha1=blob,cohort=cohort) for key,relative,blob,cohort in SOURCE_TABLE]

def verify_bytes(raw, entry):
    if not isinstance(raw,bytes) or len(raw)>64000 or git_blob_sha1(raw)!=entry["blob_sha1"]:
        raise ValueError("external source does not match its pinned blob")
    parsed=parse_dimacs(raw,max_bytes=64000)
    if (parsed["n"],len(parsed["clauses"])) not in ((50,218),(75,325)):
        raise ValueError("source cohort dimensions mismatch")
    return parsed

def obtain(entry,directory:Path,*,download=True):
    allowed={row["path"]:row["blob_sha1"] for row in catalog()}
    if entry["path"] not in allowed or allowed[entry["path"]]!=entry["blob_sha1"]:
        raise ValueError("unregistered external source")
    destination=directory/(entry["id"]+".cnf")
    directory.mkdir(parents=True,exist_ok=True)
    if destination.exists(): raw=destination.read_bytes()
    elif download:
        url=(f"https://raw.githubusercontent.com/{CORPUS_REPO}/{CORPUS_COMMIT}/"
             +entry["path"])
        with urlopen(Request(url,headers={"User-Agent":"IFS-BENCH01F/1.0"}),timeout=20) as response:
            raw=response.read(64001)
    else: raise FileNotFoundError(destination)
    parsed=verify_bytes(raw,entry)
    if not destination.exists():
        target=destination.with_suffix('.partial');target.write_bytes(raw);target.replace(destination)
    return {"id":entry["id"],"n":parsed["n"],"clauses":parsed["clauses"],
            "origin":"third-party-repo-immutable", "publisher_label_ignored":True}


def campaign(cache:Path,*,timeout=12.,spn_nodes=8192,download=True,with_cdcl=True):
    if not 1<=timeout<=120 or not 1<=spn_nodes<=100000:
        raise ValueError("invalid worker budget")
    stages={"training":[],"validation":[],"final":[]}
    source_provenance=[]
    started=perf_counter_ns()
    for entry in catalog():
        item=obtain(entry,cache,download=download)
        source_provenance.append({"id":entry["id"],"path":entry["path"],
          "sha1_git_blob":entry["blob_sha1"],"source_sha256":sha256((cache/(entry["id"]+".cnf")).read_bytes()).hexdigest(),
          "cohort":entry["cohort"]})
        stages[entry["cohort"]].append(observed(item,timeout=timeout,nodes=spn_nodes))
    candidate=train_policy(stages["training"])
    frozen=validate_and_freeze(candidate,stages["training"],stages["validation"])
    final=evaluate_final(frozen,stages["training"],stages["validation"],stages["final"])
    cdcl=[]
    if with_cdcl:
        for record in stages["final"]:
            comparison=run_cdcl(record["n"],record["clauses"],timeout=timeout)
            if comparison["accepted"]=="UNVERIFIED_UNSAT" and record["direct"]["status"]=="UNSAT":
                # Original clauses were independently refuted by SPN.
                comparison["accepted"]="UNSAT"
                comparison["reason"]="corroborated-by-source-replayed-SPN"
            if (comparison["accepted"] in ("SAT","UNSAT") and
                record["direct"]["status"] in ("SAT","UNSAT") and
                comparison["accepted"]!=record["direct"]["status"]):
                raise ValueError("external CDCL conflicts with checked SPN result")
            cdcl.append({"id":record["id"],"accepted":comparison["accepted"],
                         "wall_ms":comparison["wall_ms"],"reason":comparison["reason"]})
    return {"schema":SCHEMA,"cohort":"third-party-fixed-12-external-3SAT",
            "source_repository":CORPUS_REPO,"source_commit":CORPUS_COMMIT,
            "source_pins":source_provenance,
            "timing":"single measurements; includes worker and source verification; non-calibrated",
            "candidate":candidate,"frozen":frozen,"final":final,"cdcl_final":cdcl,
            "configuration":{"timeout_seconds":timeout,"spn_nodes":spn_nodes},
            "campaign_wall_ms":round((perf_counter_ns()-started)/1e6,5),
            "raw_source_checked_observations":stages}

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("cache",type=Path)
    p.add_argument("--timeout",type=float,default=12.)
    p.add_argument("--spn-nodes",type=int,default=8192)
    p.add_argument("--no-download",action="store_true")
    p.add_argument("--no-cdcl",action="store_true")
    p.add_argument("--output",type=Path)
    args=p.parse_args(argv)
    result=campaign(args.cache,timeout=args.timeout,spn_nodes=args.spn_nodes,
                    download=not args.no_download,with_cdcl=not args.no_cdcl)
    body=json.dumps(result,sort_keys=True,indent=2)+"\n"
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(body)
    print(json.dumps({"candidate_rules":result["candidate"]["selected_rules"],
         "admission":result["frozen"]["admission"],
         "frozen_rules":result["frozen"]["selected_rules"],
         "validation":result["frozen"]["validation"],"final":result["final"],
         "cdcl_final":result["cdcl_final"]},indent=2))
    return 0

if __name__=="__main__":raise SystemExit(main())
