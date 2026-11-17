"""Adversarial mutation of a freshly generated public-only CGS-008 transcript.

No root, receiver or observer private keys enter the independent verifier job.
Tampered signatures cannot be legitimately replaced there.
"""
from __future__ import annotations
import copy
import json
import sys
from pathlib import Path
import verify_authority as verify

def replay_mutations(bundle):
    verify.verify_bundle(bundle)
    mutations = [
        ("forged policy epoch",lambda b: b["policies"][1]["body"].__setitem__("version",3)),
        ("removed independent root signature",lambda b: b["policies"][1]["signatures"].pop()),
        ("duplicated root signature",lambda b: b["policies"][1]["signatures"].__setitem__(1,
            copy.deepcopy(b["policies"][1]["signatures"][0]))),
        ("unsigned revocation replacement",lambda b: b["policies"][1]["body"].__setitem__("revoked",[])),
        ("changed policy authority",lambda b: b["policies"][1]["body"]["grants"][1].__setitem__("observer","bob")),
        ("forged receiver checkpoint digest",lambda b: b["checkpoint2"]["body"].__setitem__("policy_digest","0"*64)),
        ("backdated receiver checkpoint",lambda b: b["checkpoint2"]["body"].__setitem__("last_time",0)),
        ("counter rollback",lambda b: b["checkpoint_after2"]["body"].__setitem__("counter",0)),
        ("wrong Ground",lambda b: b["request2"]["body"].__setitem__("ground","a"*64)),
        ("wrong challenge nonce",lambda b: b["receipts2"][0]["body"].__setitem__("nonce","c"*32)),
        ("wrong feature",lambda b: b["receipts2"][0]["body"].__setitem__("feature","full-state")),
        ("forged signed value",lambda b: b["receipts2"][0]["body"].__setitem__("value",0)),
        ("substitute revoked Bob",lambda b: b["receipts2"].__setitem__(1,copy.deepcopy(b["receipts1"][1]))),
        ("reused peer twice",lambda b: b["receipts2"].__setitem__(1,copy.deepcopy(b["receipts2"][0]))),
        ("mutated signed receipt commitment",lambda b: b["checkpoint_after2"]["body"].__setitem__("last_receipt","0"*64)),
    ]
    results=[]
    for title, mutate in mutations:
        trial=copy.deepcopy(bundle)
        mutate(trial)
        try:
            verify.verify_bundle(trial)
        except (ValueError, KeyError, TypeError, IndexError):
            results.append(title)
        else:
            raise AssertionError(f"CGS-008 independently accepted mutation: {title}")
    return {"public_bundle_source_verified":True,
            "mutated_unsigned_transcripts_rejected":len(results),
            "unrejected_transcripts":[],"negative_cases":results,
            "private_keys_received":False}

if __name__ == "__main__":
    data=json.loads(Path(sys.argv[1]).read_text(encoding="utf8"))
    print(json.dumps(replay_mutations(data),indent=2))
