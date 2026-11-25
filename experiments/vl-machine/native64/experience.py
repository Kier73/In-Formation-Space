"""VLM-011: bounded experience formation, behavior shapes and tool qualification."""
import json, random
from collections import Counter, defaultdict
from hashlib import sha256
from pathlib import Path
from struct import pack, iter_unpack
from template_ground import learn, qualify
from test_application import ins, execute, workload, CONST, BUILD, LEARN, PUBLISH, SPAWN, SEEK, READ, ADD, MUL, XOR, EMIT
from test_native_template import install, invoke
from test_core import MASK

ARMS=('arithmetic','navigate','compose','invalid')
ALL_ARMS=ARMS+('fork',)
PHASES=('train','validation','challenge','refine','refine_validation','final')
TARGET=12
ZERO='0'*64
NAMES=('CONST','BUILD','LEARN','PUBLISH','SPAWN','SEEK','READ','ADD','MUL','XOR','EMIT','POLICY')

def canonical(x):return json.dumps(x,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def digest(x):return sha256(canonical(x)).hexdigest()
def wire(code):return b''.join(pack('<6I',*[getattr(i,k) for k in ('op','d','a','b','lo','hi')]) for i in code)
def decode(p):return [ins(*a) for a in iter_unpack('<6I',p)]

def task(arm,phase,index):
    if arm not in ALL_ARMS or phase not in PHASES or type(index) is not int or not 0<=index<10000:raise ValueError('task address')
    r=random.Random(int(digest([arm,phase,index]),16));x,y,z=(r.getrandbits(32) for _ in range(3));t=r.getrandbits(64)
    return {'arm':arm,'phase':phase,'index':index,'x':x,'y':y,'z':z,'time':t,'time2':r.getrandbits(64)}

def construct(q):
    x,y,z,t=(q[k] for k in ('x','y','z','time'));arm=q['arm']
    if arm=='arithmetic':
        return [ins(CONST,0,lo=x),ins(CONST,1,lo=y),ins(CONST,2,lo=z),ins(ADD,3,0,1),ins(MUL,4,3,2),ins(XOR,5,4,0),ins(EMIT,a=5)]
    if arm=='navigate':
        return [ins(CONST,0,lo=x),ins(CONST,1,lo=y),ins(CONST,2,lo=z),ins(BUILD,a=0,b=1,lo=16),ins(LEARN,3),ins(PUBLISH,4),ins(SPAWN,5,4,2),ins(SEEK,a=5,lo=t&MASK,hi=t>>32),ins(READ,6,5),ins(EMIT,a=6)]
    if arm in ('compose','fork'):
        code=workload(x,t)
        if arm=='fork':
            q2=q['time2'];code[15]=ins(SEEK,a=9,lo=q2&MASK,hi=q2>>32)
        return code
    if arm=='invalid':return [ins(CONST,0,lo=x),ins(ADD,1,0,2),ins(EMIT,a=1)]
    raise ValueError('arm')

def reference(q):
    """Task-level oracle; no native verifier or generated instruction interpretation."""
    x,y,z,t=(q[k] for k in ('x','y','z','time'));arm=q['arm']
    if arm=='arithmetic':return [(((x+y)*z)&MASK)^x]
    # Independent affine power via a 2x2 triangular matrix multiplication.
    def power(a,b,n):
        p,q=1,0
        while n:
            if n&1:p,q=(p*a)&MASK,(p*b+q)&MASK
            a,b=a*a&MASK,(a*b+b)&MASK;n>>=1
        return p,q
    def at(a,b,depth,seed,time):
        a,b=power(a,b,depth);a,b=power(a,b,time);return (a*seed+b)&MASK
    if arm=='navigate':return [at(x,y,16,z,t)]
    if arm in ('compose','fork'):
        v=at(3,7,128,x,t);return [1,v,1,at(v,7,4,x,q['time2'] if arm=='fork' else t),v]
    if arm=='invalid':return None
    raise ValueError('arm')

def shape(p):
    """Sensor: preserve opcode/dependency and restricted immediates, mask free coordinates."""
    rows=[]
    for op,d,a,b,lo,hi in iter_unpack('<6I',p):
        rows.append((op,d,a,b,0 if op in (CONST,SEEK) else lo,0 if op==SEEK else hi))
    return digest(rows)

def observe(q):
    code=construct(q);p=wire(code);expected=reference(q);ok,out,_=execute(code)
    accepted=ok and expected is not None and out==expected
    status='verified' if accepted else 'expected_rejection' if not ok and expected is None else 'mismatch'
    if status=='mismatch':raise RuntimeError('native execution disagreed with task oracle')
    return {'task':q,'source_hex':p.hex(),'source_sha256':sha256(p).hexdigest(),'shape':shape(p),'tools':[NAMES[i.op] for i in code], 'route':'ordinary','native_ok':ok,'output':out,'reference':expected,'status':status}

class Ledger:
    def __init__(self):self.rows=[];self.head=ZERO;self.ids=set();self.sources=set()
    def add(self,row):
        q=row['task'];key=(q['arm'],q['phase'],q['index'])
        if key in self.ids or row['source_sha256'] in self.sources:raise ValueError('duplicate encounter/source')
        self.ids.add(key);self.sources.add(row['source_sha256']);body={'sequence':len(self.rows),'previous':self.head,'experience':row};self.head=digest(body);self.rows.append(body|{'digest':self.head})
    def write(self,path):Path(path).write_bytes(b''.join(canonical(r)+b'\n' for r in self.rows))

def replay(rows,expected_head):
    """Check chain and regenerate every task, source, route-independent expectation and native outcome."""
    l=Ledger()
    for row in rows:
        e=row['experience'];q=e['task'];fresh=task(q['arm'],q['phase'],q['index'])
        if fresh!=q:raise ValueError('task identity')
        observed=observe(fresh)
        # Final route evidence is checked by the separate catalogue replay below;
        # these rows are baseline encounters, not a claim about timing or host identity.
        if observed!=e:raise ValueError('experience mismatch')
        l.add(e)
        if l.rows[-1]!=row:raise ValueError('chain mismatch')
    if l.head!=expected_head:raise ValueError('head mismatch')
    return l

def form():
    """Initial skewed encounter stream, then request examples for observed deficits."""
    l=Ledger();indices=Counter();counts=Counter();warmup=Counter()
    def take(arm):
        i=indices[arm];indices[arm]+=1;e=observe(task(arm,'train',i));l.add(e);counts[arm]+=e['status']==('expected_rejection' if arm=='invalid' else 'verified')
    for arm in ['compose']*10+['arithmetic','navigate','invalid']:
        take(arm);warmup[arm]+=1
    # Negative controls receive a smaller budget; failed tasks are not positive examples.
    targets={a:(4 if a=='invalid' else TARGET) for a in ARMS}
    while any(counts[a]<targets[a] for a in ARMS):
        arm=max(ARMS,key=lambda a:targets[a]-counts[a]);take(arm)
    # Freeze the initial curriculum before encountering a changed workload.
    for arm in ARMS:
        for i in range(TARGET if arm!='invalid' else 4):l.add(observe(task(arm,'validation',i)))
    return l,dict(warmup),dict(counts)

def train_tools(rows,refined=False):
    groups=defaultdict(list);validation=defaultdict(list)
    for row in rows:
        e=row['experience'];phase=e['task']['phase']
        training=('train','refine') if refined else ('train',)
        checks=('validation','refine_validation') if refined else ('validation',)
        if e['status']=='verified' and phase in training+checks:
            (groups if phase in training else validation)[e['shape']].append(bytes.fromhex(e['source_hex']))
    catalogue={};decisions=[]
    for key,examples in sorted(groups.items()):
        v=validation[key]
        if len(examples)<2 or not v:continue
        candidate=learn(examples);qualified,cost=qualify(candidate,v)
        reason='not_economical';admitted=False
        if qualified is not None:
            try:g=install(qualified)
            except AssertionError:reason='native_rejected'
            else:
                # Native qualification on separate validation sources, exact output parity.
                for p in v:
                    instance=qualified.match(p)
                    if instance is None or invoke(g,instance.values)[:2]!=execute(decode(p))[:2]:raise RuntimeError('validation mismatch')
                catalogue[key]=qualified;reason='qualified';admitted=True
        decisions.append({'shape':key,'training':len(examples),'validation':len(v),'candidate_sha256':candidate.digest.hex(),'parameters':len(candidate.groups),'wire_bytes':len(candidate.encode()),'cost':cost,'admitted':admitted,'reason':reason})
    return catalogue,decisions

def evaluate(rows,catalogue):
    resident=None;generation=0;results=[];counts=Counter()
    for row in rows:
        e=row['experience']
        if e['task']['phase']!='final':continue
        p=bytes.fromhex(e['source_hex']);key=e['shape'];t=catalogue.get(key);inst=t.match(p) if t else None
        if inst is None:
            ok,out,_=execute(decode(p));route='ordinary';counts['ordinary']+=1
        else:
            if resident!=key:generation=install(t);resident=key;counts['installs']+=1
            ok,out,_=invoke(generation,inst.values);route='constructor';counts['constructor']+=1
            counts['parameter_bytes']+=len(inst.values)
        if (ok,out)!=(e['native_ok'],e['output']):raise RuntimeError('final mismatch')
        counts['verified']+=e['status']=='verified';counts['rejections']+=e['status']=='expected_rejection';counts['raw_instruction_bytes']+=len(p)
        results.append({'source_sha256':e['source_sha256'],'shape':key,'route':route,'tool_sha256':t.digest.hex() if inst else None,'native_ok':ok,'output':out})
    return dict(counts),results

def campaign():
    ledger,warmup,counts=form();initial,initial_decisions=train_tools(ledger.rows)
    # The challenge environment changes a relationship, not the structural shape.
    # A nonmatching learned tool triggers a request for fresh same-arm data.
    misses=[]
    for i in range(8):
        e=observe(task('fork','challenge',i));ledger.add(e)
        t=initial.get(e['shape']);p=bytes.fromhex(e['source_hex'])
        if t is None or t.match(p) is None:misses.append(e['source_sha256'])
    if misses:
        for phase in ('refine','refine_validation'):
            for i in range(TARGET):ledger.add(observe(task('fork',phase,i)))
    catalogue,decisions=train_tools(ledger.rows,refined=True)
    # Only now generate the final cohort; neither learner may consume it.
    for arm in ALL_ARMS:
        for i in range(32 if arm!='invalid' else 4):ledger.add(observe(task(arm,'final',i)))
    before,_=evaluate(ledger.rows,initial);evaluation,results=evaluate(ledger.rows,catalogue)
    runtime={name:sha256(Path(__file__).with_name(name).read_bytes()).hexdigest() for name in ('experience.py','application.c','core.c','core.h','template_ground.py','libcore.so')}
    return ledger,{'schema':'vlm-experience-v1','runtime_sha256':runtime,'head':ledger.head,'encounters':len(ledger.rows),'warmup':warmup,'training_counts':counts,'shapes':len({r['experience']['shape'] for r in ledger.rows}),'status':dict(Counter(r['experience']['status'] for r in ledger.rows)),'initial_decisions':initial_decisions,'challenge_misses':misses,'tool_decisions':decisions,'initial_evaluation':before,'evaluation':evaluation,'final_results_digest':digest(results),'final_results':results,'catalogue':{k:t.encode().hex() for k,t in catalogue.items()}}

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--ledger');parser.add_argument('--summary');args=parser.parse_args()
    l,report=campaign()
    if args.ledger:l.write(args.ledger)
    if args.summary:Path(args.summary).write_bytes(canonical(report)+b'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ('catalogue','final_results')},indent=2,sort_keys=True))
