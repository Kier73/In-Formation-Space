"""PGT-004: model-guided semantic observations over actual HTTP and stdio paths.

Imports PGT-003 trained neural policy, existing COG-009 signer/key enrollment,
existing signed-query witness verification and offline recovery. Does not
introduce an E-CPU Hypervisor/IOS-003 authority or promote a candidate Ground.
"""
from __future__ import annotations
import base64,hashlib,json,secrets,subprocess,sys,time
from pathlib import Path
from urllib.parse import quote,urlsplit
from urllib.request import Request,build_opener,HTTPRedirectHandler
from urllib.error import URLError,HTTPError
from cognitive_grounds import canonical,digest,GroundRefused
from signed_query_path import SignedObserverPath,verify_frame,recover
from query_worker import KIND
from decision_experiment import Context,ALL,split,terminal,H,indices
from train_policy import propose

SCHEMA='ifs.pgt004.semantic-cross-path.v1'

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):raise ValueError('HTTP redirects not admitted')

class HTTPPeer:
    """One *local* HTTP observer subprocess and its independently enrolled key."""
    transport='http-observer'
    def __init__(self,host,cmd,price=lambda q:5):
        self.host=host;self.command=list(cmd);self.price=price;self.proc=None;self.port=None;self.calls=0;self.bytes=0
        self.evidence=[]
    def start(self):
        if self.proc is not None:raise ValueError('already started')
        self.proc=subprocess.Popen(self.command,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,bufsize=0)
        assert self.proc.stdout is not None
        import selectors
        with selectors.DefaultSelector() as sel:
            sel.register(self.proc.stdout,selectors.EVENT_READ)
            if not sel.select(4):raise GroundRefused('HTTP observer start timeout')
        line=self.proc.stdout.readline(100)
        if not line.startswith(b'LISTEN_PORT='):raise GroundRefused('HTTP observer failed to start')
        self.port=int(line.split(b'=')[1]);assert 1<=self.port<=65535
    def stop(self,kill=False):
        if self.proc is None:return
        if self.proc.poll() is None:
            self.proc.kill() if kill else self.proc.terminate()
            try:self.proc.wait(timeout=2)
            except subprocess.TimeoutExpired:self.proc.kill();self.proc.wait(timeout=2)
        if self.proc.stdout:self.proc.stdout.close()
        self.proc=None;self.port=None
    def alive(self):return self.proc is not None and self.proc.poll() is None
    def request(self,body):
        if not self.alive():raise GroundRefused('HTTP observer unavailable')
        raw=canonical(body)
        if len(raw)>1024:raise GroundRefused('HTTP request exceeded budget')
        token=base64.urlsafe_b64encode(raw).decode('ascii').rstrip('=')
        url='http://127.0.0.1:'+str(self.port)+'/v1/observe?request='+token
        assert urlsplit(url).hostname=='127.0.0.1'
        req=Request(url,method='GET',headers={'Accept':'application/vnd.ifs.signed-observation+json'})
        try:
            start=time.monotonic_ns()
            with build_opener(NoRedirect()).open(req,timeout=3.0) as response:
                if response.status!=200 or response.headers.get('Content-Type')!='application/vnd.ifs.signed-observation+json' or response.headers.get('Cache-Control')!='no-store':raise GroundRefused('HTTP response contract differs')
                clen=response.headers.get('Content-Length')
                if clen is None or not clen.isdecimal() or not 0<int(clen)<=4096:raise GroundRefused('HTTP response length invalid')
                payload=response.read(4097)
                if len(payload)!=int(clen):raise GroundRefused('HTTP response length mismatch')
                etag=response.headers.get('ETag')
                if etag!='"'+hashlib.sha256(payload).hexdigest()+'"':raise GroundRefused('HTTP ETag/bytes digest mismatch')
                elapsed=time.monotonic_ns()-start
        except (URLError,HTTPError,OSError) as exc:raise GroundRefused('HTTP origin unavailable or rejected request') from exc
        try:frame=json.loads(payload)
        except ValueError as exc:raise GroundRefused('malformed HTTP observation') from exc
        if canonical(frame)!=payload:raise GroundRefused('noncanonical HTTP response')
        self.calls+=1;self.bytes+=len(payload)
        entry={'transport':self.transport,'host':self.host.name,'coordinate':body['coordinate'],
               'request_digest':hashlib.sha256(raw).hexdigest(),
               'frame_sha256':hashlib.sha256(payload).hexdigest(),
               'etag':etag,'status':200,'body_bytes':len(payload),'elapsed_ns':elapsed,
               'cache_control':'no-store'}
        self.evidence.append(entry)
        return frame

class StdioPeer:
    transport='signed-stdio'
    def __init__(self,peer,price=lambda q:5):self.peer=peer;self.host=peer.host;self.price=price;self.evidence=[]
    def start(self):self.peer.start()
    def stop(self,kill=False):self.peer.stop(kill=kill)
    def alive(self):return self.peer.proc is not None and self.peer.proc.poll() is None
    def request(self,body):
        start=time.monotonic_ns();frame=self.peer.request(body);elapsed=time.monotonic_ns()-start
        raw=canonical(frame)
        self.evidence.append({'transport':self.transport,'host':self.host.name,'coordinate':body['coordinate'],
            'request_digest':hashlib.sha256(canonical(body)).hexdigest(),'frame_sha256':hashlib.sha256(raw).hexdigest(),
            'body_bytes':len(raw),'elapsed_ns':elapsed})
        return frame

class MixedPathGround(SignedObserverPath):
    """Reuses PGT-003's cryptographic witness format and recovery, but stops on quorum.

    Each requested coordinate is a typed semantic input. The preferred paths
    can differ by coordinate, and their changing availability affects the
    advisory neural query policy. No result is admitted merely by this quorum.
    """
    def __init__(self,root,peers):
        super().__init__(root,peers)
        self.transport_log=[];self.route_attempts=0
    def prices(self,allowed=None):
        choices=self.peers if allowed is None else tuple(p for p in self.peers if p.host.name in allowed)
        prices=[]
        for q in range(8):
            vals=sorted((int(p.price(q)) for p in choices if p.alive()))
            prices.append(min(40,sum(vals[:2])) if len(vals)>=2 else 40)
        return tuple(max(1,x) for x in prices)
    def read(self,q):
        if type(q)!=int or not 0<=q<8:raise ValueError('invalid coordinate')
        if q in self.observed:return self.observed[q]
        votes={}
        # Earlier receipt votes are retained and can aid recovery, never rewound.
        for event in self.events:
            req=event['request'];v=event['frame']['body']['value']
            if req['coordinate']==q:
                peer=next(p for p in self.peers if p.host.name==req['host'])
                verify_frame(event['frame'],req,peer.host)
                old=votes.get(peer.host.name)
                if old is not None and old!=v:raise ValueError('source equivocation')
                votes[peer.host.name]=v
        for val in (0,1):
            if list(votes.values()).count(val)>=2:self.observed[q]=val;return val
        for peer in sorted(self.peers,key=lambda p:(p.price(q),p.host.name)):
            if peer.host.name in votes:continue
            req={'kind':KIND,'host':peer.host.name,'nonce':secrets.token_hex(16),
                 'root':self.source_root,'coordinate':q}
            try:frame=peer.request(req)
            except GroundRefused:continue
            # Verify against the actual independently created challenge, never
            # a nonce supplied or reflected by the untrusted receiver.
            verify_frame(frame,req,peer.host)
            self.request_calls+=1;votes[peer.host.name]=frame['body']['value']
            event={'index':len(self.events),'previous':self.head,'request':req,'frame':frame}
            self.events.append({**event,'digest':digest(event)})
            self.transport_log.append(peer.evidence[-1])
            for val in (0,1):
                if list(votes.values()).count(val)>=2:self.observed[q]=val;return val
        raise GroundRefused('unknown: no two enrolled agreeing observers')
    def export_paths(self):
        record={'schema':SCHEMA,'roster':self.roster_digest,'head':self.head,
                'events':self.transport_log,'witness_ledger':self.export()}
        return {**record,'digest':digest(record)}

def recover_paths(bundle,trust):
    if set(bundle)!={'schema','roster','head','events','witness_ledger','digest'} or bundle['schema']!=SCHEMA:raise ValueError('path bundle invalid')
    if digest({k:v for k,v in bundle.items() if k!='digest'})!=bundle['digest'] or bundle['head']!=trust['head'] or bundle['roster']!=trust['roster_digest']:raise ValueError('external path pin changed')
    from multi_observer_fabric import Host
    hosts=[Host(a['name'],a['key'],a['cost']) for a in trust['hosts']]
    accepted=recover(bundle['witness_ledger'],trust['source_root'],hosts,trust['roster_digest'],trust['head'])
    events=bundle['witness_ledger']['events']
    if len(events)!=len(bundle['events']):raise ValueError('transport receipt count differs')
    for event,path in zip(events,bundle['events']):
        frame_raw=canonical(event['frame']);req=event['request']
        if path['host']!=req['host'] or path['coordinate']!=req['coordinate'] or path['frame_sha256']!=hashlib.sha256(frame_raw).hexdigest() or path['request_digest']!=hashlib.sha256(canonical(req)).hexdigest() or path['body_bytes']!=len(frame_raw):raise ValueError('path receipt does not match signed witness')
        if path['transport']=='http-observer':
            if path['status']!=200 or path['cache_control']!='no-store' or path['etag']!='"'+path['frame_sha256']+'"':raise ValueError('HTTP representation metadata changed')
        elif path['transport']!='signed-stdio':raise ValueError('unknown transport representation')
    return {**accepted,'http_reads':sum(p['transport']=='http-observer' for p in bundle['events']),
            'stdio_reads':sum(p['transport']=='signed-stdio' for p in bundle['events']),
            'bytes_observed':sum(p['body_bytes'] for p in bundle['events']),
            'elapsed_ns_observed':sum(p['elapsed_ns'] for p in bundle['events'])}


def navigate(model,ctx,ground,max_steps=6):
    """Model proposes query only; Ground verifier publishes only witnessed target."""
    mask=ALL;used=0;queries=[];candidate=None
    for step in range(max_steps):
        if terminal(ctx,mask):break
        # Ground-conditioned *physical-path* estimate plus the task's own
        # symbolic observation price. The trained model sees a unified cost
        # projection, but neither transport identity nor its claims confer truth.
        paths=ground.prices()
        costs=tuple(min(40,paths[q]+ctx.costs[q]) for q in range(8))
        advised=Context(ctx.target,costs,ctx.weights)
        q=propose(model,advised,mask,used)
        if q is None:break
        try:v=ground.read(q)
        except GroundRefused as exc:
            queries.append({'q':q,'status':'unknown','reason':str(exc)});break
        used|=1<<q;mask=split(mask,q)[v]
        queries.append({'q':q,'v':v,'status':'witnessed','route_cost_units':costs[q]})
        if not mask:break
    if mask and terminal(ctx,mask):candidate=int(H[indices(mask)[0],ctx.target])
    # No finite-source law is admitted to the receiver in this experiment.
    # Even a confident candidate cannot be published as source truth.
    if ctx.target not in ground.observed:
        try:ground.read(ctx.target)
        except GroundRefused:return {'status':'UNKNOWN','candidate':candidate,'result':None,'queries':queries,
                                    'proof':'target not independently witnessed'}
    return {'status':'WITNESSED_NOT_GROUND_ADMITTED','result':ground.observed[ctx.target],
            'candidate':candidate,'queries':queries,'proof':'two-enrolled-key-reports-not-source-truth'}
