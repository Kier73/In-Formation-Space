"""Generate a controlled pre-attention K/V observation using actual trained GSM-001 weights."""
import argparse,hashlib
from pathlib import Path
import numpy as np
import torch
from torch.nn import functional as F
PIN='eb9c2eb010deb2826859a6b42d38e74adbd8a3f6ae04ecfb2287b68469d40465'

def observe(path):
    if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=PIN:raise ValueError('checkpoint identity')
    d=torch.load(path,map_location='cpu',weights_only=True)
    # Candidate feature tuple (key0=0,key1=0,payload=b,offset=0,match=1,role=0).
    h=d['byte.weight'].double()+2*d['byte.weight'][0].double()+d['offset.weight'][0].double()+d['sensor.weight'][1].double()+d['role.weight'][0].double()
    h=F.layer_norm(h,(32,),d['block.norm1.weight'].double(),d['block.norm1.bias'].double())
    z=F.linear(h,d['block.self_attn.in_proj_weight'].double(),d['block.self_attn.in_proj_bias'].double())
    return torch.cat([z[:,32:40],z[:,64:72]],dim=1).numpy()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('checkpoint');p.add_argument('output');a=p.parse_args();np.save(a.output,observe(a.checkpoint),allow_pickle=False)
