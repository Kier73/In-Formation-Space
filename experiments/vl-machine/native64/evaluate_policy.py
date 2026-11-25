"""Compare the trained selector with a feature lookup and exact fallback."""
from collections import Counter,defaultdict
import ctypes as c
import json
from time import perf_counter_ns
from test_neural import L,U,I,load,model,install,dataset

def main():
    train=defaultdict(Counter)
    for _,_,x,y in dataset(20261124,2000):train[tuple(x)][y]+=1
    lookup={x:max(range(3),key=lambda k:counts[k]) for x,counts in train.items()}
    cases=list(dataset(20261125,1000));install(model())
    report={name:{'admitted':0,'false_admission':0,'elapsed_ns':0,'fallbacks':0} for name in ('exact','neural','lookup','neural_fallback')}
    collisions=defaultdict(Counter)
    for p,o,x,y in cases:collisions[tuple(x)][y]+=1
    for name,record in report.items():
        for p,o,x,y in cases:
            load(p,o);a,b=U(),U();features=(I*6)()
            start=perf_counter_ns()
            if name=='exact':admitted=L.discover_active()
            elif name=='lookup':
                assert L.graph_features(features);admitted=L.try_ground_kind(lookup.get(tuple(features),0))
            else:
                assert L.nn_policy(c.byref(a),c.byref(b));admitted=b.value
                if name=='neural_fallback' and not admitted:
                    record['fallbacks']+=1;admitted=L.discover_active()
            record['elapsed_ns']+=perf_counter_ns()-start
            record['admitted']+=bool(admitted);record['false_admission']+=bool(admitted and admitted!=y)
    assert report['exact']['admitted']==report['neural_fallback']['admitted']
    assert not any(r['false_admission'] for r in report.values())
    print(json.dumps({'cases':len(cases),'training_feature_classes':len(train),'heldout_feature_classes':len(collisions),'ambiguous_heldout_classes':sum(len(v)>1 for v in collisions.values()),'feature_accuracy_upper_bound':sum(max(v.values()) for v in collisions.values()),'routes':report},indent=2,sort_keys=True))
if __name__=='__main__':main()
