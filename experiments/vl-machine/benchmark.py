"""Deterministic experiment; timings are observations, not admission authority."""
import json
import random
from time import perf_counter_ns
from machine import *

def main():
    r=random.Random(128)
    xs=[r.getrandbits(32) for _ in range(256)]
    results=[]
    for depth in [1,8,128,512]:
        p=layered_affine(3,7,depth)
        m=Machine()
        t=perf_counter_ns()
        expected=[reference(p,x) for x in xs]
        ref_ns=perf_counter_ns()-t
        t=perf_counter_ns()
        plain=[m.observe(p,x) for x in xs]
        demand_ns=perf_counter_ns()-t
        t=perf_counter_ns()
        admission=m.learn(p)
        admission_ns=perf_counter_ns()-t
        t=perf_counter_ns()
        accelerated=[m.observe(p,x) for x in xs]
        ground_ns=perf_counter_ns()-t
        assert [x["output"] for x in plain]==expected==[x["output"] for x in accelerated]
        results.append({"depth":depth,"queries":len(xs),"reference_ns":ref_ns,
            "demand_ns":demand_ns,"candidate_ns":ground_ns,"admission_ns":admission_ns,
            "demand_word_ops":plain[0]["word_ops"],"candidate_word_ops":accelerated[0]["word_ops"],
            "admission":admission})
    print(json.dumps(results,indent=2))

if __name__=="__main__": main()
