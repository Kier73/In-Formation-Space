"""VLM-017: measured acquisition routes on resident local and IPC sources."""
import argparse,json,os,random,struct,time,multiprocessing as mp
from collections import Counter
from statistics import median
from pathlib import Path
from transfer_policy import portable,target_rows,PROBES,MASK,polynomial_affine,inspect
from intention_acquisition import symbolic_inspect
from experience_contract import canonical,digest,require,kernel,k1_law,k1_step

ROUTES=('inspect','proof','probe_first','inspect_first','two_probes')

def program(m,s):
    return m.Program(tuple(m.Node(op,tuple(args),v) for op,args,v in s['nodes']),s['output'])

def stress(m,seed,n):
    r=random.Random(seed)
    for i in range(n):
        a=r.getrandbits(32);b=r.getrandbits(32);nodes=[m.Node('input'),m.Node('const',value=a),m.Node('const',value=b)]
        if i%3==0: # nested conditional, outside the original topology
            nodes += [m.Node('lt',(0,1)),m.Node('select',(3,0,2))]
            # distinguish from prior conditional family by a nested add
            nodes += [m.Node('add',(4,2))]
        elif i%3==1: # exact identity obscured by bitwise syntax
            nodes += [m.Node('xor',(0,1)),m.Node('xor',(3,1)),m.Node('add',(4,2))]
        else: # degree-four modular null polynomial, with a nonlinear intermediate
            nodes += [m.Node('mul',(0,0)),m.Node('mul',(3,3)),m.Node('const',value=1<<31),m.Node('mul',(4,5)),m.Node('add',(6,2))]
        p=m.Program(tuple(nodes),len(nodes)-1);s={'family':'stress'+str(i%3),'nodes':[[v.op,list(v.args),v.value] for v in p.nodes],'output':p.output}
        row=inspect(p.identity,s,lambda x:m.reference(p,x),lambda a,b:polynomial_affine(m,p,a,b));row['polynomial_eligible']=row['eligible'];yield row

def worker(conn,sources):
    m=portable();ps=[program(m,s) for s in sources];conn.send_bytes(b'R')
    try:
        while True:
            data=conn.recv_bytes(8)
            if not data:break
            i,x=struct.unpack('<II',data);conn.send_bytes(struct.pack('<I',m.reference(ps[i],x)))
    finally:conn.close()

class Source:
    def __init__(self,m,rows,mode):
        start=time.perf_counter_ns()
        self.m=m;self.mode=mode;self.ps=[program(m,r['source']) for r in rows];self.conn=None;self.proc=None
        if mode=='ipc':
            ctx=mp.get_context('spawn');a,b=ctx.Pipe();self.conn=a;self.proc=ctx.Process(target=worker,args=(b,[r['source'] for r in rows]));self.proc.start();b.close();require(a.poll(10) and a.recv_bytes()==b'R','worker ready')
        self.setup_ns=time.perf_counter_ns()-start
    def close(self):
        if self.conn:
            self.conn.send_bytes(b'');self.conn.close();self.proc.join(10)
            if self.proc.is_alive():self.proc.terminate();self.proc.join();raise RuntimeError('worker shutdown')
            require(self.proc.exitcode==0,'worker failure')
    def observe(self,i,x):
        if self.mode=='local':return self.m.reference(self.ps[i],x)
        self.conn.send_bytes(struct.pack('<II',i,x));require(self.conn.poll(10),'worker timeout');return struct.unpack('<I',self.conn.recv_bytes(4))[0]

def execute(src,i,route,probes):
    counts=Counter();times=Counter();a=b=None;witness=None
    def timed(name,fn):
        t=time.perf_counter_ns();v=fn();times[name]+=time.perf_counter_ns()-t;counts[name]+=1;return v
    def observe(x):return timed('observe',lambda:src.observe(i,x))
    def basis():
        nonlocal a,b
        b=observe(0);a=(observe(1)-b)&MASK
    def probe(seq):
        nonlocal witness
        for x in seq:
            v=observe(x)
            if v!=((a*x+b)&MASK):witness=[x,v];return 'refuted'
        return 'unknown'
    def source_inspect():
        nonlocal a,b,witness
        r=timed('inspect',lambda:symbolic_inspect(src.m,src.ps[i]));a,b=r['a'],r['b'];witness=r.get('witness');return r['status']
    if route=='inspect':status=source_inspect()
    elif route=='proof':
        basis();status='certified' if timed('proof',lambda:polynomial_affine(src.m,src.ps[i],a,b)) else 'unknown'
    elif route=='inspect_first':
        status=source_inspect()
        if status=='unknown':basis();status=probe(probes[:1])
    elif route in ('probe_first','two_probes'):
        basis();status=probe(probes[:1] if route=='probe_first' else probes)
        if status=='unknown':status=source_inspect()
    else:raise ValueError('route')
    return {'status':status,'a':a,'b':b,'witness':witness},dict(counts),dict(times)

def learn_probes(rows):
    remaining=list(rows);out=[]
    for _ in range(2):
        i=max((i for i,x in enumerate(PROBES) if x not in out),key=lambda i:(sum(r['bad'][i] for r in remaining),-i));out.append(PROBES[i]);remaining=[r for r in remaining if not r['bad'][i]]
    return out

def bench(m,rows,mode,probes,repeats=5):
    require(repeats>=1,'repeats');src=Source(m,rows,mode);allstats={r:[] for r in ROUTES};evidence={};rng=random.Random(771)
    try:
        for rep in range(repeats):
            order=list(ROUTES);rng.shuffle(order)
            for route in order:
                totals=Counter();actions=Counter();counts=Counter();ev=[];start=time.perf_counter_ns()
                for i,row in enumerate(rows):
                    out,c,t=execute(src,i,route,probes);ev.append(out);counts[out['status']]+=1;actions.update(c);totals.update(t)
                elapsed=time.perf_counter_ns()-start
                # Check outside the timed section, against source and exact independent checker.
                for i,(row,out) in enumerate(zip(rows,ev)):
                    if out['status']=='certified':require(row['polynomial_eligible'] and (out['a'],out['b'])==(row['a'],row['b']),'false certificate')
                    if out['status']=='refuted':
                        x,v=out['witness'];require(m.reference(src.ps[i],x)==v and v!=((row['a']*x+row['b'])&MASK) and (out['a'],out['b'])==(row['a'],row['b']),'false witness')
                if route in evidence:require(evidence[route]==ev,'nondeterministic outcome')
                evidence[route]=ev;allstats[route].append({'elapsed_ns':elapsed,'action_ns':dict(totals),'actions':dict(actions),'status':dict(counts)})
    finally:src.close()
    report={}
    for route,samples in allstats.items():
        s=samples[0];require(all(x['actions']==s['actions'] and x['status']==s['status'] for x in samples),'nondeterministic counts')
        report[route]={'median_ns':int(median(x['elapsed_ns'] for x in samples)),'min_ns':min(x['elapsed_ns'] for x in samples),'max_ns':max(x['elapsed_ns'] for x in samples),'status':s['status'],'actions':s['actions'],'payload_bytes':12*s['actions'].get('observe',0) if mode=='ipc' else 0,'samples':samples}
    return {'setup_ns':src.setup_ns,'routes':report,'outcomes':evidence}

def select(report):
    # Fixed intention: maximize resolved cases, then minimize median measured latency.
    return min(ROUTES,key=lambda r:(report[r]['status'].get('unknown',0),report[r]['median_ns'],r))

def native_profile(root,repeats=5):
    """New K1 sources: compare equivalent certification scope, not all-program refutation."""
    k=kernel(root);r=random.Random(1705);rows=[]
    for i in range(240):
        o=r.randrange(4);other=(o+1)%4;p=[]
        for j in range(r.randrange(2,20)):
            d=r.randrange(4);p.append([r.choice(('add','mul','set')),d,r.getrandbits(32)])
        if i%3==1:p.append(['addr',o,other])
        elif i%3==2:p.append(['mulr',o,other])
        rows.append({'program':p,'observer':o})
    require(len({digest(s) for s in rows})==len(rows),'K1 duplicate')
    evidence=[]
    for s in rows:
        p,o=s['program'],s['observer'];observed=[]
        for x in (0,1):
            seed=[0]*4;seed[o]=x;out=k.evaluate(seed,p,1,mode='reference');require(out['status']==0 and out['registers']==k1_step(p,seed),'K1 reference');observed.append(out['registers'][o])
        law=k1_law(p,o);require(law is None or law==((observed[1]-observed[0])&MASK,observed[0]),'K1 law');evidence.append({'source':s,'basis':observed,'law':law})
    timings={'direct':[],'basis_then_check':[]};rng=random.Random(1706)
    for _ in range(repeats):
        order=list(timings);rng.shuffle(order)
        for route in order:
            t=time.perf_counter_ns();results=[]
            for s in rows:
                p,o=s['program'],s['observer']
                if route=='basis_then_check':
                    basis=[]
                    for x in (0,1):
                        seed=[0]*4;seed[o]=x;out=k.evaluate(seed,p,1,mode='reference');require(out['status']==0,'K1 execution');basis.append(out['registers'][o])
                law=k1_law(p,o)
                if route=='basis_then_check' and law is not None:require(law==((basis[1]-basis[0])&MASK,basis[0]),'K1 candidate')
                results.append(law)
            timings[route].append(time.perf_counter_ns()-t)
            require(results==[e['law'] for e in evidence],'K1 route disagreement')
    return {'programs':len(rows),'certified':sum(e['law'] is not None for e in evidence),'unknown':sum(e['law'] is None for e in evidence),'source_digest':digest(rows),'evidence':evidence,'routes':{n:{'samples_ns':v,'median_ns':int(median(v)),'observations':0 if n=='direct' else 480} for n,v in timings.items()}}

def campaign(root,repeats=5):
    m=portable();train=list(target_rows(m,1701,120));val=list(target_rows(m,1702,120));final=list(target_rows(m,1703,240));hard=list(stress(m,1704,120));seen=set()
    for rows in (train,val,final,hard):
        ids={r['id'] for r in rows};require(len(ids)==len(rows) and not seen&ids,'cohort overlap');seen|=ids
    probes=learn_probes(train);report={}
    for mode in ('local','ipc'):
        validation=bench(m,val,mode,probes,repeats);chosen=select(validation['routes']);held=bench(m,final,mode,probes,repeats);stress_result=bench(m,hard,mode,probes,repeats)
        report[mode]={'selected':chosen,'validation':validation,'final':held,'stress':stress_result}
    return {'schema':'vlm-measured-acquisition-v1','probes':probes,'cohorts':{'training':train,'validation':val,'final':final,'stress':hard},'cohort_digests':{k:digest(v) for k,v in [('training',train),('validation',val),('final',final),('stress',hard)]},'repeats':repeats,'report':report,'native_vlk':native_profile(root,repeats)}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);p.add_argument('--repeats',type=int,default=5);p.add_argument('--root',default=os.environ.get('VLK_ROOT'));a=p.parse_args();r=campaign(a.root,a.repeats);Path(a.output).write_bytes(canonical(r)+b'\n');print(json.dumps({k:{'selected':v['selected'],**{c:{n:{x:y for x,y in s.items() if x!='samples'} for n,s in v[c]['routes'].items()} for c in ('validation','final','stress')}} for k,v in r['report'].items()},indent=2))
