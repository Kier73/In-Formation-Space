"""Train a tiny quantized policy on verifier-labelled synthetic graphs."""
import json
import numpy as np
from pathlib import Path
from test_neural import dataset,campaign

def main():
    examples=list(dataset(20261124,2000));x=np.array([e[2] for e in examples])/16;y=np.eye(3)[[e[3] for e in examples]]
    rng=np.random.default_rng(42);a=rng.normal(0,.4,(6,8));b=np.zeros(8);c=rng.normal(0,.4,(8,3));d=np.zeros(3)
    for _ in range(600):
        z=x@a+b;h=np.clip(z,0,7.9375);p=h@c+d;p=np.exp(p-p.max(axis=1,keepdims=True));p/=p.sum(axis=1,keepdims=True)
        err=(p-y)/len(x);dh=(err@c.T)*((z>0)&(z<7.9375));da=x.T@dh;db=dh.sum(axis=0);dc=h.T@err;dd=err.sum(axis=0)
        a-=.3*da;b-=.3*db;c-=.3*dc;d-=.3*dd
    w=np.concatenate([a.T.ravel(),np.zeros(64),b,c.T.ravel(),d]);w=np.clip(np.rint(w*16),-127,127).astype(int).tolist()
    artifact={'schema':'vlm-q4-rnn-v1','weights':w,'training_seed':20261124,'training_cases':2000,'optimizer_seed':42,'epochs':600}
    Path(__file__).with_name('policy_weights.json').write_text(json.dumps(artifact,sort_keys=True,separators=(',',':'))+'\n')
    print('train',campaign(w,20261124,2000));print('held-out',campaign(w,20261125,1000))
if __name__=='__main__':main()
