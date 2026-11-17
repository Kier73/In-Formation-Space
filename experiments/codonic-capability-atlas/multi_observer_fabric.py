"""COG-009: signed, disagreement-preserving observer ensemble for COG-008.

Ed25519 source identity is independently pinned; signatures DO NOT prove that a
source is truthful. Two different enrolled observers must agree before a query
becomes a provisional membership observation. Conflicts stay visible as
unknown. Native E-CPU mTLS, Hypervisor and quorum remain separate authorities.
"""
from __future__ import annotations
import base64
import hashlib
import json
import secrets
import selectors
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cognitive_grounds import GroundRefused, canonical, digest
from partial_observation import _answers, _word
from observer_worker import KIND, RESPONSE

SCHEMA='ifs.cog009.signed-observer-fabric.v1'


def _check64(v: Any)->bool:
    return type(v) is str and len(v)==64 and all(c in '0123456789abcdef' for c in v)


def _key_id(public: Ed25519PublicKey)->str:
    return hashlib.sha256(public.public_bytes(serialization.Encoding.DER,serialization.PublicFormat.SubjectPublicKeyInfo)).hexdigest()


@dataclass(frozen=True)
class Host:
    name:str
    public_key_pem:str
    cost:int=1
    def __post_init__(self):
        if (type(self.name) is not str or not self.name.isidentifier() or
                type(self.cost) is not int or not 1<=self.cost<=1000):
            raise GroundRefused('invalid enrolled host or acquisition cost')
        pub=serialization.load_pem_public_key(self.public_key_pem.encode('ascii'))
        if not isinstance(pub,Ed25519PublicKey):raise GroundRefused('observer keys must be Ed25519')
    @property
    def public(self)->Ed25519PublicKey:
        return serialization.load_pem_public_key(self.public_key_pem.encode('ascii'))
    @property
    def key_id(self)->str:return _key_id(self.public)


class HostProcess:
    """A genuinely separate child-process observer with a pinned signing key."""
    def __init__(self,host:Host,command:Sequence[str],*,timeout:float=10):
        self.host=host;self.command=tuple(command);self.timeout=timeout
        self.proc:subprocess.Popen|None=None;self.calls=0;self.starts=0

    def start(self)->None:
        if self.proc is not None and self.proc.poll() is None:raise GroundRefused('observer already running')
        self.proc=subprocess.Popen(self.command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
                                   bufsize=0)
        self.starts+=1

    def stop(self,*,kill:bool=False)->None:
        if self.proc is None:return
        if self.proc.poll() is None:
            (self.proc.kill() if kill else self.proc.terminate())
            try:self.proc.wait(timeout=2)
            except subprocess.TimeoutExpired:self.proc.kill();self.proc.wait(timeout=2)
        for h in (self.proc.stdin,self.proc.stdout,self.proc.stderr):
            if h:h.close()
        self.proc=None

    def request(self,body:Mapping[str,Any])->dict:
        if self.proc is None or self.proc.poll() is not None:raise GroundRefused('observer process unavailable')
        encoded=canonical(body)+b'\n'
        if len(encoded)>8192:raise GroundRefused('request exceeds bounded transport frame')
        try:
            assert self.proc.stdin is not None and self.proc.stdout is not None
            self.proc.stdin.write(encoded);self.proc.stdin.flush()
            # Distinct worker processes are live; the deadline prevents hanging verification.
            selector=selectors.DefaultSelector()
            selector.register(self.proc.stdout,selectors.EVENT_READ)
            try:
                if not selector.select(self.timeout):raise GroundRefused('observer response timeout')
            finally:selector.close()
            raw=self.proc.stdout.readline(65537)
        except (BrokenPipeError,OSError) as exc:
            raise GroundRefused('observer process transport failed') from exc
        if not raw or len(raw)>65536 or not raw.endswith(b'\n'):
            raise GroundRefused('observer reply missing, truncated or oversized')
        try:frame=json.loads(raw)
        except (ValueError,UnicodeDecodeError) as exc:raise GroundRefused('malformed observer JSON') from exc
        self.calls+=1
        return frame


def verify_signed(frame:Mapping[str,Any],req:Mapping[str,Any],host:Host,source_root:str,
                  alphabet:tuple[str,...])->tuple[tuple,...]:
    """Independently verify identity, exact request correlation and signed contents."""
    if not isinstance(frame,Mapping) or set(frame)!={'body','signature'} or not isinstance(frame['body'],Mapping):
        raise GroundRefused('unsigned or malformed source response')
    body=frame['body']
    if (set(body)!={'kind','host','source_root','nonce','request_digest','path','outputs','boot','key_id'}
        or body['kind']!=RESPONSE or body['host']!=host.name or body['source_root']!=source_root
        or body['nonce']!=req['nonce'] or body['request_digest']!=digest(req)
        or body['path']!=req['path'] or body['key_id']!=host.key_id or
        type(body['boot']) is not str or len(body['boot'])!=32):
        raise GroundRefused('source identity, epoch, request, or public key mismatch')
    path=_word(body['path'],alphabet)
    output=_answers(body['outputs'],len(path))
    try:
        signature=base64.b64decode(frame['signature'],validate=True)
        if len(signature)!=64 or base64.b64encode(signature).decode('ascii')!=frame['signature']:
            raise ValueError('not canonical Ed25519 signature')
        host.public.verify(signature,hashlib.sha256(canonical(body)).digest())
    except Exception as exc:
        # Cryptographic rejection, regardless of correctly recomputed outer hashes.
        raise GroundRefused('source signature invalid or untrusted') from exc
    return output


def _request(source_root:str,host:str,path:Sequence[str],alphabet:tuple[str,...])->dict:
    w=_word(path,alphabet)
    return {'kind':KIND,'host':host,'source_root':source_root,'nonce':secrets.token_hex(16),'path':list(w)}


class SignedFabric:
    """Receiver-owned witness ledger; agrees, disagrees, or remains unknown.

    Enrolled public keys are trusted only if provided out of band; neither an
    embedded key nor a majority of signatures confers real-world truth.
    """
    def __init__(self,source_root:str,alphabet:Sequence[str],peers:Sequence[HostProcess],*,quorum:int=2):
        if not _check64(source_root):raise GroundRefused('source epoch must be a pinned digest')
        if not isinstance(alphabet,(list,tuple)) or not alphabet or len(set(alphabet))!=len(alphabet):
            raise GroundRefused('source alphabet invalid')
        self.source_epoch=source_root;self.alphabet=tuple(alphabet)
        self.peers={p.host.name:p for p in peers}
        if (len(self.peers)!=len(peers) or len(peers)<quorum or type(quorum) is not int or
                quorum<2 or quorum>len(peers) or len({p.host.key_id for p in peers})!=len(peers)):
            raise GroundRefused('quorum needs independent distinct pinned keys')
        self.quorum=quorum;self.qualified:set[str]=set()
        self.events:list[dict]=[];self.votes:dict[tuple[str,...],dict[str,tuple[tuple,...]]]={}
        self.memo:dict[tuple[str,...],tuple[tuple,...]]={}
        self.external_calls=0

    @property
    def roster(self)->tuple[Host,...]:return tuple(sorted((p.host for p in self.peers.values()),key=lambda h:h.name))
    @property
    def source_root(self)->str:
        return digest({'schema':SCHEMA,'source_epoch':self.source_epoch,'alphabet':list(self.alphabet),
                       'roster':[(h.name,h.key_id,h.cost) for h in self.roster],'quorum':self.quorum})
    @property
    def genesis(self)->str:return digest({'schema':SCHEMA,'genesis':self.source_root})
    @property
    def head(self)->str:return self.events[-1]['digest'] if self.events else self.genesis

    def _poll(self,name:str,path:Sequence[str],*,phase:str)->tuple[tuple,...]:
        host=self.peers[name].host
        req=_request(self.source_epoch,name,path,self.alphabet)
        frame=self.peers[name].request(req)
        out=verify_signed(frame,req,host,self.source_epoch,self.alphabet)
        self.external_calls+=1
        w=tuple(req['path'])
        prior=self.votes.setdefault(w,{}).get(name)
        if prior is not None and prior!=out:
            raise GroundRefused('same qualified observer equivocated within the pinned source epoch')
        self.votes[w][name]=out
        core={'index':len(self.events),'previous':self.head,'phase':phase,
              'request':req,'signed_receipt':frame}
        self.events.append({**core,'digest':digest(core)})
        return out

    def qualify(self,name:str)->bool:
        if name not in self.peers:raise GroundRefused('unregistered host')
        # Known interpretation probes test a small contract, not arbitrary source honesty.
        tests=((('minutes',),(('unknown',),)),
               (('clear','minutes'),(('cleared',),('unknown',))))
        for word,expected in tests:
            out=self._poll(name,word,phase='qualification')
            if out!=expected:raise GroundRefused('host failed bounded behavioral qualification')
        self.qualified.add(name)
        return True

    def _agreed(self,path:tuple[str,...])->tuple[tuple,...]|None:
        votes=self.votes.get(path,{})
        groups:dict[tuple[tuple,...],set[str]]={}
        for host,out in votes.items():
            if host in self.qualified:groups.setdefault(out,set()).add(host)
        strong=[out for out,hosts in groups.items() if len(hosts)>=self.quorum]
        if len(strong)>1:raise GroundRefused('multiple incompatible quorums; equivocation unresolved')
        return strong[0] if strong else None

    def query(self,path:Sequence[str])->tuple[tuple,...]:
        p=_word(path,self.alphabet)
        found=self._agreed(p)
        if found is not None:
            self.memo[p]=found
            return found
        hosts=sorted((h for h in self.qualified if h not in self.votes.get(p,{})),
                     key=lambda name:(self.peers[name].host.cost,name))
        for h in hosts:
            try:self._poll(h,p,phase='membership')
            except GroundRefused as exc:
                if 'unavailable' in str(exc) or 'transport failed' in str(exc):
                    continue
                raise
            found=self._agreed(p)
            if found is not None:
                self.memo[p]=found
                return found
        raise GroundRefused('unknown: independent authenticated observer agreement unavailable')

    def dispute(self,path:Sequence[str])->dict:
        p=_word(path,self.alphabet)
        votes=self.votes.get(p,{})
        by_out={}
        for h,v in votes.items():
            if h in self.qualified:by_out.setdefault(v,[]).append(h)
        remaining=sorted((h for h in self.qualified if h not in votes),
                         key=lambda h:(self.peers[h].host.cost,h))
        return {'status':'provisional_agreement' if self._agreed(p) is not None else 'unknown',
                'different_results':len(by_out),'evidence_hosts':len(votes),
                'next_qualified_observer':remaining[0] if remaining else None,
                'all_views_retained':True}

    def document(self)->dict:
        core={'schema':SCHEMA+'.ledger','source_epoch':self.source_epoch,'source_root':self.source_root,
              'alphabet':list(self.alphabet),'quorum':self.quorum,
              'roster':[{'host':h.name,'key':h.public_key_pem,'cost':h.cost} for h in self.roster],
              'qualified':sorted(self.qualified),'events':self.events,'head':self.head}
        return {**core,'digest':digest(core)}


class FrozenFabric:
    """Independent offline verifier. Keys, ledger head and roster root MUST be pinned externally."""
    def __init__(self,doc:Mapping[str,Any],*,expected_digest:str,expected_head:str,expected_roster_root:str,
                 trusted_hosts:Sequence[Host]):
        if (not isinstance(doc,Mapping) or set(doc)!={'schema','source_epoch','source_root','alphabet','quorum','roster','qualified','events','head','digest'}
            or doc['schema']!=SCHEMA+'.ledger' or doc['digest']!=expected_digest or doc['head']!=expected_head
            or doc['source_root']!=expected_roster_root or digest({k:v for k,v in doc.items() if k!='digest'})!=doc['digest']):
            raise GroundRefused('untrusted or stale fabric high water')
        hosts={h.name:h for h in trusted_hosts}
        if (len(hosts)!=len(trusted_hosts) or len(hosts)!=len(doc['roster']) or
            [{'host':h.name,'key':h.public_key_pem,'cost':h.cost} for h in sorted(hosts.values(),key=lambda h:h.name)]!=doc['roster']):
            raise GroundRefused('enrolled public keys differ from independent trust pins')
        self.external_calls=0;self.source_root=doc['source_root'];self.alphabet=tuple(doc['alphabet'])
        self.source_epoch=doc['source_epoch'];self.quorum=doc['quorum']
        if (not _check64(self.source_epoch) or self.quorum<2 or self.quorum>len(hosts) or
                len(set(self.alphabet))!=len(self.alphabet) or
                len({h.key_id for h in hosts.values()})!=len(hosts)):
            raise GroundRefused('invalid restored source contract')
        expected_root=digest({'schema':SCHEMA,'source_epoch':self.source_epoch,'alphabet':list(self.alphabet),
                             'roster':[(h.name,h.key_id,h.cost) for h in sorted(hosts.values(),key=lambda h:h.name)],
                             'quorum':self.quorum})
        if expected_root!=self.source_root:raise GroundRefused('source roster fingerprint mismatch')
        head=digest({'schema':SCHEMA,'genesis':self.source_root})
        votes={};qualified=set();test_answers={}
        seen_nonces=set()
        for i,event in enumerate(doc['events']):
            if not isinstance(event,dict) or set(event)!={'index','previous','phase','request','signed_receipt','digest'}:
                raise GroundRefused('invalid signed witness item')
            core={k:v for k,v in event.items() if k!='digest'}
            if event['index']!=i or event['previous']!=head or event['digest']!=digest(core):
                raise GroundRefused('fabric event chain changed')
            req=event['request']
            if (not isinstance(req,dict) or set(req)!={'kind','source_root','host','nonce','path'} or
                 req['kind']!=KIND or req['source_root']!=self.source_epoch or req['host'] not in hosts or
                 type(req['nonce']) is not str or len(req['nonce'])!=32 or req['nonce'] in seen_nonces):
                raise GroundRefused('replayed or substituted request')
            seen_nonces.add(req['nonce'])
            out=verify_signed(event['signed_receipt'],req,hosts[req['host']],self.source_epoch,self.alphabet)
            key=tuple(req['path']);v=votes.setdefault(key,{})
            if req['host'] in v and v[req['host']]!=out:raise GroundRefused('equivocating observer receipt')
            v[req['host']]=out
            if event['phase']=='qualification':
                if key not in (('minutes',),('clear','minutes')):
                    raise GroundRefused('unscheduled behavioral qualification')
                test_answers.setdefault(req['host'],{})[key]=out
                probes=test_answers[req['host']]
                if probes.get(('minutes',))==(('unknown',),) and probes.get(('clear','minutes'))==(('cleared',),('unknown',)):
                    qualified.add(req['host'])
            elif event['phase']=='membership':
                if req['host'] not in qualified:
                    raise GroundRefused('membership published before observed qualification')
            else:
                raise GroundRefused('unknown receipt phase')
            head=event['digest']
        if head!=doc['head']:raise GroundRefused('fabric high-water mismatch')
        if qualified!=set(doc['qualified']):raise GroundRefused('source qualification cannot be reconstructed')
        self.votes=votes;self.qualified=qualified;self.head=head

    def query(self,path:Sequence[str])->tuple[tuple,...]:
        word=_word(path,self.alphabet)
        groups={}
        for h,out in self.votes.get(word,{}).items():
            if h in self.qualified:groups.setdefault(out,set()).add(h)
        strong=[v for v,hs in groups.items() if len(hs)>=self.quorum]
        if len(strong)!=1:raise GroundRefused('unknown: evidence did not establish a unique qualified agreement')
        return strong[0]
