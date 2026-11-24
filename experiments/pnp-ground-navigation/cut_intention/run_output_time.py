"""CIG-022 campaign: nonlinear desired outputs over pairs of spatial cycles."""
import json, random, argparse
from math import lcm
from itertools import product
from run_temporal_ground import law, encode_law, step, timed, size, power_oracle
from temporal_ground import compile_transport, Navigator
from inverse_time import spatial_groups
from shared_proof import synthesize_shared, evaluate
from source_section import compile_section
from verify_temporal_ground import Receiver
from output_time import seek_outputs
from verify_output_time import verify_output_seek


def circuit_source(k, exprs, seed=222):
    """Independent input OR aliases, then a Boolean AST per output; shuffle source labels."""
    s=[];q=[];inputs=[];n=0
    for i in range(k):
        a,b,z=n+1,n+2,n+3;n+=3;q.append((a,b));inputs.append(z)
        s.extend([(-a,z),(-b,z),(a,b,-z)])
    def gate(op,a,b):
        nonlocal n
        n+=1;z=n
        for x,y,v in product((0,1),repeat=3):
            if v!=(x&y if op=='and' else x|y if op=='or' else x^y):
                s.append(tuple(-r if bit else r for r,bit in zip((a,b,z),(x,y,v))))
        return z
    def build(e):
        if type(e)is int:return inputs[e]
        op,a,b=e;return gate(op,build(a),build(b))
    fs=[(build(e),) for e in exprs]
    rng=random.Random(seed);labels=list(range(1,n+1));rng.shuffle(labels)
    def move(c):return tuple(sorted((labels[abs(v)-1]*(1 if v>0 else -1) for v in c),key=abs))
    s=list(map(move,s));rng.shuffle(s)
    return n,s,list(map(move,q)),list(map(move,fs))


def expr_eval(e,code):
    if type(e)is int:return code>>e&1
    op,a,b=e;x=expr_eval(a,code);y=expr_eval(b,code)
    return x&y if op=='and' else x|y if op=='or' else x^y


def fixture(k):
    w=3;ts,p,f,initial,P=law(k,w,long_period=True);g=compile_transport(ts,k,w)
    groups=spatial_groups(p);start=10**1000+173;desired=start+P//2
    nav=Navigator(k,w,g,{'contract':'fixture','circuit':{'gates':[],'outputs':[]}})
    code=nav.jump(initial,desired);nextcode=nav.jump(initial,desired+1)
    markers=[]
    for z in groups:
        a=next(i for i in z if code>>(w*i)&1)*w;b=next(i for i in z if nextcode>>(w*i)&1)*w
        markers.append((a,b))
    # True iff each of two cycles is at one of two selected phases and
    # their phase choices agree. XOR of A_first and B_second is true.
    exprs=[]
    for i in range(0,len(markers)-1,2):
        a,b=markers[i];c,d=markers[i+1]
        if a==b or c==d:raise ValueError('fixture requires nontrivial cycles')
        exprs.append(('and',('and',('or',a,b),('or',c,d)),('xor',a,d)))
    if len(markers)%2:exprs.append(markers[-1][0])
    # Additional output contradicts the first required output when true.
    exprs.append(('and',markers[0][0],markers[0][1]))
    n,s,q,fs=circuit_source(k,exprs);return n,s,q,fs,ts,g,p,f,initial,P,start,exprs,markers,desired


def oracle_time(periods,desired,start):
    # Independently combine one synchronized choice per pair by Bezout CRT.
    # This is fixture-specific; does not read decoder or proof factor tables.
    from math import gcd
    R=[(0,1)]
    for i in range(0,len(periods),2):
        L=lcm(*periods[i:i+2]);choices=[desired%L,(desired+1)%L] if i+1<len(periods) else [desired%L];new=[]
        for x,M in R:
            for y in choices:
                d=gcd(M,L)
                if (y-x)%d:continue
                # Euclidean modular inverse, independent of Python pow inverse.
                a,b=M//d,L//d;aa,bb=a,b;u,v=1,0
                while bb:qq=aa//bb;aa,bb=bb,aa%bb;u,v=v,u-qq*v
                joint=lcm(M,L);new.append(((x+M*((y-x)//d*u%b))%joint,joint))
        R=list(set(new))
    return min(start+(x-start)%m for x,m in R),len(R)


def trial(k):
    (n,s,q,fs,ts,g,p,f,initial,P,start,exprs,markers,desired),fixture_ms=timed(fixture,k)
    d,compile_ms=timed(synthesize_shared,n,s,q,fs);assert d['status']=='COMPLETE' and all(x['status']=='SUFFICIENT' for x in d['goals'])
    sec,section_ms=timed(compile_section,n,s,q);assert sec is not None
    receiver,admit_ms=timed(Receiver,n,s,q,fs,d,ts,3,g,initial,section=sec);nav=Navigator(k,3,g,d)
    targets=[1]*(len(fs)-1)+[None];r,ms=timed(seek_outputs,nav,initial,targets,start);assert r['status']=='FOUND',r.get('local_cells')
    ok,vs=timed(verify_output_seek,receiver,targets,start,r);assert ok
    t=int(r['time']);expected,classes=oracle_time([len(z) for z in spatial_groups(p)],desired,start);assert t==expected
    code=power_oracle(initial,k,3,p,f,t);assert r['terminal']['code']==str(code) and r['terminal']['outputs']==[expr_eval(e,code) for e in exprs]
    plain,plain_ms=timed(seek_outputs,nav,initial,targets,start,grouped=False);plain_ok,plain_vs=timed(verify_output_seek,receiver,targets,start,plain,grouped=False);assert plain_ok and plain['time']==r['time'] and plain['residues']==r['residues']
    bad=targets[:-1]+[1];no,nt=timed(seek_outputs,nav,initial,bad,start);assert no['status']=='UNREACHABLE';valid,nv=timed(verify_output_seek,receiver,bad,start,no);assert valid
    return dict(n=n,observed=k,clauses=len(s),period=str(P),outputs=len(fs),decoder_gates=len(d['circuit']['gates']),spatial_cycles=len(markers),factor_count=len(r['factors']),max_factor_period=max(x['period'] for x in r['factors']),coupled_factors=sum(len(x['groups'])>1 for x in r['factors']),local_cells=r['local_cells'],crt_pairs=r['pairs'],feasible_classes=classes,offset=str(t-start),fixture_ms=fixture_ms,decoder_compile_ms=compile_ms,section_ms=section_ms,admit_ms=admit_ms,seek_ms=ms,verify_ms=vs,receipt_bytes=size(r),ungrouped_cells=plain['local_cells'],ungrouped_pairs=plain['pairs'],ungrouped_seek_ms=plain_ms,ungrouped_verify_ms=plain_vs,unreachable_ms=nt,unreachable_verify_ms=nv,unreachable_cells=no['local_cells'],receipt=r)

def broad_control():
    k=174;n,s,q,fs,ts,g,p,f,initial,P,start,exprs,markers,desired=fixture(k)
    e=markers[0][0]
    for x,y in markers[1:]:e=('xor',e,x)
    n,s,q,fs=circuit_source(k,[e]);d,compile_ms=timed(synthesize_shared,n,s,q,fs)
    assert d['status']=='COMPLETE' and d['goals'][0]['status']=='SUFFICIENT'
    sec=compile_section(n,s,q);rec=Receiver(n,s,q,fs,d,ts,3,g,initial,section=sec);nav=Navigator(k,3,g,d)
    # The target is known reachable at a particular time (not necessarily earliest).
    witness=power_oracle(initial,k,3,p,f,desired);targets=[expr_eval(e,witness)]
    assert rec.accept(desired,nav.result(initial,desired))
    r,seek_ms=timed(seek_outputs,nav,initial,targets,start);assert r['status']=='UNKNOWN' and not verify_output_seek(rec,targets,start,r)
    return dict(n=n,observed=k,period=str(P),targets=targets,known_feasible_offset=str(desired-start),status=r['status'],estimated_cells=r['local_cells'],max_cells=2000000,decoder_compile_ms=compile_ms,seek_ms=seek_ms)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--sizes',nargs='+',type=int,default=[60,174,384,1023]);p.add_argument('--output',default='CIG-022-results.json');a=p.parse_args();d={'trials':[],'broad_control':None}
    for k in a.sizes:
        r=trial(k);d['trials'].append(r);open(a.output,'w').write(json.dumps(d,indent=2)+'\n');print({x:y for x,y in r.items() if x!='receipt'},flush=True)
    d['broad_control']=broad_control();open(a.output,'w').write(json.dumps(d,indent=2)+'\n');print(d['broad_control'],flush=True)
