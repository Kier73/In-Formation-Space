"""Reproduce GSM-005 acquisition budget sweep, separate from the scale benchmark."""
import json
import numpy as np
from interaction import MODELS,DESIGNS,learn

def run():
    out=[]
    for budget in (20,22,24,26,28,32):
        r=np.random.default_rng(501);counts={m:0 for m in ('active','rank','random')};errors={m:[] for m in counts}
        for i in range(21):
            edge=MODELS[i%7];src=DESIGNS[edge]@r.integers(-4,5,(DESIGNS[edge].shape[1],8));perm=r.permutation(256);pool=perm[:192];held=perm[192:]
            for mode in counts:
                e,c,tr=learn(lambda j:src[j].copy(),pool,pool[:12],budget,mode,i+700);pred=DESIGNS[e]@np.rint(c);counts[mode]+=int(np.array_equal(src,pred));errors[mode].append(float(np.mean((pred[held]-src[held])**2)))
        out.append({'budget':budget,'exact':counts,'heldout_mse':{m:float(np.mean(v)) for m,v in errors.items()}})
    return out

if __name__=='__main__':
    print(json.dumps(run(),indent=2))
