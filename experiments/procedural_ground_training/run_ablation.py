"""Ground-signal ablation: identical optimizer/model with relational evidence erased."""
import json
from pathlib import Path
import torch
import numpy as np
from procedural_ground_training import dataset,canonical,SCHEMA
from train_ground_model import GroundStudent,restore

def main():
    torch.set_num_threads(3);torch.manual_seed(73)
    x,y,_=dataset(4001,10000);xv,yv,_=dataset(4002,1500)
    xt,yt,_=dataset(4003,1500)
    x[:,:16]=0.;xv[:,:16]=0.;xt[:,:16]=0.
    xx=torch.from_numpy(x);yy=torch.from_numpy(y)
    model=GroundStudent();opt=torch.optim.AdamW(model.parameters(),lr=0.002,weight_decay=1e-4)
    count=np.bincount(y,minlength=9).astype(float)
    weight=torch.from_numpy((len(y)/(9*np.maximum(count,1))).astype(np.float32))
    criterion=torch.nn.CrossEntropyLoss(weight=weight)
    best=0.;beststate=None
    for ep in range(35):
        for idx in torch.randperm(len(xx)).split(256):
            opt.zero_grad();loss=criterion(model(xx[idx]),yy[idx]);loss.backward();
            torch.nn.utils.clip_grad_norm_(model.parameters(),3.)
            opt.step()
        with torch.no_grad():
            score=float((model(torch.from_numpy(xv)).argmax(1).numpy()==yv).mean())
        if score>best:
            best=score;beststate={k:v.clone() for k,v in model.state_dict().items()}
    model.load_state_dict(beststate)
    with torch.no_grad():
        masks=model(torch.from_numpy(xt)).argmax(1).numpy()
    p=float((masks==yt).mean())
    untrained=GroundStudent()
    with torch.no_grad():
        p0=float((untrained(torch.from_numpy(xt)).argmax(1).numpy()==yt).mean())
    trained,_=restore(Path(__file__).resolve().parent/'results')
    with torch.no_grad():
        pm=float((trained(torch.from_numpy(dataset(4003,1500)[0])).argmax(1).numpy()==yt).mean())
    report={'schema':SCHEMA+'.ablation','full_relational_student_accuracy':pm,
            'cost_only_student_accuracy':p,'untrained_random_student_accuracy':p0,
            'training_and_test_seed_same_as_main':True,
            'explanation':'cost-only masks the first 16 pairwise-difference and agreement features; it cannot observe the target relation of the Ground'}
    (Path(__file__).resolve().parent/'results'/'ablation-report.json').write_bytes(canonical(report))
    print(json.dumps(report,indent=2))
if __name__=='__main__': main()
