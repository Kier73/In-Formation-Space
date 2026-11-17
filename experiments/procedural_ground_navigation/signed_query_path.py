"""PGT-003 adapter to COG-009's real subprocess and enrolled-key identities.

Ed25519 attests *which enrolled process key signed an observation*. Agreement
is not a correctness proof, public-key enrollment not a host attestation, and
this local stdio transport is not an E-CPU mutual-TLS / Hypervisor grant.
"""
from __future__ import annotations
import base64,hashlib,json,secrets
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cognitive_grounds import canonical,digest,GroundRefused
from multi_observer_fabric import Host,HostProcess
from query_worker import KIND,REPLY

SCHEMA='ifs.pgt003.signed-finite-observation.v1'

def refute(msg):raise ValueError(msg)

def verify_frame(frame,req,host):
    if type(frame)!=dict or set(frame)!={'body','signature'} or type(frame['body'])!=dict:refute('unsigned frame')
    b=frame['body']
    if set(b)!={'kind','host','nonce','root','coordinate','value','request_digest','boot','key_id'}:refute('unexpected frame fields')
    if b['kind']!=REPLY or b['host']!=host.name or b['nonce']!=req['nonce'] or b['root']!=req['root'] or b['coordinate']!=req['coordinate'] or b['request_digest']!=hashlib.sha256(canonical(req)).hexdigest() or b['key_id']!=host.key_id or type(b['boot'])!=str or len(b['boot'])!=32 or type(b['value'])!=int or b['value'] not in (0,1):refute('signed request correlation invalid')
    try:
        sig=base64.b64decode(frame['signature'],validate=True)
        if len(sig)!=64:refute('signature length invalid')
        host.public.verify(sig,hashlib.sha256(canonical(b)).digest())
    except Exception as exc:raise ValueError('signature invalid') from exc
    return b['value']

class SignedObserverPath:
    def __init__(self,source_root,peers):
        self.source_root=source_root
        self.peers=tuple(peers)
        if type(source_root)!=str or len(source_root)!=64 or len(self.peers)<2 or len({p.host.key_id for p in self.peers})!=len(self.peers):refute('source identity/roster invalid')
        self.events=[];self.observed={};self.request_calls=0
    @property
    def roster(self):return [p.host for p in self.peers]
    @property
    def roster_digest(self):return digest([(h.name,h.key_id,h.cost) for h in sorted(self.roster,key=lambda h:h.name)])
    @property
    def genesis(self):return digest({'schema':SCHEMA,'source_root':self.source_root,'roster_digest':self.roster_digest})
    @property
    def head(self):return self.events[-1]['digest'] if self.events else self.genesis
    def read(self,q):
        if type(q)!=int or not 0<=q<8:refute('invalid coordinate')
        if q in self.observed:return self.observed[q]
        votes={}
        for peer in self.peers:
            req={'kind':KIND,'host':peer.host.name,'nonce':secrets.token_hex(16),'root':self.source_root,'coordinate':q}
            try:frame=peer.request(req)
            except GroundRefused:continue  # unavailable host is not affirmative evidence
            v=verify_frame(frame,req,peer.host);self.request_calls+=1;votes[peer.host.name]=v
            event={'index':len(self.events),'previous':self.head,'request':req,'frame':frame}
            self.events.append({**event,'digest':digest(event)})
        accepted=[val for val in (0,1) if list(votes.values()).count(val)>=2]
        if len(accepted)!=1:raise ValueError('insufficient enrolled-source agreement')
        val=accepted[0];self.observed[q]=val;return val
    def export(self):
        core={'schema':SCHEMA,'source_root':self.source_root,'roster_digest':self.roster_digest,
              'events':self.events,'head':self.head}
        return {**core,'digest':digest(core)}


def recover(doc,source_root,hosts,expected_roster,expected_head):
    if type(doc)!=dict or set(doc)!={'schema','source_root','roster_digest','events','head','digest'}:refute('unrecognized ledger')
    if doc['schema']!=SCHEMA or doc['source_root']!=source_root or doc['head']!=expected_head or doc['roster_digest']!=expected_roster or digest({k:v for k,v in doc.items() if k!='digest'})!=doc['digest']:refute('external head/root mismatch')
    known={h.name:h for h in hosts}
    if len(known)!=len(hosts) or digest([(h.name,h.key_id,h.cost) for h in sorted(hosts,key=lambda h:h.name)])!=expected_roster:refute('receiver key roster changed')
    prior=digest({'schema':SCHEMA,'source_root':source_root,'roster_digest':expected_roster})
    votes={};request_set=set()
    for i,event in enumerate(doc['events']):
        if type(event)!=dict or set(event)!={'index','previous','request','frame','digest'} or event['index']!=i or event['previous']!=prior or digest({k:v for k,v in event.items() if k!='digest'})!=event['digest']:refute('observation ledger chain changed')
        req=event['request']; host=known.get(req.get('host'))
        if host is None or req['root']!=source_root:refute('unknown signed observer/source')
        unique=(req['host'],req['nonce'])
        if unique in request_set:refute('replayed challenge')
        request_set.add(unique)
        v=verify_frame(event['frame'],req,host)
        key=(req['coordinate'],host.name)
        if key in votes and votes[key]!=v:refute('same-observer equivocation')
        votes[key]=v;prior=event['digest']
    if prior!=expected_head:refute('incomplete ledger')
    values={}
    for q in range(8):
        records=[v for (coord,host),v in votes.items() if coord==q]
        accepted=[val for val in (0,1) if records.count(val)>=2]
        if len(accepted)==1:values[q]=accepted[0]
    return {'source_root':source_root,'admitted':False,'qualified_observations':values,
            'event_count':len(doc['events']),'signed_receipt_count':len(doc['events']),
            'process_source_calls':0,'head':prior}
