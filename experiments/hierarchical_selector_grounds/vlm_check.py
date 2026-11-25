"""Check the selector's decoded leaf sequences with actual pinned VLM-008/009."""
import json
import subprocess
import sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from byte_ground import Ground,Source
from compose_ground import Composite,certify,restore
from hashlib import sha256
cases=json.loads(subprocess.check_output(["node",str(Path(__file__).with_name("clt013.js")),"--native-cases"]))
checks=0
for case in cases:
    src=bytes(case["source"])
    def leaf(r):
        return Ground("ramp" if r["kind"]==2 else "period",r["n"],tuple(r["v"]) if r["kind"]==2 else (bytes(r["v"]),))
    original=Composite(tuple(map(leaf,case["records"])))
    transferred=Composite(tuple(map(leaf,case["candidateRecords"])))
    digest=sha256(src).hexdigest()
    assert certify(Source(src),transferred)==digest
    assert restore(original.encode(),digest).read(0,len(src))==src
    assert restore(transferred.encode(),digest).read(0,len(src))==src
    for i in range(0,len(src),127):
        j=min(i+257,len(src))
        assert transferred.total(i,j)==sum(src[i:j])
        checks+=1
print(json.dumps({"cases":len(cases),"native_range_checks":checks}))
