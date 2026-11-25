"""Replay the generated proposals through the actual pinned VLM hosted core."""
import json
import subprocess
import sys
import ctypes as c
from pathlib import Path

root=Path(__file__).resolve().parent
native=Path(sys.argv[1]).resolve()
sys.path.insert(0,str(native))
from test_core import L,U,load
I=c.c_int32
L.graph_features.argtypes=[c.POINTER(I)]
L.graph_features.restype=c.c_int
L.try_ground_kind.argtypes=[U]
L.try_ground_kind.restype=U
L.discover_active.argtypes=[]
L.discover_active.restype=U

cases=json.loads(subprocess.check_output(["node",str(root/"clt011.js"),"--native-cases"]))
counts={"cases":0,"admitted":0,"rejected_nonzero":0,"fallback":0,"false_admission":0}
for case in cases:
    nodes,out=case["nodes"],case["out"]
    load(nodes,out)
    f=(I*6)()
    assert L.graph_features(f)
    assert list(f)==case["features"]
    label=L.discover_active()
    assert label==case["label"], (label,case["label"])
    load(nodes,out)
    proposed=case["proposal"]
    admitted=L.try_ground_kind(proposed)
    counts["cases"]+=1
    counts["admitted"]+=bool(admitted)
    counts["rejected_nonzero"]+=bool(proposed and not admitted)
    counts["false_admission"]+=bool(admitted and admitted!=label)
    if not admitted:
        counts["fallback"]+=1
        admitted=L.discover_active()
    assert admitted==label
assert counts["false_admission"]==0
print(json.dumps(counts,sort_keys=True))
