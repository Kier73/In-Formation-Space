"""Differentiable address softmax, with independent dense autograd control."""
import json,time
import torch
from address_attention import rectangles


def attention(q,k,v,p,stop):
    depth,radix,dk=k.shape
    logits=torch.einsum('bd,jad->bja',q,k)/dk**.5
    masses=[];values=[]
    for box in rectangles(0,stop,radix,depth):
        fields=[];sums=[];products=[]
        for j,(a,b) in enumerate(box):
            s=logits[:,j,a:b];w=torch.softmax(s,dim=-1)
            fields.append(torch.logsumexp(s,dim=-1));sums.append(w@v[j,a:b]);products.append(w@p[j,a:b])
        masses.append(torch.stack(fields).sum(0));values.append(torch.stack(sums).sum(0)+torch.stack(products).prod(0))
    return (torch.softmax(torch.stack(masses,dim=1),dim=1)[:,:,None]*torch.stack(values,dim=1)).sum(1)


def dense(q,k,v,p,stop):
    depth,radix,dk=k.shape;a=torch.arange(stop)
    digits=[(a//radix**(depth-j-1))%radix for j in range(depth)]
    keys=torch.stack([k[j,d] for j,d in enumerate(digits)]).sum(0)
    values=torch.stack([v[j,d] for j,d in enumerate(digits)]).sum(0)+torch.stack([p[j,d] for j,d in enumerate(digits)]).prod(0)
    return torch.softmax(q@keys.T/dk**.5,dim=-1)@values


def campaign():
    torch.set_num_threads(1);torch.manual_seed(90127)
    def params(radix):
        return [torch.randn((4,radix,d),dtype=torch.float64)*.3 for d in (8,4,4)]
    base=params(8);q=torch.randn(16,8,dtype=torch.float64);teacher=params(8);stops=(1,127,1023,4096)
    models=[[t.clone().requires_grad_() for t in base] for _ in range(2)]
    opt=[torch.optim.AdamW(m,lr=.01) for m in models];history=[]
    for i in range(24):
        stop=stops[i%len(stops)];target=dense(q,*teacher,stop);outputs=[];losses=[]
        for fn,m,o in zip((attention,dense),models,opt):
            out=fn(q,*m,stop);loss=(out-target).square().mean();o.zero_grad();loss.backward();outputs.append(out.detach());losses.append(float(loss.detach()))
        grad=max(float((a.grad-b.grad).abs().max()) for a,b in zip(*models))
        for o in opt:o.step()
        delta=max(float((a-b).detach().abs().max()) for a,b in zip(*models))
        history.append({'stop':stop,'output_error':float((outputs[0]-outputs[1]).abs().max()),'gradient_error':grad,'parameter_error':delta,'losses':losses})
    assert max(max(x['output_error'],x['gradient_error'],x['parameter_error']) for x in history)<1e-10
    # Learn a 24-bit factorized head without a dense activation tensor. Teacher is in the same family.
    teacher=params(64);m=[x.requires_grad_() for x in params(64)];opt=torch.optim.AdamW(m,lr=.025);qtrain=torch.randn(64,8,dtype=torch.float64);qtest=torch.randn(64,8,dtype=torch.float64)
    with torch.no_grad():ytrain=attention(qtrain,*teacher,64**4);ytest=attention(qtest,*teacher,64**4);initial=float((attention(qtest,*m,64**4)-ytest).square().mean())
    t=time.perf_counter_ns()
    for _ in range(100):
        loss=(attention(qtrain,*m,64**4)-ytrain).square().mean();opt.zero_grad();loss.backward();opt.step()
    elapsed=time.perf_counter_ns()-t
    with torch.no_grad():final=float((attention(qtest,*m,64**4)-ytest).square().mean())
    return {'trajectory':history,'max_output_error':max(x['output_error'] for x in history),'max_gradient_error':max(x['gradient_error'] for x in history),'max_parameter_error':max(x['parameter_error'] for x in history),'full_address_training':{'addresses':64**4,'parameters':sum(x.numel() for x in m),'updates':100,'train_queries':64,'heldout_queries':64,'initial_mse':initial,'final_mse':final,'training_ns':elapsed,'teacher':'same structured family; not dense pretrained attention'}}

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);a=p.parse_args();r=campaign();open(a.output,'w').write(json.dumps(r,indent=2)+'\n');print({k:v for k,v in r.items() if k!='trajectory'})
